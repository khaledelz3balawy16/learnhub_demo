"""M22: companies buying program seats. Signup locks the workspace until the first order is
paid; the order's rules (minimum seats, intakes, server prices); Stripe checkout and the
paid / expired webhooks; allocation (company enrolment, modules, group placement, manager
area, no seat left, release before starting); swaps (company step, cut-off reason, provider
step moves the seat and keeps the old progress) and the line manager view.
Stripe is replaced at the gateway boundary; everything else is real."""

from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Course, Module
from apps.commerce import webhooks
from apps.commerce.models import PriceTier, StripeEvent
from apps.corporate.models import ProgramSeatAllocation, ProgramSeatEvent, ProgramSeatOrder, SeatSwapRequest
from apps.delivery.tests.test_programs import API, ProgramBase
from apps.identity.models import User
from apps.learning.models import Enrollment, EnrollmentModule
from apps.org import services as org_services
from apps.org.models import Organization, OrgMember, OrgUnit
from core.errors import ServiceError
from core.tenancy import tenant_context


def fake_session(**kw):
    return {
        "id": f"cs_test_{kw['metadata']['id']}_{kw['idempotency_key'][-6:]}",
        "url": "https://stripe.test/pay",
    }


class SeatBase(ProgramBase):
    def setUp(self):
        super().setUp()
        pid, v, _ = self.build_program((1, 1))
        self.publish(pid, v)
        self.pid = pid
        with tenant_context(staff=True):
            live = Course.objects.get(pk=pid).live_version_id
            self.m1 = str(Module.objects.filter(version_id=live).order_by("position").first().module_key)
            self.tier = PriceTier.objects.get(name="Tier 5")
        monday = timezone.localdate() + timedelta(days=7 - timezone.localdate().weekday())
        self.cohort = self.ok("post", f"/console/programs/{pid}/cohorts",
                              {"name": "Spring", "start_date": monday.isoformat()})["id"]  # fmt: skip
        self.g1 = self.ok("post", f"/console/program-cohorts/{self.cohort}/groups",
                          {"name": "G1", "weekday": 2, "capacity": 2})["id"]  # fmt: skip
        self.g2 = self.ok("post", f"/console/program-cohorts/{self.cohort}/groups",
                          {"name": "G2", "weekday": 3, "capacity": 5})["id"]  # fmt: skip
        self.live = self.ok("post", f"/console/programs/{pid}/offers",
                            {"mode": "live", "tier_id": str(self.tier.id)})["id"]  # fmt: skip
        self.rec_m1 = self.ok("post", f"/console/programs/{pid}/offers",
                              {"mode": "recorded", "module_key": self.m1, "tier_id": str(self.tier.id)})["id"]  # fmt: skip
        mk = User.objects.create_user
        self.owner = mk('contact+4cff1c083b0f@example.com', "x", full_name="Olive Owner")
        self.mia = mk('contact+4eda8ca7bdbc@example.com', "x", full_name="Mia Manager")
        self.emps = [mk(f"e{i}@acme.example.com", "x", full_name=f"Emp {i}") for i in range(1, 6)]

    # ------------------------------------------------------------ helpers
    def org_call(self, method, path, data=None, org=None):
        return getattr(self.client, method)(API + path, data=data, content_type="application/json",
                                            HTTP_X_ORG_ID=str(org or self.org_id))  # fmt: skip

    def org_ok(self, method, path, data=None, org=None):
        r = self.org_call(method, path, data, org)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def code(self, r):
        return r.json()["error"]["code"]

    def deliver(self, event):
        with mock.patch("apps.commerce.gateway.construct_event", return_value=event):
            return webhooks.handle(b"{}", "sig")

    def session_event(self, order_id, *, kind="checkout.session.completed", amount=None, eid="evt_1"):
        with tenant_context(staff=True):
            o = ProgramSeatOrder.objects.get(pk=order_id)
        return self.deliver({"id": eid, "type": kind, "data": {"object": {
            "id": o.stripe_session_id, "payment_status": "paid", "payment_intent": "pi_seats",
            "amount_total": o.total_minor if amount is None else amount, "currency": "gbp",
            "metadata": {"kind": "program_seats", "id": str(o.id), "org_id": str(o.org_id)}}}})  # fmt: skip

    def checkout(self):
        with mock.patch("apps.commerce.gateway.create_checkout_session", side_effect=fake_session), \
             mock.patch("apps.commerce.gateway.expire_checkout_session"):  # fmt: skip
            return self.org_call("post", "/corporate/program-seats/draft/checkout")

    def active_company(self):
        """An existing company (made by staff: active straight away) with a team of five,
        Mia managing a unit that holds Emp 4 only."""
        self.as_(self.owner)
        with tenant_context(staff=True):
            org = org_services.create_organization(name="Acme", slug="acme", owner=self.owner)
            now = timezone.now()
            members = {}
            for u in [self.mia, *self.emps]:
                role = "manager" if u is self.mia else "learner"
                members[u.id] = OrgMember.objects.create(org=org, user=u, role=role, joined_at=now)
            root = OrgUnit.objects.get(org=org, parent__isnull=True)
            with tenant_context(org_id=org.id):
                unit = org_services.create_unit(parent=root, kind="team", name="Ops")
                org_services.add_member_to_unit(member=members[self.emps[3].id], unit=unit, primary=True)
                org_services.set_unit_managers(unit=unit, members=[members[self.mia.id]])
        self.org_id = org.id
        return org

    def buy(self, lines):
        self.as_(self.owner)
        self.org_ok("put", "/corporate/program-seats/draft", {"lines": lines})
        self.assertEqual(self.checkout().status_code, 200)
        order = self.org_ok("get", "/corporate/program-seats/setup")["draft"]
        self.session_event(order["id"], eid=f"evt_{order['id']}")
        found = self.org_ok("get", "/corporate/program-seats/orders")["items"]
        return {(ln["offer_id"], ln["cohort_id"]): ln["id"] for o in found for ln in o["lines"]}

    def enrolment(self, user):
        with tenant_context(staff=True):
            return Enrollment.objects.get(user=user, course_id=self.pid, org_id=self.org_id)


class SignupAndOrderTest(SeatBase):
    def test_signup_locks_the_workspace_until_paid(self):
        self.as_(self.owner)
        org = self.ok("post", "/corporate/program-seats/signup", {"name": "Newco Ltd", "currency": "GBP"})
        self.org_id = org["org_id"]
        self.assertEqual(org["onboarding_state"], "ordering")
        self.assertEqual(self.code(self.call("post", "/corporate/program-seats/signup", {"name": "Again"})),
                         "setup_in_progress")  # fmt: skip
        me = self.ok("get", "/identity/me")
        self.assertEqual(me["memberships"][0]["onboarding_state"], "ordering")
        # the workspace stays shut; the setup endpoints work
        for path in ("/corporate/program-seats/orders", "/org/people"):
            r = self.org_call("get", path)
            self.assertEqual((r.status_code, self.code(r)), (403, "workspace_locked"), path)
        cat = self.org_ok("get", "/corporate/program-seats/catalogue")
        program = next(p for p in cat["programs"] if p["id"] == self.pid)
        self.assertEqual(program["min_seats"], 2)
        self.assertEqual(program["intakes"][0]["places_left"], 7)

        # the order's rules
        bad = [
            ([{"offer_id": self.live, "seats": 2}], "choose_intake"),
            ([{"offer_id": self.live, "cohort_id": self.cohort, "seats": 1}], "bad_seats"),
            ([{"offer_id": self.live, "cohort_id": self.cohort, "seats": 8}], "intake_full"),
            ([{"offer_id": self.rec_m1, "cohort_id": self.cohort, "seats": 2}], "no_intake"),
        ]
        for lines, code in bad:
            self.assertEqual(
                self.code(self.org_call("put", "/corporate/program-seats/draft", {"lines": lines})), code
            )
        unit = next(o["unit_minor"] for o in program["offers"] if o["id"] == self.live)
        draft = self.org_ok("put", "/corporate/program-seats/draft", {"lines": [
            {"offer_id": self.live, "cohort_id": self.cohort, "seats": 2},
            {"offer_id": self.rec_m1, "seats": 3}]})["draft"]  # fmt: skip
        self.assertEqual(draft["total_minor"], unit * 2 + draft["lines"][1]["unit_minor"] * 3)

        # pay: waiting, then a wrong amount is refused, then the right one opens the workspace
        self.assertEqual(self.checkout().json()["checkout_url"], "https://stripe.test/pay")
        with tenant_context(staff=True):
            self.assertEqual(Organization.objects.get(pk=self.org_id).onboarding_state, "awaiting_payment")
        with self.assertRaises(ServiceError):  # stored on the event for the console; Stripe retries
            self.session_event(draft["id"], amount=1, eid="evt_wrong")
        with tenant_context(staff=True):
            self.assertIn("doesn't match", StripeEvent.objects.get(event_id="evt_wrong").error)
        self.assertEqual(self.org_call("get", "/corporate/program-seats/orders").status_code, 403)
        self.session_event(draft["id"], eid="evt_right")
        self.session_event(draft["id"], eid="evt_again")  # a retry changes nothing
        orders = self.org_ok("get", "/corporate/program-seats/orders")["items"]
        self.assertEqual([o["status"] for o in orders], ["paid"])
        with tenant_context(staff=True):
            self.assertEqual(Organization.objects.get(pk=self.org_id).onboarding_state, "active")
            self.assertEqual(ProgramSeatEvent.objects.filter(org_id=self.org_id, action="ordered").count(), 1)

    def test_expired_checkout_goes_back_to_the_draft(self):
        self.as_(self.owner)
        self.org_id = self.ok("post", "/corporate/program-seats/signup", {"name": "Newco"})["org_id"]
        draft = self.org_ok("put", "/corporate/program-seats/draft",
                            {"lines": [{"offer_id": self.rec_m1, "seats": 2}]})["draft"]  # fmt: skip
        self.checkout()
        self.session_event(draft["id"], kind="checkout.session.expired", eid="evt_exp")
        setup = self.org_ok("get", "/corporate/program-seats/setup")
        self.assertEqual((setup["onboarding_state"], setup["draft"]["status"]), ("ordering", "draft"))
        # a learner of another company can't touch this setup
        self.as_(self.emps[0])
        self.assertEqual(self.org_call("get", "/corporate/program-seats/setup").status_code, 403)


class AllocationTest(SeatBase):
    def setUp(self):
        super().setUp()
        self.active_company()
        self.lines = self.buy([{"offer_id": self.live, "cohort_id": self.cohort, "seats": 2},
                               {"offer_id": self.rec_m1, "seats": 3}])  # fmt: skip
        self.live_line = self.lines[(self.live, self.cohort)]
        self.m1_line = self.lines[(self.rec_m1, None)]

    def give(self, line, user, as_user=None):
        self.as_(as_user or self.owner)
        return self.org_call(
            "post", "/corporate/program-seats/allocate", {"line_id": line, "user_id": str(user.id)}
        )

    def test_allocate_places_and_limits(self):
        e1, e2, e3, e4, e5 = self.emps
        r = self.give(self.live_line, e1)
        self.assertEqual(r.status_code, 200, r.content)
        e = self.enrolment(e1)
        self.assertEqual((e.source, e.scope, str(e.cohort_id), str(e.group_id)),
                         ("organization", "program", self.cohort, self.g2))  # the emptiest group  # fmt: skip
        self.assertEqual(self.code(self.give(self.live_line, e1)), "already_has_seat")
        self.give(self.live_line, e2)
        self.assertEqual(self.code(self.give(self.live_line, e3)), "no_seats_left")

        # a module seat covers that module only
        self.give(self.m1_line, e3)
        e = self.enrolment(e3)
        self.assertEqual(e.scope, "modules")
        with tenant_context(staff=True):
            self.assertEqual([str(k) for k in EnrollmentModule.objects.filter(enrollment=e).values_list(
                "module_key", flat=True)], [self.m1])  # fmt: skip
        self.assertEqual(self.code(self.give(self.m1_line, e1)), "already_has_seat")  # whole live program

        # a manager allocates inside their units only
        self.assertEqual(self.give(self.m1_line, e5, as_user=self.mia).status_code, 404)
        self.assertEqual(self.give(self.m1_line, e4, as_user=self.mia).status_code, 200)

        # release before starting gives the seat back; after starting it's a swap
        self.as_(self.owner)
        holders = self.org_ok("get", f"/corporate/program-seats/lines/{self.m1_line}/holders")["items"]
        e3_seat = next(h["id"] for h in holders if h["user_id"] == str(e3.id))
        self.org_ok("post", f"/corporate/program-seats/allocations/{e3_seat}/release")
        self.assertEqual(self.enrolment(e3).status, "revoked")
        with tenant_context(staff=True):
            Enrollment.objects.filter(user=e4, org_id=self.org_id).update(last_accessed_at=timezone.now())
        e4_seat = next(h["id"] for h in holders if h["user_id"] == str(e4.id))
        r = self.org_call("post", f"/corporate/program-seats/allocations/{e4_seat}/release")
        self.assertEqual(self.code(r), "already_started")

    def test_swaps_need_the_company_then_the_provider(self):
        e1, e2, e3, e4, e5 = self.emps
        self.give(self.live_line, e1)
        self.give(self.m1_line, e4)
        self.as_(self.staff)
        self.ok("put", f"/console/programs/{self.pid}/settings",
                {"swap_cutoff_mode": "progress_pct", "swap_cutoff_value": 50})  # fmt: skip
        with tenant_context(staff=True):
            Enrollment.objects.filter(user=e1, org_id=self.org_id).update(progress_pct=60)
            seat1 = ProgramSeatAllocation.objects.get(user=e1, status="active").id
            seat4 = ProgramSeatAllocation.objects.get(user=e4, status="active").id

        # past the cut-off a reason is needed; the owner's request skips the company step
        self.as_(self.owner)
        path = f"/corporate/program-seats/allocations/{seat1}/swap"
        self.assertEqual(
            self.code(self.org_call("post", path, {"to_user_id": str(e3.id)})), "reason_required"
        )
        s1 = self.org_ok("post", path, {"to_user_id": str(e3.id), "reason": "Emp 1 is leaving the company."})
        self.assertEqual((s1["status"], s1["after_cutoff"]), ("pending_provider", True))
        self.assertEqual(self.code(self.org_call("post", path, {"to_user_id": str(e5.id), "reason": "x" * 12})),
                         "swap_open")  # fmt: skip

        # Mia's team member to someone outside her units: the company must approve first
        self.as_(self.mia)
        s4 = self.org_ok(
            "post", f"/corporate/program-seats/allocations/{seat4}/swap", {"to_user_id": str(e5.id)}
        )
        self.assertEqual(s4["status"], "pending_company")
        r = self.org_call("post", f"/corporate/program-seats/swaps/{s4['id']}/decide", {"approve": True})
        self.assertEqual(r.status_code, 403)
        self.as_(self.owner)
        mine = self.org_ok("get", "/corporate/program-seats/swaps")["items"]
        self.assertTrue(next(s for s in mine if s["id"] == s4["id"])["can_decide"])
        self.org_ok("post", f"/corporate/program-seats/swaps/{s4['id']}/decide", {"approve": True})

        # the provider: a tutor can't; staff reject one and approve the other
        self.as_(self.tutor)
        self.assertEqual(self.call("get", "/console/seat-swaps").status_code, 403)
        self.as_(self.staff)
        queue = self.ok("get", "/console/seat-swaps")["items"]
        self.assertEqual({q["id"] for q in queue}, {s1["id"], s4["id"]})
        self.ok("post", f"/console/seat-swaps/{s4['id']}/decide", {"approve": False, "note": "Not now"})
        self.assertEqual(self.enrolment(e4).status, "active")  # nothing moved
        self.ok("post", f"/console/seat-swaps/{s1['id']}/decide", {"approve": True})
        old, new = self.enrolment(e1), self.enrolment(e3)
        self.assertEqual((old.status, float(old.progress_pct)), ("revoked", 60.0))  # progress kept on record
        self.assertEqual((new.status, str(new.group_id)), ("active", self.g2))  # same group as the old seat
        with tenant_context(staff=True):
            self.assertEqual(SeatSwapRequest.objects.get(pk=s1["id"]).status, "approved")
            actions = set(
                ProgramSeatEvent.objects.filter(org_id=self.org_id).values_list("action", flat=True)
            )
        self.assertTrue({"swap_requested", "swap_company_ok", "swap_approved", "swap_rejected"} <= actions)
        self.assertEqual(self.call("post", f"/console/seat-swaps/{s1['id']}/decide", {"approve": True}).status_code,
                         400)  # fmt: skip

    def test_team_view_scope_and_query_count(self):
        e1, e2, e3, e4, _ = self.emps
        self.give(self.live_line, e1)
        self.give(self.m1_line, e4)
        self.as_(self.owner)
        rows = self.org_ok("get", "/corporate/program-seats/team")["items"]
        self.assertEqual({r["email"] for r in rows}, {e1.email, e4.email})
        live = next(r for r in rows if r["email"] == e1.email)
        self.assertEqual((live["live"], live["group_name"]), (True, "G2"))
        self.as_(self.mia)
        self.assertEqual(
            [r["email"] for r in self.org_ok("get", "/corporate/program-seats/team")["items"]], [e4.email]
        )

        self.as_(self.owner)
        with CaptureQueriesContext(connection) as two:
            self.org_ok("get", "/corporate/program-seats/team")
        self.give(self.live_line, e2)
        self.give(self.m1_line, e3)
        self.as_(self.owner)
        with CaptureQueriesContext(connection) as four:
            self.org_ok("get", "/corporate/program-seats/team")
        self.assertEqual(len(four), len(two), "the team page must not query per row")


class StaleSessionTest(SeatBase):
    def test_an_old_pages_expiry_never_resets_the_order(self):
        """Pay, come back, pay again: closing the first Stripe page must not undo the second."""
        self.as_(self.owner)
        self.org_id = self.ok("post", "/corporate/program-seats/signup", {"name": "Newco"})["org_id"]
        lines = {"lines": [{"offer_id": self.rec_m1, "seats": 2}]}
        draft = self.org_ok("put", "/corporate/program-seats/draft", lines)["draft"]
        self.checkout()
        with tenant_context(staff=True):
            old = ProgramSeatOrder.objects.get(pk=draft["id"]).stripe_session_id
        with mock.patch("apps.commerce.gateway.expire_checkout_session", return_value="expired"):
            self.org_ok("put", "/corporate/program-seats/draft", lines)
        self.checkout()
        self.deliver({"id": "evt_old_exp", "type": "checkout.session.expired", "data": {"object": {
            "id": old, "metadata": {"kind": "program_seats", "id": draft["id"], "org_id": str(self.org_id)}}}})  # fmt: skip
        setup = self.org_ok("get", "/corporate/program-seats/setup")
        self.assertEqual(
            (setup["onboarding_state"], setup["draft"]["status"]), ("awaiting_payment", "pending")
        )
        self.session_event(draft["id"], eid="evt_new_paid")
        self.assertEqual(self.org_ok("get", "/corporate/program-seats/orders")["items"][0]["status"], "paid")

        # a page paid a moment ago is never replaced
        self.org_ok("put", "/corporate/program-seats/draft", lines)  # a new order (the paid one stays)
        self.checkout()
        with mock.patch("apps.commerce.gateway.expire_checkout_session", return_value="paid"):
            r = self.org_call("put", "/corporate/program-seats/draft", lines)
        self.assertEqual(self.code(r), "already_paid")
