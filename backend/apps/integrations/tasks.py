"""HR sync jobs (Celery). Each runs for ONE company inside its own RLS context."""

import logging

from celery import shared_task
from django.utils import timezone

from core.errors import ServiceError
from core.tenancy import tenant_context

from . import services
from .models import HrConnection

log = logging.getLogger(__name__)


@shared_task(name="integrations.hr_sync_run")
def hr_sync_run_task(org_id: str, run_id: str) -> str:
    # process_sync opens its own short RLS transactions: none is held while Breathe answers
    return services.process_sync(run_id, org_id=org_id).status


@shared_task(name="integrations.hr_hourly")
def hr_hourly_task() -> int:
    """Every connected company once an hour (client question 24). The idempotency key is
    the hour, so a second beat in the same hour never starts a second run."""
    with tenant_context(staff=True):
        conns = list(
            HrConnection.objects.filter(status__in=("active", "attention")).values_list("id", "org_id")
        )
    hour = timezone.now().strftime("%Y-%m-%dT%H")
    started = 0
    for conn_id, org_id in conns:
        with tenant_context(org_id=org_id):
            conn = HrConnection.objects.get(pk=conn_id)
            try:
                services.queue_sync(conn=conn, trigger="hourly", key=f"hourly:{conn_id}:{hour}")
                started += 1
            except ServiceError as exc:  # already running, paused since: skip this hour
                log.info("hourly HR sync skipped for %s: %s", org_id, exc.code)
    return started


@shared_task(name="integrations.hr_reconcile")
def hr_reconcile_task(org_id: str, member_ids: list[str]) -> int:
    with tenant_context(org_id=org_id):
        if not HrConnection.objects.exists():
            return 0
        return services.reconcile_members(org_id=org_id, member_ids=member_ids)
