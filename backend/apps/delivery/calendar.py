"""Week dates for a cohort (Programs plan D16). Pure functions: no database, no clock.

Rules:
  * A teaching week is Monday to Friday. Weekends are never teaching days.
  * Week 1 starts on the cohort start date (moved to Monday if it falls on a weekend).
  * Each program week (catalog Section) takes the next teaching week.
  * A teaching week with NO working day (every weekday is a bank holiday or closure) is
    skipped and reported as a break; the program week moves to the next one.
  * Bank holidays inside a week are listed on that week (the week still runs).
  * A module starts on its cohort override date when one is set (weekend -> Monday),
    otherwise the teaching week after the previous module. An override earlier than
    the previous module's last week is allowed but reported as an overlap warning.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID

MAX_SKIPPED_WEEKS = 104  # two years of closures in a row means bad data, not a calendar


class CalendarError(ValueError):
    pass


@dataclass(frozen=True)
class WeekIn:
    section_id: UUID
    title: str


@dataclass(frozen=True)
class ModuleIn:
    module_key: UUID
    title: str
    weeks: Sequence[WeekIn]


@dataclass(frozen=True)
class ClosureIn:
    starts_on: date
    ends_on: date
    reason: str


@dataclass(frozen=True)
class DayOff:
    date: date
    title: str


@dataclass
class WeekPlan:
    section_id: UUID
    number: int  # 1-based across the whole program
    title: str
    starts_on: date  # first working day
    ends_on: date  # last working day
    days_off: list[DayOff] = field(default_factory=list)


@dataclass
class ModulePlan:
    module_key: UUID
    title: str
    starts_on: date | None
    ends_on: date | None
    override: date | None
    weeks: list[WeekPlan] = field(default_factory=list)


@dataclass(frozen=True)
class BreakPlan:
    starts_on: date  # Monday
    ends_on: date  # Friday
    reason: str


@dataclass
class Schedule:
    modules: list[ModulePlan]
    breaks: list[BreakPlan]
    warnings: list[str]

    @property
    def end_date(self) -> date | None:
        ends = [m.ends_on for m in self.modules if m.ends_on]
        return max(ends) if ends else None

    def this_or_next_week(self, day: date) -> WeekPlan | None:
        """The week running on `day`, else the next one to start (None once all are over)."""
        if (week := self.week_for(day)) is not None:
            return week
        return next((w for m in self.modules for w in m.weeks if w.starts_on > day), None)

    def week_for(self, day: date) -> WeekPlan | None:
        """The program week running on `day` (Monday-Sunday of its teaching week)."""
        for m in self.modules:
            for w in m.weeks:
                monday = w.starts_on - timedelta(days=w.starts_on.weekday())
                if monday <= day <= monday + timedelta(days=6):
                    return w
        return None


def _to_weekday(d: date) -> date:
    return d + timedelta(days=7 - d.weekday()) if d.weekday() >= 5 else d


def _next_monday(d: date) -> date:
    return d + timedelta(days=7 - d.weekday())


def _off_reason(day: date, holidays: Mapping[date, str], closures: Sequence[ClosureIn]) -> str | None:
    for c in closures:
        if c.starts_on <= day <= c.ends_on:
            return c.reason
    return holidays.get(day)


def build(
    modules: Sequence[ModuleIn],
    *,
    start: date,
    overrides: Mapping[UUID, date] | None = None,
    holidays: Mapping[date, str] | None = None,
    closures: Iterable[ClosureIn] = (),
    min_days: int = 1,
) -> Schedule:
    """`min_days`: a week is a teaching week only with at least this many working days
    (provider setting learning.program_min_working_days); otherwise it becomes a break."""
    if not 1 <= min_days <= 5:
        raise CalendarError("A teaching week needs between 1 and 5 working days.")
    overrides = overrides or {}
    holidays = holidays or {}
    closures = list(closures)
    cursor = _to_weekday(start)
    number = 0
    plans: list[ModulePlan] = []
    breaks: dict[date, BreakPlan] = {}
    warnings: list[str] = []
    last_end: date | None = None

    for module in modules:
        override = overrides.get(module.module_key)
        if override is not None:
            cursor = _to_weekday(override)
            if last_end is not None and cursor <= last_end:
                warnings.append(f"“{module.title}” starts before the previous module ends.")
        plan = ModulePlan(module.module_key, module.title, None, None, override)
        for week in module.weeks:
            skipped = 0
            while True:
                friday = cursor + timedelta(days=4 - cursor.weekday())
                days = [cursor + timedelta(days=i) for i in range((friday - cursor).days + 1)]
                reasons = {d: _off_reason(d, holidays, closures) for d in days}
                working = [d for d in days if reasons[d] is None]
                if len(working) >= min_days:
                    break
                monday = cursor - timedelta(days=cursor.weekday())
                first_reason = next((r for r in reasons.values() if r), "Too few teaching days")
                breaks.setdefault(monday, BreakPlan(monday, monday + timedelta(days=4), first_reason))
                cursor = _next_monday(cursor)
                skipped += 1
                if skipped > MAX_SKIPPED_WEEKS:
                    raise CalendarError("No teaching days found for two years. Check the closures.")
            number += 1
            plan.weeks.append(
                WeekPlan(
                    section_id=week.section_id,
                    number=number,
                    title=week.title,
                    starts_on=working[0],
                    ends_on=working[-1],
                    days_off=[DayOff(d, r) for d, r in reasons.items() if r],
                )
            )
            cursor = _next_monday(cursor)
        if plan.weeks:
            plan.starts_on, plan.ends_on = plan.weeks[0].starts_on, plan.weeks[-1].ends_on
            last_end = plan.ends_on if last_end is None else max(last_end, plan.ends_on)
        plans.append(plan)

    return Schedule(plans, sorted(breaks.values(), key=lambda b: b.starts_on), warnings)
