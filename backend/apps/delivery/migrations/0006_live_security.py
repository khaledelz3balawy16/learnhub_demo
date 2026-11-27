"""M20: live sessions and workshops are provider reference data like cohorts and groups
(read by all signed-in requests, written by staff and platform jobs)."""

from django.db import migrations

from core import rls


class Migration(migrations.Migration):
    dependencies = [("delivery", "0005_livesession_workshop")]

    operations = [migrations.RunSQL(*rls.reference("delivery", t)) for t in ("live_sessions", "workshops")]
