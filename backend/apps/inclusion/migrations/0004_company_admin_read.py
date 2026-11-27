"""A company's owners and admins may READ the inclusion answers of their current members
(user decision 2026-11-25). Added as a second, SELECT-only policy next to `tenant_personal`
(learner or staff); permissive policies combine with OR.

The request must carry the company (app.org_id, set only for active members), the caller must
be an active owner or admin there, and the answer's learner an active member of it. Managers,
learners, other companies and removed members see nothing. Additive.
"""

from django.db import migrations

from core.rls import ORG, USER

FORWARD = f"""
CREATE POLICY company_admin_read ON "inclusion"."attempts" FOR SELECT USING (
  {ORG} IS NOT NULL
  AND EXISTS (SELECT 1 FROM "org"."org_members" me
              WHERE me.org_id = {ORG} AND me.user_id = {USER}
                AND me.removed_at IS NULL AND me.role IN ('owner', 'admin'))
  AND EXISTS (SELECT 1 FROM "org"."org_members" m
              WHERE m.org_id = {ORG} AND m.user_id = "inclusion"."attempts".user_id AND m.removed_at IS NULL)
);
"""
REVERSE = 'DROP POLICY IF EXISTS company_admin_read ON "inclusion"."attempts";'


class Migration(migrations.Migration):
    dependencies = [("inclusion", "0003_security"), ("org", "0002_security")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
