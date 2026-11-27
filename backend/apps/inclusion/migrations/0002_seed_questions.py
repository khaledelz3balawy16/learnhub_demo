"""The client's inclusion questions (seed/questions.json, 2026-11-25): six sections of ten.

Insert-only: a section or question whose key already exists is left as it is, so this never
overwrites what admins have edited in the console. Runs before 0003 forces row security.
"""

import json
from pathlib import Path

from django.db import migrations

SEED = Path(__file__).resolve().parents[1] / "seed" / "questions.json"


def seed(apps, schema_editor):
    Section = apps.get_model("inclusion", "Section")
    Question = apps.get_model("inclusion", "Question")
    db = schema_editor.connection.alias if schema_editor else "default"  # tests call seed() directly
    data = json.loads(SEED.read_text(encoding="utf-8"))
    for n, s in enumerate(data["sections"], start=1):
        section, _ = Section.objects.using(db).get_or_create(
            key=s["key"], defaults={"title": s["title"], "position": n, "flag_threshold": data["default_threshold"]}
        )
        for m, q in enumerate(s["questions"], start=1):
            Question.objects.using(db).get_or_create(
                key=q["key"], defaults={"section": section, "text": q["text"], "position": m, "options": data["options"]}
            )


class Migration(migrations.Migration):
    dependencies = [("inclusion", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
