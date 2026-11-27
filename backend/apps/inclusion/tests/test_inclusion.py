"""Inclusion test: learner draft and submit, scoring and flags, the admin-only console
(editor and results) and row security."""

import importlib

from django.apps import apps as django_apps
from django.db import connections

from apps.identity.models import StaffRole, StaffRoleAssignment, User
from apps.inclusion.models import Attempt, Question, Section
from core.staff_perms import PERMISSIONS
from core.tenancy import tenant_context
from core.tests import factories as f
from core.tests.base import SchemaTransactionTestCase

API = "/api/v1"
seed_migration = importlib.import_module("apps.inclusion.migrations.0002_seed_questions")


class InclusionBase(SchemaTransactionTestCase):
    def setUp(self):
        self.staff, self.teacher, self.sara, self.omar = f.users()
        self.tutor = User.objects.create_user('contact+f9997e4b3dd5@example.com', "x", is_staff=True, full_name="Tia")
        with tenant_context(staff=True):
            seed_migration.seed(django_apps, None)
            admin = StaffRole.objects.create(name="Admin", permissions=list(PERMISSIONS), is_system=True)
            teach = StaffRole.objects.create(name="Tutor", permissions=["groups.teach", "reports.view"])
            StaffRoleAssignment.objects.create(user=self.staff, role=admin)
            StaffRoleAssignment.objects.create(user=self.tutor, role=teach)

    def call(self, method, path, data=None):
        return getattr(self.client, method)(API + path, data=data, content_type="application/json")

    def ok(self, method, path, data=None):
        r = self.call(method, path, data)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def answer_all(self, me, value=0, overrides=None):
        answers = {q["id"]: value for s in me["sections"] for q in s["questions"]}
        answers.update(overrides or {})
        return answers


class LearnerTest(InclusionBase):
    def test_seeded_questionnaire(self):
        self.client.force_login(self.sara)
        me = self.ok("get", "/inclusion/me")
        self.assertEqual(len(me["sections"]), 6)
        self.assertEqual(sum(len(s["questions"]) for s in me["sections"]), 60)
        self.assertEqual(me["sections"][0]["title"], "Technology Anxiety and Digital Access")
        self.assertEqual([o["value"] for o in me["sections"][0]["questions"][0]["options"]], [0, 1, 2, 3])
        self.assertEqual((me["consented"], me["has_draft"], me["attempts"]), (False, False, 0))

    def test_draft_needs_consent_then_keeps_answers(self):
        self.client.force_login(self.sara)
        me = self.ok("get", "/inclusion/me")
        first = me["sections"][0]["questions"][0]["id"]
        r = self.call("put", "/inclusion/me/draft", {"answers": {first: 2}})
        self.assertEqual(r.json()["error"]["code"], "consent_needed")
        self.ok("put", "/inclusion/me/draft", {"answers": {first: 2}, "consent": True})
        self.ok("put", "/inclusion/me/draft", {"answers": {first: 3}})  # consent is remembered
        me = self.ok("get", "/inclusion/me")
        self.assertEqual((me["answers"], me["has_draft"], me["consented"]), ({first: 3}, True, True))
        bad = self.call("put", "/inclusion/me/draft", {"answers": {first: 7}})
        self.assertEqual(bad.json()["error"]["code"], "bad_answer")

    def test_submit_scores_flags_and_retake(self):
        self.client.force_login(self.sara)
        me = self.ok("get", "/inclusion/me")
        tech = [q["id"] for q in me["sections"][0]["questions"]]
        partial = {tech[0]: 1}
        r = self.call("post", "/inclusion/me/submit", {"answers": partial, "consent": True})
        self.assertEqual(r.json()["error"]["code"], "unanswered")
        # technology 2 x 10 = 20 (flagged at 15); everything else 0
        answers = self.answer_all(me, 0, {q: 2 for q in tech})
        self.ok("post", "/inclusion/me/submit", {"answers": answers, "consent": True})
        with tenant_context(staff=True):
            a = Attempt.objects.get(user=self.sara)
            self.assertTrue(a.is_latest)
            self.assertEqual((a.scores[0]["score"], a.scores[0]["max"], a.flag_count), (20, 30, 1))
            self.assertEqual(len(a.items), 60)
            self.assertEqual(a.items[0]["label"], "Often")
        # retake starts from the last answers; the new one becomes the latest
        me = self.ok("get", "/inclusion/me")
        self.assertEqual((me["attempts"], me["has_draft"], me["answers"][tech[0]]), (1, False, 2))
        retake = {"answers": self.answer_all(me, 1)}
        self.assertEqual(
            self.call("post", "/inclusion/me/submit", retake).status_code, 400
        )  # each attempt asks again
        self.ok("post", "/inclusion/me/submit", {**retake, "consent": True})
        with tenant_context(staff=True):
            rows = list(Attempt.objects.filter(user=self.sara).order_by("submitted_at"))
            self.assertEqual([r.is_latest for r in rows], [False, True])
            self.assertEqual(rows[1].flag_count, 0)  # 10 per section, under 15

    def test_a_learner_only_sees_their_own_attempts(self):
        """Row security: another learner's connection can't read Sara's answers."""
        self.client.force_login(self.sara)
        me = self.ok("get", "/inclusion/me")
        self.ok("post", "/inclusion/me/submit", {"answers": self.answer_all(me), "consent": True})
        with tenant_context(user_id=self.omar.id):
            self.assertEqual(Attempt.objects.count(), 0)
        with tenant_context(user_id=self.sara.id):
            self.assertEqual(Attempt.objects.count(), 1)
        with connections["default"].cursor() as cur:  # no RLS keys at all: nothing
            cur.execute("SELECT count(*) FROM inclusion.attempts")
            self.assertEqual(cur.fetchone()[0], 0)


class ConsoleTest(InclusionBase):
    def submit_as(self, user, overrides_value=None):
        self.client.force_login(user)
        me = self.ok("get", "/inclusion/me")
        tech = {q["id"]: overrides_value for q in me["sections"][0]["questions"]} if overrides_value else {}
        self.ok("post", "/inclusion/me/submit", {"answers": self.answer_all(me, 0, tech), "consent": True})

    def test_admins_only(self):
        for user in (self.tutor, self.sara):
            self.client.force_login(user)
            for path in ("/console/inclusion/questions", "/console/inclusion/results"):
                self.assertEqual(self.call("get", path).status_code, 403, (user.email, path))

    def test_results_flags_follow_the_threshold(self):
        self.submit_as(self.sara, overrides_value=2)  # tech 20
        self.submit_as(self.omar)  # all 0
        self.client.force_login(self.staff)
        res = self.ok("get", "/console/inclusion/results")
        self.assertEqual(res["summary"], {"learners": 2, "flagged": 1})
        flagged = self.ok("get", "/console/inclusion/results?flagged=true")["items"]
        self.assertEqual([r["email"] for r in flagged], ['contact+a6b7d7235186@example.com'])
        tech = flagged[0]["scores"][0]
        self.assertEqual((tech["score"], tech["threshold"], tech["flagged"]), (20, 15, True))
        by_section = self.ok("get", f"/console/inclusion/results?section={tech['section_id']}")["items"]
        self.assertEqual(len(by_section), 1)

        # raising the threshold above 20 clears the flag; clearing it turns flags off
        self.ok("patch", f"/console/inclusion/sections/{tech['section_id']}", {"flag_threshold": 25})
        self.assertEqual(self.ok("get", "/console/inclusion/results")["summary"]["flagged"], 0)
        self.ok("patch", f"/console/inclusion/sections/{tech['section_id']}", {"flag_threshold": 10})
        self.assertEqual(self.ok("get", "/console/inclusion/results")["summary"]["flagged"], 1)
        self.ok("patch", f"/console/inclusion/sections/{tech['section_id']}", {"flag_threshold": None})
        self.assertEqual(self.ok("get", "/console/inclusion/results")["summary"]["flagged"], 0)

        detail = self.ok("get", f"/console/inclusion/results/{flagged[0]['attempt_id']}")
        self.assertEqual(len(detail["groups"]), 6)
        self.assertEqual(len(detail["groups"][0]["answers"]), 10)
        self.assertEqual(detail["groups"][0]["answers"][0]["label"], "Often")
        self.assertEqual(len(detail["history"]), 1)
        with tenant_context(staff=True):
            from apps.platform.models import AuditLog

            self.assertTrue(AuditLog.objects.filter(action="inclusion.result_view").exists())

    def test_editor_changes_what_learners_see_but_not_past_answers(self):
        self.submit_as(self.sara, overrides_value=3)
        self.client.force_login(self.staff)
        ed = self.ok("get", "/console/inclusion/questions")
        self.assertEqual((len(ed["sections"]), ed["sections"][0]["max_score"]), (6, 30))
        tech = ed["sections"][0]
        q1 = tech["questions"][0]

        self.ok("patch", f"/console/inclusion/questions/{q1['id']}", {"text": "New wording?"})
        options = [{"label": "No", "value": 0}, {"label": "Yes", "value": 1}]
        self.ok("patch", f"/console/inclusion/questions/{q1['id']}", {"options": options})
        bad = self.call("patch", f"/console/inclusion/questions/{q1['id']}",
                        {"options": [{"label": "A", "value": 1}, {"label": "B", "value": 1}]})  # fmt: skip
        self.assertEqual(bad.json()["error"]["code"], "bad_options")
        new_q = self.ok(
            "post", f"/console/inclusion/sections/{tech['id']}/questions", {"text": "Extra question"}
        )["id"]
        new_s = self.ok(
            "post", "/console/inclusion/sections", {"title": "Caring duties", "flag_threshold": 3}
        )["id"]
        self.ok("post", f"/console/inclusion/sections/{new_s}/questions", {"text": "I care for someone."})
        self.ok(
            "patch", f"/console/inclusion/sections/{ed['sections'][5]['id']}", {"is_active": False}
        )  # hide mood
        ids = [s["id"] for s in ed["sections"]]
        self.ok("put", "/console/inclusion/sections-order", {"ids": [new_s, *ids]})
        self.ok("delete", f"/console/inclusion/questions/{tech['questions'][9]['id']}")

        self.client.force_login(self.omar)
        me = self.ok("get", "/inclusion/me")
        titles = [s["title"] for s in me["sections"]]
        self.assertEqual(titles[0], "Caring duties")
        self.assertNotIn("Mood, Motivation and Learning Capacity", titles)
        tech_q = me["sections"][1]["questions"]
        self.assertEqual((tech_q[0]["text"], len(tech_q[0]["options"])), ("New wording?", 2))
        self.assertEqual(tech_q[-1]["id"], new_q)
        self.assertEqual(len(tech_q), 10)  # 10 - 1 deleted + 1 added

        with tenant_context(staff=True):  # Sara's answers keep the wording she saw
            a = Attempt.objects.get(user=self.sara)
            self.assertEqual(
                a.items[0]["text"], "I worry that I will not be able to join online sessions successfully."
            )
            self.assertEqual(a.items[0]["label"], "Very often / Yes")
            self.assertEqual(Question.objects.filter(section_id=new_s).count(), 1)

    def test_deleting_a_section_clears_its_flag(self):
        self.submit_as(self.sara, overrides_value=2)
        self.client.force_login(self.staff)
        with tenant_context(staff=True):
            tech = Section.objects.get(key="technology_anxiety_digital_access")
        self.ok("delete", f"/console/inclusion/sections/{tech.id}")
        res = self.ok("get", "/console/inclusion/results")
        self.assertEqual(res["summary"]["flagged"], 0)
        detail = self.ok("get", f"/console/inclusion/results/{res['items'][0]['attempt_id']}")
        self.assertEqual(
            detail["groups"][0]["title"], "Technology Anxiety and Digital Access"
        )  # still readable
        self.assertIsNone(detail["groups"][0]["threshold"])


class CompanyAdminTest(InclusionBase):
    """A company's owners and admins read their current members' answers (user decision
    2026-11-25); managers, learners, other companies and removed members don't."""

    def setUp(self):
        super().setUp()
        from django.utils import timezone

        from apps.org import services as org_services
        from apps.org.models import OrgMember

        self.owner = User.objects.create_user('contact+4398d0f39102@example.com', "x", full_name="Hana Owner")
        self.boss = User.objects.create_user('contact+bffa4b1a8fdc@example.com', "x", full_name="Max Manager")
        self.acme = org_services.create_organization(name="Acme", slug="acme", owner=self.owner)
        with tenant_context(org_id=self.acme.id, user_id=self.owner.id):
            now = timezone.now()
            OrgMember.objects.create(org=self.acme, user=self.sara, joined_at=now)
            OrgMember.objects.create(org=self.acme, user=self.boss, joined_at=now, role="manager")
        # Sara is in Acme; Omar learns on his own
        for user in (self.sara, self.omar):
            self.client.force_login(user)
            me = self.ok("get", "/inclusion/me")
            self.ok("post", "/inclusion/me/submit", {"answers": self.answer_all(me, 3), "consent": True})

    def as_company(self, user, method, path):
        self.client.force_login(user)
        return getattr(self.client, method)(API + path, HTTP_X_ORG_ID=str(self.acme.id))

    def test_owner_sees_only_current_members(self):
        r = self.as_company(self.owner, "get", "/inclusion/company/results")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual([i["email"] for i in body["items"]], ['contact+a6b7d7235186@example.com'])
        self.assertEqual(body["summary"], {"learners": 1, "flagged": 1})
        sara_attempt = body["items"][0]["attempt_id"]
        detail = self.as_company(self.owner, "get", f"/inclusion/company/results/{sara_attempt}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["groups"]), 6)
        with tenant_context(staff=True):
            omar_attempt = Attempt.objects.get(user=self.omar).id
        self.assertEqual(
            self.as_company(self.owner, "get", f"/inclusion/company/results/{omar_attempt}").status_code, 404
        )

    def test_managers_and_learners_are_refused(self):
        for user in (self.boss, self.sara):
            self.assertEqual(
                self.as_company(user, "get", "/inclusion/company/results").status_code, 403, user.email
            )
        self.client.force_login(self.owner)  # no company selected
        self.assertEqual(self.call("get", "/inclusion/company/results").status_code, 403)

    def test_database_enforces_the_same_rule(self):
        with tenant_context(org_id=self.acme.id, user_id=self.owner.id):
            self.assertEqual(set(Attempt.objects.values_list("user_id", flat=True)), {self.sara.id})
        with tenant_context(org_id=self.acme.id, user_id=self.boss.id):  # a manager: nothing
            self.assertEqual(Attempt.objects.count(), 0)
        with tenant_context(org_id=self.acme.id, user_id=self.owner.id):  # Sara leaves the company
            from django.utils import timezone

            from apps.org.models import OrgMember

            OrgMember.objects.filter(user=self.sara).update(removed_at=timezone.now())
            self.assertEqual(Attempt.objects.count(), 0)
