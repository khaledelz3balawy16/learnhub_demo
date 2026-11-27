"""Console: program live sessions and workshops (M20, plan D3, D17, D18, D24).

Who may do what:
  * cohorts.manage: everything (plan a group's sessions, move or cancel them, workshops).
  * groups.teach: their own groups' sessions (add a link, Teams meeting, attendance,
    recording); they read workshops (brief B6: cohort managers run workshops).
Every change is audited. Teams status never reveals a secret.
"""

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Field, Schema

from apps.catalog import media, teams
from apps.catalog.models import Course
from apps.catalog.schemas import PlaybackOut
from apps.delivery import sessions
from apps.delivery.models import Group, LiveSession, MeetingFields, Workshop
from apps.learning import live
from apps.learning.models import SessionAttendance, WorkshopBooking
from core import cursor as keyset
from core.errors import ServiceError
from core.staff_perms import has_perm

from ..services import audit_request
from .common import ConsoleIdOut, ConsoleOkOut, clamp, router, staff

MANAGE, TEACH = "cohorts.manage", "groups.teach"
FORBIDDEN = ("forbidden", "You don't have permission to do this.")


def _manage(request) -> bool:
    staff(request)
    return has_perm(request, MANAGE)


def _group(request, group_id, *, plan: bool = False) -> Group:
    """A group the caller may run: every group (cohorts.manage) or one they tutor."""
    manage = _manage(request)
    g = get_object_or_404(Group.objects.select_related("cohort__program"), pk=group_id)
    if manage or (not plan and has_perm(request, TEACH) and g.tutor_id == request.user.id):
        return g
    raise ServiceError(*FORBIDDEN, status=403)


def _session(request, session_id) -> LiveSession:
    s = get_object_or_404(
        LiveSession.objects.select_related("group__cohort__program", "recording"), pk=session_id
    )
    _group(request, s.group_id)
    return s


def _workshop(request, workshop_id, *, write: bool = False) -> Workshop:
    manage = _manage(request)
    if not (manage or (not write and has_perm(request, TEACH))):
        raise ServiceError(*FORBIDDEN, status=403)
    return get_object_or_404(
        Workshop.objects.select_related("program", "cohort", "recording"), pk=workshop_id
    )


def _recording_state(obj: MeetingFields) -> str:
    """none / pending / processing / ready / failed, from the job state and the video's own state."""
    if obj.recording_id is None:
        return obj.recording_status if obj.recording_status != MeetingFields.Recording.READY else "none"
    return "ready" if obj.recording.status in ("playable", "ready") else "processing"


def _recording(obj: MeetingFields) -> dict | None:
    if obj.recording_id is None or obj.recording.status not in ("playable", "ready"):
        return None
    return media.playback(obj.recording)


# ---------------------------------------------------------------- schemas
class ConsoleMeetingsStatusOut(Schema):
    teams_connected: bool
    organizer: str


class ConsoleLiveSessionOut(Schema):
    id: UUID
    lecture_key: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    duration_min: int
    status: str
    provider: str
    join_url: str
    has_meeting: bool
    recording_state: str
    recording: PlaybackOut | None
    present: int
    marked: int
    attendance_synced_at: datetime | None


class ConsoleLiveSessionListOut(Schema):
    items: list[ConsoleLiveSessionOut]
    teams_connected: bool
    can_plan: bool
    time_zone: str


class ConsoleLivePlanOut(Schema):
    created: int
    moved: int
    cancelled: int
    skipped: list[str]


class ConsoleLiveSessionPatchIn(Schema):
    starts_at: datetime | None = None
    duration_min: int | None = Field(None, ge=5, le=720)
    join_url: str | None = Field(None, max_length=1000)
    status: str | None = Field(None, pattern="^(scheduled|cancelled)$")


class ConsoleLiveAttendanceRowOut(Schema):
    enrollment_id: UUID
    name: str
    email: str
    minutes: int | None  # None = not marked
    source: str


class ConsoleLiveAttendanceOut(Schema):
    items: list[ConsoleLiveAttendanceRowOut]
    duration_min: int
    present_min: int
    started: bool
    has_meeting: bool


class ConsoleLiveAttendanceMarkIn(Schema):
    enrollment_id: UUID
    minutes: int | None = Field(None, ge=0, le=1440)  # None = present for the whole event


class ConsoleLiveAttendanceIn(Schema):
    marks: list[ConsoleLiveAttendanceMarkIn] = Field(..., max_length=500)


class ConsoleLiveMarkedOut(Schema):
    written: int


class ConsoleLiveUploadIn(Schema):
    filename: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., gt=0, le=20 * 1024**3)


class ConsoleLiveBunnyUploadOut(Schema):
    endpoint: str
    headers: dict[str, str]
    expires_at: int


class ConsoleLiveUploadOut(Schema):
    asset_id: UUID
    upload: ConsoleLiveBunnyUploadOut


class ConsoleWorkshopOut(Schema):
    id: UUID
    program_id: UUID
    program_title: str
    cohort_id: UUID | None
    cohort_name: str | None
    title: str
    description: str
    starts_at: datetime
    ends_at: datetime
    duration_min: int
    capacity: int | None
    booked: int
    expected_otj_min: int
    cpd_min: int
    status: str
    provider: str
    join_url: str
    has_meeting: bool
    recording_state: str
    recording: PlaybackOut | None


class ConsoleWorkshopListOut(Schema):
    items: list[ConsoleWorkshopOut]
    next_cursor: str | None
    can_manage: bool
    teams_connected: bool


class ConsoleWorkshopIn(Schema):
    program_id: UUID
    cohort_id: UUID | None = None
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field("", max_length=4000)
    starts_at: datetime
    duration_min: int = Field(..., ge=5, le=720)
    capacity: int | None = Field(None, ge=1, le=10000)
    expected_otj_min: int = Field(0, ge=0, le=1440)
    cpd_min: int = Field(0, ge=0, le=6000)
    join_url: str = Field("", max_length=1000)


class ConsoleWorkshopPatchIn(Schema):
    cohort_id: UUID | None = None
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, max_length=4000)
    starts_at: datetime | None = None
    duration_min: int | None = Field(None, ge=5, le=720)
    capacity: int | None = Field(None, ge=1, le=10000)
    expected_otj_min: int | None = Field(None, ge=0, le=1440)
    cpd_min: int | None = Field(None, ge=0, le=6000)
    join_url: str | None = Field(None, max_length=1000)
    status: str | None = Field(None, pattern="^(scheduled|cancelled)$")


# ---------------------------------------------------------------- Teams status
@router.get("/meetings/status", response=ConsoleMeetingsStatusOut)
def meetings_status(request):
    staff(request)
    return {"teams_connected": teams.connected(), "organizer": teams.organizer() if teams.connected() else ""}


# ---------------------------------------------------------------- group sessions
def _session_row(s: LiveSession) -> dict:
    return {
        "id": s.id, "lecture_key": s.lecture_key, "title": s.title, "starts_at": s.starts_at,
        "ends_at": live.ends_at(s), "duration_min": s.duration_min, "status": s.status, "provider": s.provider,
        "join_url": s.join_url, "has_meeting": bool(s.teams_meeting_id), "recording_state": _recording_state(s),
        "recording": _recording(s), "present": getattr(s, "present", 0), "marked": getattr(s, "marked", 0),
        "attendance_synced_at": s.attendance_synced_at,
    }  # fmt: skip


@router.get("/program-groups/{group_id}/sessions", response=ConsoleLiveSessionListOut)
def group_sessions(request, group_id: UUID):
    g = _group(request, group_id)
    present = live.present_min()
    rows = (
        LiveSession.objects.filter(group=g)
        .select_related("recording__library")
        .annotate(
            marked=Count("attendance"),
            present=Count("attendance", filter=Q(attendance__minutes__gte=present)),
        )
        .order_by("starts_at")
    )
    return {
        "items": [_session_row(s) for s in rows],
        "teams_connected": teams.connected(),
        "can_plan": has_perm(request, MANAGE),
        "time_zone": str(sessions.provider_tz()),
    }


@router.post("/program-groups/{group_id}/sessions/plan", response=ConsoleLivePlanOut)
def plan_group_sessions(request, group_id: UUID):
    g = _group(request, group_id, plan=True)
    r = sessions.plan_sessions(group=g, by=request.user)
    audit_request(request, "sessions.plan", "group", g.id,
                  {"created": r.created, "moved": r.moved, "cancelled": r.cancelled})  # fmt: skip
    return {"created": r.created, "moved": r.moved, "cancelled": r.cancelled, "skipped": r.skipped}


@router.patch("/program-sessions/{session_id}", response=ConsoleOkOut)
def update_session(request, session_id: UUID, body: ConsoleLiveSessionPatchIn):
    s = _session(request, session_id)
    changes = body.dict(exclude_unset=True)
    if set(changes) - {"join_url"} and not has_perm(request, MANAGE):
        raise ServiceError("forbidden", "Only cohort managers move or cancel sessions.", status=403)
    sessions.update_session(session=s, by=request.user, **changes)
    audit_request(request, "session.update", "live_session", s.id, {k: str(v) for k, v in changes.items()})
    return {"ok": True}


@router.post("/program-sessions/{session_id}/teams", response=ConsoleOkOut)
def session_teams(request, session_id: UUID):
    s = _session(request, session_id)
    if not teams.connected():
        raise ServiceError("teams_not_configured", "Microsoft Teams isn't connected. Add a link instead.")
    sessions.ensure_meeting(s)
    audit_request(request, "session.teams", "live_session", s.id, {})
    return {"ok": True}


def _attendance_out(obj: MeetingFields, rows: list[dict]) -> dict:
    from django.utils import timezone

    return {
        "items": rows, "duration_min": obj.duration_min, "present_min": live.present_min(),
        "started": obj.starts_at <= timezone.now(), "has_meeting": bool(obj.teams_meeting_id),
    }  # fmt: skip


@router.get("/program-sessions/{session_id}/attendance", response=ConsoleLiveAttendanceOut)
def session_attendance(request, session_id: UUID):
    s = _session(request, session_id)
    marks = {a.enrollment_id: a for a in SessionAttendance.objects.filter(session=s)}
    rows = []
    for e in live.session_members(s):
        a = marks.get(e.id)
        rows.append({"enrollment_id": e.id, "name": e.user.full_name, "email": e.user.email,
                     "minutes": a.minutes if a else None, "source": a.source if a else ""})  # fmt: skip
    return _attendance_out(s, rows)


@router.put("/program-sessions/{session_id}/attendance", response=ConsoleLiveMarkedOut)
def mark_session(request, session_id: UUID, body: ConsoleLiveAttendanceIn):
    s = _session(request, session_id)
    marks = {m.enrollment_id: (s.duration_min if m.minutes is None else m.minutes) for m in body.marks}
    n = live.mark_session(session=s, marks=marks, by=request.user)
    audit_request(request, "session.attendance", "live_session", s.id, {"marked": n})
    return {"written": n}


@router.post("/program-sessions/{session_id}/attendance/sync", response=ConsoleLiveMarkedOut)
def sync_session(request, session_id: UUID):
    s = _session(request, session_id)
    n = live.sync_session_attendance(s)
    audit_request(request, "session.attendance_sync", "live_session", s.id, {"marked": n})
    return {"written": n}


@router.post("/program-sessions/{session_id}/recording", response=ConsoleLiveUploadOut)
def session_recording(request, session_id: UUID, body: ConsoleLiveUploadIn):
    s = _session(request, session_id)
    out = sessions.start_recording_upload(
        obj=s, by=request.user, filename=body.filename, size_bytes=body.size_bytes
    )
    audit_request(request, "session.recording", "live_session", s.id, {"asset_id": str(out["asset_id"])})
    return out


# ---------------------------------------------------------------- workshops
def _workshop_row(w: Workshop) -> dict:
    return {
        "id": w.id, "program_id": w.program_id, "program_title": w.program.title, "cohort_id": w.cohort_id,
        "cohort_name": w.cohort.name if w.cohort_id else None, "title": w.title, "description": w.description,
        "starts_at": w.starts_at, "ends_at": live.ends_at(w), "duration_min": w.duration_min, "capacity": w.capacity,
        "booked": getattr(w, "booked", 0), "expected_otj_min": w.expected_otj_min, "cpd_min": w.cpd_min,
        "status": w.status, "provider": w.provider, "join_url": w.join_url, "has_meeting": bool(w.teams_meeting_id),
        "recording_state": _recording_state(w), "recording": _recording(w),
    }  # fmt: skip


@router.get("/program-workshops", response=ConsoleWorkshopListOut)
def workshops(request, program_id: UUID | None = None, cursor: str | None = None, limit: int = 30):
    """Newest first (by start)."""
    manage = _manage(request)
    if not (manage or has_perm(request, TEACH)):
        raise ServiceError(*FORBIDDEN, status=403)
    limit = clamp(limit, 100)
    qs = (
        Workshop.objects.select_related("program", "cohort", "recording__library")
        .annotate(booked=Count("bookings", filter=Q(bookings__status=WorkshopBooking.Status.BOOKED)))
        .order_by("-starts_at", "-id")
    )
    if program_id:
        qs = qs.filter(program_id=program_id)
    after = keyset.decode(cursor, 2)
    if after:
        qs = qs.filter(Q(starts_at__lt=after[0]) | Q(starts_at=after[0], id__lt=after[1]))
    rows = list(qs[: limit + 1])
    page = rows[:limit]
    return {
        "items": [_workshop_row(w) for w in page],
        "next_cursor": keyset.encode(page[-1].starts_at.isoformat(), page[-1].id)
        if len(rows) > limit
        else None,
        "can_manage": manage,
        "teams_connected": teams.connected(),
    }


@router.post("/program-workshops", response=ConsoleIdOut)
def create_workshop(request, body: ConsoleWorkshopIn):
    if not _manage(request):
        raise ServiceError(*FORBIDDEN, status=403)
    program = get_object_or_404(Course, pk=body.program_id, kind=Course.Kind.PROGRAM)
    fields = body.dict(exclude={"program_id"})
    w = sessions.create_workshop(program=program, by=request.user, **fields)
    audit_request(request, "workshop.create", "workshop", w.id, {"title": w.title})
    return {"id": w.id}


@router.patch("/program-workshops/{workshop_id}", response=ConsoleOkOut)
def update_workshop(request, workshop_id: UUID, body: ConsoleWorkshopPatchIn):
    w = _workshop(request, workshop_id, write=True)
    changes = body.dict(exclude_unset=True)
    sessions.update_workshop(workshop=w, **changes)
    audit_request(request, "workshop.update", "workshop", w.id, {k: str(v) for k, v in changes.items()})
    return {"ok": True}


@router.post("/program-workshops/{workshop_id}/teams", response=ConsoleOkOut)
def workshop_teams(request, workshop_id: UUID):
    w = _workshop(request, workshop_id, write=True)
    if not teams.connected():
        raise ServiceError("teams_not_configured", "Microsoft Teams isn't connected. Add a link instead.")
    sessions.ensure_meeting(w)
    audit_request(request, "workshop.teams", "workshop", w.id, {})
    return {"ok": True}


@router.get("/program-workshops/{workshop_id}/attendance", response=ConsoleLiveAttendanceOut)
def workshop_attendance(request, workshop_id: UUID):
    w = _workshop(request, workshop_id)
    rows = [
        {"enrollment_id": b.enrollment_id, "name": b.enrollment.user.full_name, "email": b.enrollment.user.email,
         "minutes": b.attended_min, "source": b.source}
        for b in live.workshop_members(w)
    ]  # fmt: skip
    return _attendance_out(w, rows)


@router.put("/program-workshops/{workshop_id}/attendance", response=ConsoleLiveMarkedOut)
def mark_workshop(request, workshop_id: UUID, body: ConsoleLiveAttendanceIn):
    w = _workshop(request, workshop_id, write=True)
    n = live.mark_workshop(
        workshop=w, marks={m.enrollment_id: m.minutes for m in body.marks}, by=request.user
    )
    audit_request(request, "workshop.attendance", "workshop", w.id, {"marked": n})
    return {"written": n}


@router.post("/program-workshops/{workshop_id}/attendance/sync", response=ConsoleLiveMarkedOut)
def sync_workshop(request, workshop_id: UUID):
    w = _workshop(request, workshop_id, write=True)
    n = live.sync_workshop_attendance(w)
    audit_request(request, "workshop.attendance_sync", "workshop", w.id, {"marked": n})
    return {"written": n}


@router.post("/program-workshops/{workshop_id}/recording", response=ConsoleLiveUploadOut)
def workshop_recording(request, workshop_id: UUID, body: ConsoleLiveUploadIn):
    w = _workshop(request, workshop_id, write=True)
    out = sessions.start_recording_upload(
        obj=w, by=request.user, filename=body.filename, size_bytes=body.size_bytes
    )
    audit_request(request, "workshop.recording", "workshop", w.id, {"asset_id": str(out["asset_id"])})
    return out


# ---------------------------------------------------------------- a tutor's groups
class ConsoleTeachingGroupOut(Schema):
    id: UUID
    name: str
    cohort_id: UUID
    cohort_name: str
    program_title: str
    weekday: int | None
    starts_at: time | None
    ends_at: time | None
    learner_count: int
    next_session_at: datetime | None


@router.get("/program-teaching", response=list[ConsoleTeachingGroupOut])
def my_teaching(request):
    """The active groups the signed-in tutor teaches, with their next session. Two queries."""
    from django.db.models import Min
    from django.utils import timezone

    from apps.delivery import selectors as delivery

    staff(request)
    if not (has_perm(request, TEACH) or has_perm(request, MANAGE)):
        raise ServiceError(*FORBIDDEN, status=403)
    now = timezone.now()
    groups = list(
        Group.objects.filter(tutor=request.user, status=Group.Status.ACTIVE)
        .select_related("cohort__program")
        .annotate(next_at=Min("sessions__starts_at", filter=Q(sessions__starts_at__gte=now,
                                                               sessions__status=LiveSession.Status.SCHEDULED)))
        .order_by("cohort__start_date", "name")[:200]
    )  # fmt: skip
    counts = delivery.learner_counts(group_ids=[g.id for g in groups])
    return [
        {"id": g.id, "name": g.name, "cohort_id": g.cohort_id, "cohort_name": g.cohort.name,
         "program_title": g.cohort.program.title, "weekday": g.weekday,
         "starts_at": g.starts_at,
         "ends_at": g.ends_at,
         "learner_count": counts.get(g.id, 0), "next_session_at": g.next_at}
        for g in groups
    ]  # fmt: skip
