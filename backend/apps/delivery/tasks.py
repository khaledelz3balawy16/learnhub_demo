"""Delivery jobs (Celery): bank holiday sync and cohort end-date refresh."""

import logging

import httpx
from celery import shared_task

from core.tenancy import tenant_context

log = logging.getLogger(__name__)

GOV_UK_BANK_HOLIDAYS = "https://www.gov.uk/bank-holidays.json"


def fetch_bank_holidays(timeout: float = 15.0) -> dict:
    """GOV.UK's public feed (no key). Raises on network or HTTP errors."""
    resp = httpx.get(GOV_UK_BANK_HOLIDAYS, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected bank holiday feed shape")
    return data


@shared_task(
    name="delivery.sync_bank_holidays", autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=5
)
def sync_bank_holidays_task() -> int:
    from . import services

    payload = fetch_bank_holidays()
    with tenant_context(staff=True):
        return services.sync_holidays(payload)  # also refreshes the cohorts' end dates


@shared_task(name="delivery.refresh_cohort_end_dates")
def refresh_cohort_end_dates(program_id: str | None = None) -> int:
    """Store each live cohort's last teaching day again (all, or one program's)."""
    from . import services

    with tenant_context(staff=True):
        return services.refresh_end_dates(program_id=program_id)


# ---------------------------------------------------------------- live teaching (M20)
@shared_task(name="delivery.sync_meetings", max_retries=3, default_retry_delay=120, bind=True)
def sync_meetings(self, kind: str, obj_id: str) -> int:
    """Create or move the Teams meetings of one group's sessions ("session") or one workshop."""
    from core.errors import ServiceError

    from . import sessions
    from .models import Workshop

    with tenant_context(staff=True):
        try:
            if kind == "workshop":
                w = Workshop.objects.filter(pk=obj_id).first()
                return int(sessions.ensure_meeting(w)) if w else 0
            return sessions.sync_group_meetings(obj_id)
        except ServiceError as exc:
            if exc.status >= 500:
                raise self.retry(exc=exc) from exc
            log.warning("teams meeting sync skipped for %s %s: %s", kind, obj_id, exc.code)
            return 0


@shared_task(name="delivery.live_followup", expires=25 * 60)
def live_followup() -> dict:
    """Every 30 minutes: read Teams attendance for events that ended, then copy recordings
    that are due. Each event is handled on its own: one failure never stops the rest."""
    from apps.learning import live
    from core.errors import ServiceError

    from . import sessions
    from .models import LiveSession

    done = {"attendance": 0, "recordings": 0}
    with tenant_context(staff=True):
        for obj in sessions.attendance_due():
            try:
                if isinstance(obj, LiveSession):
                    live.sync_session_attendance(obj)
                else:
                    live.sync_workshop_attendance(obj)
                done["attendance"] += 1
            except ServiceError as exc:
                log.info("attendance not read for %s: %s", obj.pk, exc.code)
            except Exception:  # noqa: BLE001 - one event's failure never stops the rest
                log.exception("attendance sync failed for %s", obj.pk)
        for obj in sessions.recordings_due():
            try:
                if sessions.pull_recording(obj) == "ready":
                    done["recordings"] += 1
            except Exception:  # noqa: BLE001
                log.exception("recording copy failed for %s", obj.pk)
    return done
