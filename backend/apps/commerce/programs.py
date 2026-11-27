"""Selling programs to people (M21; Programs plan D5, D6, D7, D10).

    offers / intakes      what is for sale, at what price, and the cohorts with places left
    checkout              one offer -> an Order (paid in full: Checkout payment mode) or an
                          Order + InstalmentPlan (N monthly payments: Checkout subscription mode)
    fulfil_item           called by services.fulfil_order once the money arrived: enrol, set
                          what the enrolment covers, and for a live seat place the learner
    unlock_module         a recorded module paid with tokens (D6)
    instalment_*          the monthly plan's webhooks: paid, failed (grace period), cancelled

Money rules are the same as for courses (services.py): prices come from the database, the
browser sends ids only, and only a signed Stripe webhook (or the success page asking Stripe
directly) marks anything paid. Every webhook step is idempotent.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.catalog.models import Course, Module
from apps.delivery.models import Cohort, Group
from apps.learning import placement
from apps.learning import services as learning
from apps.learning.models import Enrollment, EnrollmentModule
from core.errors import ServiceError

from . import gateway, pricing
from .models import (
    Currency,
    InstalmentPayment,
    InstalmentPlan,
    Order,
    OrderItem,
    Payment,
    ProgramOffer,
)

log = logging.getLogger(__name__)

INSTALMENTS_KIND = "program_instalments"  # Stripe metadata kind of a monthly plan
LIVE_ACCESS = (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED)


# ---------------------------------------------------------------- offers
def active_offers(program_id) -> list[ProgramOffer]:
    return list(
        ProgramOffer.objects.filter(program_id=program_id, is_active=True).order_by(
            F("module_key").asc(nulls_first=True), "mode", "created_at"
        )
    )


def offer_amounts(offers: list[ProgramOffer], code: str) -> dict:
    """{offer_id: amount_minor} for the offers with a cash price, in one query."""
    cur = Currency.objects.filter(code=code, is_active=True).values("exponent").first()
    if cur is None:
        raise ServiceError("bad_currency", f"{code} is not offered.")
    amounts = pricing.tier_amounts({o.tier_id for o in offers if o.tier_id}, code, cur["exponent"])
    return {o.id: amounts[o.tier_id] for o in offers if o.tier_id}


def from_prices(program_ids, code: str) -> dict:
    """{program_id: lowest cash price} for catalogue cards ("from £X")."""
    offers = list(
        ProgramOffer.objects.filter(program_id__in=list(program_ids), is_active=True, tier__isnull=False)
    )
    if not offers:
        return {}
    amounts = offer_amounts(offers, code)
    out: dict = {}
    for o in offers:
        out[o.program_id] = min(out.get(o.program_id, amounts[o.id]), amounts[o.id])
    return out


def has_offers_q() -> Q:
    """Catalogue filter: short courses, or programs with at least one active offer (D29 lifted for B2C)."""
    from django.db.models import Exists, OuterRef

    on_sale = ProgramOffer.objects.filter(program_id=OuterRef("pk"), is_active=True)
    return Q(kind__in=Course.SELLABLE_KINDS) | (Q(kind=Course.Kind.PROGRAM) & Q(Exists(on_sale)))


def _module_titles(program: Course) -> dict:
    return dict(Module.objects.filter(version_id=program.live_version_id).values_list("module_key", "title"))


def offer_name(offer: ProgramOffer, program: Course, titles: dict | None = None) -> str:
    mode = "live" if offer.mode == ProgramOffer.Mode.LIVE else "recorded"
    if offer.module_key is None:
        return f"{program.title} ({mode})"
    titles = titles if titles is not None else _module_titles(program)
    return f"{program.title}: {titles.get(offer.module_key, 'module')} ({mode})"


# ---------------------------------------------------------------- intakes
def seat_counts(cohort_ids) -> dict:
    """{(cohort_id, group_id): placed} for everyone (SECURITY DEFINER count; numbers only)."""
    ids = [str(i) for i in cohort_ids]
    if not ids:
        return {}
    with connection.cursor() as cur:
        cur.execute("SELECT cohort_id, group_id, placed FROM learning.cohort_seat_counts(%s::uuid[])", [ids])
        return {(c, g): n for c, g, n in cur.fetchall()}


def _spare(capacity, placed: int):
    return None if capacity is None else max(capacity - placed, 0)


def intakes(program: Course, *, cohort_id=None) -> list[dict]:
    """The program's cohorts that take learners and have an active group, soonest first, with
    places left (None = no limit). One query for cohorts and groups, one for the counts."""
    qs = Cohort.objects.filter(program=program, status__in=placement.PLACEABLE).order_by("start_date", "name")
    if cohort_id is not None:
        qs = qs.filter(pk=cohort_id)
    cohorts = list(qs[:24])
    groups: dict = {}
    for g in Group.objects.filter(cohort__in=cohorts, status=Group.Status.ACTIVE).order_by("name"):
        groups.setdefault(g.cohort_id, []).append(g)
    counts = seat_counts([c.id for c in cohorts])
    out = []
    for c in cohorts:
        gs = groups.get(c.id)
        if not gs:
            continue
        spares = [_spare(g.capacity, counts.get((c.id, g.id), 0)) for g in gs]
        left = None if any(s is None for s in spares) else sum(spares)
        cohort_placed = sum(n for (cid, _), n in counts.items() if cid == c.id)
        cohort_left = _spare(c.capacity, cohort_placed)
        if cohort_left is not None:
            left = cohort_left if left is None else min(left, cohort_left)
        out.append({
            "id": c.id, "name": c.name, "start_date": c.start_date, "end_date": c.end_date,
            "places_left": left, "groups": list(zip(gs, spares, strict=True)),
        })  # fmt: skip
    return out


# ---------------------------------------------------------------- what a learner has
def personal_enrollment(user, program_id, *, lock: bool = False) -> Enrollment | None:
    qs = Enrollment.objects.filter(user=user, course_id=program_id, org__isnull=True).exclude(
        status=Enrollment.Status.SUPERSEDED
    )
    return (qs.select_for_update() if lock else qs).first()


def _has_access(e: Enrollment | None) -> bool:
    return bool(
        e
        and e.status in LIVE_ACCESS
        and (e.access_expires_at is None or e.access_expires_at > timezone.now())
    )


def owned_modules(e: Enrollment) -> set | None:
    """None = every module (scope program); otherwise the module keys bought."""
    if e.scope == Enrollment.Scope.PROGRAM:
        return None
    return set(EnrollmentModule.objects.filter(enrollment=e).values_list("module_key", flat=True))


def covers(e: Enrollment | None, offer: ProgramOffer) -> bool:
    """True when the learner already has what this offer sells."""
    if not _has_access(e):
        return False
    if offer.mode == ProgramOffer.Mode.LIVE and not (e.group_id or e.cohort_id):
        return False  # recorded learners may buy a live seat; a paid one waiting for a group has it
    owned = owned_modules(e)
    if offer.module_key is None:
        return owned is None
    return owned is None or offer.module_key in owned


OPEN_PLAN = ("active", "past_due")


def open_plan(e: Enrollment | None) -> InstalmentPlan | None:
    """The monthly plan still paying for this enrolment (active or overdue), if any."""
    if e is None or e.source != Enrollment.Source.PURCHASE or not e.source_ref:
        return None
    return InstalmentPlan.objects.filter(order__items__id=e.source_ref, status__in=OPEN_PLAN).first()


def _no_open_plan(e: Enrollment | None) -> None:
    """While a monthly plan pays for the enrolment, it stays linked to that plan (source_ref):
    a second purchase would cut the link and let a stopped plan keep access, or charge twice."""
    plan = open_plan(e)
    if plan is None:
        return
    if plan.status == InstalmentPlan.Status.PAST_DUE:
        raise ServiceError(
            "payment_overdue", "A monthly payment for this program is overdue. Update your card first."
        )
    raise ServiceError(
        "plan_in_progress", "You're paying for this program monthly. You can add more once it is paid."
    )


def access_summary(e: Enrollment | None) -> dict | None:
    paused = False
    if not _has_access(e):
        plan = open_plan(e) if e is not None and e.status in LIVE_ACCESS else None
        if plan is None:
            return None
        paused = True  # a missed monthly payment: say so instead of offering to buy again
    owned = owned_modules(e)
    plan = open_plan(e)
    return {
        "enrollment_id": e.id,
        "scope": e.scope,
        "module_keys": sorted(owned, key=str) if owned is not None else [],
        "live": bool(e.group_id),
        "cohort_id": e.cohort_id,
        "paused": paused,
        "paying_monthly": plan is not None,
    }


# ---------------------------------------------------------------- checkout
def _offer_for_sale(offer_id) -> ProgramOffer:
    offer = (
        ProgramOffer.objects.select_related("program")
        .filter(pk=offer_id, is_active=True, program__kind=Course.Kind.PROGRAM, program__status="published",
                program__live_version__isnull=False, program__owner_org__isnull=True,
                program__deleted_at__isnull=True)
        .first()
    )  # fmt: skip
    if offer is None:
        raise ServiceError("not_for_sale", "This program is not available.")
    if offer.module_key is not None and offer.module_key not in _module_titles(offer.program):
        raise ServiceError("not_for_sale", "This module is not available.")
    return offer


def _intake(offer: ProgramOffer, cohort_id) -> Cohort:
    if cohort_id is None:
        raise ServiceError("choose_intake", "Choose an intake for your live place.")
    found = intakes(offer.program, cohort_id=cohort_id)
    if not found:
        raise ServiceError("intake_closed", "This intake isn't taking learners.")
    if found[0]["places_left"] == 0:
        raise ServiceError("intake_full", "This intake is full. Choose another one.")
    return Cohort.objects.get(pk=cohort_id)


@transaction.atomic
def checkout(*, user, offer_id, currency: str, cohort_id=None, instalments: int = 1) -> dict:
    """Returns {"order", "checkout_url"}. The browser sends ids only; the price is the offer's tier."""
    offer = _offer_for_sale(offer_id)
    program = offer.program
    if offer.tier_id is None:
        raise ServiceError("tokens_only", "This module is unlocked with tokens.")
    if not 1 <= instalments <= offer.instalments_max:
        raise ServiceError("bad_instalments", "Choose a payment option that this program offers.")
    cur = Currency.objects.filter(code=currency, is_active=True, stripe_supported=True).first()
    if cur is None:
        raise ServiceError("bad_currency", f"Payments in {currency} are not available.")
    e = personal_enrollment(user, program.id)
    if covers(e, offer):
        raise ServiceError("already_owned", "You already have this.")
    _no_open_plan(e)
    cohort = None
    if offer.mode == ProgramOffer.Mode.LIVE:
        cohort = _intake(offer, cohort_id)
        if _has_access(e) and e.cohort_id and e.cohort_id != cohort.id:
            raise ServiceError("other_intake", "You already study with another intake. Choose that one.")
    price = offer_amounts([offer], cur.code)[offer.id]
    per = -(-price // instalments)  # rounded up: N equal payments
    total = per * instalments
    rate = pricing.latest_rate(cur.code)
    gbp = pricing.gbp_equivalent(total, cur.exponent, rate)
    order = Order.objects.create(user=user, currency=cur, subtotal_minor=total, total_minor=total,
                                 fx_rate=rate, gbp_total_minor=gbp)  # fmt: skip
    OrderItem.objects.create(order=order, user=user, course=program, list_minor=total, gross_minor=total,
                             gbp_gross_minor=gbp, offer=offer, cohort=cohort)  # fmt: skip
    if total == 0:
        from . import services

        services.fulfil_order(order_id=order.id)
        order.refresh_from_db()
        return {"order": order, "checkout_url": None}
    name = offer_name(offer, program)[:250]
    common = {
        "customer_email": user.email,
        "success_url": f"{settings.FRONTEND_URL}/checkout/success?order={order.id}",
        "cancel_url": f"{settings.FRONTEND_URL}/courses/{program.slug}",
    }
    if instalments == 1:
        session = gateway.create_checkout_session(
            mode="payment",
            line_items=[{"quantity": 1, "price_data": {
                "currency": cur.code.lower(), "unit_amount": gateway.to_stripe_amount(total, cur.code, cur.exponent),
                "product_data": {"name": name}}}],
            metadata={"kind": "order", "id": str(order.id)},
            idempotency_key=f"order-{order.id}", **common,
        )  # fmt: skip
    else:
        plan = InstalmentPlan.objects.create(order=order, user=user, count=instalments, amount_minor=per)
        session = gateway.create_checkout_session(
            mode="subscription",
            line_items=[{"quantity": 1, "price_data": {
                "currency": cur.code.lower(), "unit_amount": gateway.to_stripe_amount(per, cur.code, cur.exponent),
                "recurring": {"interval": "month"},
                "product_data": {"name": f"{name}, {instalments} monthly payments"[:250]}}}],
            metadata={"kind": INSTALMENTS_KIND, "id": str(plan.id), "order": str(order.id)},
            idempotency_key=f"instalments-{plan.id}", customer=user.stripe_customer_id or "", **common,
        )  # fmt: skip
        InstalmentPlan.objects.filter(pk=plan.pk).update(stripe_session_id=session["id"])
    Order.objects.filter(pk=order.pk).update(stripe_session_id=session["id"])
    order.stripe_session_id = session["id"]
    return {"order": order, "checkout_url": session["url"]}


# ---------------------------------------------------------------- after payment
def _grant(*, user, program: Course, module_key, source: str, source_ref) -> Enrollment:
    """Enrol (or bring back) the learner and record what the enrolment now covers."""
    e = personal_enrollment(user, program.id, lock=True)
    new = e is None
    if new:
        e = learning.enrol(
            user=user, course=program, source=Enrollment.Source.PURCHASE, source_ref=source_ref
        )
    lapsed = not _has_access(e)
    fields = {"source": Enrollment.Source.PURCHASE, "source_ref": source_ref}
    if lapsed:  # refunded or expired: this purchase opens it again, and only for what it bought
        # never the old group: a live purchase places them again (capacity checked)
        fields.update(status=Enrollment.Status.ACTIVE, access_expires_at=None, cohort_id=None, group_id=None)
        EnrollmentModule.objects.filter(enrollment=e).delete()
    if module_key is None:
        fields["scope"] = Enrollment.Scope.PROGRAM
    elif new or lapsed:  # a lapsed whole-program access comes back as just this module
        fields["scope"] = Enrollment.Scope.MODULES
    Enrollment.objects.filter(pk=e.pk).update(**fields, updated_at=timezone.now())
    for k, v in fields.items():
        setattr(e, k, v)
    if module_key is not None and e.scope == Enrollment.Scope.MODULES:
        EnrollmentModule.objects.get_or_create(
            enrollment=e,
            module_key=module_key,
            defaults={"user_id": e.user_id, "source": source, "source_ref": source_ref},
        )
    return e


def _place(e: Enrollment, user, cohort: Cohort, program: Course, *, prefer_group_id=None) -> None:
    """A live seat: the active group with the most spare places. placement.place re-checks
    capacity under a lock; if a race filled every group, the learner keeps the paid seat in
    the cohort without a group and cohort managers are asked to place them."""
    if e.group_id and e.cohort_id == cohort.id:
        return
    found = intakes(program, cohort_id=cohort.id)
    order = sorted(found[0]["groups"], key=lambda gs: (gs[1] is not None, -(gs[1] or 0))) if found else []
    order.sort(key=lambda gs: gs[0].id != prefer_group_id)  # a swap keeps the old seat's group first
    for group, spare in order:
        if spare == 0:
            continue
        try:
            with transaction.atomic():
                placement.place(group_id=group.id, users=[user], org_id=e.org_id)
            return
        except ServiceError as err:
            if err.code not in ("group_full", "cohort_full", "group_closed", "cohort_closed"):
                raise
    Enrollment.objects.filter(pk=e.pk).update(cohort_id=cohort.id, group_id=None, updated_at=timezone.now())
    _tell_managers(user, cohort, program)


def _tell_managers(user, cohort: Cohort, program: Course) -> None:
    from apps.engagement.notify import notify
    from apps.identity.models import User
    from core.tenancy import tenant_context

    with tenant_context(staff=True):
        ids = list(
            User.objects.filter(is_staff=True, is_active=True)
            .filter(Q(is_superuser=True) | Q(staff_roles__role__permissions__contains=["cohorts.manage"]))
            .values_list("id", flat=True)
            .distinct()
        )
    notify(ids, "program_learner_unplaced",
           {"name": user.full_name or user.email, "cohort": cohort.name, "program": program.title},
           url=f"/console/programs/{program.id}", dedupe=f"unplaced:{cohort.id}:{user.id}")  # fmt: skip


def fulfil_item(item: OrderItem, user) -> Enrollment:
    """services.fulfil_order calls this for a program line (inside its transaction)."""
    offer, program = item.offer, item.course
    e = _grant(user=user, program=program, module_key=offer.module_key,
               source=EnrollmentModule.Source.PURCHASE, source_ref=item.id)  # fmt: skip
    if offer.mode == ProgramOffer.Mode.LIVE and item.cohort_id:
        _place(e, user, item.cohort, program)
    return e


# ---------------------------------------------------------------- tokens (D6)
@transaction.atomic
def unlock_module(*, user, offer_id, request=None) -> Enrollment:
    from . import wallet

    offer = _offer_for_sale(offer_id)
    if offer.mode != ProgramOffer.Mode.RECORDED or offer.module_key is None or not offer.token_price:
        raise ServiceError("no_token_price", "This can't be unlocked with tokens.")
    with connection.cursor() as cur:  # a double click never spends twice
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"unlock-module:{user.id}:{offer.id}"]
        )
    e = personal_enrollment(user, offer.program_id)
    if covers(e, offer):
        raise ServiceError("already_owned", "You already have this module.")
    _no_open_plan(e)
    try:
        spend = wallet.spend_tokens(user=user, scope="module", target_id=offer.id, tokens=offer.token_price,
                                    course_id=offer.program_id, actor=user, request=request)  # fmt: skip
    except wallet.InsufficientTokens as exc:
        raise ServiceError("insufficient_tokens", "You don't have enough tokens.", status=402) from exc
    return _grant(user=user, program=offer.program, module_key=offer.module_key,
                  source=EnrollmentModule.Source.TOKENS, source_ref=spend.id)  # fmt: skip


# ---------------------------------------------------------------- monthly plans (D7)
def grace_days() -> int:
    from apps.platform.services import get_setting

    return int(get_setting("payments.instalment_grace_days"))


def _plan_enrollments(plan: InstalmentPlan):
    """The enrolments this plan pays for (a later purchase moves source_ref away, so a
    lapsed old plan never pauses access bought again another way)."""
    items = OrderItem.objects.filter(order_id=plan.order_id).values_list("id", flat=True)
    return Enrollment.objects.filter(source_ref__in=list(items), org__isnull=True)


def plan_for_invoice(inv: dict) -> InstalmentPlan | None:
    parent = (inv.get("parent") or {}).get("subscription_details") or {}
    meta = parent.get("metadata") or (inv.get("subscription_details") or {}).get("metadata") or {}
    if meta.get("kind") == INSTALMENTS_KIND and meta.get("id"):
        return InstalmentPlan.objects.filter(pk=meta["id"]).first()
    sub = inv.get("subscription") or parent.get("subscription")
    return InstalmentPlan.objects.filter(stripe_subscription_id=sub).first() if sub else None


def link_session(session: dict, meta: dict) -> None:
    sub, customer = session.get("subscription"), session.get("customer") or ""
    if sub:
        InstalmentPlan.objects.filter(pk=meta["id"], stripe_subscription_id__isnull=True).update(
            stripe_subscription_id=sub, updated_at=timezone.now()
        )
    plan = InstalmentPlan.objects.filter(pk=meta["id"]).values("user_id").first()
    if customer and plan:
        from apps.identity.models import User

        User.objects.filter(pk=plan["user_id"], stripe_customer_id="").update(stripe_customer_id=customer)


@transaction.atomic
def instalment_paid(plan_id, *, invoice_id: str, amount, currency: str, payment_intent: str = "") -> bool:
    """One paid monthly invoice. The first one fulfils the order; a repeat is ignored; a
    wrong amount is refused; the last one completes the plan and stops Stripe charging."""
    from . import services

    plan = (
        InstalmentPlan.objects.select_for_update()
        .select_related("order__currency")
        .filter(pk=plan_id)
        .first()
    )
    if plan is None or not invoice_id:
        return False
    if InstalmentPayment.objects.filter(stripe_invoice_id=invoice_id).exists():
        return False
    order, cur = plan.order, plan.order.currency
    if (
        amount != gateway.to_stripe_amount(plan.amount_minor, cur.code, cur.exponent)
        or (currency or "").upper() != cur.code
    ):
        raise ServiceError("amount_mismatch", "Paid amount does not match the plan.")
    now = timezone.now()
    InstalmentPayment.objects.create(plan=plan, user_id=order.user_id, stripe_invoice_id=invoice_id,
                                     amount_minor=plan.amount_minor, paid_at=now)  # fmt: skip
    Payment.objects.create(order=order, user_id=order.user_id, provider_ref=(payment_intent or invoice_id)[:64],
                           amount_minor=plan.amount_minor, currency=cur, status="succeeded")  # fmt: skip
    plan.paid_count += 1
    plan.grace_until = None
    if plan.status != InstalmentPlan.Status.CANCELLED:
        plan.status = (
            InstalmentPlan.Status.COMPLETED if plan.paid_count >= plan.count else InstalmentPlan.Status.ACTIVE
        )
    plan.save(update_fields=["paid_count", "grace_until", "status", "updated_at"])
    if order.status == Order.Status.PENDING:
        services.complete_paid_order(order, payment_intent=payment_intent)
    elif plan.status != InstalmentPlan.Status.CANCELLED:  # a paused learner paid: access comes back
        _plan_enrollments(plan).filter(access_expires_at__isnull=False).update(
            access_expires_at=None, updated_at=now
        )
    if plan.status == InstalmentPlan.Status.COMPLETED and plan.stripe_subscription_id:
        gateway.cancel_subscription(
            plan.stripe_subscription_id
        )  # inside the transaction: retried if it fails
    return True


@transaction.atomic
def instalment_failed(plan: InstalmentPlan) -> None:
    """A monthly payment failed: the learner keeps access for the grace period, then it pauses
    (access_expires_at) until a later payment clears it."""
    from apps.engagement.notify import notify

    plan = InstalmentPlan.objects.select_for_update().select_related("order__currency").get(pk=plan.pk)
    if plan.status not in (InstalmentPlan.Status.ACTIVE, InstalmentPlan.Status.PAST_DUE):
        return  # a first payment that failed at checkout opened nothing
    now = timezone.now()
    if plan.grace_until is None:
        plan.grace_until = now + timedelta(days=grace_days())
    plan.status, plan.last_failed_at = InstalmentPlan.Status.PAST_DUE, now
    plan.save(update_fields=["status", "grace_until", "last_failed_at", "updated_at"])
    _plan_enrollments(plan).filter(
        Q(access_expires_at__isnull=True) | Q(access_expires_at__gt=plan.grace_until)
    ).update(access_expires_at=plan.grace_until, updated_at=now)
    cur = plan.order.currency
    title = (
        OrderItem.objects.filter(order_id=plan.order_id).values_list("course__title", flat=True).first() or ""
    )
    notify([plan.order.user_id], "instalment_payment_failed",
           {"program": title, "amount": pricing.format_money(plan.amount_minor, cur.code, cur.exponent),
            "date": f"{plan.grace_until.day} {plan.grace_until:%b %Y}"},
           url="/account/orders",
           dedupe=f"instalment-failed:{plan.id}:{now:%Y%m%d}")  # fmt: skip


@transaction.atomic
def instalment_subscription_changed(sub: dict) -> None:
    """Stripe stopped the subscription (gave up retrying, or the learner cancelled it) before
    the plan was paid: the plan ends and access stops after the grace period."""
    if sub.get("status") not in ("canceled", "unpaid", "incomplete_expired"):
        return
    plan = InstalmentPlan.objects.select_for_update().filter(stripe_subscription_id=sub.get("id")).first()
    if plan is None or plan.status in (InstalmentPlan.Status.COMPLETED, InstalmentPlan.Status.CANCELLED):
        return
    if plan.paid_count >= plan.count:  # every payment is in (the cancel we asked for arrived first)
        return
    now = timezone.now()
    ends = plan.grace_until or now + timedelta(days=grace_days())
    if plan.status == InstalmentPlan.Status.PENDING:
        ends = now
    plan.status, plan.grace_until = InstalmentPlan.Status.CANCELLED, ends
    plan.save(update_fields=["status", "grace_until", "updated_at"])
    _plan_enrollments(plan).filter(Q(access_expires_at__isnull=True) | Q(access_expires_at__gt=ends)).update(
        access_expires_at=ends, updated_at=now
    )


def expire_checkout(meta: dict) -> None:
    from . import services

    InstalmentPlan.objects.filter(pk=meta.get("id"), status=InstalmentPlan.Status.PENDING).update(
        status=InstalmentPlan.Status.CANCELLED, updated_at=timezone.now()
    )
    if meta.get("order"):
        services.expire_order(order_id=meta["order"])


def session_completed(session: dict, meta: dict) -> None:
    """Checkout (subscription mode) finished: link the subscription; when the first invoice
    is already paid, count it now (invoice.paid may arrive before or after; either is fine)."""
    link_session(session, meta)
    if session.get("payment_status") == "paid" and session.get("invoice"):
        instalment_paid(meta["id"], invoice_id=session["invoice"], amount=session.get("amount_total"),
                        currency=session.get("currency") or "")  # fmt: skip


def check_refund(item: OrderItem) -> None:
    """A program purchase can be refunded in the app only when it is all the learner holds in
    that program (one enrolment covers every purchase): another paid line, tokens or staff
    grants on the same enrolment mean staff sort it out by hand."""
    e = Enrollment.objects.filter(pk=item.enrollment_id).first() if item.enrollment_id else None
    if e is None:
        return
    other_lines = (
        OrderItem.objects.filter(user_id=item.user_id, course_id=item.course_id, offer__isnull=False,
                                 refunded_at__isnull=True, order__status__in=["paid", "partially_refunded"])
        .exclude(pk=item.pk)
        .exists()
    )  # fmt: skip
    other_modules = EnrollmentModule.objects.filter(enrollment=e).exclude(source_ref=item.id).exists()
    if e.source_ref != item.id or other_lines or other_modules:
        raise ServiceError(
            "not_refundable", "This purchase is combined with others on the same program. Please contact us."
        )


def refunded(item: OrderItem) -> None:
    """After the refund: the module this line bought is no longer covered, and a revoked
    enrolment gives back its group place and its future workshop places."""
    from apps.learning import live

    EnrollmentModule.objects.filter(source_ref=item.id).delete()
    if item.enrollment_id and Enrollment.objects.filter(
        pk=item.enrollment_id, status=Enrollment.Status.REVOKED
    ).update(cohort_id=None, group_id=None, updated_at=timezone.now()):
        live.cancel_future_bookings(item.enrollment_id)


def plan_out(plan: InstalmentPlan | None) -> dict | None:
    if plan is None:
        return None
    return {"count": plan.count, "paid_count": plan.paid_count, "amount_minor": plan.amount_minor,
            "status": plan.status, "grace_until": plan.grace_until}  # fmt: skip


# ---------------------------------------------------------------- console: offers
def _clean_offer(program: Course, fields: dict, *, creating: bool) -> dict:
    """Friendly checks before the database constraints (which stay the last word)."""
    from .models import PriceTier

    mode, module_key = fields["mode"], fields.get("module_key")
    if mode not in ProgramOffer.Mode.values:
        raise ServiceError("bad_mode", "Choose live or recorded.")
    if creating and module_key is not None and module_key not in _module_titles(program):
        raise ServiceError("bad_module", "Choose a module of the published program.")
    tier_id, tokens = fields.get("tier_id"), fields.get("token_price")
    if tier_id is not None and not PriceTier.objects.filter(pk=tier_id, is_active=True).exists():
        raise ServiceError("bad_tier", "Choose an active price tier.")
    if tokens is not None and (module_key is None or mode != ProgramOffer.Mode.RECORDED):
        raise ServiceError("bad_tokens", "Only a recorded module can be unlocked with tokens.")
    if tier_id is None and tokens is None:
        raise ServiceError("no_price", "Set a price, a token price, or both.")
    n = fields.get("instalments_max", 1)
    if not 1 <= n <= 24 or (n > 1 and (mode != ProgramOffer.Mode.LIVE or tier_id is None)):
        raise ServiceError("bad_instalments", "Monthly payments (2 to 24) are for live places with a price.")
    return fields


@transaction.atomic
def save_offer(*, program: Course, offer: ProgramOffer | None = None, **changes) -> ProgramOffer:
    if program.kind != Course.Kind.PROGRAM or program.owner_org_id is not None:
        raise ServiceError("not_a_program", "Offers are for programs sold on the marketplace.")
    if program.live_version_id is None:
        raise ServiceError("not_published", "Publish the program before you sell it.")
    current = (
        {"mode": offer.mode, "module_key": offer.module_key, "tier_id": offer.tier_id,
         "token_price": offer.token_price, "instalments_max": offer.instalments_max, "is_active": offer.is_active}
        if offer else {"instalments_max": 1, "is_active": True}
    )  # fmt: skip
    changes = {k: v for k, v in changes.items() if v is not None or k in ("tier_id", "token_price")}
    fields = _clean_offer(program, {**current, **changes}, creating=offer is None)
    # module_key=None filters IS NULL: the whole-program offer of this mode
    same = ProgramOffer.objects.filter(
        program=program, mode=fields["mode"], module_key=fields.get("module_key")
    )
    if offer is not None:
        same = same.exclude(pk=offer.pk)
    if same.exists():
        raise ServiceError("offer_exists", "There is already an offer like this. Edit that one.")
    if offer is None:
        return ProgramOffer.objects.create(program=program, **fields)
    for k, v in fields.items():
        setattr(offer, k, v)
    offer.save()
    return offer
