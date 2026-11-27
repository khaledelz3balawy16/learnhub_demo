"""M20: attendance and workshop bookings are learner rows like the OTJ ledger: org_id and
user_id come from the enrolment (trigger), and the mixed policy applies."""

from django.db import migrations

from core import rls

S = "learning"
TABLES = ("session_attendance", "workshop_bookings")


class Migration(migrations.Migration):
    dependencies = [("learning", "0010_sessionattendance_workshopbooking")]

    operations = [
        *(migrations.RunSQL(*rls.inherit_parent(S, t, "learning.enrollments", "enrollment_id")) for t in TABLES),
        *(migrations.RunSQL(*rls.mixed(S, t)) for t in TABLES),
    ]
