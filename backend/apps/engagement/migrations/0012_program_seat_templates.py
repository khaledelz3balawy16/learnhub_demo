"""Wordings for company program seats (M22). Insert only: an existing row with the same code
is left exactly as staff edited it. The urls are passed by apps.corporate.program_seats."""

from django.db import migrations

TEMPLATES = [
    (
        "program_seat_given",
        "You have a place on {program}",
        "Your company has given you a place on {program}. Open My learning to start.",
        True,
    ),
    (
        "seat_swap_company",
        "A seat swap needs your approval",
        "Someone asked to move {from}'s seat on {program} to another person. Check it and decide.",
        True,
    ),
    (
        "seat_swap_provider",
        "A company seat swap is waiting",
        "A company asked to move {from}'s seat on {program} to another person. Check it and decide.",
        True,
    ),
    (
        "seat_swap_decided",
        "Your seat swap was {decision}",
        "Your request to move {from}'s seat on {program} was {decision}.",
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
    dependencies = [("engagement", "0011_program_buying_templates")]

    operations = [migrations.RunPython(insert, migrations.RunPython.noop)]
