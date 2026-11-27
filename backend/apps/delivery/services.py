"""Delivery writes: cohorts, module start dates, groups, closures, bank holidays.

Callers check permissions first (console: cohorts.manage). These run with the staff RLS
key (console requests, or core.tenancy.tenant_context(staff=True) in jobs), because the
delivery tables are reference data: readable by all, written only by staff and jobs.
Every change that can move a date bumps the cached schedule.
"""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.catalog.models import Course, Module
from core import html
from core.errors import ServiceError

from . import selectors
from .models import Closure, Cohort, CohortModule, Division, Group, Holiday

MAX_RANGE_DAYS = 366  # one closure may cover at most a year


# ---------------------------------------------------------------- cohorts
def _program(program_id) -> Course:
    course = Course.objects.filter(pk=program_id, kind=Course.Kind.PROGRAM, deleted_at__isnull=True).first()
    if course is None:
        raise ServiceError("not_found", "Program not found.", status=404)
    return course


CLOSED = (Cohort.Status.FINISHED, Cohort.Status.CANCELLED)


def _refresh_end(cohort: Cohort) -> None:
    """Store the cohort's last teaching day, built fresh (not from the cache), and make the
    cached schedule stale once the transaction commits."""
    end = selectors.fresh_schedule(cohort).end_date
    if end != cohort.end_date:
        Cohort.objects.filter(pk=cohort.pk).update(end_date=end)
        cohort.end_date = end
    selectors.bump_schedule(cohort.id)


def refresh_end_dates(*, program_id=None) -> int:
    """Re-store the end date of every cohort still running or to come (optionally one
    program's), after a provider-wide change or a new program version. Returns how many
    changed. Bounded: finished and cancelled cohorts are skipped."""
    live = Cohort.objects.exclude(status__in=CLOSED).select_related("program")
    if program_id is not None:
        live = live.filter(program_id=program_id)
    changed = 0
    for cohort in live.iterator(chunk_size=200):
        before = cohort.end_date
        _refresh_end(cohort)
        changed += cohort.end_date != before
    return changed


def _open(cohort: Cohort) -> None:
    if cohort.status in CLOSED:
        raise ServiceError("cohort_closed", "A finished or cancelled cohort can't be changed.")


def _placed(*, cohort_id=None, group_id=None) -> int:
    if group_id is not None:
        return selectors.learner_counts(group_ids=[group_id]).get(group_id, 0)
    return selectors.learner_counts(cohort_ids=[cohort_id]).get(cohort_id, 0)


def _name(value: str) -> str:
    name = html.plain(value, 120).strip()
    if not name:
        raise ServiceError("missing_name", "Give it a name.")
    return name


@transaction.atomic
def create_cohort(
    *, program_id, name: str, start_date: date, calendar: str | None, capacity: int | None, by
) -> Cohort:
    """`calendar` None takes the provider's default (setting learning.program_calendar)."""
    program = _program(program_id)
    if program.live_version_id is None:
        raise ServiceError("not_published", "Publish the program before opening a cohort.")
    if calendar is None:
        from apps.platform.services import get_setting

        calendar = get_setting("learning.program_calendar")
    if calendar not in Division.values:
        raise ServiceError("bad_calendar", "Choose a bank holiday calendar.")
    try:
        with transaction.atomic():
            cohort = Cohort.objects.create(
                program=program, name=_name(name), start_date=start_date, calendar=calendar,
                capacity=capacity, created_by=by,
            )  # fmt: skip
    except IntegrityError:
        raise ServiceError("duplicate", "This program already has a cohort with that name.") from None
    _refresh_end(cohort)
    return cohort


TRANSITIONS = {
    Cohort.Status.PLANNED: {Cohort.Status.OPEN, Cohort.Status.CANCELLED},
    Cohort.Status.OPEN: {Cohort.Status.PLANNED, Cohort.Status.RUNNING, Cohort.Status.CANCELLED},
    Cohort.Status.RUNNING: {Cohort.Status.FINISHED},
    Cohort.Status.FINISHED: set(),
    Cohort.Status.CANCELLED: set(),
}


@transaction.atomic
def update_cohort(*, cohort: Cohort, **changes) -> Cohort:
    cohort = Cohort.objects.select_for_update().select_related("program").get(pk=cohort.pk)
    _open(cohort)
    if "name" in changes and changes["name"] is not None:
        cohort.name = _name(changes["name"])
    if changes.get("start_date") is not None:
        if cohort.status == Cohort.Status.RUNNING:
            raise ServiceError("cohort_running", "The start date can't change once the cohort is running.")
        cohort.start_date = changes["start_date"]
    if changes.get("calendar") is not None:
        if changes["calendar"] not in Division.values:
            raise ServiceError("bad_calendar", "Choose a bank holiday calendar.")
        cohort.calendar = changes["calendar"]
    if "capacity" in changes:
        capacity = changes["capacity"]
        if capacity is not None and capacity < (placed := _placed(cohort_id=cohort.pk)):
            raise ServiceError("capacity", f"{placed} learners are already in this cohort.")
        cohort.capacity = capacity
    status = changes.get("status")
    if status is not None and status != cohort.status:
        if status not in TRANSITIONS[cohort.status]:
            raise ServiceError("bad_status", "That status change isn't allowed.")
        cohort.status = status
    try:
        with transaction.atomic():
            cohort.save()
    except IntegrityError:
        raise ServiceError("duplicate", "This program already has a cohort with that name.") from None
    _refresh_end(cohort)
    return cohort


@transaction.atomic
def set_module_start(*, cohort: Cohort, module_key: UUID, starts_on: date | None) -> None:
    """D16: optional per-module start date; None goes back to the automatic date."""
    cohort = Cohort.objects.select_for_update().select_related("program").get(pk=cohort.pk)
    _open(cohort)
    if not Module.objects.filter(version_id=cohort.program.live_version_id, module_key=module_key).exists():
        raise ServiceError("not_found", "Module not found in this program.", status=404)
    if starts_on is None:
        CohortModule.objects.filter(cohort=cohort, module_key=module_key).delete()
    else:
        if starts_on < cohort.start_date:
            raise ServiceError("bad_date", "A module can't start before the cohort.")
        CohortModule.objects.update_or_create(
            cohort=cohort, module_key=module_key, defaults={"starts_on": starts_on}
        )
    _refresh_end(cohort)


# ---------------------------------------------------------------- groups
def _check_times(weekday, starts_at: time | None, ends_at: time | None) -> None:
    if weekday is not None and not 0 <= weekday <= 6:
        raise ServiceError("bad_weekday", "Choose a day of the week.")
    if starts_at and ends_at and ends_at <= starts_at:
        raise ServiceError("bad_time", "The end time must be after the start time.")


def _check_tutor(tutor_id) -> None:
    if tutor_id is None:
        return
    from apps.identity.models import User
    from core.staff_perms import user_permissions

    tutor = User.objects.filter(pk=tutor_id, is_active=True).first()
    if tutor is None or "groups.teach" not in user_permissions(tutor):
        raise ServiceError("bad_tutor", "Choose a staff member who can teach groups.")


@transaction.atomic
def save_group(*, cohort: Cohort, group: Group | None = None, **fields) -> Group:
    _open(cohort)
    # lock an existing group: learning.placement.place locks it too, so a capacity change
    # and a placement can't both pass their checks at once
    group = Group.objects.select_for_update().get(pk=group.pk) if group else Group(cohort=cohort)
    if "name" in fields and fields["name"] is not None:
        group.name = html.plain(fields["name"], 80).strip()
    if not group.name:
        raise ServiceError("missing_name", "Give the group a name.")
    for f in ("weekday", "starts_at", "ends_at", "capacity", "tutor_id"):
        if f in fields:
            setattr(group, f, fields[f])
    if fields.get("status") is not None:
        if fields["status"] not in Group.Status.values:
            raise ServiceError("bad_status", "Unknown group status.")
        group.status = fields["status"]
    _check_times(group.weekday, group.starts_at, group.ends_at)
    if "tutor_id" in fields:
        _check_tutor(group.tutor_id)
    if not group._state.adding and group.capacity is not None:  # new rows: pk is still the db default
        placed = _placed(group_id=group.pk)
        if group.capacity < placed:
            raise ServiceError("capacity", f"{placed} learners are already in this group.")
    try:
        with transaction.atomic():
            group.save()
    except IntegrityError:
        raise ServiceError("duplicate", "This cohort already has a group with that name.") from None
    return group


@transaction.atomic
def delete_group(*, group: Group) -> None:
    """Only an empty group: ANY enrolment pointing at it (even an ended one, which keeps the
    record of where the learner studied) blocks the delete."""
    from apps.learning.models import Enrollment

    group = Group.objects.select_for_update().get(pk=group.pk)
    if Enrollment.objects.filter(group_id=group.pk).exists():
        raise ServiceError("not_empty", "This group has learners, past or present. Close it instead.")
    group.delete()


# ---------------------------------------------------------------- closures and holidays
@transaction.atomic
def add_closure(*, cohort: Cohort | None, starts_on: date, ends_on: date, reason: str, by) -> Closure:
    if cohort is not None:
        _open(cohort)
    if ends_on < starts_on:
        raise ServiceError("bad_range", "The end date must be on or after the start date.")
    if (ends_on - starts_on).days > MAX_RANGE_DAYS:
        raise ServiceError("bad_range", "A closure can cover at most a year.")
    reason = html.plain(reason, 200).strip()
    if not reason:
        raise ServiceError("missing_reason", "Say why the provider is closed.")
    closure = Closure.objects.create(
        cohort=cohort, starts_on=starts_on, ends_on=ends_on, reason=reason, created_by=by
    )
    _after_closure_change(cohort)
    return closure


@transaction.atomic
def delete_closure(*, closure: Closure) -> None:
    cohort = closure.cohort
    if cohort is not None:
        _open(cohort)
    closure.delete()
    _after_closure_change(cohort)


def _after_closure_change(cohort: Cohort | None) -> None:
    if cohort is not None:
        _refresh_end(cohort)
        return
    selectors.bump_schedule(None)  # provider-wide: every cohort's dates may move
    refresh_end_dates()  # inline: no worker needed, and the change and dates commit together


@transaction.atomic
def sync_holidays(payload: dict) -> int:
    """Upsert GOV.UK bank holidays (the bank-holidays.json shape) in ONE statement.
    Returns rows written. Only adds or updates days: a day GOV.UK drops is kept (it may
    already explain a break in a running cohort)."""
    rows: dict[tuple[str, date], Holiday] = {}
    for division in Division.values:
        for e in (payload.get(division) or {}).get("events") or []:
            try:
                day = date.fromisoformat(str(e["date"]))
            except (KeyError, TypeError, ValueError):
                continue
            title = html.plain(str(e.get("title") or "Bank holiday"), 120).strip() or "Bank holiday"
            rows[(division, day)] = Holiday(division=division, date=day, title=title)
    if rows:
        Holiday.objects.bulk_create(
            rows.values(), update_conflicts=True, unique_fields=["division", "date"], update_fields=["title"]
        )
        selectors.bump_schedule(None)
        refresh_end_dates()
    return len(rows)


# ---------------------------------------------------------------- program settings (M19)
@transaction.atomic
def save_program_settings(*, program_id, by, **fields):
    """Create or change a program's delivery settings. Only the given fields change."""
    from apps.catalog.models import KsbStandard

    from .models import ProgramSetting

    _program(program_id)
    setting, _ = ProgramSetting.objects.select_for_update().get_or_create(program_id=program_id)
    if "ksb_standard_id" in fields:
        sid = fields["ksb_standard_id"]
        if sid is not None and not KsbStandard.objects.filter(pk=sid).exists():
            raise ServiceError("not_found", "KSB standard not found.", status=404)
        setting.ksb_standard_id = sid
    if fields.get("otj_target_mode") is not None:
        if fields["otj_target_mode"] not in ProgramSetting.OtjTarget.values:
            raise ServiceError("bad_target", "Choose how the off-the-job target is measured.")
        setting.otj_target_mode = fields["otj_target_mode"]
    if fields.get("swap_cutoff_mode") is not None:
        if fields["swap_cutoff_mode"] not in ProgramSetting.SwapCutoff.values:
            raise ServiceError("bad_cutoff", "Choose how the seat swap cut-off is measured.")
        setting.swap_cutoff_mode = fields["swap_cutoff_mode"]
    for name in ("otj_target_value", "otj_amber_pct", "otj_daily_cap_min", "min_seats_per_line",
                 "swap_cutoff_value"):  # fmt: skip
        if fields.get(name) is not None:
            setattr(setting, name, fields[name])
    if setting.swap_cutoff_mode == ProgramSetting.SwapCutoff.PROGRESS and setting.swap_cutoff_value > 100:
        raise ServiceError("bad_cutoff", "A progress cut-off is a percentage, up to 100.")
    if setting.swap_cutoff_mode != ProgramSetting.SwapCutoff.NONE and not setting.swap_cutoff_value:
        raise ServiceError("missing_cutoff", "Give the seat swap cut-off a value.")
    if setting.otj_target_mode != ProgramSetting.OtjTarget.NONE and not setting.otj_target_value:
        raise ServiceError("missing_target", "Give the off-the-job target a value.")
    setting.updated_by = by
    setting.save()
    return setting
