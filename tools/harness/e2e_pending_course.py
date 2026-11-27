"""HARNESS ONLY: a single new instructor-owned course, submitted for review and waiting
in the approvals queue, so the E2E "reject" step always has something of its own to
reject (the shared "new courses" queue otherwise empties out after a few harness runs).

A single print() (not two) on purpose: when this runs under tools/run_check.py's
Windows `shell=True` subprocess wrapping, the first line of a multi-line stdout capture
from this grandchild process was occasionally lost, which broke scripts expecting two
lines. One line sidesteps that.

    python e2e_pending_course.py   -> prints "<title>|||<version_id>"
"""
import os
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()

from apps.catalog import services as cat  # noqa: E402
from apps.catalog.models import VideoLibrary  # noqa: E402
from apps.commerce.models import CoursePrice  # noqa: E402
from apps.identity.models import InstructorProfile, User  # noqa: E402
from core.tenancy import tenant_context  # noqa: E402

owner = User.objects.filter(email__startswith="daniel.reeve").first() or User.objects.get(
    pk=InstructorProfile.objects.filter(status="approved").values_list("user_id", flat=True)[:1]
)
staff = User.objects.filter(is_staff=True).first()
stamp = int(time.time() * 1000)
title = f"E2E Pending Review Course {stamp}"
slug = f"e2e-pending-{stamp}"

with tenant_context(user_id=owner.id):
    c = cat.create_course(title=title, slug=slug, ownership="instructor", created_by=owner,
                          subtitle="Awaiting review (E2E harness)", description="<p>Harness course.</p>")  # fmt: skip
    v = c.versions.get()
    s1 = cat.add_section(version=v, title="Intro")
    with tenant_context(user_id=staff.id, staff=True):
        lib = VideoLibrary.objects.filter(is_default=True).first() or VideoLibrary.objects.first()
    video = cat.create_media(kind="video", status="ready", library=lib, uploaded_by=owner, duration_sec=60)
    cat.add_lecture(section=s1, kind="video", title="Lesson one", video=video, duration_sec=60)
    # the publish checklist needs a price (or "free") before submission
    with tenant_context(user_id=staff.id, staff=True):
        CoursePrice.objects.create(course=c, is_free=True, tier=None)
    cat.submit(version=v, by=owner)

print(f"{title}|||{v.id}")
