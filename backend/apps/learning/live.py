"""Live attendance and workshop bookings (M20, plan D14, D24): learner rows that feed the
off-the-job ledger and CPD.

Present = minutes >= setting learning.live_present_min. A present learner gets ONE
automatic OTJ entry per session or workshop (unique source + ref), updated if staff
re-mark them and removed if they are marked absent. Manual marks always beat the Teams
report: a later sync never overwrites a row staff marked.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.delivery.models import LiveSession, MeetingFields, Workshop
from core.errors import ServiceError

from .models import Enrollment, OtjEntry, SessionAttendance, WorkshopBooking, holds_place

PLACED = (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED)


def present_min() -> int:
    from apps.platform.services import get_setting

    return int(get_setting("learning.live_present_min"))


def join_early_min() -> int:
    from apps.platform.services import get_setting

    return int(get_setting("learning.live_join_early_min"))


def ends_at(obj: MeetingFields):
    return obj.starts_at + timedelta(minutes=obj.duration_min)


def join_url(obj: MeetingFields, now=None) -> str | None:
    """The attendee link, only from N minutes before the start until the end."""
    now = now or timezone.now()
    if not obj.join_url or obj.status != MeetingFields.Status.SCHEDULED:
        return None
    if obj.starts_at - timedelta(minutes=join_early_min()) <= now <= ends_at(obj):
        return obj.join_url
    return None


def _otj(enrollment: Enrollment, *, source: str, ref, minutes: int, day, note: str) -> None:
    """Upsert (present) or remove (absent) the automatic ledger entry for one event."""
    qs = OtjEntry.objects.filter(enrollment=enrollment, source=source, source_ref=str(ref))
    if minutes <= 0:
        qs.filter(status=OtjEntry.Status.AUTO_APPROVED).delete()
        return
    if qs.update(minutes=minutes, occurred_on=day, updated_at=timezone.now()):
        return
    OtjEntry.objects.create(
        enrollment=enrollment, org_id=enrollment.org_id, user_id=enrollment.user_id, source=source,
        source_ref=str(ref), minutes=minutes, occurred_on=day, status=OtjEntry.Status.AUTO_APPROVED,
        note=note[:1000],
    )  # fmt: skip


def _local_day(obj: MeetingFields):
    from apps.delivery.sessions import provider_tz

    return obj.starts_at.astimezone(provider_tz()).date()


# ---------------------------------------------------------------- group sessions
def session_members(session: LiveSession) -> list[Enrollment]:
    return list(
        Enrollment.objects.filter(holds_place(), group_id=session.group_id)
        .select_related("user")
        .order_by("user__full_name", "user__email")
    )


@transaction.atomic
def mark_session(*, session: LiveSession, marks: dict, by, source=SessionAttendance.Source.MANUAL,
                 joins: dict | None = None) -> int:  # fmt: skip
    """marks = {enrollment_id: minutes}. Only the group's placed learners; only once the
    session has started. Returns how many rows were written."""
    s = LiveSession.objects.select_for_update().get(pk=session.pk)
    if s.starts_at > timezone.now():
        raise ServiceError("not_started", "Attendance can be marked once the session has started.")
    if s.status != LiveSession.Status.SCHEDULED:
        raise ServiceError("cancelled", "This session was cancelled.")
    members = {
        e.id: e for e in Enrollment.objects.filter(holds_place(), group_id=s.group_id, id__in=list(marks))
    }
    rows = {
        a.enrollment_id: a
        for a in SessionAttendance.objects.filter(session=s, enrollment_id__in=list(members))
    }
    floor, day, written = present_min(), _local_day(s), 0
    for eid, minutes in marks.items():
        e = members.get(eid)
        if e is None:
            continue
        row = rows.get(eid)
        if (
            source == SessionAttendance.Source.GRAPH
            and row is not None
            and row.source == SessionAttendance.Source.MANUAL
        ):
            continue  # staff marks win over the Teams report
        minutes = max(0, min(int(minutes), s.duration_min))
        first, last = (joins or {}).get(eid, (None, None))
        SessionAttendance.objects.update_or_create(
            session=s, enrollment=e,
            defaults={"minutes": minutes, "source": source, "marked_by": by, "first_join": first, "last_leave": last,
                      "org_id": e.org_id, "user_id": e.user_id},
        )  # fmt: skip
        _otj(e, source=OtjEntry.Source.LIVE_SESSION, ref=s.id, minutes=minutes if minutes >= floor else 0,
             day=day, note=s.title)  # fmt: skip
        written += 1
    return written


def _need_report(report: dict) -> None:
    """An empty report usually means Teams hasn't written it yet: never mark everyone absent
    on it (the follow-up job tries again later)."""
    if not report:
        raise ServiceError(
            "no_report", "Teams has no attendance report for this meeting yet. Try again later."
        )


def _by_email(enrollments) -> dict:
    return {e.user.email.lower(): e for e in enrollments}


def sync_session_attendance(session: LiveSession) -> int:
    """Read the Teams attendance report and mark the group's learners by email."""
    from apps.catalog import teams

    if not session.teams_meeting_id:
        raise ServiceError("not_teams", "This session isn't a Teams meeting the app created.")
    report = teams.attendance(meeting_id=session.teams_meeting_id, owner=session.teams_organizer)
    _need_report(report)
    people = _by_email(session_members(session))
    marks, joins = {}, {}
    for email, e in people.items():
        row = report.get(email)
        marks[e.id] = round(row["seconds"] / 60) if row else 0
        if row:
            joins[e.id] = (row["first_join"], row["last_leave"])
    n = mark_session(
        session=session, marks=marks, by=None, source=SessionAttendance.Source.GRAPH, joins=joins
    )
    LiveSession.objects.filter(pk=session.pk).update(attendance_synced_at=timezone.now())
    return n


# ---------------------------------------------------------------- workshops
def booked_counts(workshop_ids) -> dict:
    """Places taken per workshop, counting everyone's bookings (a SECURITY DEFINER function:
    a learner's RLS only shows their own rows). One query."""
    ids = [str(i) for i in workshop_ids]
    if not ids:
        return {}
    with connection.cursor() as cur:
        cur.execute("SELECT workshop_id, booked FROM learning.workshop_booked_counts(%s::uuid[])", [ids])
        return dict(cur.fetchall())


def cancel_future_bookings(enrollment_id) -> int:
    """The learner lost their place (refund, seat released or swapped): their places at
    workshops that haven't started go back to others."""
    return WorkshopBooking.objects.filter(
        enrollment_id=enrollment_id,
        status=WorkshopBooking.Status.BOOKED,
        workshop__starts_at__gt=timezone.now(),
    ).update(status=WorkshopBooking.Status.CANCELLED, updated_at=timezone.now())


def can_attend(workshop: Workshop, enrollment: Enrollment) -> bool:
    return (
        enrollment.course_id == workshop.program_id
        and enrollment.status in PLACED
        and (enrollment.access_expires_at is None or enrollment.access_expires_at > timezone.now())
        and (workshop.cohort_id is None or workshop.cohort_id == enrollment.cohort_id)
    )


@transaction.atomic
def book(*, workshop: Workshop, enrollment: Enrollment) -> WorkshopBooking:
    """Take a place. A per-workshop advisory lock (learners may not lock the reference row
    itself under RLS) makes bookings queue, so two people can't take the last place."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('workshop:' || %s::text, 0))", [str(workshop.pk)]
        )
    w = Workshop.objects.get(pk=workshop.pk)
    if not can_attend(w, enrollment):
        raise ServiceError("not_found", "Workshop not found.", status=404)
    if w.status != Workshop.Status.SCHEDULED:
        raise ServiceError("cancelled", "This workshop was cancelled.")
    if w.starts_at <= timezone.now():
        raise ServiceError("started", "This workshop has already started.")
    row = WorkshopBooking.objects.filter(workshop=w, enrollment=enrollment).first()
    if row and row.status == WorkshopBooking.Status.BOOKED:
        return row
    if w.capacity is not None:
        taken = booked_counts([w.id]).get(w.id, 0)
        if taken >= w.capacity:
            raise ServiceError("full", "This workshop is full.", status=409)
    if row:
        row.status = WorkshopBooking.Status.BOOKED
        row.save(update_fields=["status", "updated_at"])
        return row
    return WorkshopBooking.objects.create(workshop=w, enrollment=enrollment, org_id=enrollment.org_id,
                                          user_id=enrollment.user_id)  # fmt: skip


@transaction.atomic
def cancel_booking(*, workshop: Workshop, enrollment: Enrollment) -> None:
    row = WorkshopBooking.objects.select_for_update().filter(workshop=workshop, enrollment=enrollment).first()
    if row is None or row.status != WorkshopBooking.Status.BOOKED:
        raise ServiceError("not_booked", "You haven't booked this workshop.")
    if workshop.starts_at <= timezone.now():
        raise ServiceError("started", "This workshop has already started.")
    row.status = WorkshopBooking.Status.CANCELLED
    row.save(update_fields=["status", "updated_at"])


def workshop_members(workshop: Workshop) -> list[WorkshopBooking]:
    return list(
        WorkshopBooking.objects.filter(workshop=workshop, status=WorkshopBooking.Status.BOOKED)
        .select_related("enrollment__user")
        .order_by("enrollment__user__full_name", "enrollment__user__email")
    )


@transaction.atomic
def mark_workshop(*, workshop: Workshop, marks: dict, by, source=SessionAttendance.Source.MANUAL) -> int:
    """marks = {enrollment_id: minutes or None}. None = present for the whole workshop (its
    expected OTJ minutes, or its length). Only booked learners."""
    w = Workshop.objects.select_for_update().get(pk=workshop.pk)
    if w.starts_at > timezone.now():
        raise ServiceError("not_started", "Attendance can be marked once the workshop has started.")
    if w.status != Workshop.Status.SCHEDULED:
        raise ServiceError("cancelled", "This workshop was cancelled.")
    rows = {
        b.enrollment_id: b
        for b in WorkshopBooking.objects.select_for_update()
        .filter(workshop=w, status=WorkshopBooking.Status.BOOKED, enrollment_id__in=list(marks))
        .select_related("enrollment")
    }
    floor, day, written = present_min(), _local_day(w), 0
    full = w.expected_otj_min or w.duration_min
    for eid, minutes in marks.items():
        b = rows.get(eid)
        if b is None:
            continue
        if source == SessionAttendance.Source.GRAPH and b.source == SessionAttendance.Source.MANUAL:
            continue
        attended = w.duration_min if minutes is None else max(0, min(int(minutes), w.duration_min))
        b.attended_min, b.source, b.marked_by = attended, source, by
        b.save(update_fields=["attended_min", "source", "marked_by", "updated_at"])
        # OTJ: the workshop's expected minutes when marked present outright, else what was attended
        otj = (full if minutes is None else attended) if attended >= floor else 0
        _otj(
            b.enrollment,
            source=OtjEntry.Source.WORKSHOP,
            ref=w.id,
            minutes=min(otj, 1440),
            day=day,
            note=w.title,
        )
        written += 1
    return written


def sync_workshop_attendance(workshop: Workshop) -> int:
    from apps.catalog import teams

    if not workshop.teams_meeting_id:
        raise ServiceError("not_teams", "This workshop isn't a Teams meeting the app created.")
    report = teams.attendance(meeting_id=workshop.teams_meeting_id, owner=workshop.teams_organizer)
    _need_report(report)
    marks = {}
    for b in workshop_members(workshop):
        row = report.get(b.enrollment.user.email.lower())
        marks[b.enrollment_id] = round(row["seconds"] / 60) if row else 0
    n = mark_workshop(workshop=workshop, marks=marks, by=None, source=SessionAttendance.Source.GRAPH)
    Workshop.objects.filter(pk=workshop.pk).update(attendance_synced_at=timezone.now())
    return n


def workshop_cpd_min(enrollment: Enrollment) -> int:
    """CPD from workshops the learner attended (D24)."""
    present = present_min()
    rows = WorkshopBooking.objects.filter(enrollment=enrollment, status=WorkshopBooking.Status.BOOKED,
                                          attended_min__gte=present).values_list("workshop__cpd_min", flat=True)  # fmt: skip
    return sum(rows)


# ---------------------------------------------------------------- learner views
def _recording(obj: MeetingFields) -> dict | None:
    from apps.catalog import media

    a = obj.recording
    if a is None or a.status not in ("playable", "ready"):
        return None
    return media.playback(a)


def _owned_session_keys(enrollment: Enrollment) -> set | None:
    """None = every session of the group; otherwise the live components of the modules this
    enrolment covers (a module seat or purchase never opens the other modules' sessions)."""
    from apps.catalog.models import Lecture

    from .models import EnrollmentModule

    if enrollment.scope == Enrollment.Scope.PROGRAM:
        return None
    modules = EnrollmentModule.objects.filter(enrollment=enrollment).values("module_key")
    return set(
        Lecture.objects.filter(
            version__course_id=enrollment.course_id, kind=Lecture.Kind.LIVE_SESSION,
            section__module__module_key__in=modules,
        ).values_list("lecture_key", flat=True)
    )  # fmt: skip


def my_sessions(enrollment: Enrollment) -> list[dict]:
    if enrollment.group_id is None:
        return []
    now = timezone.now()
    qs = LiveSession.objects.filter(group_id=enrollment.group_id)
    keys = _owned_session_keys(enrollment)
    if keys is not None:
        qs = qs.filter(lecture_key__in=keys)
    sessions = list(qs.select_related("recording__library").order_by("starts_at"))
    mine = dict(
        SessionAttendance.objects.filter(enrollment=enrollment, session__in=sessions).values_list(
            "session_id", "minutes"
        )
    )
    return [
        {"id": s.id, "lecture_key": s.lecture_key, "title": s.title, "starts_at": s.starts_at, "ends_at": ends_at(s),
         "status": s.status, "provider": s.provider, "join_url": join_url(s, now),
         "has_link": bool(s.join_url), "recording": _recording(s), "attended_min": mine.get(s.id)}
        for s in sessions
    ]  # fmt: skip


def my_workshops(enrollment: Enrollment, *, limit: int = 100) -> list[dict]:
    """The program's workshops for this learner (all cohorts, or theirs), newest last."""
    from django.db.models import Q

    now = timezone.now()
    qs = (
        Workshop.objects.filter(program_id=enrollment.course_id)
        .filter(Q(cohort__isnull=True) | Q(cohort_id=enrollment.cohort_id))
        .filter(starts_at__gte=now - timedelta(days=120))
        .select_related("recording__library")
        .order_by("starts_at")[:limit]
    )
    workshops = list(qs)
    taken = booked_counts([w.id for w in workshops])
    mine = {
        b.workshop_id: b
        for b in WorkshopBooking.objects.filter(enrollment=enrollment, workshop__in=workshops)
    }
    out = []
    for w in workshops:
        b = mine.get(w.id)
        booked = bool(b and b.status == WorkshopBooking.Status.BOOKED)
        out.append({
            "id": w.id, "title": w.title, "description": w.description, "starts_at": w.starts_at,
            "ends_at": ends_at(w), "status": w.status, "capacity": w.capacity,
            "spaces_left": None if w.capacity is None else max(w.capacity - taken.get(w.id, 0), 0),
            "booked": booked, "join_url": join_url(w, now) if booked else None,
            "recording": _recording(w) if booked else None,
            "attended_min": b.attended_min if booked else None,
            "expected_otj_min": w.expected_otj_min, "cpd_min": w.cpd_min,
        })  # fmt: skip
    return out
