"""HARNESS ONLY: a published course with a full-course token price, and two fresh
learners for the M6 B2C checks:
  - "unlocker": has tokens, no access yet -> unlocks from the course page.
  - "preenrolled": already has a full-course entitlement (token unlock) but NO enrolment,
    simulating the pre-fix state the M6 build-status entry describes, so "Start learning"
    must call the new enrol endpoint.

    python e2e_b2c.py <password>   -> prints one JSON line
"""
import json
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()
from django.utils import timezone  # noqa: E402
from allauth.account.models import EmailAddress  # noqa: E402

from apps.catalog import services as cat  # noqa: E402
from apps.catalog.models import VideoLibrary  # noqa: E402
from apps.commerce import pricing_service, wallet  # noqa: E402
from apps.commerce.models import CoursePrice, PriceTier  # noqa: E402
from apps.identity.models import InstructorProfile, User  # noqa: E402
from apps.platform.models import ContentEntitlement  # noqa: E402
from core.tenancy import tenant_context  # noqa: E402

password = sys.argv[1]
stamp = int(time.time())


def user(local: str, name: str) -> User:
    email = f"e2e.b2c.{local}.{stamp}@learnhub.example.com"
    u = User.objects.create_user(email, password, full_name=name)
    EmailAddress.objects.create(user=u, email=email, verified=True, primary=True)
    return u


owner = User.objects.filter(email__startswith="daniel.reeve").first() or User.objects.get(
    pk=InstructorProfile.objects.filter(status="approved").values_list("user_id", flat=True)[:1]
)
staff = User.objects.filter(is_staff=True).first()
unlocker = user("unlocker", "Toni Unlocker")
preenrolled = user("preenrolled", "Pat Preenrolled")
slug = f"e2e-b2c-tokens-{stamp}"

with tenant_context(user_id=owner.id):
    c = cat.create_course(title="Token Unlock Course (E2E)", slug=slug, ownership="instructor", created_by=owner,
                          subtitle="Unlock the whole course with tokens", description="<p>Harness course.</p>")  # fmt: skip
    v = c.versions.get()
    s1 = cat.add_section(version=v, title="Basics")
    with tenant_context(user_id=staff.id, staff=True):
        lib = VideoLibrary.objects.filter(is_default=True).first() or VideoLibrary.objects.first()
    video = cat.create_media(kind="video", status="ready", library=lib, uploaded_by=owner, duration_sec=120)
    cat.add_lecture(section=s1, kind="video", title="Lesson one", video=video, duration_sec=120)
    with tenant_context(user_id=staff.id, staff=True):
        tier = PriceTier.objects.filter(is_active=True).order_by("sort_order", "gbp_minor").first()
        CoursePrice.objects.create(course=c, is_free=False, tier=tier)
    cat.submit(version=v, by=owner)
with tenant_context(user_id=staff.id, staff=True):
    cat.approve(version=v, reviewer=staff)
    pricing_service.set_course_price(c, full_course_token_price=100, actor=staff, reason="e2e harness")

with tenant_context(staff=True):
    wallet.grant_tokens(user=unlocker, source="admin", amount=500, actor=staff, note="e2e harness")
    wallet.grant_tokens(user=preenrolled, source="admin", amount=500, actor=staff, note="e2e harness")
    # Simulate the pre-fix state: an entitlement with no matching enrolment (unlock_course
    # now creates both; direct ORM write here reproduces the gap the build-status entry fixed).
    ContentEntitlement.objects.create(
        user=preenrolled,
        scope=ContentEntitlement.Scope.COURSE,
        target_id=c.id,
        source=ContentEntitlement.Source.FULL_COURSE_TOKEN_UNLOCK,
        granted_at=timezone.now(),
    )

print(json.dumps({
    "slug": slug, "course_id": str(c.id), "token_price": 100,
    "unlocker": unlocker.email, "preenrolled": preenrolled.email,
}))  # fmt: skip
