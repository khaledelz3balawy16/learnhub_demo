"""Console > Programs (M18): programs, cohorts, dated schedules, groups, placement, closures.

Permissions (core.staff_perms): reading program structure and cohort schedules needs
programs.build OR cohorts.manage; learner personal data (group members) and every change
to cohorts, groups, closures or placement need cohorts.manage. Every change is
written to the audit log. Schema names start with ConsoleProgram / ConsoleCohort.
"""

from datetime import date, datetime, time
from uuid import UUID

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Field, Schema

from apps.catalog.models import Course, Module, Section
from apps.delivery import selectors as delivery
from apps.delivery import services as delivery_svc
from apps.delivery.models import Closure, Cohort, Group
from apps.delivery.tasks import fetch_bank_holidays
from apps.identity.models import User
from apps.learning import placement
from apps.learning.models import Enrollment
from core.errors import ServiceError
from core.staff_perms import has_perm, require_perm

from ..services import audit_request
from .common import ConsoleIdOut, ConsoleOkOut, clamp, router, staff

MAX_EMAILS = 200


def _reader(request) -> None:
    staff(request)
    if not (has_perm(request, "programs.build") or has_perm(request, "cohorts.manage")):
        raise ServiceError("forbidden", "You don't have permission to do this.", status=403)


def _manager(request) -> None:
    staff(request)
    require_perm(request, "cohorts.manage")


# ---------------------------------------------------------------- schemas
class ConsoleProgramRowOut(Schema):
    id: UUID
    slug: str
    title: str
    status: str
    published: bool
    module_count: int
    week_count: int
    cohort_count: int
    updated_at: datetime


class ConsoleProgramListOut(Schema):
    items: list[ConsoleProgramRowOut]
    next_cursor: str | None
    # what the signed-in staff member may do here (the page hides what they can't)
    can_build: bool
    can_manage: bool
    default_calendar: str


class ConsoleProgramWeekOut(Schema):
    id: UUID
    title: str


class ConsoleProgramModuleOut(Schema):
    id: UUID
    module_key: UUID
    title: str
    weeks: list[ConsoleProgramWeekOut]


class ConsoleCohortRowOut(Schema):
    id: UUID
    name: str
    status: str
    start_date: date
    end_date: date | None
    calendar: str
    capacity: int | None
    group_count: int
    learner_count: int


class ConsoleProgramDetailOut(Schema):
    id: UUID
    slug: str
    title: str
    status: str
    published: bool
    can_build: bool
    can_manage: bool
    modules: list[ConsoleProgramModuleOut]
    cohorts: list[ConsoleCohortRowOut]


class ConsoleProgramCohortIn(Schema):
    name: str = Field(..., min_length=1, max_length=120)
    start_date: date
    calendar: str | None = None  # None = the provider's default (setting learning.program_calendar)
    capacity: int | None = Field(None, ge=1, le=100000)


class ConsoleCohortPatchIn(Schema):
    name: str | None = Field(None, min_length=1, max_length=120)
    start_date: date | None = None
    calendar: str | None = None
    capacity: int | None = Field(None, ge=1, le=100000)
    status: str | None = None


class ConsoleCohortDayOffOut(Schema):
    date: date
    title: str


class ConsoleCohortWeekOut(Schema):
    section_id: UUID
    number: int
    title: str
    starts_on: date
    ends_on: date
    days_off: list[ConsoleCohortDayOffOut]


class ConsoleCohortModuleOut(Schema):
    module_key: UUID
    title: str
    starts_on: date | None
    ends_on: date | None
    override: date | None
    weeks: list[ConsoleCohortWeekOut]


class ConsoleCohortBreakOut(Schema):
    starts_on: date
    ends_on: date
    reason: str


class ConsoleCohortGroupOut(Schema):
    id: UUID
    name: str
    status: str
    weekday: int | None
    starts_at: time | None
    ends_at: time | None
    capacity: int | None
    tutor_id: UUID | None
    tutor_name: str | None
    learner_count: int


class ConsoleCohortClosureOut(Schema):
    id: UUID
    starts_on: date
    ends_on: date
    reason: str
    provider_wide: bool


class ConsoleCohortDetailOut(Schema):
    id: UUID
    program_id: UUID
    program_title: str
    name: str
    status: str
    start_date: date
    end_date: date | None
    calendar: str
    capacity: int | None
    learner_count: int
    can_manage: bool
    modules: list[ConsoleCohortModuleOut]
    breaks: list[ConsoleCohortBreakOut]
    warnings: list[str]
    groups: list[ConsoleCohortGroupOut]
    closures: list[ConsoleCohortClosureOut]


class ConsoleModuleStartIn(Schema):
    starts_on: date | None = None  # None = back to the automatic date


class ConsoleGroupIn(Schema):
    name: str | None = Field(None, min_length=1, max_length=80)
    weekday: int | None = Field(None, ge=0, le=6)
    starts_at: time | None = None
    ends_at: time | None = None
    capacity: int | None = Field(None, ge=1, le=10000)
    tutor_id: UUID | None = None
    status: str | None = None


class ConsoleGroupMemberOut(Schema):
    enrollment_id: UUID
    user_id: UUID
    name: str
    email: str
    progress_pct: float
    status: str


class ConsoleGroupMembersOut(Schema):
    items: list[ConsoleGroupMemberOut]
    next_cursor: str | None


class ConsoleGroupAddIn(Schema):
    emails: list[str] = Field(..., min_length=1, max_length=MAX_EMAILS)


class ConsoleGroupAddOut(Schema):
    added: int
    not_found: list[str]


class ConsoleClosureIn(Schema):
    cohort_id: UUID | None = None  # None = every cohort
    starts_on: date
    ends_on: date
    reason: str = Field(..., min_length=2, max_length=200)


class ConsoleProgramTutorOut(Schema):
    id: UUID
    name: str
    email: str


class ConsoleHolidaySyncOut(Schema):
    saved: int


# ---------------------------------------------------------------- programs
@router.get("/programs", response=ConsoleProgramListOut)
def programs(request, q: str = "", cursor: str | None = None, limit: int = 50):
    """Keyset by (title, id)."""
    from apps.platform.services import get_setting
    from core import cursor as keyset

    _reader(request)
    limit = clamp(limit, 100)
    qs = Course.objects.filter(kind=Course.Kind.PROGRAM, deleted_at__isnull=True)
    if q.strip():
        qs = qs.filter(title__icontains=q.strip()[:80])
    after = keyset.decode(cursor, 2)
    if after:
        qs = qs.filter(Q(title__gt=after[0]) | Q(title=after[0], id__gt=after[1]))
    fetched = list(qs.annotate(cohort_count=Count("cohorts")).order_by("title", "id")[: limit + 1])
    rows = fetched[:limit]
    live = [c.live_version_id for c in rows if c.live_version_id]
    modules = dict(
        Module.objects.filter(version_id__in=live)
        .values("version_id")
        .annotate(n=Count("id"))
        .values_list("version_id", "n")
    )
    weeks = dict(
        Section.objects.filter(version_id__in=live, module__isnull=False)
        .values("version_id").annotate(n=Count("id")).values_list("version_id", "n")
    )  # fmt: skip
    items = [
        {"id": c.id, "slug": c.slug, "title": c.title, "status": c.status, "published": bool(c.live_version_id),
         "module_count": modules.get(c.live_version_id, 0), "week_count": weeks.get(c.live_version_id, 0),
         "cohort_count": c.cohort_count, "updated_at": c.updated_at}
        for c in rows
    ]  # fmt: skip
    return {
        "items": items,
        "next_cursor": keyset.encode(rows[-1].title, rows[-1].id) if len(fetched) > limit else None,
        "can_build": has_perm(request, "programs.build"),
        "can_manage": has_perm(request, "cohorts.manage"),
        "default_calendar": get_setting("learning.program_calendar"),
    }


def _program(program_id) -> Course:
    return get_object_or_404(Course, pk=program_id, kind=Course.Kind.PROGRAM, deleted_at__isnull=True)


def _cohort_rows(cohorts: list[Cohort]) -> list[dict]:
    counts = delivery.learner_counts(cohort_ids=[c.id for c in cohorts])
    return [
        {"id": c.id, "name": c.name, "status": c.status, "start_date": c.start_date, "end_date": c.end_date,
         "calendar": c.calendar, "capacity": c.capacity, "group_count": c.group_count,
         "learner_count": counts.get(c.id, 0)}
        for c in cohorts
    ]  # fmt: skip


@router.get("/programs/{program_id}", response=ConsoleProgramDetailOut)
def program(request, program_id: UUID):
    _reader(request)
    c = _program(program_id)
    outline = delivery.outline(c.live_version_id) if c.live_version_id else []
    ids = dict(Module.objects.filter(version_id=c.live_version_id).values_list("module_key", "id"))
    return {
        "id": c.id, "slug": c.slug, "title": c.title, "status": c.status, "published": bool(c.live_version_id),
        "can_build": has_perm(request, "programs.build"), "can_manage": has_perm(request, "cohorts.manage"),
        "modules": [{"id": ids[m.module_key], "module_key": m.module_key, "title": m.title,
                     "weeks": [{"id": w.section_id, "title": w.title} for w in m.weeks]} for m in outline],
        "cohorts": _cohort_rows(delivery.cohorts_for_program(c.id)),
    }  # fmt: skip


# ---------------------------------------------------------------- cohorts
@router.post("/programs/{program_id}/cohorts", response=ConsoleIdOut)
def create_cohort(request, program_id: UUID, body: ConsoleProgramCohortIn):
    _manager(request)
    cohort = delivery_svc.create_cohort(program_id=program_id, name=body.name, start_date=body.start_date,
                                        calendar=body.calendar, capacity=body.capacity, by=request.user)  # fmt: skip
    audit_request(
        request, "cohort.create", "cohort", cohort.id, {"program_id": str(program_id), "name": cohort.name}
    )
    return {"id": cohort.id}


def _cohort(cohort_id) -> Cohort:
    return get_object_or_404(Cohort.objects.select_related("program"), pk=cohort_id)


@router.get("/program-cohorts/{cohort_id}", response=ConsoleCohortDetailOut)
def cohort(request, cohort_id: UUID):
    _reader(request)
    c = _cohort(cohort_id)
    plan = delivery.schedule(c)
    groups = delivery.groups(c.id)
    per_group = delivery.learner_counts(group_ids=[g.id for g in groups])
    closures = Closure.objects.filter(Q(cohort=c) | Q(cohort__isnull=True)).order_by("starts_on")[:200]
    return {
        "id": c.id, "program_id": c.program_id, "program_title": c.program.title, "name": c.name,
        "status": c.status, "start_date": c.start_date, "end_date": c.end_date, "calendar": c.calendar,
        "capacity": c.capacity, "learner_count": delivery.learner_counts(cohort_ids=[c.id]).get(c.id, 0),
        "can_manage": has_perm(request, "cohorts.manage"),
        "modules": [
            {"module_key": m.module_key, "title": m.title, "starts_on": m.starts_on, "ends_on": m.ends_on,
             "override": m.override,
             "weeks": [{"section_id": w.section_id, "number": w.number, "title": w.title, "starts_on": w.starts_on,
                        "ends_on": w.ends_on, "days_off": [{"date": d.date, "title": d.title} for d in w.days_off]}
                       for w in m.weeks]}
            for m in plan.modules
        ],
        "breaks": [{"starts_on": b.starts_on, "ends_on": b.ends_on, "reason": b.reason} for b in plan.breaks],
        "warnings": plan.warnings,
        "groups": [
            {"id": g.id, "name": g.name, "status": g.status, "weekday": g.weekday, "starts_at": g.starts_at,
             "ends_at": g.ends_at, "capacity": g.capacity, "tutor_id": g.tutor_id,
             "tutor_name": g.tutor.full_name if g.tutor_id else None, "learner_count": per_group.get(g.id, 0)}
            for g in groups
        ],
        "closures": [
            {"id": x.id, "starts_on": x.starts_on, "ends_on": x.ends_on, "reason": x.reason,
             "provider_wide": x.cohort_id is None}
            for x in closures
        ],
    }  # fmt: skip


@router.patch("/program-cohorts/{cohort_id}", response=ConsoleOkOut)
def update_cohort(request, cohort_id: UUID, body: ConsoleCohortPatchIn):
    _manager(request)
    changes = body.dict(exclude_unset=True)
    delivery_svc.update_cohort(cohort=_cohort(cohort_id), **changes)
    audit_request(request, "cohort.update", "cohort", cohort_id, {k: str(v) for k, v in changes.items()})
    return {"ok": True}


@router.put("/program-cohorts/{cohort_id}/modules/{module_key}/start", response=ConsoleOkOut)
def set_module_start(request, cohort_id: UUID, module_key: UUID, body: ConsoleModuleStartIn):
    _manager(request)
    delivery_svc.set_module_start(cohort=_cohort(cohort_id), module_key=module_key, starts_on=body.starts_on)
    audit_request(request, "cohort.module_start", "cohort", cohort_id,
                  {"module_key": str(module_key), "starts_on": str(body.starts_on)})  # fmt: skip
    return {"ok": True}


# ---------------------------------------------------------------- groups
@router.post("/program-cohorts/{cohort_id}/groups", response=ConsoleIdOut)
def create_group(request, cohort_id: UUID, body: ConsoleGroupIn):
    _manager(request)
    if not body.name:
        raise ServiceError("missing_name", "Give the group a name.")
    g = delivery_svc.save_group(cohort=_cohort(cohort_id), **body.dict(exclude_unset=True))
    audit_request(request, "group.create", "group", g.id, {"cohort_id": str(cohort_id), "name": g.name})
    return {"id": g.id}


def _group(group_id) -> Group:
    return get_object_or_404(Group.objects.select_related("cohort__program"), pk=group_id)


@router.patch("/program-groups/{group_id}", response=ConsoleOkOut)
def update_group(request, group_id: UUID, body: ConsoleGroupIn):
    _manager(request)
    g = _group(group_id)
    changes = body.dict(exclude_unset=True)
    delivery_svc.save_group(cohort=g.cohort, group=g, **changes)
    audit_request(request, "group.update", "group", g.id, {k: str(v) for k, v in changes.items()})
    return {"ok": True}


@router.delete("/program-groups/{group_id}", response=ConsoleOkOut)
def delete_group(request, group_id: UUID):
    _manager(request)
    g = _group(group_id)
    delivery_svc.delete_group(group=g)
    audit_request(request, "group.delete", "group", group_id, {"name": g.name})
    return {"ok": True}


@router.get("/program-groups/{group_id}/members", response=ConsoleGroupMembersOut)
def group_members(request, group_id: UUID, cursor: str | None = None, limit: int = 100):
    _manager(request)  # names, emails and progress: cohort managers only
    from core import cursor as keyset

    limit = clamp(limit, 200)
    qs = Enrollment.objects.filter(group_id=group_id).select_related("user").order_by("-id")
    after = keyset.decode(cursor, 1)
    if after:
        qs = qs.filter(id__lt=after[0])
    rows = list(qs[: limit + 1])
    page = rows[:limit]
    return {
        "items": [
            {"enrollment_id": e.id, "user_id": e.user_id, "name": e.user.full_name, "email": e.user.email,
             "progress_pct": float(e.progress_pct), "status": e.status}
            for e in page
        ],
        "next_cursor": keyset.encode(page[-1].id) if len(rows) > limit else None,
    }  # fmt: skip


@router.post("/program-groups/{group_id}/members", response=ConsoleGroupAddOut)
def add_members(request, group_id: UUID, body: ConsoleGroupAddIn):
    _manager(request)
    emails = list(dict.fromkeys(e.strip().lower() for e in body.emails if e.strip()))[:MAX_EMAILS]
    users = list(User.objects.filter(email__in=emails, is_active=True))
    found = {u.email for u in users}
    placed = placement.place(group_id=group_id, users=users) if users else []
    audit_request(request, "group.add_members", "group", group_id, {"emails": sorted(found)})
    return {"added": len(placed), "not_found": [e for e in emails if e not in found]}


@router.delete("/program-groups/{group_id}/members/{enrollment_id}", response=ConsoleOkOut)
def remove_member(request, group_id: UUID, enrollment_id: UUID):
    _manager(request)
    e = get_object_or_404(Enrollment, pk=enrollment_id, group_id=group_id)
    placement.remove(enrollment=e)
    audit_request(request, "group.remove_member", "group", group_id, {"enrollment_id": str(enrollment_id)})
    return {"ok": True}


@router.get("/program-tutors", response=list[ConsoleProgramTutorOut])
def tutors(request, q: str = ""):
    """Staff who can be a group's tutor (role holds groups.teach, or superuser)."""
    _reader(request)
    can_teach = Q(is_superuser=True) | Q(staff_roles__role__permissions__contains=["groups.teach"])
    qs = User.objects.filter(can_teach, is_staff=True, is_active=True).distinct()
    if q.strip():
        term = q.strip()[:80]
        qs = qs.filter(Q(email__icontains=term) | Q(full_name__icontains=term))
    return [
        {"id": u.id, "name": u.full_name or u.email, "email": u.email} for u in qs.order_by("full_name")[:100]
    ]


# ---------------------------------------------------------------- closures and holidays
@router.get("/program-closures", response=list[ConsoleCohortClosureOut])
def closures(request):
    """Provider-wide closures (every cohort)."""
    _reader(request)
    rows = Closure.objects.filter(cohort__isnull=True).order_by("-starts_on")[:200]
    return [{"id": x.id, "starts_on": x.starts_on, "ends_on": x.ends_on, "reason": x.reason, "provider_wide": True}
            for x in rows]  # fmt: skip


@router.post("/program-closures", response=ConsoleIdOut)
def add_closure(request, body: ConsoleClosureIn):
    _manager(request)
    cohort_obj = _cohort(body.cohort_id) if body.cohort_id else None
    x = delivery_svc.add_closure(cohort=cohort_obj, starts_on=body.starts_on, ends_on=body.ends_on,
                                 reason=body.reason, by=request.user)  # fmt: skip
    audit_request(request, "closure.create", "closure", x.id,
                  {"cohort_id": str(body.cohort_id) if body.cohort_id else None, "reason": x.reason})  # fmt: skip
    return {"id": x.id}


@router.delete("/program-closures/{closure_id}", response=ConsoleOkOut)
def delete_closure(request, closure_id: UUID):
    _manager(request)
    x = get_object_or_404(Closure.objects.select_related("cohort__program"), pk=closure_id)
    delivery_svc.delete_closure(closure=x)
    audit_request(request, "closure.delete", "closure", closure_id, {"reason": x.reason})
    return {"ok": True}


@router.post("/program-holidays/sync", response=ConsoleHolidaySyncOut)
def sync_holidays(request):
    """Fetch GOV.UK bank holidays now (also runs monthly)."""
    _manager(request)
    try:
        payload = fetch_bank_holidays(timeout=10)
    except Exception:  # noqa: BLE001 - network: tell the user, never 500
        raise ServiceError(
            "holidays_unavailable", "GOV.UK couldn't be reached. Try again later.", status=502
        ) from None
    saved = delivery_svc.sync_holidays(payload)  # also refreshes the cohorts' end dates
    audit_request(request, "holidays.sync", "holidays", "gov.uk", {"saved": saved})
    return {"saved": saved}
