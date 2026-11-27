"""M19 (additive): the public certificate check also finds module certificates. A NEW
function; nothing is replaced or dropped."""

from django.db import migrations

VERIFY_MODULE = """
-- Public check of a module certificate: ONLY these fields. Runs as the owner so it can read
-- past RLS, and exposes nothing else. The title reads "Program: Module".
CREATE OR REPLACE FUNCTION learning.verify_module_certificate(p_code text)
RETURNS TABLE (verification_code text, recipient_name text, course_title text,
               cpd_hours numeric, issued_at timestamptz, is_revoked boolean,
               expires_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = learning, pg_temp AS $$
  SELECT m.verification_code, m.recipient_name, co.title || ': ' || m.module_title,
         CASE WHEN m.cpd_min > 0 THEN round(m.cpd_min / 60.0, 1) END, m.issued_at,
         false, NULL::timestamptz
  FROM learning.module_certificates m
  JOIN learning.enrollments e ON e.id = m.enrollment_id
  JOIN catalog.courses co ON co.id = e.course_id
  WHERE m.verification_code = upper(trim(p_code))
  LIMIT 1
$$;
REVOKE ALL ON FUNCTION learning.verify_module_certificate(text) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lms_app') THEN
    GRANT EXECUTE ON FUNCTION learning.verify_module_certificate(text) TO lms_app;
  END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("learning", "0008_programs_security")]

    operations = [
        migrations.RunSQL(VERIFY_MODULE, "DROP FUNCTION IF EXISTS learning.verify_module_certificate(text);"),
    ]
