"""M21 (additive): bought modules are learner rows (org_id and user_id from the enrolment by
trigger, mixed policy). `cohort_seat_counts` gives the program page and checkout the number
of learners placed in each group of some cohorts: learners only see their own enrolments
under RLS, yet "places left" needs everyone's. It returns counts only (no names, no rows)."""

from django.db import migrations

from core import rls

S = "learning"

COUNTS = """
CREATE OR REPLACE FUNCTION learning.cohort_seat_counts(p_cohorts uuid[])
RETURNS TABLE (cohort_id uuid, group_id uuid, placed integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = learning, pg_temp AS $$
  SELECT e.cohort_id, e.group_id, count(*)::integer
  FROM learning.enrollments e
  WHERE e.cohort_id = ANY(p_cohorts) AND e.status IN ('active', 'completed')
  GROUP BY e.cohort_id, e.group_id
$$;
REVOKE ALL ON FUNCTION learning.cohort_seat_counts(uuid[]) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lms_app') THEN
    GRANT EXECUTE ON FUNCTION learning.cohort_seat_counts(uuid[]) TO lms_app;
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("learning", "0013_enrollment_scope_modules")]

    operations = [
        migrations.RunSQL(
            *rls.inherit_parent(S, "enrollment_modules", "learning.enrollments", "enrollment_id")
        ),
        migrations.RunSQL(*rls.mixed(S, "enrollment_modules")),
        migrations.RunSQL(COUNTS, "DROP FUNCTION IF EXISTS learning.cohort_seat_counts(uuid[]);"),
    ]
