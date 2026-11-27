"""Inclusion test: the inclusion schema. Only lms_app gets access: unlike the other
schemas, lms_readonly gets NO grant, because these are health answers and any role can set the
RLS staff key itself (review 2026-11-25). Additive and safe to re-run; grants are skipped for
roles that do not exist (a developer's local database)."""

from django.db import migrations

FORWARD = """
CREATE SCHEMA IF NOT EXISTS inclusion;
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['lms_app'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT USAGE ON SCHEMA inclusion TO %I', r);
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lms_app') THEN
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA inclusion GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lms_app';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA inclusion GRANT USAGE, SELECT ON SEQUENCES TO lms_app';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA inclusion GRANT EXECUTE ON FUNCTIONS TO lms_app';
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0004_delivery_schema")]

    operations = [migrations.RunSQL(FORWARD, reverse_sql=migrations.RunSQL.noop)]
