"""M19: KSB standards, items and the component mapping are reference data: everyone reads,
only staff (console) and platform jobs write."""

from django.db import migrations

from core import rls

TABLES = ("ksb_standards", "ksb_items", "component_ksbs")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0013_lecture_cpd_min_lecture_expected_otj_min_ksbstandard_and_more")]

    operations = [migrations.RunSQL(*rls.reference("catalog", t)) for t in TABLES]
