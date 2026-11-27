"""Wordings for buying programs (M21). Insert only: an existing row with the same code is
left exactly as staff edited it. The urls are passed by apps.commerce.programs."""

from django.db import migrations

TEMPLATES = [
    (
        "instalment_payment_failed",
        "Your payment for {program} didn't go through",
        "We couldn't take your monthly payment of {amount}. Update your card by {date} to keep your access.",
        True,
    ),
    (
        "program_learner_unplaced",
        "A learner needs a group",
        "{name} paid for a place in {cohort} ({program}), but every group was full. Place them in a group.",
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
    dependencies = [("engagement", "0010_program_record_templates")]

    operations = [migrations.RunPython(insert, migrations.RunPython.noop)]
