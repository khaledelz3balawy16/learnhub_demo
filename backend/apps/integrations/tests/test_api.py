"""The HR system API (M17) end to end over HTTP: who may do what (learner 403, manager
read only, admins change things), the admin flow connect -> sync -> people -> match ->
invite -> accept -> matched, department units, the training map, the member link and
leave badges, the API key never leaving the server, and another company seeing nothing."""

import json
from unittest import mock

from django.test import override_settings

from apps.compliance.models import CompletionRecord, MemberStatus
from apps.identity.models import User
from apps.integrations.models import ExternalPerson, HrConnection
from apps.org import services as org_services
from apps.org.models import MemberUnit, OrgMember, OrgUnit
from apps.platform.models import AuditLog
from core.tenancy import tenant_context

from .test_fixtures import API_KEY
from .test_sync import HR_SETTINGS, HrBase

API = "/api/v1"
HR = f"{API}/integrations/hr"


class ApiBase(HrBase):
    def setUp(self):
        super().setUp()
        self.bodies: list[bytes] = []  # every response body, to prove the key never leaves

    def call(self, method, path, data=None, *, user=None, org=None):
        if user is not None:
            self.client.force_login(user)
        kw = {"content_type": "application/json"} if data is not None else {}
        r = getattr(self.client, method)(path, data=data, HTTP_X_ORG_ID=str(org or self.acme.id), **kw)
        self.bodies.append(r.content)
        return r

    def ok(self, method, path, data=None, **kw):
        r = self.call(method, path, data, **kw)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def code(self, r):
        return r.json()["error"]["code"]

    def people(self, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return {p["external_employee_id"]: p for p in self.ok("get", f"{HR}/people?{query}")["items"]}


class AccessTest(ApiBase):
    def test_a_learner_gets_403_everywhere(self):
        self.client.force_login(self.sara)
        for method, path, data in (
            ("get", HR, None),
            ("get", f"{HR}/people", None),
            ("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"}),
            ("post", f"{HR}/sync", None),
            ("get", f"{HR}/members/{self.m_sara.id}", None),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.call(method, path, data).status_code, 403)

    def test_a_manager_reads_but_cannot_change(self):
        with tenant_context(**self.ACME):
            team = org_services.create_unit(parent=self.root, kind="team", name="Floor")
            org_services.add_member_to_unit(member=self.m_sara, unit=team, primary=True)
            org_services.set_unit_managers(unit=team, members=[self.m_mia])
        self.client.force_login(self.hr)
        self.ok("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"})
        sara = self.people()["101"]
        omar = self.people()["102"]
        self.ok("post", f"{HR}/people/{sara['id']}/match", {"member_id": str(self.m_sara.id)})
        self.ok("post", f"{HR}/people/{omar['id']}/match", {"member_id": str(self.m_omar.id)})

        self.client.force_login(self.mia)
        out = self.ok("get", HR)
        self.assertFalse(out["can_manage"])
        self.assertEqual(out["connection"]["account_name"], "Acme Care Ltd")
        # only linked people inside her units, and no suggestions
        mine = self.people()
        self.assertEqual(list(mine), ["101"])
        self.assertIsNone(mine["101"]["suggestion"])
        self.assertTrue(self.ok("get", f"{HR}/members/{self.m_sara.id}")["linked"])
        self.assertFalse(self.ok("get", f"{HR}/members/{self.m_omar.id}")["linked"])  # not in her units
        self.ok("get", f"{HR}/runs")
        self.ok("get", f"{HR}/departments")
        self.ok("get", f"{HR}/training/titles")
        # training records: only for linked people inside her units (Sara's 501 and 503)
        records = self.ok("get", f"{HR}/training/records")
        self.assertEqual(sorted(r["title"] for r in records), ["Fire Safety Awareness", "Manual Handling"])
        self.assertEqual({r["person_name"] for r in records}, {"Sara Ahmed"})
        for method, path, data in (
            ("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"}),
            ("post", f"{HR}/sync", None),
            ("post", f"{HR}/validate", None),
            ("post", f"{HR}/replace-key", {"api_key": API_KEY}),
            ("patch", f"{HR}/features", {"features": []}),
            ("post", f"{HR}/pause", {"paused": True}),
            ("delete", HR, None),
            ("post", f"{HR}/people/{sara['id']}/ignore", None),
            ("post", f"{HR}/people/{sara['id']}/reset", None),
            ("put", f"{HR}/training/map", {"title": "Food Hygiene"}),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.call(method, path, data).status_code, 403)
        with tenant_context(**self.ACME):
            self.assertEqual(HrConnection.objects.get().status, "active")

    @override_settings(HR_INTEGRATION={**HR_SETTINGS, "CREDENTIAL_KEY": ""})
    def test_a_server_without_an_encryption_key_says_so(self):
        self.client.force_login(self.hr)
        self.assertFalse(self.ok("get", HR)["configured"])
        r = self.call("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"})
        self.assertEqual((r.status_code, self.code(r)), (503, "not_configured"))


class AdminFlowTest(ApiBase):
    def test_connect_sync_match_invite_accept_departments_training(self):
        self.client.force_login(self.hr)
        out = self.ok("get", HR)
        self.assertEqual((out["configured"], out["can_manage"], out["connection"]), (True, True, None))
        self.assertEqual(self.code(self.call("get", f"{HR}/people")), "not_connected")

        # connect: the account name comes from Breathe, and the first sync runs at once
        conn = self.ok("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"})
        self.assertEqual((conn["account_name"], conn["external_account_id"], conn["environment"], conn["status"]),
                         ("Acme Care Ltd", "4242", "sandbox", "active"))  # fmt: skip
        out = self.ok("get", HR)
        self.assertEqual(out["latest_run"]["status"], "completed")
        self.assertEqual(out["latest_run"]["trigger"], "connect")
        self.assertEqual((out["counts"]["people"], out["counts"]["to_review"], out["counts"]["leavers"],
                          out["counts"]["departments"], out["counts"]["on_leave"]), (4, 3, 1, 2, 1))  # fmt: skip
        self.assertEqual(self.ok("post", f"{HR}/validate")["status"], "active")

        # "Sync now" (another run), then the history
        run = self.ok("post", f"{HR}/sync")
        self.assertEqual(run["triggered_by"], "Hana HR")
        self.assertEqual(run["counts"]["people"], 0)  # queued when answered: typed zeros
        detail = self.ok("get", f"{HR}/runs/{run['id']}")
        self.assertEqual(detail["status"], "completed")
        self.assertEqual(
            detail["counts"],
            {"people": 4, "new_people": 0, "leavers": 1, "departments": 2, "training": 4, "applied": 0,
             "leave": 2, "to_review": 3},
        )  # fmt: skip
        self.assertEqual(len(self.ok("get", f"{HR}/runs")), 2)

        # people: Sara's email matches a member: a suggestion only
        people = self.people()
        self.assertEqual(len(people), 4)
        self.assertEqual(people["101"]["status"], "pending")
        self.assertEqual(people["101"]["suggestion"]["member_id"], str(self.m_sara.id))
        self.assertIsNone(people["103"]["suggestion"])
        self.assertTrue(people["104"]["is_leaver"])
        self.assertEqual(people["101"]["contracted_hours"], 37.5)
        self.assertEqual(list(self.people(status="leaver")), ["104"])
        self.assertEqual(list(self.people(q="nina")), ["103"])
        first = self.ok("get", f"{HR}/people?limit=2")
        self.assertEqual(len(first["items"]), 2)
        rest = self.ok("get", f"{HR}/people?limit=2&cursor={first['next_cursor']}")
        self.assertEqual(len(rest["items"]), 2)
        self.assertIsNone(rest["next_cursor"])

        # match the suggestion; the Person page link and the leave badge
        self.ok("post", f"{HR}/people/{people['101']['id']}/match", {"member_id": str(self.m_sara.id)})
        link = self.ok("get", f"{HR}/members/{self.m_sara.id}")
        self.assertEqual((link["linked"], link["provider"], link["external_employee_id"], link["department"]),
                         (True, "Breathe HR", "101", "Care"))  # fmt: skip
        self.assertTrue(link["leave"]["current"])
        self.assertFalse(self.ok("get", f"{HR}/members/{self.m_omar.id}")["linked"])
        leave = self.ok("get", f"{HR}/leave?member_ids={self.m_sara.id}&member_ids={self.m_omar.id}")
        self.assertEqual([lv["member_id"] for lv in leave], [str(self.m_sara.id)])
        self.assertEqual(leave[0]["leave_type"], "Holiday")
        self.assertEqual(self.ok("get", HR)["counts"]["on_leave"], 1)

        # department: create a unit; the matched person is placed in it
        depts = {d["external_department_id"]: d for d in self.ok("get", f"{HR}/departments")}
        self.assertEqual(
            (depts["12"]["name"], depts["12"]["people"], depts["12"]["status"]), ("Care", 2, "pending")
        )
        care = self.ok("put", f"{HR}/departments/{depts['12']['id']}/unit", {"create": True})
        self.assertEqual((care["status"], care["unit_name"]), ("linked", "Care"))
        with tenant_context(**self.ACME):
            unit = OrgUnit.objects.get(pk=care["unit_id"])
            self.assertEqual((unit.kind, unit.code), ("department", "12"))
            self.assertTrue(MemberUnit.objects.filter(member=self.m_sara, unit=unit).exists())

        # training: map a Breathe title to a requirement -> imported evidence -> compliant
        req = self.requirement(targets=[{"unit_id": unit.id}])
        titles = {t["title"]: t for t in self.ok("get", f"{HR}/training/titles")}
        self.assertEqual(titles["Fire Safety Awareness"]["records"], 2)
        self.assertIsNone(titles["Fire Safety Awareness"]["requirement_id"])
        body = {"title": "Fire Safety Awareness", "requirement_id": str(req.id)}
        self.assertEqual(
            self.ok("put", f"{HR}/training/map", body)["applied"], 1
        )  # Sara's; Nina is not here yet
        with tenant_context(**self.ACME):
            self.assertEqual(
                MemberStatus.objects.get(member=self.m_sara, requirement=req).status, "compliant"
            )
            self.assertEqual(
                CompletionRecord.objects.get(member=self.m_sara, requirement=req).source, "import"
            )

        # invite Nina (no account yet); she accepts and becomes linked, in her department,
        # and her Breathe training counts straight away
        tokens = []
        with mock.patch("apps.org.tasks.send_invite_task.delay", side_effect=lambda *a: tokens.append(a[3])):
            inv = self.ok("post", f"{HR}/people/{people['103']['id']}/invite", {"role": "learner"})
        self.assertEqual(inv["email"], 'contact+9e97169adf42@example.com')
        self.assertEqual(self.people()["103"]["status"], "invited")
        nina = User.objects.create_user('contact+9e97169adf42@example.com', "x", full_name="Nina Patel")
        self.client.force_login(nina)
        accepted = self.client.post(
            f"{API}/org/invitations/{tokens[0]}/accept", content_type="application/json"
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        with tenant_context(**self.ACME):
            m_nina = OrgMember.objects.get(user=nina)
            person = ExternalPerson.objects.get(external_employee_id="103")
            self.assertEqual((person.mapping_status, person.member_id), ("matched", m_nina.id))
            self.assertTrue(MemberUnit.objects.filter(member=m_nina, unit=unit).exists())
            self.assertEqual(MemberStatus.objects.get(member=m_nina, requirement=req).status, "compliant")
            self.assertEqual(CompletionRecord.objects.get(member=m_nina, requirement=req).source, "import")

        self.client.force_login(self.hr)
        titles = {t["title"]: t for t in self.ok("get", f"{HR}/training/titles")}
        fire = titles["Fire Safety Awareness"]
        self.assertEqual((fire["applied"], fire["requirement_name"]), (2, "Fire Safety"))
        records = {r["title"]: r for r in self.ok("get", f"{HR}/training/records")}
        self.assertTrue(records["Fire Safety Awareness"]["applied"])
        self.assertFalse(records["Manual Handling"]["applied"])

        # archived units cannot be used
        with tenant_context(**self.ACME):
            old = org_services.create_unit(parent=self.root, kind="team", name="Old team")
            org_services.archive_unit(unit=old)
        r = self.call("put", f"{HR}/departments/{depts['11']['id']}/unit", {"unit_id": str(old.id)})
        self.assertEqual(r.status_code, 404)
        r = self.call(
            "post", f"{HR}/people/{people['104']['id']}/invite", {"role": "learner", "unit_id": str(old.id)}
        )
        self.assertEqual(r.status_code, 404)

        # ignore / reset, features, pause, disconnect
        self.ok("post", f"{HR}/people/{people['102']['id']}/ignore")
        self.assertEqual(self.people()["102"]["status"], "ignored")
        self.ok("post", f"{HR}/people/{people['102']['id']}/reset")
        self.assertEqual(self.people()["102"]["status"], "pending")
        self.assertEqual(
            self.ok("patch", f"{HR}/features", {"features": ["leave", "bogus"]})["features"], ["leave"]
        )
        self.assertEqual(self.ok("post", f"{HR}/pause", {"paused": True})["status"], "paused")
        self.assertEqual(self.code(self.call("post", f"{HR}/sync")), "not_active")
        self.ok("post", f"{HR}/pause", {"paused": False})
        self.assertEqual(self.ok("post", f"{HR}/replace-key", {"api_key": API_KEY})["status"], "active")
        self.ok("delete", HR)
        self.assertEqual(self.ok("get", HR)["connection"]["status"], "disabled")

        # the key never left the server: not in any response, the audit trail or plain in the database
        for body in self.bodies:
            self.assertNotIn(API_KEY.encode(), body)
        with tenant_context(staff=True):
            audit = list(
                AuditLog.objects.filter(org_id=self.acme.id, action__startswith="hr.").values_list(
                    "data", flat=True
                )
            )
        self.assertGreaterEqual(len(audit), 5)
        self.assertNotIn(API_KEY, json.dumps(audit))

    def test_the_key_is_stored_encrypted(self):
        self.client.force_login(self.hr)
        out = self.ok("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"})
        self.assertNotIn("secret", json.dumps(out))
        with tenant_context(**self.ACME):
            stored = HrConnection.objects.get().secret_ciphertext
        self.assertTrue(stored)
        self.assertNotIn(API_KEY, stored)


class IsolationTest(ApiBase):
    def test_another_company_sees_nothing(self):
        self.client.force_login(self.hr)
        self.ok("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"})
        sara = self.people()["101"]
        self.ok("post", f"{HR}/people/{sara['id']}/match", {"member_id": str(self.m_sara.id)})
        depts = self.ok("get", f"{HR}/departments")
        run = self.ok("get", f"{HR}/runs")[0]

        self.client.force_login(self.bob)
        beta = self.beta.id
        out = self.ok("get", HR, org=beta)
        self.assertIsNone(out["connection"])
        self.assertEqual(self.code(self.call("get", f"{HR}/people", org=beta)), "not_connected")
        self.assertEqual(self.call("get", f"{HR}/runs/{run['id']}", org=beta).status_code, 404)
        self.assertEqual(self.call("post", f"{HR}/people/{sara['id']}/ignore", org=beta).status_code, 404)
        self.assertEqual(
            self.call(
                "put", f"{HR}/departments/{depts[0]['id']}/unit", {"create": True}, org=beta
            ).status_code,
            404,
        )
        self.assertFalse(self.ok("get", f"{HR}/members/{self.m_sara.id}", org=beta)["linked"])
        self.assertEqual(self.ok("get", f"{HR}/leave?member_ids={self.m_sara.id}", org=beta), [])
        # Bob cannot point the Acme header at himself either
        self.assertEqual(self.call("get", HR, org=self.acme.id).status_code, 403)
        # the same Breathe account cannot be connected twice
        r = self.call("post", f"{HR}/connect", {"api_key": API_KEY, "environment": "sandbox"}, org=beta)
        self.assertEqual((r.status_code, self.code(r)), (409, "account_in_use"))
        # and at the database level, RLS hides every Acme row from Beta
        with tenant_context(**self.BETA):
            self.assertFalse(HrConnection.objects.exists())
            self.assertFalse(ExternalPerson.objects.exists())
        with tenant_context(**self.ACME):
            self.assertEqual(ExternalPerson.objects.get(external_employee_id="101").mapping_status, "matched")
