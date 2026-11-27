"""Live sessions and workshops (M20, plan D3, D17, D18, D24): planning a group's sessions
from the cohort calendar, Teams meetings, and copying recordings to Bunny.

Attendance and bookings are learner rows: see apps.learning.live.

Nothing here needs Teams. Without a connected tenant, staff paste a link and upload the
recording themselves; with one, meetings are created and kept in step after commit by a
Celery job, and recordings are copied by the beat job `delivery.pull_recordings`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.catalog import teams
from apps.catalog.models import Lecture
from core import html
from core.errors import ServiceError

from . import selectors
from .models import Group, LiveSession, MeetingFields, Workshop

log = logging.getLogger(__name__)
MAX_RECORDING_ATTEMPTS = 5


def provider_tz() -> ZoneInfo:
    from apps.platform.services import get_setting

    try:
        return ZoneInfo(str(get_setting("general.time_zone") or "UTC"))
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def _setting(key: str) -> int:
    from apps.platform.services import get_setting

    return int(get_setting(key))


# ---------------------------------------------------------------- planning
@dataclass
class PlanResult:
    created: int = 0
    moved: int = 0
    cancelled: int = 0
    skipped: list[str] = field(default_factory=list)  # component titles with no teaching day


def session_day(week, weekday: int) -> date | None:
    """The group's weekday inside a dated week; if that day is off, the next working day in
    the same week; None when there is none. A group that meets at the weekend keeps its own
    day (the calendar's weeks run Monday to Friday, so the weekend after them is used)."""
    off = {d.date for d in week.days_off}
    monday = week.starts_on - timedelta(days=week.starts_on.weekday())
    own = monday + timedelta(days=weekday)
    if weekday >= 5:
        return own if own not in off else None
    day = max(own, week.starts_on)
    while day <= week.ends_on:
        if day.weekday() < 5 and day not in off:
            return day
        day += timedelta(days=1)
    return None


def _has_attendance(session_ids) -> set:
    from apps.learning.models import SessionAttendance

    return set(
        SessionAttendance.objects.filter(session_id__in=session_ids).values_list("session_id", flat=True)
    )


@transaction.atomic
def plan_sessions(*, group: Group, by, sync: bool = True) -> PlanResult:
    """One session per live component of the program's live version, dated from the cohort
    calendar and the group's timetable. Idempotent: re-planning moves future sessions with
    no attendance, cancels those whose component left the program, and never deletes or
    touches the past. `sync=False` leaves the Teams meetings to be made later (demo seed)."""
    group = Group.objects.select_for_update().select_related("cohort__program").get(pk=group.pk)
    if group.weekday is None or group.starts_at is None or group.ends_at is None:
        raise ServiceError("no_timetable", "Set the group's day and times first.")
    program = group.cohort.program
    if program.live_version_id is None:
        raise ServiceError("not_published", "Publish the program first.")
    weeks = {w.section_id: w for m in selectors.fresh_schedule(group.cohort).modules for w in m.weeks}
    live = list(
        Lecture.objects.filter(version_id=program.live_version_id, kind=Lecture.Kind.LIVE_SESSION)
        .order_by("section__position", "position")
        .values_list("lecture_key", "title", "section_id")
    )
    tz = provider_tz()
    now = timezone.now()
    length = int(
        (
            datetime.combine(date.min, group.ends_at) - datetime.combine(date.min, group.starts_at)
        ).total_seconds()
        // 60
    )
    if not 5 <= length <= 720:
        raise ServiceError("bad_length", "A group's sessions must last between 5 minutes and 12 hours.")
    existing = {s.lecture_key: s for s in LiveSession.objects.select_for_update().filter(group=group)}
    attended = _has_attendance([s.id for s in existing.values()])
    result = PlanResult()
    keep = set()
    for key, title, section_id in live:
        keep.add(key)
        week = weeks.get(section_id)
        day = session_day(week, group.weekday) if week else None
        if day is None:
            result.skipped.append(title)
            continue
        starts = datetime.combine(day, group.starts_at, tzinfo=tz).astimezone(ZoneInfo("UTC"))
        s = existing.get(key)
        if s is None:
            LiveSession.objects.create(group=group, lecture_key=key, title=title[:200], starts_at=starts,
                                       duration_min=length, created_by=by)  # fmt: skip
            result.created += 1
            continue
        # past, attended or cancelled by a manager: re-planning leaves it alone
        frozen = s.starts_at <= now or s.id in attended or s.status == LiveSession.Status.CANCELLED
        if frozen:
            continue
        changes = {}
        if (s.starts_at, s.duration_min) != (starts, length):
            changes.update(starts_at=starts, duration_min=length, meeting_synced_at=None)
            result.moved += 1
        if s.title != title[:200]:
            changes.update(title=title[:200], meeting_synced_at=None)
        if changes:
            LiveSession.objects.filter(pk=s.pk).update(**changes, updated_at=now)
    for key, s in existing.items():
        if key not in keep and s.starts_at > now and s.status == LiveSession.Status.SCHEDULED:
            LiveSession.objects.filter(pk=s.pk).update(status=LiveSession.Status.CANCELLED, updated_at=now)
            result.cancelled += 1
    if sync:
        _after_commit_sync("session", group_id=group.id)
    return result


def _after_commit_sync(kind: str, *, group_id=None, workshop_id=None) -> None:
    """Teams connected: create or move the meetings in the background, after commit."""
    if not teams.connected():
        return
    from .tasks import sync_meetings

    transaction.on_commit(lambda: sync_meetings.delay(kind, str(group_id or workshop_id)), robust=True)


def _clean_url(url: str) -> str:
    url = (url or "").strip()
    if url and not url.lower().startswith("https://"):
        raise ServiceError("bad_link", "Use a full https:// meeting link.")
    return url[:1000]


def _check_times(starts_at: datetime | None, duration_min: int | None) -> None:
    if duration_min is not None and not 5 <= duration_min <= 720:
        raise ServiceError("bad_length", "A session lasts between 5 minutes and 12 hours.")
    if starts_at is not None and timezone.is_naive(starts_at):
        raise ServiceError("bad_time", "Send the time with its time zone.")


@transaction.atomic
def update_session(*, session: LiveSession, by, **changes) -> LiveSession:
    """Move one session, change its link or cancel it. Sessions with attendance keep their time."""
    s = LiveSession.objects.select_for_update().get(pk=session.pk)
    _check_times(changes.get("starts_at"), changes.get("duration_min"))
    fields = {}
    if "join_url" in changes:
        fields["join_url"] = _clean_url(changes["join_url"])
        if not fields["join_url"] and s.provider == LiveSession.Provider.TEAMS and s.teams_meeting_id:
            raise ServiceError(
                "teams_link", "This is the Teams meeting's link. Paste another link to replace it."
            )
        if (
            fields["join_url"]
            and s.provider == LiveSession.Provider.TEAMS
            and fields["join_url"] != s.join_url
        ):
            fields.update(provider=LiveSession.Provider.MANUAL, teams_meeting_id="", teams_organizer="")
    moving = any(changes.get(k) is not None for k in ("starts_at", "duration_min"))
    if moving and _has_attendance([s.id]):
        raise ServiceError("has_attendance", "This session already has attendance, so its time can't change.")
    for k in ("starts_at", "duration_min"):
        if changes.get(k) is not None:
            fields[k] = changes[k]
    if changes.get("status") in (LiveSession.Status.SCHEDULED, LiveSession.Status.CANCELLED):
        fields["status"] = changes["status"]
    if not fields:
        return s
    if moving or "status" in fields:
        fields["meeting_synced_at"] = None
    for k, v in fields.items():
        setattr(s, k, v)
    s.save(update_fields=[*fields, "updated_at"])
    if moving and s.provider == LiveSession.Provider.TEAMS:
        _after_commit_sync("session", group_id=s.group_id)
    return s


# ---------------------------------------------------------------- workshops
WORKSHOP_FIELDS = ("title", "description", "starts_at", "duration_min", "capacity", "expected_otj_min",
                   "cpd_min", "join_url", "cohort_id", "status")  # fmt: skip


def _workshop_fields(changes: dict) -> dict:
    out = {k: v for k, v in changes.items() if k in WORKSHOP_FIELDS}
    if "title" in out:
        out["title"] = html.plain(out["title"], 200).strip()
        if len(out["title"]) < 3:
            raise ServiceError("bad_title", "Give the workshop a title.")
    if "description" in out:
        out["description"] = html.plain(out["description"] or "", 4000)
    if "join_url" in out:
        out["join_url"] = _clean_url(out["join_url"])
    if out.get("expected_otj_min") is not None and out["expected_otj_min"] > 1440:
        raise ServiceError("bad_otj", "Off-the-job minutes go up to 1440 (24 hours).")
    _check_times(out.get("starts_at"), out.get("duration_min"))
    return out


@transaction.atomic
def create_workshop(*, program, by, **changes) -> Workshop:
    fields = _workshop_fields(changes)
    for need in ("title", "starts_at", "duration_min"):
        if fields.get(need) in (None, ""):
            raise ServiceError("missing_field", "Give the workshop a title, a start and a length.")
    if fields["starts_at"] <= timezone.now():
        raise ServiceError("in_past", "Pick a time in the future.")
    _check_cohort(program, fields.get("cohort_id"))
    w = Workshop.objects.create(program=program, created_by=by, **fields)
    _after_commit_sync("workshop", workshop_id=w.id)
    return w


def _check_cohort(program, cohort_id) -> None:
    from .models import Cohort

    if cohort_id and not Cohort.objects.filter(pk=cohort_id, program=program).exists():
        raise ServiceError("bad_cohort", "That cohort isn't part of this program.")


@transaction.atomic
def update_workshop(*, workshop: Workshop, **changes) -> Workshop:
    from django.db import connection

    with connection.cursor() as cur:  # the same lock bookings take (apps.learning.live.book)
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('workshop:' || %s::text, 0))", [str(workshop.pk)]
        )
    w = Workshop.objects.select_for_update().get(pk=workshop.pk)
    fields = _workshop_fields(changes)
    if "cohort_id" in fields:
        _check_cohort(w.program, fields["cohort_id"])
    if "capacity" in fields and fields["capacity"] is not None:
        from apps.learning.models import WorkshopBooking

        booked = WorkshopBooking.objects.filter(workshop=w, status=WorkshopBooking.Status.BOOKED).count()
        if fields["capacity"] < booked:
            raise ServiceError("capacity_low", f"{booked} people have booked already.")
    moving = any(k in fields and fields[k] is not None for k in ("starts_at", "duration_min", "title"))
    if "join_url" in fields and fields["join_url"] and fields["join_url"] != w.join_url:
        fields.update(provider=Workshop.Provider.MANUAL, teams_meeting_id="", teams_organizer="")
    if moving or "status" in fields:
        fields["meeting_synced_at"] = None
    for k, v in fields.items():
        setattr(w, k, v)
    if fields:
        w.save(update_fields=[*fields, "updated_at"])
    if (moving and w.provider == Workshop.Provider.TEAMS) or not w.join_url:
        _after_commit_sync("workshop", workshop_id=w.id)
    return w


# ---------------------------------------------------------------- Teams meetings
def ensure_meeting(obj: MeetingFields) -> bool:
    """Create the Teams meeting (no link yet) or move it (times changed). Returns True when
    Graph was called. Manual links are never replaced."""
    model = type(obj)
    with transaction.atomic():
        obj = model.objects.select_for_update().get(pk=obj.pk)  # the button and the job never both create one
        return _ensure_meeting(obj)


def _ensure_meeting(obj: MeetingFields) -> bool:
    if obj.status != MeetingFields.Status.SCHEDULED or obj.starts_at <= timezone.now():
        return False
    if obj.provider == MeetingFields.Provider.MANUAL and obj.join_url:
        return False
    ends = obj.starts_at + timedelta(minutes=obj.duration_min)
    model = type(obj)
    if obj.teams_meeting_id:
        if obj.meeting_synced_at:
            return False
        teams.update_online_meeting(meeting_id=obj.teams_meeting_id, owner=obj.teams_organizer,
                                    subject=obj.title, starts=obj.starts_at, ends=ends)  # fmt: skip
        model.objects.filter(pk=obj.pk).update(meeting_synced_at=timezone.now())
        return True
    from apps.platform.services import get_setting

    record = bool(get_setting("learning.teams_record_automatically"))  # client question: recording by default
    meeting = teams.create_online_meeting(subject=obj.title, starts=obj.starts_at, ends=ends, record=record)
    # a manual link pasted meanwhile wins: only fill an empty one
    model.objects.filter(pk=obj.pk, join_url="").update(
        provider=MeetingFields.Provider.TEAMS, join_url=meeting["join_url"], teams_meeting_id=meeting["meeting_id"],
        teams_organizer=meeting["organizer"], meeting_synced_at=timezone.now(), updated_at=timezone.now(),
    )  # fmt: skip
    return True


def sync_group_meetings(group_id) -> int:
    n = 0
    for s in LiveSession.objects.filter(group_id=group_id, status=LiveSession.Status.SCHEDULED,
                                        starts_at__gt=timezone.now()):  # fmt: skip
        n += ensure_meeting(s)
    return n


# ---------------------------------------------------------------- recordings
def _library():
    from apps.catalog.models import VideoLibrary

    return VideoLibrary.objects.filter(is_default=True).first()


def _owner_org(obj) -> object:
    program = obj.program if isinstance(obj, Workshop) else obj.group.cohort.program
    return program.owner_org_id


def start_recording_upload(*, obj: MeetingFields, by, filename: str, size_bytes: int) -> dict:
    """Manual fallback: staff upload the recording straight to Bunny (TUS), like a lesson video."""
    from apps.catalog import bunny
    from apps.catalog import services as catalog_services

    if obj.status != MeetingFields.Status.SCHEDULED or obj.starts_at > timezone.now():
        raise ServiceError("not_started", "A recording can be added once the event has started.")
    library = _library()
    if library is None:
        raise ServiceError("video_unavailable", "Video uploads are not configured.", status=503)
    guid = bunny.create_video(library, f"Recording: {obj.title}")
    asset = catalog_services.create_media(
        kind="video", status="awaiting_upload", library=library, uploaded_by=by, owner_org_id=_owner_org(obj),
        bunny_video_guid=guid, original_filename=html.plain(filename, 255), size_bytes=size_bytes,
    )  # fmt: skip
    type(obj).objects.filter(pk=obj.pk).update(recording=asset, recording_status=MeetingFields.Recording.READY,
                                               updated_at=timezone.now())  # fmt: skip
    return {"asset_id": asset.id, "upload": bunny.upload_session(library, guid)}


def pull_recording(obj: MeetingFields) -> str:
    """Copy a Teams recording (and transcript) to Bunny. Idempotent: does nothing once a
    recording is attached; gives up after MAX_RECORDING_ATTEMPTS. Returns the new status."""
    from apps.catalog import bunny
    from apps.catalog import services as catalog_services

    model = type(obj)
    if obj.recording_id or not obj.teams_meeting_id:
        return obj.recording_status
    # claim it: only one worker copies a recording, even when a long copy outlasts the beat
    claimed = model.objects.filter(pk=obj.pk, recording__isnull=True, recording_attempts=obj.recording_attempts).update(
        recording_attempts=F("recording_attempts") + 1, recording_status=MeetingFields.Recording.PENDING,
        updated_at=timezone.now(),
    )  # fmt: skip
    if not claimed:
        return MeetingFields.Recording.PENDING
    try:
        found = teams.recordings(meeting_id=obj.teams_meeting_id, owner=obj.teams_organizer)
        if not found:
            raise ServiceError("no_recording", "Teams has no recording yet.")
        library = _library()
        if library is None:
            raise ServiceError("video_unavailable", "Video uploads are not configured.", status=503)
        owner = obj.created_by
        if owner is None:
            raise ServiceError("no_owner", "Nobody owns this event's recording.")
        guid = bunny.create_video(library, f"Recording: {obj.title}")
        with teams.recording_stream(meeting_id=obj.teams_meeting_id, owner=obj.teams_organizer,
                                    recording_id=found[-1]["id"]) as resp:  # fmt: skip
            bunny.upload_stream(library, guid, resp.iter_bytes(1024 * 1024))
        asset = catalog_services.create_media(kind="video", status="processing", library=library, uploaded_by=owner,
                                              owner_org_id=_owner_org(obj), bunny_video_guid=guid,
                                              original_filename=f"{obj.title[:200]}.mp4")  # fmt: skip
        try:
            text = teams.transcript(meeting_id=obj.teams_meeting_id, owner=obj.teams_organizer)
        except ServiceError:
            text = ""  # a missing transcript never blocks the recording
        model.objects.filter(pk=obj.pk).update(recording=asset, recording_status=MeetingFields.Recording.READY,
                                               transcript=text, updated_at=timezone.now())  # fmt: skip
        return MeetingFields.Recording.READY
    except Exception as e:  # noqa: BLE001 - one event's failure never stops the job
        failed = obj.recording_attempts + 1 >= MAX_RECORDING_ATTEMPTS
        status = MeetingFields.Recording.FAILED if failed else MeetingFields.Recording.PENDING
        model.objects.filter(pk=obj.pk).update(recording_status=status, updated_at=timezone.now())
        log.info(
            "recording not copied for %s %s: %s", model.__name__, obj.pk, getattr(e, "code", type(e).__name__)
        )
        return status


def recordings_due(now: datetime | None = None) -> list[MeetingFields]:
    """Teams events that ended long enough ago and still have no recording."""
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=_setting("learning.recording_pull_after_min"))
    out: list[MeetingFields] = []
    for model in (LiveSession, Workshop):
        qs = model.objects.filter(
            provider=MeetingFields.Provider.TEAMS, status=MeetingFields.Status.SCHEDULED, recording__isnull=True,
            recording_status__in=(MeetingFields.Recording.NONE, MeetingFields.Recording.PENDING),
            starts_at__lte=cutoff, starts_at__gte=now - timedelta(days=14),
        ).filter(
            Q(recording_attempts=0) | Q(updated_at__lte=now - timedelta(hours=2))  # a copy in progress keeps its claim
        ).select_related("created_by", "group__cohort__program" if model is LiveSession else "program").order_by("starts_at")  # fmt: skip
        out += [o for o in qs[:50] if o.starts_at + timedelta(minutes=o.duration_min) <= cutoff]
    return out


def attendance_due(now: datetime | None = None) -> list[MeetingFields]:
    """Teams events that ended and whose attendance hasn't been read yet."""
    now = now or timezone.now()
    out: list[MeetingFields] = []
    for model in (LiveSession, Workshop):
        qs = model.objects.filter(provider=MeetingFields.Provider.TEAMS, status=MeetingFields.Status.SCHEDULED,
                                  attendance_synced_at__isnull=True, starts_at__lte=now,
                                  starts_at__gte=now - timedelta(days=2)).order_by("starts_at")  # fmt: skip
        # Teams writes the report within minutes; after two days staff mark attendance by hand
        out += [o for o in qs[:50] if o.starts_at + timedelta(minutes=o.duration_min + 15) <= now]
    return out
