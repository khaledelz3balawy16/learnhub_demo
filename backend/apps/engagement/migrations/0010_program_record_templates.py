"""Wordings for program records (M19). Insert only: an existing row with the same code is
left exactly as staff edited it. Each notice links to the learner's record page (the url
is passed by apps.learning.records when it notifies)."""

from django.db import migrations

TEMPLATES = [
    (
        "module_certificate_issued",
        "Module complete: {module}",
        "You've finished every part of {module}. Your module certificate is on your record page.",
        True,
    ),
    (
        "otj_approved",
        "Your off-the-job hours were approved",
        "Your tutor approved {minutes} minutes for {day}. {note}",
        False,
    ),
    (
        "otj_rejected",
        "Your off-the-job hours weren't approved",
        "Your tutor didn't approve {minutes} minutes for {day}: {note}",
        True,
    ),
]


def insert(apps, schema_editor):
    Template = apps.get_model("engagement", "NotificationTemplate")
    db = schema_editor.connection.alias
    for code, title, body, email in TEMPLATES:
        Template.objects.using(db).get_or_create(
            code=code, defaults={"title": title, "body": body, "email_enabled": email}
        )


class Migration(migrations.Migration):
    dependencies = [("engagement", "0009_hr_system_templates")]

    operations = [migrations.RunPython(insert, migrations.RunPython.noop)]
