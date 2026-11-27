"""Row-Level Security for the inclusion schema.

sections, questions: reference data (everyone reads, only staff write).
attempts: personal (the learner's own rows, or staff). Nothing here has an org_id, so no
company, and so no employer, can ever read an answer.
"""

from django.db import migrations

from core import rls

S = "inclusion"


class Migration(migrations.Migration):
    dependencies = [("inclusion", "0002_seed_questions")]

    operations = [
        migrations.RunSQL(*rls.reference(S, "sections")),
        migrations.RunSQL(*rls.reference(S, "questions")),
        migrations.RunSQL(*rls.personal(S, "attempts")),
    ]
