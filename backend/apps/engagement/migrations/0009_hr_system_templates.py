"""Wordings for the HR system (M17). Insert only: an existing row with the same code is
left exactly as staff edited it. Each notice links to /business/hr-system (the url is
passed by apps.integrations.services when it notifies, not stored here)."""

from django.db import migrations

TEMPLATES = [
    (
        "hr_sync_failed",
        "{provider} sync didn't finish",
        "We couldn't bring your people up to date from {provider}: {error} Open the HR system page to check the connection.",
        True,
    ),
    (
        "hr_people_to_review",
        "{count} people from {provider} to review",
        "New people arrived from {provider}. Link each one to their {platform} account, or invite them.",
        False,
    ),
    (
        "hr_connection_attention",
        "Your {provider} connection needs attention",
        "{provider} no longer accepts the saved API key, so syncing has stopped. Replace the key on the HR system page.",
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
    dependencies = [("engagement", "0008_payment_notices")]

    operations = [migrations.RunPython(insert, migrations.RunPython.noop)]
