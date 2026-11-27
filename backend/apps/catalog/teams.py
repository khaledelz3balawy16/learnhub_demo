"""Small, server-side Microsoft Teams client (Microsoft Graph, app-only).

It uses client credentials and only the configured organiser. Graph credentials and
meeting host URLs are never returned to the browser; learners receive only joinWebUrl
through the join gate. Each install connects its own Microsoft tenant (plan D19): the
values live in backend/.env, see docs/teams-setup.md.

Used by single live lectures (studio) and by program sessions and workshops (M20):
create and update meetings, read attendance reports, list recordings and stream their
content, and read transcripts.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.errors import ServiceError

TOKEN_CACHE_KEY = "teams:graph:token"  # noqa: S105 - cache key, not a credential


def connected() -> bool:
    """True when the app can create meetings (Graph app settings and an organiser)."""
    return bool(
        settings.GRAPH_TENANT_ID
        and settings.GRAPH_CLIENT_ID
        and settings.GRAPH_CLIENT_SECRET
        and settings.TEAMS_MEETING_ORGANIZER.strip()
    )


def organizer() -> str:
    value = settings.TEAMS_MEETING_ORGANIZER.strip()
    if not value:
        raise ServiceError(
            "teams_not_configured", "Set TEAMS_MEETING_ORGANIZER before creating a Teams session."
        )
    return value


def _http(timeout: float = 20) -> httpx.Client:
    """The one place an HTTP client is made (tests swap in a fake transport here)."""
    return httpx.Client(timeout=timeout)


def _token(client: httpx.Client) -> str:
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token
    if not all((settings.GRAPH_TENANT_ID, settings.GRAPH_CLIENT_ID, settings.GRAPH_CLIENT_SECRET)):
        raise ServiceError(
            "teams_not_configured", "Microsoft Teams is not configured yet. Add the Graph app settings."
        )
    response = client.post(
        f"https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}/oauth2/v2.0/token",
        data={
            "client_id": settings.GRAPH_CLIENT_ID,
            "client_secret": settings.GRAPH_CLIENT_SECRET,
            "scope": settings.GRAPH_SCOPE,
            "grant_type": "client_credentials",
        },
    )
    try:
        response.raise_for_status()
        payload = response.json()
        token = payload["access_token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ServiceError(
            "teams_auth_failed", "Could not authenticate with Microsoft Teams.", status=502
        ) from exc
    cache.set(TOKEN_CACHE_KEY, token, timeout=max(60, int(payload.get("expires_in", 3600)) - 300))
    return token


def _call(method: str, path: str, *, code: str, message: str, json: dict | None = None) -> dict:
    """One Graph request; any failure becomes ServiceError(code, message, 502)."""
    try:
        with _http() as client:
            token = _token(client)
            response = client.request(
                method,
                f"{settings.GRAPH_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
    except ServiceError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceError(code, message, status=502) from exc


def _iso(dt: datetime) -> str:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, UTC)
    return dt.astimezone(UTC).isoformat()


def _meeting_path(meeting_id: str, owner: str) -> str:
    return f"/users/{owner}/onlineMeetings/{meeting_id}"


# ---------------------------------------------------------------- meetings
def create_online_meeting(
    *, subject: str, starts: datetime, ends: datetime, record: bool = False
) -> dict[str, str]:
    owner = organizer()
    result = _call(
        "POST",
        f"/users/{owner}/onlineMeetings",
        code="teams_create_failed",
        message="Microsoft Teams could not create the meeting. Check Graph permissions and the organiser policy.",
        json={"subject": subject[:250], "startDateTime": _iso(starts), "endDateTime": _iso(ends),
              "recordAutomatically": record},
    )  # fmt: skip
    if not result.get("id") or not result.get("joinWebUrl"):
        raise ServiceError(
            "teams_create_failed", "Microsoft Teams returned an incomplete meeting.", status=502
        )
    return {"meeting_id": result["id"], "join_url": result["joinWebUrl"], "organizer": owner}


def update_online_meeting(
    *, meeting_id: str, owner: str, subject: str, starts: datetime, ends: datetime
) -> None:
    _call(
        "PATCH",
        _meeting_path(meeting_id, owner),
        code="teams_update_failed",
        message="Microsoft Teams could not move the meeting.",
        json={"subject": subject[:250], "startDateTime": _iso(starts), "endDateTime": _iso(ends)},
    )


def create_meeting(*, lecture) -> dict[str, str]:
    """A single live lecture (studio)."""
    starts = lecture.live_starts_at
    return create_online_meeting(
        subject=lecture.title, starts=starts, ends=starts + timedelta(minutes=lecture.live_duration_min)
    )


# ---------------------------------------------------------------- after the meeting
def _parse_dt(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def attendance(*, meeting_id: str, owner: str) -> dict[str, dict]:
    """Every attendee across the meeting's attendance reports, by lower-case email:
    {email: {"seconds", "first_join", "last_leave"}}. People without an email (guests
    who typed a name) can't be matched, so they are left out."""
    path = _meeting_path(meeting_id, owner)
    msg = "Microsoft Teams could not send the attendance report."
    reports = _call("GET", f"{path}/attendanceReports", code="teams_attendance_failed", message=msg)
    out: dict[str, dict] = {}
    for rep in reports.get("value", [])[:20]:
        detail = _call("GET", f"{path}/attendanceReports/{rep['id']}?$expand=attendanceRecords",
                       code="teams_attendance_failed", message=msg)  # fmt: skip
        for rec in detail.get("attendanceRecords", []):
            email = (rec.get("emailAddress") or "").strip().lower()
            if not email:
                continue
            row = out.setdefault(email, {"seconds": 0, "first_join": None, "last_leave": None})
            row["seconds"] += int(rec.get("totalAttendanceInSeconds") or 0)
            for iv in rec.get("attendanceIntervals") or []:
                joined, left = _parse_dt(iv.get("joinDateTime")), _parse_dt(iv.get("leaveDateTime"))
                if joined and (row["first_join"] is None or joined < row["first_join"]):
                    row["first_join"] = joined
                if left and (row["last_leave"] is None or left > row["last_leave"]):
                    row["last_leave"] = left
    return out


def recordings(*, meeting_id: str, owner: str) -> list[dict]:
    """The meeting's recordings, oldest first: [{"id", "created"}]."""
    data = _call("GET", f"{_meeting_path(meeting_id, owner)}/recordings", code="teams_recording_failed",
                 message="Microsoft Teams could not list the recordings.")  # fmt: skip
    rows = [
        {"id": r["id"], "created": r.get("createdDateTime") or ""}
        for r in data.get("value", [])
        if r.get("id")
    ]
    return sorted(rows, key=lambda r: r["created"])


@contextmanager
def recording_stream(*, meeting_id: str, owner: str, recording_id: str) -> Iterator[httpx.Response]:
    """The recording file as a streamed response (never loaded into memory)."""
    path = f"{_meeting_path(meeting_id, owner)}/recordings/{recording_id}/content"
    try:
        with _http(timeout=600) as client:
            token = _token(client)
            with client.stream("GET", f"{settings.GRAPH_BASE_URL}{path}",
                               headers={"Authorization": f"Bearer {token}"}, follow_redirects=True) as response:  # fmt: skip
                response.raise_for_status()
                yield response
    except ServiceError:
        raise
    except httpx.HTTPError as exc:
        raise ServiceError(
            "teams_recording_failed", "Microsoft Teams could not send the recording.", status=502
        ) from exc


def transcript(*, meeting_id: str, owner: str) -> str:
    """The first transcript as WebVTT text, or "" when there is none."""
    path = _meeting_path(meeting_id, owner)
    msg = "Microsoft Teams could not send the transcript."
    data = _call("GET", f"{path}/transcripts", code="teams_transcript_failed", message=msg)
    first = next((t for t in data.get("value", []) if t.get("id")), None)
    if first is None:
        return ""
    try:
        with _http() as client:
            token = _token(client)
            response = client.get(f"{settings.GRAPH_BASE_URL}{path}/transcripts/{first['id']}/content",
                                  params={"$format": "text/vtt"}, headers={"Authorization": f"Bearer {token}"})  # fmt: skip
            response.raise_for_status()
            return response.text[:500_000]
    except httpx.HTTPError as exc:
        raise ServiceError("teams_transcript_failed", msg, status=502) from exc
