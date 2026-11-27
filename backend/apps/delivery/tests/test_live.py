"""M20 live teaching: planning a group's sessions, the join window, attendance feeding the
OTJ ledger (manual and from a fake Microsoft Graph), workshop booking capacity and CPD."""

from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import httpx
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.catalog import teams
from apps.catalog.models import Section
from apps.delivery import calendar
from apps.delivery.models import LiveSession, Workshop
from apps.delivery.sessions import session_day
from apps.identity.models import StaffRole, StaffRoleAssignment, User
from apps.learning.models import Enrollment, OtjEntry
from core.tenancy import tenant_context

from .test_programs import ProgramBase

GRAPH = {"GRAPH_TENANT_ID": "tenant", "GRAPH_CLIENT_ID": "client", 'CHANGE_ME': 'CHANGE_ME',
         "TEAMS_MEETING_ORGANIZER": 'contact+c83fcc67ef4b@example.com'}  # fmt: skip


def fake_graph(request: httpx.Request) -> httpx.Response:
    """A stand-in for Microsoft Graph: token, meetings and one attendance report."""
    path = request.url.path
    if request.url.host == "login.microsoftonline.com":
        return httpx.Response(200, json={"access_token": 'CHANGE_ME', "expires_in": 3600})
    if request.method == "POST" and path.endswith("/onlineMeetings"):
        return httpx.Response(
            200, json={"id": "meet-1", "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/1"}
        )
    if path.endswith("/attendanceReports"):
        return httpx.Response(200, json={"value": [{"id": "r1"}]})
    if path.endswith("/attendanceReports/r1"):
        return httpx.Response(200, json={"attendanceRecords": [
            {"emailAddress": 'contact+a6b7d7235186@example.com', "totalAttendanceInSeconds": 3600,
             "attendanceIntervals": [{"joinDateTime": "2026-01-01T10:00:00Z", "leaveDateTime": "2026-01-01T11:00:00Z"}]},
            {"emailAddress": "", "totalAttendanceInSeconds": 999},  # a guest without an email: ignored
        ]})  # fmt: skip
    return httpx.Response(404)


def graph_client(timeout: float = 20) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake_graph))


class SessionDayTest(SimpleTestCase):
    def test_weekday_and_days_off(self):
        week = calendar.WeekPlan(section_id=None, number=1, title="w", starts_on=datetime(2027, 1, 4).date(),
                                 ends_on=datetime(2027, 1, 8).date())  # fmt: skip
        self.assertEqual(session_day(week, 2).isoformat(), "2027-01-06")  # Wednesday
        week.days_off = [calendar.DayOff(datetime(2027, 1, 6).date(), "Closed")]
        self.assertEqual(session_day(week, 2).isoformat(), "2027-01-07")  # the next working day
        week.days_off += [calendar.DayOff(datetime(2027, 1, 8).date(), "Closed")]
        self.assertIsNone(session_day(week, 4))  # Friday off and nothing after it
        self.assertEqual(session_day(week, 5).isoformat(), "2027-01-09")  # a Saturday group keeps its day


class LiveTest(ProgramBase):
    def setUp(self):
        super().setUp()
        cache.delete(teams.TOKEN_CACHE_KEY)
        pid, v, _ = self.build_program((2, 1))
        with tenant_context(staff=True):
            sections = list(Section.objects.filter(version_id=v).order_by("position"))
        for i, sec in enumerate((sections[0], sections[2]), start=1):
            self.ok(
                "post",
                f"/studio/sections/{sec.id}/lectures",
                {"kind": "live_session", "title": f"Live class {i}"},
            )
        self.publish(pid, v)
        self.pid = pid
        today = timezone.localdate()
        self.monday = today + timedelta(days=7 - today.weekday())  # next Monday
        cohort = self.ok("post", f"/console/programs/{pid}/cohorts",
                         {"name": "Spring", "start_date": self.monday.isoformat()})["id"]  # fmt: skip
        self.cohort = cohort
        self.group = self.ok("post", f"/console/program-cohorts/{cohort}/groups",
                             {"name": "G1", "tutor_id": str(self.tutor.id), "weekday": 2,
                              "starts_at": "18:00", "ends_at": "19:30"})["id"]  # fmt: skip
        self.ok("post", f"/console/program-groups/{self.group}/members",
                {"emails": ['contact+a6b7d7235186@example.com', 'contact+95190e115eae@example.com']})  # fmt: skip
        with tenant_context(staff=True):
            self.sara_e = Enrollment.objects.get(user=self.sara, course_id=pid).id
            self.omar_e = Enrollment.objects.get(user=self.omar, course_id=pid).id

    def _past(self, session_id, minutes_ago=120):
        with tenant_context(staff=True):
            LiveSession.objects.filter(pk=session_id).update(
                starts_at=timezone.now() - timedelta(minutes=minutes_ago)
            )

    def _otj(self, source):
        with tenant_context(staff=True):
            return list(
                OtjEntry.objects.filter(enrollment_id=self.sara_e, source=source).values_list(
                    "minutes", flat=True
                )
            )

    def test_plan_scope_attendance_and_otj(self):
        plan = self.ok("post", f"/console/program-groups/{self.group}/sessions/plan")
        self.assertEqual((plan["created"], plan["skipped"]), (2, []))
        again = self.ok("post", f"/console/program-groups/{self.group}/sessions/plan")
        self.assertEqual((again["created"], again["moved"], again["cancelled"]), (0, 0, 0))  # idempotent
        last = self.ok("get", f"/console/program-groups/{self.group}/sessions")["items"][1]["id"]
        self.ok("patch", f"/console/program-sessions/{last}", {"status": "cancelled"})
        self.ok("post", f"/console/program-groups/{self.group}/sessions/plan")
        self.assertEqual(
            self.ok("get", f"/console/program-groups/{self.group}/sessions")["items"][1]["status"],
            "cancelled",
        )
        self.ok(
            "patch", f"/console/program-sessions/{last}", {"status": "scheduled"}
        )  # only a person restores it

        listed = self.ok("get", f"/console/program-groups/{self.group}/sessions")["items"]
        first = listed[0]
        wednesday = self.monday + timedelta(days=2)
        local = datetime.fromisoformat(first["starts_at"]).astimezone(ZoneInfo("Europe/London"))
        self.assertEqual((local.date(), local.hour, first["duration_min"]), (wednesday, 18, 90))

        # a tutor runs their own group: links and attendance, never planning or moving
        self.as_(self.tutor)
        self.assertEqual(
            self.call("post", f"/console/program-groups/{self.group}/sessions/plan").status_code, 403
        )
        bad = self.call(
            "patch", f"/console/program-sessions/{first['id']}", {"join_url": "http://x.example.com"}
        )
        self.assertEqual(bad.json()["error"]["code"], "bad_link")
        self.ok(
            "patch", f"/console/program-sessions/{first['id']}", {"join_url": "https://meet.example.com/abc"}
        )
        move = self.call("patch", f"/console/program-sessions/{first['id']}", {"duration_min": 60})
        self.assertEqual(move.status_code, 403)
        early = self.call("put", f"/console/program-sessions/{first['id']}/attendance",
                          {"marks": [{"enrollment_id": str(self.sara_e), "minutes": 30}]})  # fmt: skip
        self.assertEqual(early.json()["error"]["code"], "not_started")

        other = User.objects.create_user('contact+4c94e0e0f413@example.com', "x", is_staff=True)
        with tenant_context(staff=True):
            StaffRoleAssignment.objects.create(user=other, role=StaffRole.objects.get(name="Tutor"))
        self.as_(other)  # a tutor of another group
        self.assertEqual(self.call("get", f"/console/program-groups/{self.group}/sessions").status_code, 403)

        # the join link shows only inside the window
        self.as_(self.sara)
        self.assertIsNone(
            self.ok("get", f"/learning/enrollments/{self.sara_e}/sessions")["items"][0]["join_url"]
        )
        self._past(first["id"], minutes_ago=-10)  # starts in 10 minutes
        mine = self.ok("get", f"/learning/enrollments/{self.sara_e}/sessions")
        self.assertEqual(
            (mine["group_name"], mine["items"][0]["join_url"]), ("G1", "https://meet.example.com/abc")
        )

        # manual attendance: present gives OTJ minutes (capped at the length), absent removes them
        self._past(first["id"])
        self.as_(self.tutor)
        marks = {
            "marks": [
                {"enrollment_id": str(self.sara_e), "minutes": 500},
                {"enrollment_id": str(self.omar_e), "minutes": 0},
            ]
        }
        self.assertEqual(
            self.ok("put", f"/console/program-sessions/{first['id']}/attendance", marks)["written"], 2
        )
        self.assertEqual(self._otj("live_session"), [90])
        self.ok("put", f"/console/program-sessions/{first['id']}/attendance",
                {"marks": [{"enrollment_id": str(self.sara_e), "minutes": 2}]})  # fmt: skip
        self.assertEqual(self._otj("live_session"), [])  # under the present threshold (3 min)
        att = self.ok("get", f"/console/program-sessions/{first['id']}/attendance")
        self.assertEqual({r["email"]: r["minutes"] for r in att["items"]},
                         {'contact+a6b7d7235186@example.com': 2, 'contact+95190e115eae@example.com': 0})  # fmt: skip

        # Teams: the second session gets a meeting, then its attendance report marks Sara by email
        second = listed[1]
        self.as_(self.staff)
        with override_settings(**GRAPH), mock.patch.object(teams, "_http", graph_client):
            self.ok("post", f"/console/program-sessions/{second['id']}/teams")
            row = self.ok("get", f"/console/program-groups/{self.group}/sessions")["items"][1]
            self.assertEqual((row["provider"], row["has_meeting"]), ("teams", True))
            self._past(second["id"])
            self.assertEqual(
                self.ok("post", f"/console/program-sessions/{second['id']}/attendance/sync")["written"], 2
            )
        self.assertEqual(self._otj("live_session"), [60])
        rec = self.ok("get", f"/console/program-enrollments/{self.sara_e}/record")
        self.assertEqual(rec["otj"]["counted_min"], 60)

    def test_workshops_capacity_booking_and_cpd(self):
        starts = (timezone.now() + timedelta(days=2)).isoformat()
        body = {"program_id": self.pid, "title": "CV clinic", "starts_at": starts, "duration_min": 60,
                "capacity": 1, "expected_otj_min": 120, "cpd_min": 45}  # fmt: skip
        self.as_(self.tutor)
        self.assertEqual(self.call("post", "/console/program-workshops", body).status_code, 403)
        self.as_(self.staff)
        wid = self.ok("post", "/console/program-workshops", body)["id"]

        self.as_(self.sara)
        self.ok("post", f"/learning/enrollments/{self.sara_e}/workshops/{wid}/booking")
        self.ok("post", f"/learning/enrollments/{self.sara_e}/workshops/{wid}/booking")  # twice is fine
        self.as_(self.omar)
        full = self.call("post", f"/learning/enrollments/{self.omar_e}/workshops/{wid}/booking")
        self.assertEqual((full.status_code, full.json()["error"]["code"]), (409, "full"))
        self.as_(self.sara)
        self.ok("delete", f"/learning/enrollments/{self.sara_e}/workshops/{wid}/booking")
        self.ok("post", f"/learning/enrollments/{self.sara_e}/workshops/{wid}/booking")
        listed = self.ok("get", f"/learning/enrollments/{self.sara_e}/workshops")["items"]
        self.assertEqual((listed[0]["booked"], listed[0]["spaces_left"]), (True, 0))
        # another learner's enrolment is never reachable
        self.assertEqual(self.call("get", f"/learning/enrollments/{self.omar_e}/workshops").status_code, 404)

        with tenant_context(staff=True):
            Workshop.objects.filter(pk=wid).update(starts_at=timezone.now() - timedelta(hours=2))
        late = self.call("delete", f"/learning/enrollments/{self.sara_e}/workshops/{wid}/booking")
        self.assertEqual(late.json()["error"]["code"], "started")

        self.as_(self.tutor)  # tutors read workshops; cohort managers run them (brief B6)
        marks = {"marks": [{"enrollment_id": str(self.sara_e)}]}
        self.assertEqual(
            self.call("put", f"/console/program-workshops/{wid}/attendance", marks).status_code, 403
        )
        self.as_(self.staff)
        self.ok("put", f"/console/program-workshops/{wid}/attendance",
                {"marks": [{"enrollment_id": str(self.sara_e)}, {"enrollment_id": str(self.omar_e)}]})  # fmt: skip
        self.assertEqual(self._otj("workshop"), [120])  # present outright: the workshop's expected minutes
        self.as_(self.sara)
        cpd = self.ok("get", f"/learning/enrollments/{self.sara_e}/record")["cpd"]
        self.assertEqual((cpd["workshops_min"], cpd["earned_min"]), (45, 45))
