"""M20 (additive): how many places each workshop has taken. Learners only see their own
bookings under RLS, yet capacity and "spaces left" need everyone's: this function returns
the counts and nothing else (no names, no rows)."""

from django.db import migrations

BOOKED = """
CREATE OR REPLACE FUNCTION learning.workshop_booked_counts(p_ids uuid[])
RETURNS TABLE (workshop_id uuid, booked integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = learning, pg_temp AS $$
  SELECT b.workshop_id, count(*)::integer
  FROM learning.workshop_bookings b
  WHERE b.workshop_id = ANY(p_ids) AND b.status = 'booked'
  GROUP BY b.workshop_id
$$;
REVOKE ALL ON FUNCTION learning.workshop_booked_counts(uuid[]) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lms_app') THEN
    GRANT EXECUTE ON FUNCTION learning.workshop_booked_counts(uuid[]) TO lms_app;
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("learning", "0011_live_security")]

    operations = [
        migrations.RunSQL(BOOKED, "DROP FUNCTION IF EXISTS learning.workshop_booked_counts(uuid[]);"),
    ]
