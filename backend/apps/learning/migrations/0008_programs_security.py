"""M19: the OTJ ledger and module certificates are learner rows like progress: org_id and
user_id come from the enrolment (trigger), and the mixed policy applies (own rows, the
current company's rows, staff)."""

from django.db import migrations

from core import rls

S = "learning"
TABLES = ("otj_entries", "module_certificates")


class Migration(migrations.Migration):
    dependencies = [("learning", "0007_modulecertificate_otjentry")]

    operations = [
        *(migrations.RunSQL(*rls.inherit_parent(S, t, "learning.enrollments", "enrollment_id")) for t in TABLES),
        *(migrations.RunSQL(*rls.mixed(S, t)) for t in TABLES),
    ]
