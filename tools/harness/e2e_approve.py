"""HARNESS ONLY: small approvals the M4 E2E needs that have no dedicated harness script yet.

    python e2e_approve.py instructor <email>   -> approve a pending instructor application
    python e2e_approve.py course <course_id>   -> approve the course's in-review version

Both go through the real services (never a raw status flip for the course path)."""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django  # noqa: E402

django.setup()
from apps.catalog import services as cat  # noqa: E402
from apps.catalog.models import CourseVersion  # noqa: E402
from apps.identity.models import InstructorProfile, User  # noqa: E402
from core.tenancy import tenant_context  # noqa: E402

cmd = sys.argv[1]
if cmd == "instructor":
    email = sys.argv[2]
    user = User.objects.get(email=email)
    n = InstructorProfile.objects.filter(user=user).update(status="approved")
    if not n:
        # no application was ever sent through the UI: make one directly (demo/E2E shortcut)
        InstructorProfile.objects.create(user=user, status="approved", headline="E2E instructor")
    print("approved")
elif cmd == "course":
    course_id = sys.argv[2]
    staff = User.objects.filter(is_staff=True).first()
    with tenant_context(user_id=staff.id, staff=True):
        version = CourseVersion.objects.get(course_id=course_id, status="in_review")
        cat.approve(version=version, reviewer=staff)
    print("approved")
else:
    raise SystemExit(f"unknown command {cmd!r}")
