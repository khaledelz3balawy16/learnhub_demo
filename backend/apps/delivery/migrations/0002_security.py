"""M18: delivery tables are provider reference data. Any signed-in request may READ them
(the API decides what each person sees: learners only their own placement); only staff
(console) and platform jobs may WRITE. None has org_id, so no company policy applies."""

from django.db import migrations

from core import rls

TABLES = ("cohorts", "cohort_modules", "groups", "holidays", "closures")


class Migration(migrations.Migration):
    dependencies = [("delivery", "0001_initial")]

    operations = [migrations.RunSQL(*rls.reference("delivery", t)) for t in TABLES]
