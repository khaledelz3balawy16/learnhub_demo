"""M19: program settings are reference data (read by all, staff write)."""

from django.db import migrations

from core import rls


class Migration(migrations.Migration):
    dependencies = [("delivery", "0003_programsetting")]

    operations = [migrations.RunSQL(*rls.reference("delivery", "program_settings"))]
