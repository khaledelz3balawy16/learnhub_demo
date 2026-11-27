"""M17: the integrations schema (HR system), with the same grants as the foundation
schemas (core 0001). Additive and safe to re-run; grants are skipped for roles that do
not exist (a developer's local database)."""

from django.db import migrations

FORWARD = """
CREATE SCHEMA IF NOT EXISTS integrations;
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['lms_app', 'lms_readonly'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT USAGE ON SCHEMA integrations TO %I', r);
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lms_app') THEN
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA integrations GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lms_app';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA integrations GRANT USAGE, SELECT ON SEQUENCES TO lms_app';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA integrations GRANT EXECUTE ON FUNCTIONS TO lms_app';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lms_readonly') THEN
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA integrations GRANT SELECT ON TABLES TO lms_readonly';
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0002_secure_partitions")]

    operations = [migrations.RunSQL(FORWARD, reverse_sql=migrations.RunSQL.noop)]
