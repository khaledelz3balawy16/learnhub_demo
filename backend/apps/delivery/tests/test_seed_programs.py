"""M23: the seed_programs command (insert-only, idempotent) on the test database."""

import json
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command

from apps.catalog.models import ComponentKsb, Course, KsbStandard, Lecture
from apps.commerce.models import ProgramOffer
from apps.delivery.management.commands.seed_programs import SEED_DIR, _load, intakes, total_weeks
from apps.delivery.models import Cohort, Group, LiveSession
from apps.engagement.models import Notification
from apps.identity.models import StaffRole, StaffRoleAssignment, User
from apps.learning.models import (
    Enrollment,
    LectureProgress,
    ModuleCertificate,
    OtjEntry,
    SessionAttendance,
)
from core.tenancy import tenant_context
from core.tests import factories as f
from core.tests.base import SchemaTransactionTestCase

SPEC = {
    "key": "TST",
    "slug": "test-professional-level-5",
    "title": "Test Professional (Level 5)",
    "subtitle": "A program for the seed test.",
    "level": "advanced",
    "standard": {
        "code": "ST9999", "version": "1.0", "title": "Test professional", "level": 5,
        "items": [{"code": "K1", "kind": "knowledge", "text": "Knows the plan."},
                  {"code": "S1", "kind": "skill", "text": "Builds the plan."}],
    },
    "otj": {"mode": "hours_per_week", "value": 6},
    "intake_months": list(range(1, 13)),  # a running cohort three to seven weeks old, whatever the date
    "modules": [
        {"title": "Planning", "weeks": 2},
        {"title": "Control", "weeks": [{"title": "Week 1", "components": [
            {"kind": "live_session", "title": "Control live", "otj_min": 120, "cpd_min": 120, "ksbs": ["K1", "S1"],
             "body": "<p>Plan the {module} review.</p>"},
            {"kind": "article", "title": "Control reading", "otj_min": 60, "body": "<p>Read this.</p>"},
        ]}]},
    ],
}  # fmt: skip


class SeedProgramsTest(SchemaTransactionTestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser('contact+dc5c389c3e09@example.com', "x", is_staff=True)
        f.money(self.staff)
        self.folder = tempfile.TemporaryDirectory()
        Path(self.folder.name, "tst.json").write_text(json.dumps(SPEC), encoding="utf-8")

    def tearDown(self):
        self.folder.cleanup()

    def seed(self) -> str:
        """Teams counts as connected: the seed must still never ask for a meeting."""
        out = StringIO()
        with (
            mock.patch("apps.delivery.sessions.teams.connected", return_value=True),
            mock.patch("apps.delivery.tasks.sync_meetings.delay") as meetings,
        ):
            call_command("seed_programs", "--dir", self.folder.name, "--offline", stdout=out)
        meetings.assert_not_called()
        return out.getvalue()

    def counts(self) -> dict:
        with tenant_context(staff=True):
            return {m.__name__: m.objects.count() for m in (Course, Cohort, Group, LiveSession, Enrollment,
                    SessionAttendance, OtjEntry, ProgramOffer, KsbStandard, User, LectureProgress,
                    ModuleCertificate, ComponentKsb, StaffRole, StaffRoleAssignment, Notification)}  # fmt: skip

    def test_seed_and_run_again(self):
        self.assertIn("TST: seeded", self.seed())
        with tenant_context(staff=True):
            self.assertEqual(Notification.objects.count(), 0)  # the demo people were told nothing
            # the demo tutor, never a real staff member, with a role that only teaches
            tutor = User.objects.get(email='contact+dfaf885b3a70@example.com')
            self.assertFalse(tutor.has_usable_password())
            roles = StaffRole.objects.filter(assignments__user=tutor)
            self.assertEqual([r.permissions for r in roles], [["groups.teach"]])
            self.assertEqual(set(Group.objects.values_list("tutor_id", flat=True)), {tutor.id})
        with tenant_context(staff=True):
            program = Course.objects.get(slug=SPEC["slug"])
            self.assertEqual((program.kind, program.status), ("program", "published"))
            live = program.live_version
            self.assertEqual(list(live.modules.order_by("position").values_list("title", flat=True)),
                             ["Planning", "Control"])  # fmt: skip
            self.assertEqual(live.sections.count(), 3)
            self.assertEqual(live.lectures.count(), 3 + 3 + 2)  # two standard weeks, one given week
            reflections = Lecture.objects.filter(version=live, kind="assignment").select_related("assignment")
            self.assertTrue(reflections and all(r.assignment.instructions for r in reflections))
            given_live = Lecture.objects.get(version=live, title="Control live")
            self.assertEqual(
                given_live.body, "<p>Plan the Control review.</p>"
            )  # a live session keeps its purpose
            # standard from the file, the mapped component and the settings
            std = KsbStandard.objects.get(code="ST9999")
            self.assertEqual(std.items.count(), 2)
            self.assertEqual(ComponentKsb.objects.filter(program=program).count(), 2)
            setting = program.delivery_setting
            self.assertEqual((setting.ksb_standard_id, setting.otj_target_mode), (std.id, "hours_per_week"))
            # offers: whole program live and recorded, each module recorded
            self.assertEqual(ProgramOffer.objects.filter(program=program).count(), 4)
            # two cohorts (running and planned), two groups each, a tutor and a timetable
            cohorts = list(Cohort.objects.filter(program=program).order_by("start_date"))
            self.assertEqual([c.status for c in cohorts], ["running", "planned"])
            groups = Group.objects.filter(cohort__program=program)
            self.assertEqual(groups.count(), 4)
            self.assertFalse(groups.filter(tutor__isnull=True).exists())
            # learners placed: 4 a group in the running cohort, 2 in the planned one
            placed = Enrollment.objects.filter(course=program, group__isnull=False)
            self.assertEqual(placed.filter(cohort=cohorts[0]).count(), 8)
            self.assertEqual(placed.filter(cohort=cohorts[1]).count(), 4)
            self.assertTrue(placed.filter(user__email__endswith="@learnhub.example.com").count() == 12)
            self.assertFalse(
                User.objects.get(email='contact+86a64f5c1342@example.com').has_usable_password()
            )
            # a session per live component per group; the running cohort's past is filled in
            self.assertEqual(LiveSession.objects.filter(group__cohort__program=program).count(), 4 * 3)
            self.assertTrue(SessionAttendance.objects.filter(enrollment__cohort=cohorts[0]).exists())
            self.assertTrue(LectureProgress.objects.filter(enrollment__cohort=cohorts[0]).exists())
            manual = OtjEntry.objects.filter(enrollment__cohort=cohorts[0], source="manual")
            self.assertEqual(manual.filter(status="approved").count(), 8)
            self.assertEqual(manual.filter(status="pending").count(), 8)
            self.assertFalse(OtjEntry.objects.filter(enrollment__cohort=cohorts[1]).exists())

        before = self.counts()
        self.assertIn("TST: already there, skipped.", self.seed())
        self.assertEqual(self.counts(), before)  # a second run creates nothing

    def test_running_cohort_has_weeks_left_every_day(self):
        """On any day of the year, for every real program: the running cohort is at least three
        weeks old, still has two weeks to teach, and the planned one starts later."""
        for spec in _load(SEED_DIR, None):
            weeks = total_weeks(spec)
            for n in range(366):
                today = date(2027, 1, 1) + timedelta(days=n)
                running, planned = intakes(spec.get("intake_months") or [2, 6, 10], today, weeks)
                self.assertTrue(running <= today - timedelta(days=21), (spec["key"], today))
                self.assertTrue(running + timedelta(weeks=weeks - 2) > today, (spec["key"], today))
                self.assertEqual(running.weekday(), 0)
                self.assertTrue(planned > today)

    def test_real_program_files_are_valid(self):
        specs = _load(SEED_DIR, None)
        self.assertEqual({s["key"] for s in specs} >= {"PCP", "MM", "ME"}, True)
        for s in specs:
            self.assertTrue(s["modules"] and all(m["title"] and m["weeks"] for m in s["modules"]), s["key"])
            for m in s["modules"]:
                for w in m["weeks"] if isinstance(m["weeks"], list) else []:
                    self.assertTrue(
                        w["components"], (s["key"], m["title"], w["title"])
                    )  # a week can't be empty
                    for c in w["components"]:  # the seed formats these: stray braces would crash it
                        for field in ("title", "body", "instructions"):
                            if c.get(field):
                                c[field].format(module="M", week=1)
