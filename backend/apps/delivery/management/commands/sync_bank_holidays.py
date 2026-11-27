"""Load UK bank holidays from GOV.UK into delivery.holidays (all three divisions).

    python manage.py sync_bank_holidays

Also runs monthly through Celery beat (delivery.sync_bank_holidays)."""

from django.core.management.base import BaseCommand

from core.tenancy import tenant_context


class Command(BaseCommand):
    help = "Load UK bank holidays from GOV.UK."

    def handle(self, *args, **options):
        from apps.delivery import services
        from apps.delivery.tasks import fetch_bank_holidays, refresh_cohort_end_dates

        payload = fetch_bank_holidays()
        with tenant_context(staff=True):
            written = services.sync_holidays(payload)
            refresh_cohort_end_dates.run()
        self.stdout.write(self.style.SUCCESS(f"{written} bank holidays saved."))
