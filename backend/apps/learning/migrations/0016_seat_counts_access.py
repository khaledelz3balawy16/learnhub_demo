"""Programs review (additive): a learner whose access has run out (a cancelled monthly plan,
a pause) no longer holds a group place. Replaces the count function's body only; no table
or row changes. Same rule as learning.models.holds_place."""

from django.db import migrations

COUNTS = """
CREATE OR REPLACE FUNCTION learning.cohort_seat_counts(p_cohorts uuid[])
RETURNS TABLE (cohort_id uuid, group_id uuid, placed integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = learning, pg_temp AS $$
  SELECT e.cohort_id, e.group_id, count(*)::integer
  FROM learning.enrollments e
  WHERE e.cohort_id = ANY(p_cohorts) AND e.status IN ('active', 'completed')
    AND (e.access_expires_at IS NULL OR e.access_expires_at > now())
  GROUP BY e.cohort_id, e.group_id
$$;
"""

PREVIOUS = """
CREATE OR REPLACE FUNCTION learning.cohort_seat_counts(p_cohorts uuid[])
RETURNS TABLE (cohort_id uuid, group_id uuid, placed integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = learning, pg_temp AS $$
  SELECT e.cohort_id, e.group_id, count(*)::integer
  FROM learning.enrollments e
  WHERE e.cohort_id = ANY(p_cohorts) AND e.status IN ('active', 'completed')
  GROUP BY e.cohort_id, e.group_id
$$;
"""


class Migration(migrations.Migration):
    # CREATE OR REPLACE keeps the function's owner and its grant to lms_app (0014)
    dependencies = [("learning", "0015_enrollment_module_seat")]

    operations = [migrations.RunSQL(COUNTS, PREVIOUS)]
