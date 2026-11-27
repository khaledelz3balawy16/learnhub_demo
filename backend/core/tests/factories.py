"""Small builders for API tests: a published, priced course with every lecture kind."""

from decimal import Decimal

from django.utils import timezone

from apps.catalog import services as cat
from apps.catalog.models import Category, Course, Lecture, VideoLibrary
from apps.commerce import pricing
from apps.commerce.models import CoursePrice, Currency, PriceTier
from apps.identity.models import User
from core.tenancy import tenant_context

ECB = {"USD": Decimal("1.16"), "GBP": Decimal("0.87"), "JPY": Decimal("175")}


def priced_for_publish(course, *, tier=None):
    """The publish checklist needs a price (or "free") before submission, and a paid course
    also needs a token price on every non-preview lesson. Call it just before `submit`."""
    with tenant_context(staff=True):
        CoursePrice.objects.create(course=course, is_free=tier is None, tier=tier)
        if tier is not None:
            Lecture.objects.filter(version__course=course, is_preview=False).update(token_price=10)


def users():
    staff = User.objects.create_user('contact+fa9277f3d9c5@example.com', "x", is_staff=True, full_name="Staff")
    teacher = User.objects.create_user('contact+6c4777e254d7@example.com', "x", full_name="Tom Teacher")
    learner = User.objects.create_user('contact+a6b7d7235186@example.com', "x", full_name="Sara Ahmed")
    other = User.objects.create_user('contact+95190e115eae@example.com', "x", full_name="Omar")
    return staff, teacher, learner, other


def money(staff):
    with tenant_context(user_id=staff.id, staff=True):
        pricing.store_ecb_rates(timezone.now().date(), ECB)
        Currency.objects.filter(code__in=["GBP", "USD", "EUR"]).update(is_active=True)
        pricing.refresh_tier_amounts()
        return Category.objects.create(name="Development", slug="development", icon="code")


def course(*, staff, owner, slug, title, category=None, tier="Tier 5", ownership="instructor", org_id=None,
           free=False):  # fmt: skip
    ctx = {"user_id": owner.id, "org_id": org_id}
    with tenant_context(**ctx):
        c = cat.create_course(title=title, slug=slug, ownership=ownership, created_by=owner, owner_org_id=org_id,
                              subtitle=f"Learn {title}", category=category)  # fmt: skip
        v = c.versions.get()
        s1 = cat.add_section(version=v, title="Start")
        with tenant_context(user_id=staff.id, staff=True):
            lib = VideoLibrary.objects.first() or VideoLibrary.objects.create(
                name="L", environment="test", bunny_library_id=1, cdn_hostname="vz.test", is_default=True
            )
        video = cat.create_media(kind="video", status="ready", library=lib, uploaded_by=owner,
                                          owner_org_id=org_id, duration_sec=300)  # fmt: skip
        cat.add_lecture(
            section=s1, kind="video", title="Intro", video=video, duration_sec=300, is_preview=True
        )
        cat.add_lecture(section=s1, kind="article", title="Read me", body="<p>Notes</p>")
        quiz = cat.add_lecture(section=s1, kind="quiz", title="Check").quiz
        cat.add_question(quiz=quiz, kind="single_choice", prompt="2+2?",
                         options=[{"body": "3"}, {"body": "4", "is_correct": True}])  # fmt: skip
        cat.add_question(quiz=quiz, kind="true_false", prompt="Sky is green",
                         options=[{"body": "True"}, {"body": "False", "is_correct": True}])  # fmt: skip
        a = cat.add_lecture(section=s1, kind="assignment", title="Do it").assignment
        cat.update_assignment(assignment=a, instructions="<p>Write something</p>")
        if org_id is None:  # the publish checklist needs the price first (and token prices if paid)
            with tenant_context(user_id=staff.id, staff=True):
                CoursePrice.objects.create(
                    course=c, is_free=free, tier=None if free else PriceTier.objects.get(name=tier)
                )
                if not free:
                    Lecture.objects.filter(version=v, is_preview=False).update(token_price=10)
        cat.submit(version=v, by=owner)
    if ownership == "instructor":
        with tenant_context(user_id=staff.id, staff=True):
            cat.approve(version=v, reviewer=staff)
    with tenant_context(**ctx):
        return Course.objects.get(pk=c.pk)
