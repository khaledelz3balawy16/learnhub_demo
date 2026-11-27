"""M19 program records: KSB import and mapping, the off-the-job ledger, approvals, CPD and
module certificates."""

from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from apps.catalog import ksb_import
from apps.catalog.models import Lecture
from apps.identity.models import StaffRole, StaffRoleAssignment, User
from apps.learning import records
from apps.learning.models import Enrollment, ModuleCertificate, OtjEntry
from core.errors import ServiceError
from core.tenancy import tenant_context

from .test_programs import ProgramBase

STANDARD = {
    "code": "TST01",
    "title": "Test standard",
    "version": "1.0",
    "items": [
        {"code": "K1", "kind": "knowledge", "text": "Knows the basics"},
        {"code": "S1", "kind": "skill", "text": "Can apply them"},
    ],
}


class KsbParseTest(SimpleTestCase):
    def test_skills_england_shape(self):
        parsed = ksb_import.parse({
            "referenceNumber": "st0272", "title": "Team leader", "version": "1.2", "level": 3,
            "knowledges": [{"knowledgeId": 1, "detail": "<b>Know</b> things"}],
            "skills": [{"skillId": 4, "detail": "Do things"}],
            "behaviours": [{"behaviourId": 2, "detail": "Be kind"}],
        })  # fmt: skip
        self.assertEqual((parsed["code"], parsed["level"]), ("ST0272", 3))
        self.assertEqual(
            parsed["items"],
            [
                ("K1", "knowledge", "Know things"),
                ("S4", "skill", "Do things"),
                ("B2", "behaviour", "Be kind"),
            ],
        )

    def test_plain_shape_and_rubbish(self):
        self.assertEqual(len(ksb_import.parse(STANDARD)["items"]), 2)
        for bad in ({}, {"title": "x"}, {"code": "A", "title": "B", "items": []}, []):
            with self.assertRaises(ServiceError):
                ksb_import.parse(bad)


class RecordsTest(ProgramBase):
    def test_ksbs_hours_cpd_and_certificates(self):
        pid, v, _ = self.build_program((2, 1))
        with tenant_context(staff=True):
            lectures = list(Lecture.objects.filter(version_id=v).order_by("section__position", "position"))
        first, second = lectures[0], lectures[1]  # both in Module 1
        self.ok("patch", f"/studio/lectures/{first.id}", {"expected_otj_min": 90, "cpd_min": 60})
        self.ok("patch", f"/studio/lectures/{second.id}", {"cpd_min": 30})
        self.publish(pid, v)

        # a standard is uploaded twice (no duplicates), chosen for the program and mapped
        std = self.ok("post", "/console/ksb-imports/upload", {"standard": STANDARD})
        self.assertEqual(std["added"], 2)
        self.assertEqual(self.ok("post", "/console/ksb-imports/upload", {"standard": STANDARD})["added"], 0)
        detail = self.ok("get", f"/console/ksb-standards/{std['id']}")
        k1 = next(i["id"] for i in detail["items"] if i["code"] == "K1")
        self.assertEqual(
            self.call(
                "put", f"/console/programs/{pid}/ksb-map/{first.lecture_key}", {"item_ids": [k1]}
            ).json()["error"]["code"],
            "no_standard",
        )
        self.ok("put", f"/console/programs/{pid}/settings",
                {"ksb_standard_id": std["id"], "otj_target_mode": "hours_per_week", "otj_target_value": 1})  # fmt: skip
        self.ok("put", f"/console/programs/{pid}/ksb-map/{first.lecture_key}", {"item_ids": [k1]})
        mapped = self.ok("get", f"/console/programs/{pid}/ksb-map")
        self.assertEqual(
            next(c for c in mapped["components"] if c["lecture_key"] == str(first.lecture_key))["item_ids"],
            [k1],
        )

        # a cohort that started two weeks ago, a group with a tutor, Sara placed in it
        monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday() + 14)
        cohort = self.ok(
            "post", f"/console/programs/{pid}/cohorts", {"name": "Spring", "start_date": monday.isoformat()}
        )["id"]
        g = self.ok(
            "post",
            f"/console/program-cohorts/{cohort}/groups",
            {"name": "G1", "tutor_id": str(self.tutor.id)},
        )["id"]
        self.ok("post", f"/console/program-groups/{g}/members", {"emails": ['contact+a6b7d7235186@example.com']})

        self.as_(self.sara)
        with tenant_context(user_id=self.sara.id):
            eid = Enrollment.objects.get(user=self.sara, course_id=pid).id
        for _ in range(2):  # completing twice never counts twice
            self.ok("post", f"/learning/enrollments/{eid}/lectures/{first.lecture_key}/complete")
        rec = self.ok("get", f"/learning/enrollments/{eid}/record")
        self.assertEqual(rec["otj"]["counted_min"], 90)
        # placed today: nothing is owed for weeks before she joined, nor for the week under way
        self.assertEqual((rec["otj"]["expected_min"], rec["otj"]["rag"]), (0, "on_track"))
        with tenant_context(staff=True):
            Enrollment.objects.filter(pk=eid).update(enrolled_at=timezone.now() - timedelta(days=21))
        rec = self.ok("get", f"/learning/enrollments/{eid}/record")
        # joined at the start: 2 teaching weeks have ended x 60 min = 120 expected; 90 is under 80%
        self.assertEqual((rec["otj"]["expected_min"], rec["otj"]["rag"]), (120, "at_risk"))
        self.assertEqual({k["code"]: k["status"] for k in rec["ksbs"]}, {"K1": "met", "S1": "not_mapped"})
        self.assertEqual(rec["cpd"]["earned_min"], 60)
        self.assertEqual(rec["certificates"], [])

        # finishing Module 1 issues its certificate, once
        self.ok("post", f"/learning/enrollments/{eid}/lectures/{second.lecture_key}/complete")
        rec = self.ok("get", f"/learning/enrollments/{eid}/record")
        self.assertEqual([c["module_title"] for c in rec["certificates"]], ["Module 1"])
        self.assertEqual(rec["certificates"][0]["cpd_min"], 90)
        checked = self.ok("get", f"/learning/verify/{rec['certificates'][0]['verification_code']}")
        self.assertTrue(checked["course_title"].endswith(": Module 1"))  # employers can check it
        with tenant_context(user_id=self.sara.id):
            self.assertEqual(ModuleCertificate.objects.filter(enrollment_id=eid).count(), 1)
            self.assertEqual(OtjEntry.objects.filter(enrollment_id=eid).count(), 1)

        # learner logs: the daily cap and dates are enforced
        today = timezone.localdate().isoformat()
        logged = self.ok(
            "post",
            f"/learning/enrollments/{eid}/otj",
            {"occurred_on": today, "minutes": 300, "note": "Project work"},
        )
        over = self.call(
            "post",
            f"/learning/enrollments/{eid}/otj",
            {"occurred_on": today, "minutes": 200, "note": "More work"},
        )
        self.assertEqual(over.json()["error"]["code"], "daily_cap")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        future = self.call(
            "post",
            f"/learning/enrollments/{eid}/otj",
            {"occurred_on": tomorrow, "minutes": 30, "note": "Later"},
        )
        self.assertEqual(future.json()["error"]["code"], "future_date")
        with tenant_context(staff=True), self.assertRaises(ServiceError) as own:  # nobody approves their own
            records.decide(entry=OtjEntry.objects.get(pk=logged["id"]), approve=True, note="", by=self.sara)
        self.assertEqual(own.exception.code, "own_entry")

        # approvals: only the group's tutor (or a cohort manager) sees and decides it
        other = User.objects.create_user('contact+4c94e0e0f413@example.com', "x", is_staff=True)
        with tenant_context(staff=True):
            StaffRoleAssignment.objects.create(user=other, role=StaffRole.objects.get(name="Tutor"))
        self.as_(other)
        self.assertEqual(self.ok("get", "/console/otj-pending")["items"], [])
        self.assertEqual(
            self.call("post", f"/console/otj/{logged['id']}/decide", {"approve": True}).status_code, 404
        )
        self.as_(self.tutor)
        pending = self.ok("get", "/console/otj-pending")["items"]
        self.assertEqual([p["id"] for p in pending], [logged["id"]])
        reject = self.call("post", f"/console/otj/{logged['id']}/decide", {"approve": False})
        self.assertEqual(reject.json()["error"]["code"], "missing_reason")
        self.ok("post", f"/console/otj/{logged['id']}/decide", {"approve": True, "note": "Good"})
        staff_view = self.ok("get", f"/console/program-enrollments/{eid}/record")
        self.assertEqual(staff_view["otj"]["counted_min"], 390)

        self.as_(self.sara)
        ledger = self.ok("get", f"/learning/enrollments/{eid}/otj")["items"]
        self.assertEqual({e["status"] for e in ledger}, {"approved", "auto_approved"})
