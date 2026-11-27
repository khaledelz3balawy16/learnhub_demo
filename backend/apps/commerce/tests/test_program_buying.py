"""M21: selling programs to people. Offers (console), the catalogue listing, checkout with an
intake, placement in the emptiest group, module-only access in the player, monthly plans
(first payment fulfils, repeats ignored, wrong amounts refused, a failure pauses access after
the grace period, the last payment completes and cancels) and token module unlocks.
Stripe is replaced at the gateway boundary; everything else is real."""

from datetime import timedelta
from unittest import mock

from django.utils import timezone

from apps.catalog.models import Course, Lecture, Module
from apps.commerce import wallet, webhooks
from apps.commerce.models import InstalmentPlan, Order, PriceTier, ProgramOffer
from apps.delivery.models import Group
from apps.delivery.tests.test_programs import ProgramBase
from apps.identity.models import User
from apps.learning.models import Enrollment
from core.errors import ServiceError
from core.tenancy import tenant_context


def fake_session(**kw):
    return {"id": f"cs_test_{kw['metadata']['id']}", "url": "https://checkout.stripe.test/pay"}


class ProgramBuyingTest(ProgramBase):
    def setUp(self):
        super().setUp()
        pid, v, _ = self.build_program((1, 1))
        self.publish(pid, v)
        self.pid = pid
        with tenant_context(staff=True):
            program = Course.objects.get(pk=pid)
            self.slug, live = program.slug, program.live_version_id
            mods = list(Module.objects.filter(version_id=live).order_by("position"))
            self.m1, self.m2 = (str(m.module_key) for m in mods)
            by_id = {m.id: str(m.module_key) for m in mods}
            self.tier = PriceTier.objects.get(name="Tier 5")
            self.lectures = {
                by_id[lec.section.module_id]: lec.lecture_key
                for lec in Lecture.objects.select_related("section").filter(version_id=live)
            }
        today = timezone.localdate()
        monday = today + timedelta(days=7 - today.weekday())
        self.cohort = self.ok("post", f"/console/programs/{pid}/cohorts",
                              {"name": "Spring", "start_date": monday.isoformat()})["id"]  # fmt: skip
        self.g1 = self.ok("post", f"/console/program-cohorts/{self.cohort}/groups",
                          {"name": "G1", "weekday": 2, "capacity": 2})["id"]  # fmt: skip
        self.g2 = self.ok("post", f"/console/program-cohorts/{self.cohort}/groups",
                          {"name": "G2", "weekday": 3, "capacity": 5})["id"]  # fmt: skip
        self.live = self.ok("post", f"/console/programs/{pid}/offers",
                            {"mode": "live", "tier_id": str(self.tier.id), "instalments_max": 3})["id"]  # fmt: skip
        self.rec_m1 = self.ok("post", f"/console/programs/{pid}/offers",
                              {"mode": "recorded", "module_key": self.m1, "tier_id": str(self.tier.id),
                               "token_price": 50})["id"]  # fmt: skip

    # ------------------------------------------------------------ helpers
    def deliver(self, event):
        with mock.patch("apps.commerce.gateway.construct_event", return_value=event):
            return webhooks.handle(b"{}", "sig")

    def paid(self, order_id, event_id="evt_paid"):
        with tenant_context(staff=True):
            o = Order.objects.get(pk=order_id)
        return self.deliver({"id": event_id, "type": "checkout.session.completed", "data": {"object": {
            "id": o.stripe_session_id, "payment_status": "paid", "payment_intent": "pi_1",
            "amount_total": o.total_minor, "currency": "gbp", "metadata": {"kind": "order", "id": str(o.id)}}}})  # fmt: skip

    def buy(self, offer, **extra):
        with mock.patch("apps.commerce.gateway.create_checkout_session", side_effect=fake_session):
            return self.call(
                "post", "/commerce/programs/checkout", {"offer_id": offer, "currency": "GBP", **extra}
            )

    def enrolment(self, user):
        with tenant_context(staff=True):
            return Enrollment.objects.get(user=user, course_id=self.pid)

    # ------------------------------------------------------------ tests
    def test_offer_rules_and_listing(self):
        bad = [
            {"mode": "live", "tier_id": str(self.tier.id)},  # duplicate of the live offer
            {"mode": "live", "module_key": self.m2, "token_price": 10},  # tokens on a live offer
            {"mode": "recorded", "tier_id": str(self.tier.id), "instalments_max": 4},  # monthly on recorded
            {"mode": "recorded"},  # no price at all
        ]
        for body in bad:
            self.assertEqual(
                self.call("post", f"/console/programs/{self.pid}/offers", body).status_code, 400, body
            )
        self.as_(self.tutor)
        self.assertEqual(self.call("post", f"/console/programs/{self.pid}/offers",
                                   {"mode": "recorded", "tier_id": str(self.tier.id)}).status_code, 403)  # fmt: skip

        self.client.logout()
        cards = self.ok("get", "/catalog/courses?limit=60")["items"]
        card = next(c for c in cards if c["id"] == self.pid)  # D29 lifted: listed with an offer
        self.assertTrue(card["price_from"])
        detail = self.ok("get", f"/catalog/courses/{self.slug}?currency=GBP")
        self.assertEqual({o["mode"] for o in detail["offers"]}, {"live", "recorded"})
        self.assertEqual(detail["intakes"][0]["places_left"], 7)
        self.assertIsNone(detail["program_access"])

        # switched off: no longer listed
        self.as_(self.staff)
        for oid in (self.live, self.rec_m1):
            self.ok("patch", f"/console/program-offers/{oid}", {"is_active": False})
        self.client.logout()
        self.assertFalse(
            any(c["id"] == self.pid for c in self.ok("get", "/catalog/courses?limit=60")["items"])
        )

    def test_live_seat_goes_to_the_emptiest_group(self):
        self.ok(
            "post", f"/console/program-groups/{self.g2}/members", {"emails": ['contact+95190e115eae@example.com']}
        )
        self.as_(self.sara)
        self.assertEqual(self.buy(self.live).json()["error"]["code"], "choose_intake")
        order = self.buy(self.live, cohort_id=self.cohort).json()
        self.assertIsNotNone(order["checkout_url"])
        self.assertEqual(self.paid(order["order_id"]), "processed")
        e = self.enrolment(self.sara)
        # G1 has 2 spare places, G2 has 4: the learner goes to G2
        self.assertEqual((str(e.group_id), e.scope, e.source), (self.g2, "program", "purchase"))
        self.assertEqual(self.buy(self.live, cohort_id=self.cohort).json()["error"]["code"], "already_owned")
        self.assertEqual(self.ok("get", f"/catalog/courses/{self.slug}")["program_access"]["live"], True)

        # a full intake is refused
        self.as_(self.staff)
        with tenant_context(staff=True):
            Group.objects.filter(pk__in=[self.g1, self.g2]).update(capacity=1)
        late = User.objects.create_user('contact+61b075470290@example.com', "x")
        self.ok(
            "post", f"/console/program-groups/{self.g1}/members", {"emails": ['contact+61b075470290@example.com']}
        )
        self.as_(User.objects.create_user('contact+9c2d5eababae@example.com', "x"))
        self.assertEqual(self.buy(self.live, cohort_id=self.cohort).json()["error"]["code"], "intake_full")
        self.assertTrue(late.pk)

    def test_module_purchase_locks_the_other_module(self):
        self.as_(self.sara)
        order = self.buy(self.rec_m1).json()
        self.paid(order["order_id"])
        e = self.enrolment(self.sara)
        self.assertEqual((e.scope, e.group_id), ("modules", None))
        player = self.ok("get", f"/learning/enrollments/{e.id}")
        self.assertEqual([m["owned"] for m in player["modules"]], [True, False])
        self.ok("get", f"/learning/enrollments/{e.id}/lectures/{self.lectures[self.m1]}")
        r = self.call("get", f"/learning/enrollments/{e.id}/lectures/{self.lectures[self.m2]}")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "module_locked"))
        self.assertEqual(self.buy(self.rec_m1).json()["error"]["code"], "already_owned")

        # refunded, then another module with tokens: the refunded module stays locked
        item = self.ok("get", f"/commerce/orders/{order['order_id']}")["items"][0]
        with mock.patch("apps.commerce.gateway.refund", return_value="re_1"):
            self.ok("post", f"/commerce/orders/items/{item['id']}/refund", {"reason": "changed my mind"})
        self.as_(self.staff)
        m2 = self.ok("post", f"/console/programs/{self.pid}/offers",
                     {"mode": "recorded", "module_key": self.m2, "token_price": 5})["id"]  # fmt: skip
        with tenant_context(staff=True):
            wallet.grant_tokens(user=self.sara, source="admin", amount=5, note="test")
        self.as_(self.sara)
        self.ok("post", "/commerce/programs/unlock-module", {"offer_id": m2})
        player = self.ok("get", f"/learning/enrollments/{e.id}")
        self.assertEqual([m["owned"] for m in player["modules"]], [False, True])

    def test_refund_gives_the_place_back(self):
        """Programs review: a paid place waiting for a group is owned; a refund leaves the
        group; a later module unlock never brings the old group back, and a module learner
        sees only their module's live sessions."""
        self.as_(self.sara)
        order = self.buy(self.live, cohort_id=self.cohort).json()
        self.paid(order["order_id"])
        e = self.enrolment(self.sara)
        with tenant_context(staff=True):  # every group was full: the paid place waits for one
            Enrollment.objects.filter(pk=e.pk).update(group_id=None)
        self.assertEqual(self.buy(self.live, cohort_id=self.cohort).json()["error"]["code"], "already_owned")
        with tenant_context(staff=True):
            Enrollment.objects.filter(pk=e.pk).update(group_id=self.g2)

        item = self.ok("get", f"/commerce/orders/{order['order_id']}")["items"][0]
        with mock.patch("apps.commerce.gateway.refund", return_value="re_1"):
            self.ok("post", f"/commerce/orders/items/{item['id']}/refund", {"reason": "changed my mind"})
        e = self.enrolment(self.sara)
        self.assertEqual((e.status, e.cohort_id, e.group_id), ("revoked", None, None))

        with tenant_context(staff=True):
            wallet.grant_tokens(user=self.sara, source="admin", amount=50, note="test")
        self.ok("post", "/commerce/programs/unlock-module", {"offer_id": self.rec_m1})
        e = self.enrolment(self.sara)
        self.assertEqual((e.status, e.scope, e.group_id), ("active", "modules", None))
        self.assertEqual(self.ok("get", f"/catalog/courses/{self.slug}")["program_access"]["live"], False)

        # placed by staff with only module 1: module 2's session (and its link) stays hidden
        self.as_(self.staff)
        self.ok(
            "post", f"/console/program-groups/{self.g2}/members", {"emails": ['contact+a6b7d7235186@example.com']}
        )
        from apps.catalog.services import authoring
        from apps.delivery.models import LiveSession

        with tenant_context(staff=True), authoring():
            Lecture.objects.filter(lecture_key__in=self.lectures.values()).update(kind="live_session")
        with tenant_context(staff=True):
            for key, title in ((self.lectures[self.m1], "One"), (self.lectures[self.m2], "Two")):
                LiveSession.objects.create(group_id=self.g2, lecture_key=key, title=title,
                                           starts_at=timezone.now() + timedelta(days=3), duration_min=60)  # fmt: skip
        self.as_(self.sara)
        items = self.ok("get", f"/learning/enrollments/{e.id}/sessions")["items"]
        self.assertEqual([s["title"] for s in items], ["One"])

    def test_monthly_plan(self):
        self.as_(self.sara)
        order = self.buy(self.live, cohort_id=self.cohort, instalments=3).json()
        with tenant_context(staff=True):
            plan = InstalmentPlan.objects.get(order_id=order["order_id"])
        self.assertEqual(plan.count * plan.amount_minor, order["total_minor"])
        meta = {"kind": "program_instalments", "id": str(plan.id), "order": order["order_id"]}

        def invoice(inv_id, evt, amount=plan.amount_minor, kind="invoice.paid"):
            return self.deliver({"id": evt, "type": kind, "data": {"object": {
                "id": inv_id, "amount_paid": amount, "currency": "gbp",
                "parent": {"subscription_details": {"subscription": "sub_1", "metadata": meta}}}}})  # fmt: skip

        self.deliver({"id": "evt_s", "type": "checkout.session.completed", "data": {"object": {
            "id": plan.stripe_session_id, "payment_status": "paid", "invoice": "in_1", "subscription": "sub_1",
            "customer": "cus_1", "amount_total": plan.amount_minor, "currency": "gbp", "metadata": meta}}})  # fmt: skip
        invoice("in_1", "evt_1")  # the same invoice again: counted once
        with tenant_context(staff=True):
            plan.refresh_from_db()
            self.assertEqual(
                (plan.paid_count, plan.status, plan.stripe_subscription_id), (1, "active", "sub_1")
            )
            self.assertEqual(Order.objects.get(pk=order["order_id"]).status, "paid")
        e = self.enrolment(self.sara)
        self.assertEqual(str(e.group_id), self.g2)
        # refunds of a monthly plan go through the provider
        self.assertFalse(self.ok("get", f"/commerce/orders/{order['order_id']}")["items"][0]["refundable"])
        # while the plan runs the page says so (nothing else is sold: the enrolment stays linked to the plan)
        self.assertTrue(self.ok("get", f"/catalog/courses/{self.slug}")["program_access"]["paying_monthly"])

        with self.assertRaises(ServiceError):  # a wrong amount is refused (and Stripe retries)
            invoice("in_2", "evt_bad", amount=plan.amount_minor - 1)

        invoice("in_x", "evt_f", kind="invoice.payment_failed")
        with tenant_context(staff=True):
            plan.refresh_from_db()
            self.assertEqual(plan.status, "past_due")
            Enrollment.objects.filter(pk=e.pk).update(access_expires_at=timezone.now() - timedelta(minutes=1))
        r = self.call("get", f"/learning/enrollments/{e.id}")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "payment_overdue"))
        self.assertTrue(self.ok("get", f"/catalog/courses/{self.slug}")["program_access"]["paused"])

        invoice("in_2", "evt_2")  # paid late: access comes back
        self.assertEqual(self.call("get", f"/learning/enrollments/{e.id}").status_code, 200)
        with mock.patch("apps.commerce.gateway.cancel_subscription") as cancel:
            invoice("in_3", "evt_3")
        cancel.assert_called_once_with("sub_1")
        with tenant_context(staff=True):
            plan.refresh_from_db()
        self.assertEqual((plan.paid_count, plan.status), (3, "completed"))
        self.assertEqual(
            self.ok("get", f"/commerce/orders/{order['order_id']}")["instalments"]["paid_count"], 3
        )

    def test_token_module_unlock(self):
        with tenant_context(staff=True):
            wallet.grant_tokens(user=self.sara, source="admin", amount=80, note="test")
        self.as_(self.sara)
        e = self.ok("post", "/commerce/programs/unlock-module", {"offer_id": self.rec_m1})
        self.assertEqual(self.call("post", "/commerce/programs/unlock-module", {"offer_id": self.rec_m1}).json()["error"]["code"],
                         "already_owned")  # fmt: skip
        with tenant_context(staff=True):
            self.assertEqual(wallet.get_balance(self.sara), 30)
        self.assertEqual(self.enrolment(self.sara).id.hex, e["enrollment_id"].replace("-", ""))
        self.as_(self.staff)
        self.assertEqual(self.call("post", f"/console/programs/{self.pid}/offers",
                                   {"mode": "live", "module_key": self.m1, "token_price": 5}).status_code, 400)  # fmt: skip
        with tenant_context(staff=True):
            self.assertEqual(ProgramOffer.objects.filter(program_id=self.pid).count(), 2)
