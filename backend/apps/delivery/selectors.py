"""Delivery reads: program outlines and cohort schedules (cached)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Q

from apps.catalog.models import Module, Section
from core import cache
from core.errors import ServiceError

from . import calendar
from .models import Closure, Cohort, CohortModule, Group, Holiday

SCHEDULE_NS = "cohort_sched"
SCHEDULE_TTL = 3600


def bump_schedule(cohort_id: UUID | None = None) -> None:
    """Make cached schedules stale: one cohort, or (None) every cohort (provider-wide
    closures, holiday sync). Runs AFTER commit: bumping inside the transaction would let a
    concurrent reader cache the old rows under the new version."""
    scope = cohort_id or "all"
    transaction.on_commit(lambda: cache.bump(SCHEDULE_NS, scope))


def _min_days() -> int:
    from apps.platform.services import get_setting

    return int(get_setting("learning.program_min_working_days") or 1)


def outline(version_id) -> list[calendar.ModuleIn]:
    """A program version's modules and weeks, in order. Two queries."""
    weeks: dict[UUID, list[calendar.WeekIn]] = defaultdict(list)
    for s in (
        Section.objects.filter(version_id=version_id, module__isnull=False)
        .order_by("position")
        .only("id", "title", "module_id")
    ):
        weeks[s.module_id].append(calendar.WeekIn(s.id, s.title))
    return [
        calendar.ModuleIn(m.module_key, m.title, tuple(weeks.get(m.id, ())))
        for m in Module.objects.filter(version_id=version_id)
        .order_by("position")
        .only("id", "module_key", "title")
    ]


def _build(cohort: Cohort, version_id, min_days: int) -> calendar.Schedule:
    modules = outline(version_id)
    overrides = dict(CohortModule.objects.filter(cohort=cohort).values_list("module_key", "starts_on"))
    first = min([cohort.start_date, *overrides.values()])
    holidays = dict(
        Holiday.objects.filter(division=cohort.calendar, date__gte=first).values_list("date", "title")
    )
    closures = [
        calendar.ClosureIn(c.starts_on, c.ends_on, c.reason)
        for c in Closure.objects.filter(Q(cohort=cohort) | Q(cohort__isnull=True), ends_on__gte=first)
    ]
    try:
        return calendar.build(
            modules, start=cohort.start_date, overrides=overrides, holidays=holidays, closures=closures,
            min_days=min_days,
        )  # fmt: skip
    except calendar.CalendarError as e:
        raise ServiceError("bad_schedule", str(e)) from None


def fresh_schedule(cohort: Cohort) -> calendar.Schedule:
    """Built from the database now, never from the cache: writers use it to store the
    cohort's end date inside their own transaction."""
    version_id = cohort.program.live_version_id
    if version_id is None:
        return calendar.Schedule([], [], ["The program is not published yet."])
    return _build(cohort, version_id, _min_days())


def schedule(cohort: Cohort) -> calendar.Schedule:
    """The cohort's dated weeks for the program's LIVE version. Cached per cohort; the key
    also carries the live version, the provider-wide stamp and the working-days setting,
    so publishing a new version, a closure for everyone, a holiday sync or a settings
    change all invalidate it."""
    version_id = cohort.program.live_version_id
    if version_id is None:
        return calendar.Schedule([], [], ["The program is not published yet."])
    min_days = _min_days()
    return cache.get_or_set(
        SCHEDULE_NS,
        cohort.id,
        lambda: _build(cohort, version_id, min_days),
        version_id,
        cache.current_version(SCHEDULE_NS, "all"),
        min_days,
        timeout=SCHEDULE_TTL,
    )


def cohorts_for_program(program_id) -> list[Cohort]:
    """Newest first, with group counts; learner counts come from learner_counts()."""
    return list(
        Cohort.objects.filter(program_id=program_id)
        .annotate(group_count=Count("groups"))
        .order_by("-start_date")
    )


def learner_counts(*, cohort_ids=None, group_ids=None) -> dict[UUID, int]:
    """Placed learners per cohort (or per group) who count towards capacity (active or
    completed), in one grouped query. The group members list uses the same filter."""
    from apps.learning.models import Enrollment, holds_place

    qs = Enrollment.objects.filter(holds_place())
    if group_ids is not None:
        rows = qs.filter(group_id__in=group_ids).values("group_id").annotate(n=Count("id"))
        return {r["group_id"]: r["n"] for r in rows}
    rows = qs.filter(cohort_id__in=cohort_ids or []).values("cohort_id").annotate(n=Count("id"))
    return {r["cohort_id"]: r["n"] for r in rows}


def groups(cohort_id) -> list[Group]:
    return list(Group.objects.filter(cohort_id=cohort_id).select_related("tutor").order_by("name"))


def today_week(cohort: Cohort, today: date) -> calendar.WeekPlan | None:
    return schedule(cohort).week_for(today)
