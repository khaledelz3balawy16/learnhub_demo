"""Companies buying program seats (M22; Programs plan D8, D9, D10, D11, D22).

    signup            a signed-in person creates a company; it starts at `ordering` and its
                      workspace stays locked (core.permissions) until the first order is paid
    catalogue/draft   the programs on sale, and the company's one order being built: lines of
                      an offer (whole program or a module, live or recorded), an intake for live
                      lines, and seats >= the program's minimum
    checkout/paid     card payment through Stripe; the signed webhook marks it paid and opens
                      the workspace
    allocate/release  give a seat to an employee: a company enrolment, its modules, and for a
                      live line a group in the intake
    swaps             a request: the company approves (owner, admin or the new person's line
                      manager), then the provider (seats.approve_swap). Past the program's cut-off
                      a reason is required. The old learner's enrolment is revoked, never deleted.
    team              the line manager view: progress, KSBs, OTJ and attendance

What a company enrolment covers is always recomputed from its ACTIVE allocations (_resync),
so allocating, releasing and swapping can never leave a module open that nobody pays for.
Money rules are the same as everywhere: prices come from the database, the browser sends ids.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Course, Module
from apps.commerce import gateway
from apps.commerce import programs as selling
from apps.commerce.models import Currency, ProgramOffer
from apps.delivery.models import Cohort, ProgramSetting
from apps.learning import records
from apps.learning import services as learning
from apps.learning.models import Enrollment, EnrollmentModule, LectureProgress, OtjEntry, SessionAttendance
from apps.org.models import MemberUnit, Organization, OrgMember
from apps.platform.services import audit, audit_request
from core.errors import ServiceError
from core.html import plain
from core.permissions import Scope
from core.tenancy import tenant_context

from .models import (
    ProgramSeatAllocation as Allocation,
)
from .models import (
    ProgramSeatEvent as Event,
)
from .models import (
    ProgramSeatLine as Line,
)
from .models import (
    ProgramSeatOrder as Order,
)
from .models import (
    SeatSwapRequest as Swap,
)

log = logging.getLogger(__name__)

KIND = "program_seats"  # Stripe metadata kind
MAX_LINES = 20
MAX_SEATS = 500
REASON_MIN = 10  # characters, for a swap past the cut-off
OPEN_SWAP = (Swap.Status.PENDING_COMPANY, Swap.Status.PENDING_PROVIDER)
HAS_ACCESS = (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED)
SETUP = (Organization.Onboarding.ORDERING, Organization.Onboarding.AWAITING_PAYMENT)


def _lock(key: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


def _lock_rows(model, **filters) -> None:
    """Row lock on one table only (the read that follows joins its relations)."""
    list(model.objects.select_for_update().filter(**filters).values_list("pk", flat=True))


def _event(org_id, action, *, actor=None, line=None, allocation=None, swap=None, target=None, previous=None,
           note="") -> None:  # fmt: skip
    Event.objects.create(org_id=org_id, action=action, actor=actor, line=line, allocation=allocation, swap=swap,
                         target_user=target, previous_user=previous, note=note[:2000])  # fmt: skip


# ================================================================ signup (D8)
@transaction.atomic
def signup(*, user, name: str, currency: str) -> Organization:
    """A new company with the caller as owner, locked until its first order is paid."""
    from apps.org import services as org_services

    name = plain(name or "").strip()
    if not 2 <= len(name) <= 200:
        raise ServiceError("bad_name", "Give your company a name (2 to 200 characters).")
    code = (currency or "").upper()
    if not Currency.objects.filter(code=code, is_active=True, stripe_supported=True).exists():
        raise ServiceError("bad_currency", f"Payments in {code or 'that currency'} are not available.")
    _lock(f"company-signup:{user.id}")  # a double click makes one company, not two
    open_setup = OrgMember.objects.filter(
        user=user, role=OrgMember.Role.OWNER, removed_at__isnull=True, org__onboarding_state__in=SETUP
    ).exists()
    if open_setup:
        raise ServiceError(
            "setup_in_progress", "You're already setting up a company. Carry on with that one."
        )
    slug = f"{slugify(name)[:60] or 'company'}-{secrets.token_hex(3)}"
    org = org_services.create_organization(
        name=name,
        slug=slug,
        owner=user,
        billing_currency=code,
        onboarding_state=Organization.Onboarding.ORDERING,
    )
    with tenant_context(org_id=org.id, user_id=user.id):
        audit(
            "company.signup", "organization", org.id, actor_id=user.id, org_id=org.id, data={"currency": code}
        )
    return org


# ================================================================ catalogue
def _offers_qs():
    return ProgramOffer.objects.select_related("program").filter(
        is_active=True, tier__isnull=False, program__kind=Course.Kind.PROGRAM, program__status="published",
        program__live_version__isnull=False, program__owner_org__isnull=True, program__deleted_at__isnull=True,
    )  # fmt: skip


def _titles(programs) -> dict:
    """{(program_id, module_key): title} for the programs' live versions. One query."""
    by_version = {p.live_version_id: p.id for p in programs}
    rows = Module.objects.filter(version_id__in=list(by_version)).values_list(
        "version_id", "module_key", "title"
    )
    return {(by_version[v], k): t for v, k, t in rows}


def _settings(program_ids) -> dict:
    found = {s.program_id: s for s in ProgramSetting.objects.filter(program_id__in=list(program_ids))}
    return {pid: found.get(pid) or ProgramSetting(program_id=pid) for pid in program_ids}


def catalogue(org: Organization) -> dict:
    """The programs a company can order, with the price per seat in its currency. Offers for a
    module the live version no longer has are left out. Intakes are read per program that
    sells live seats (two queries each; the catalogue holds a handful of programs)."""
    offers = list(_offers_qs().order_by("program__title", "module_key", "mode")[:400])
    programs = {o.program_id: o.program for o in offers}
    titles = _titles(programs.values())
    offers = [o for o in offers if o.module_key is None or (o.program_id, o.module_key) in titles]
    amounts = selling.offer_amounts(offers, org.billing_currency) if offers else {}
    rules = _settings(programs)
    cur = Currency.objects.filter(code=org.billing_currency).values("exponent").first() or {"exponent": 2}
    out = []
    for pid, program in programs.items():
        mine = [o for o in offers if o.program_id == pid]
        if not mine:
            continue
        live = any(o.mode == ProgramOffer.Mode.LIVE for o in mine)
        out.append({
            "id": pid, "title": program.title, "slug": program.slug,
            "min_seats": rules[pid].min_seats_per_line,
            "offers": [{
                "id": o.id, "module_key": o.module_key, "mode": o.mode,
                "module_title": titles.get((pid, o.module_key)) if o.module_key else None,
                "unit_minor": amounts[o.id],
            } for o in mine],
            "intakes": [{
                "id": i["id"], "name": i["name"], "start_date": i["start_date"], "end_date": i["end_date"],
                "places_left": i["places_left"],
            } for i in selling.intakes(program)] if live else [],
        })  # fmt: skip
    return {"currency": org.billing_currency, "exponent": cur["exponent"], "programs": out}


# ================================================================ the order being built
def open_order(org_id, *, lock: bool = False) -> Order | None:
    qs = Order.objects.filter(org_id=org_id, status__in=(Order.Status.DRAFT, Order.Status.PENDING))
    return (qs.select_for_update() if lock else qs).first()


def _price(org: Organization, lines: list[dict]) -> list[dict]:
    """Check each line and price it from the database. Raises on the first problem."""
    if not 1 <= len(lines) <= MAX_LINES:
        raise ServiceError("bad_lines", f"Add between 1 and {MAX_LINES} lines.")
    ids = {ln["offer_id"] for ln in lines}
    offers = {o.id: o for o in _offers_qs().filter(pk__in=list(ids))}
    if len(offers) != len(ids):
        raise ServiceError(
            "not_for_sale", "Something in your order is no longer for sale. Refresh and try again."
        )
    programs = {o.program_id: o.program for o in offers.values()}
    titles = _titles(programs.values())
    rules = _settings(programs)
    amounts = selling.offer_amounts(list(offers.values()), org.billing_currency)
    seen, out, intake_seats = set(), [], {}
    for ln in lines:
        offer = offers[ln["offer_id"]]
        program = offer.program
        if offer.module_key is not None and (program.id, offer.module_key) not in titles:
            raise ServiceError("not_for_sale", "A module in your order is no longer for sale.")
        key = (offer.id, ln.get("cohort_id"))
        if key in seen:
            raise ServiceError(
                "duplicate_line", "The same item is in your order twice. Change its seats instead."
            )
        seen.add(key)
        seats = int(ln["seats"])
        intake_seats[ln.get("cohort_id")] = intake_seats.get(ln.get("cohort_id"), 0) + seats
        least = rules[program.id].min_seats_per_line
        if not least <= seats <= MAX_SEATS:
            raise ServiceError("bad_seats", f"{program.title}: order between {least} and {MAX_SEATS} seats.")
        cohort = None
        if offer.mode == ProgramOffer.Mode.LIVE:
            if not ln.get("cohort_id"):
                raise ServiceError("choose_intake", f"{program.title}: choose an intake for the live seats.")
            found = selling.intakes(program, cohort_id=ln["cohort_id"])
            if not found:
                raise ServiceError("intake_closed", f"{program.title}: that intake isn't taking learners.")
            left = found[0]["places_left"]
            if left is not None and left < intake_seats[ln["cohort_id"]]:
                raise ServiceError("intake_full", f"{found[0]['name']} has {left} places left.")
            cohort = Cohort.objects.get(pk=ln["cohort_id"])
        elif ln.get("cohort_id"):
            raise ServiceError("no_intake", "Recorded seats don't have an intake.")
        unit = amounts[offer.id]
        out.append(
            {
                "offer": offer,
                "cohort": cohort,
                "seats": seats,
                "unit_minor": unit,
                "total_minor": unit * seats,
            }
        )
    return out


def _expire_session(order: Order) -> None:
    """A changed order must never be paid at its old price: the open Stripe page is closed first."""
    if order.status == Order.Status.PENDING and order.stripe_session_id:
        if gateway.expire_checkout_session(order.stripe_session_id) == "paid":
            # paid a moment ago: the webhook credits it; nothing may replace that page
            raise ServiceError("already_paid", "This order has just been paid. Refresh the page in a moment.")


@transaction.atomic
def save_draft(*, org: Organization, user, lines: list[dict]) -> Order:
    priced = _price(org, lines)
    order = open_order(org.id, lock=True)
    if order is None:
        try:
            with transaction.atomic():
                order = Order.objects.create(org_id=org.id, buyer=user, currency=org.billing_currency)
        except IntegrityError:  # another tab made it a moment ago
            order = open_order(org.id, lock=True)
    _expire_session(order)
    Line.objects.filter(order=order).delete()  # draft lines only: a paid order is never edited
    Line.objects.bulk_create([
        Line(org_id=org.id, order=order, offer=p["offer"], cohort=p["cohort"], seats=p["seats"],
             unit_minor=p["unit_minor"], total_minor=p["total_minor"]) for p in priced
    ])  # fmt: skip
    Order.objects.filter(pk=order.pk).update(
        status=Order.Status.DRAFT, buyer=user, currency=org.billing_currency, stripe_session_id="",
        total_minor=sum(p["total_minor"] for p in priced), updated_at=timezone.now(),
    )  # fmt: skip
    if org.onboarding_state == Organization.Onboarding.AWAITING_PAYMENT:
        Organization.objects.filter(pk=org.pk).update(onboarding_state=Organization.Onboarding.ORDERING)
    order.refresh_from_db()
    return order


def _line_name(line: Line, titles: dict) -> str:
    offer = line.offer
    title = offer.program.title
    if offer.module_key:
        title = f"{title}: {titles.get((offer.program_id, offer.module_key), 'module')}"
    mode = f"live, {line.cohort.name}" if line.cohort_id else "recorded"
    return f"{title} ({mode})"[:250]


@transaction.atomic
def checkout(*, org: Organization, user) -> dict:
    order = open_order(org.id, lock=True)
    lines = list(Line.objects.filter(order=order).select_related("offer__program", "cohort")) if order else []
    if not lines:
        raise ServiceError("empty_order", "Add something to your order first.")
    # prices and places may have changed since the draft was saved: check again
    priced = _price(
        org, [{"offer_id": ln.offer_id, "cohort_id": ln.cohort_id, "seats": ln.seats} for ln in lines]
    )
    total = sum(p["total_minor"] for p in priced)
    if total != order.total_minor or any(
        p["unit_minor"] != ln.unit_minor for p, ln in zip(priced, lines, strict=True)
    ):
        raise ServiceError(
            "prices_changed", "Prices have changed since you built this order. Check it and try again."
        )
    cur = Currency.objects.filter(code=order.currency, is_active=True, stripe_supported=True).first()
    if cur is None or total <= 0:
        raise ServiceError("bad_currency", "This order can't be paid by card. Please contact us.")
    _expire_session(order)
    titles = _titles({ln.offer.program for ln in lines})
    # a company being set up goes back to its setup page; an open workspace to its seats
    back = (
        "/business/program-seats"
        if org.onboarding_state == Organization.Onboarding.ACTIVE
        else "/business/start"
    )
    session = gateway.create_checkout_session(
        mode="payment",
        line_items=[{"quantity": ln.seats, "price_data": {
            "currency": cur.code.lower(), "unit_amount": gateway.to_stripe_amount(ln.unit_minor, cur.code, cur.exponent),
            "product_data": {"name": _line_name(ln, titles)}}} for ln in lines],
        metadata={"kind": KIND, "id": str(order.id), "org_id": str(org.id)},
        # updated_at moves on every change and every checkout: a retry of THIS request reuses the session
        idempotency_key=f"pso-{order.id}-{int(order.updated_at.timestamp() * 1000)}",
        customer_email=user.email,
        success_url=f"{settings.FRONTEND_URL}{back}?paid=1",
        cancel_url=f"{settings.FRONTEND_URL}{back}",
    )  # fmt: skip
    Order.objects.filter(pk=order.pk).update(
        status=Order.Status.PENDING, stripe_session_id=session["id"], updated_at=timezone.now()
    )
    if org.onboarding_state == Organization.Onboarding.ORDERING:
        Organization.objects.filter(pk=org.pk).update(
            onboarding_state=Organization.Onboarding.AWAITING_PAYMENT
        )
    return {"checkout_url": session["url"]}


# ---------------------------------------------------------------- Stripe webhooks (staff context)
@transaction.atomic
def paid(session: dict, meta: dict) -> None:
    order = Order.objects.select_for_update().filter(pk=meta.get("id")).first()
    if order is None:
        log.warning("program_seats: order %s not found", meta.get("id"))
        return
    if order.status == Order.Status.PAID:
        return  # a retried webhook
    # a failed check raises: the webhook stores the error for the console and Stripe retries
    if session.get("id") != order.stripe_session_id:
        raise ServiceError(
            "old_session", f"Order {order.id} was paid through an old checkout page. Refund it in Stripe."
        )
    cur = Currency.objects.get(code=order.currency)
    expected = gateway.to_stripe_amount(order.total_minor, cur.code, cur.exponent)
    if session.get("amount_total") != expected or (session.get("currency") or "").upper() != cur.code:
        raise ServiceError("amount_mismatch", f"Order {order.id}: the paid amount doesn't match the order.")
    Order.objects.filter(pk=order.pk).update(
        status=Order.Status.PAID, paid_at=timezone.now(), payment_intent=session.get("payment_intent") or "",
        updated_at=timezone.now(),
    )  # fmt: skip
    Organization.objects.filter(pk=order.org_id).exclude(
        onboarding_state=Organization.Onboarding.ACTIVE
    ).update(
        onboarding_state=Organization.Onboarding.ACTIVE,
        status=Organization.Status.ACTIVE,
        updated_at=timezone.now(),
    )
    _event(
        order.org_id, Event.Action.ORDERED, actor=order.buyer, note=f"{order.currency} {order.total_minor}"
    )
    audit("program_seats.paid", "program_seat_order", order.id, org_id=order.org_id,
          data={"total_minor": order.total_minor, "currency": order.currency})  # fmt: skip


def expired(meta: dict, session_id: str) -> None:
    """The Stripe page closed unpaid: the order can be changed and paid again. Only the page the
    order is waiting on counts: closing an older one (we do that on every change) changes nothing."""
    if not session_id:
        return
    with transaction.atomic():
        n = Order.objects.filter(
            pk=meta.get("id"), status=Order.Status.PENDING, stripe_session_id=session_id
        ).update(status=Order.Status.DRAFT, stripe_session_id="", updated_at=timezone.now())
        if n:
            Organization.objects.filter(
                pk=meta.get("org_id"), onboarding_state=Organization.Onboarding.AWAITING_PAYMENT
            ).update(onboarding_state=Organization.Onboarding.ORDERING)


# ================================================================ orders and seats
def used_seats(line_ids) -> dict:
    rows = (
        Allocation.objects.filter(line_id__in=list(line_ids), status=Allocation.Status.ACTIVE)
        .values("line_id")
        .annotate(n=Count("id"))
    )
    return {r["line_id"]: r["n"] for r in rows}


def orders(org_id) -> list[dict]:
    """The company's orders, newest first, with their lines and seats used. Four queries."""
    found = list(Order.objects.filter(org_id=org_id).order_by("-created_at")[:50])
    lines = list(
        Line.objects.filter(order__in=found).select_related("offer__program", "cohort").order_by("created_at")
    )
    titles = _titles({ln.offer.program for ln in lines})
    used = used_seats([ln.id for ln in lines])
    by_order: dict = {}
    for ln in lines:
        by_order.setdefault(ln.order_id, []).append(ln)
    return [
        {"order": o, "lines": [(ln, titles.get((ln.offer.program_id, ln.offer.module_key)), used.get(ln.id, 0))
                               for ln in by_order.get(o.id, [])]}
        for o in found
    ]  # fmt: skip


def _paid_line(org_id, line_id, *, lock: bool) -> Line:
    qs = Line.objects.select_related("offer__program", "cohort").filter(
        pk=line_id, org_id=org_id, order__status=Order.Status.PAID
    )
    if lock:  # lock the row alone ("FOR UPDATE OF" can't name our schema-qualified tables)
        _lock_rows(qs.model, pk=line_id)
    line = qs.first()
    if line is None:
        raise ServiceError("not_found", "Seats not found.", status=404)
    return line


def _company_enrollment(org_id, user, program, *, lock: bool = False) -> Enrollment | None:
    qs = Enrollment.objects.filter(org_id=org_id, user=user, course=program).exclude(
        status=Enrollment.Status.SUPERSEDED
    )
    return (qs.select_for_update() if lock else qs).first()


def _resync(e: Enrollment) -> None:
    """Make the company enrolment cover exactly what its active seats pay for: the whole
    program if any seat is a whole-program one, otherwise their modules; placed in the live
    seat's intake, or not placed at all. No seat left: revoked (progress kept)."""
    seats = list(
        Allocation.objects.filter(enrollment=e, status=Allocation.Status.ACTIVE).select_related(
            "line__offer", "line"
        )
    )
    now = timezone.now()
    if not seats:
        Enrollment.objects.filter(pk=e.pk).update(
            status=Enrollment.Status.REVOKED, cohort_id=None, group_id=None, updated_at=now
        )  # progress stays on the enrolment; a later seat places them again (capacity checked)
        EnrollmentModule.objects.filter(enrollment=e, source=EnrollmentModule.Source.SEAT).delete()
        from apps.learning import live

        live.cancel_future_bookings(e.pk)
        return
    keys = {a.line.offer.module_key: a.id for a in seats if a.line.offer.module_key is not None}
    whole = any(a.line.offer.module_key is None for a in seats)
    fields = {"scope": Enrollment.Scope.PROGRAM if whole else Enrollment.Scope.MODULES, "source_ref": seats[-1].id,
              "source": Enrollment.Source.ORGANIZATION}  # fmt: skip
    if e.status not in HAS_ACCESS or (e.access_expires_at and e.access_expires_at <= now):
        fields.update(status=Enrollment.Status.ACTIVE, access_expires_at=None)
    EnrollmentModule.objects.filter(enrollment=e).exclude(module_key__in=list(keys)).delete()
    for key, alloc_id in keys.items():
        EnrollmentModule.objects.get_or_create(
            enrollment=e, module_key=key,
            defaults={"user_id": e.user_id, "org_id": e.org_id, "source": EnrollmentModule.Source.SEAT,
                      "source_ref": alloc_id},
        )  # fmt: skip
    if not any(a.line.cohort_id for a in seats) and (e.cohort_id or e.group_id):
        fields.update(cohort_id=None, group_id=None)  # only recorded seats are left
    Enrollment.objects.filter(pk=e.pk).update(**fields, updated_at=now)


def _give(*, line: Line, member: OrgMember, actor, prefer_group_id=None, note: str = "") -> Allocation:
    """The seat goes to `member` (caller checked a seat is free and may give it)."""
    program = line.offer.program
    user = member.user
    if Allocation.objects.filter(line=line, user=user, status=Allocation.Status.ACTIVE).exists():
        raise ServiceError(
            "already_has_seat", f"{user.full_name or user.email} already has one of these seats."
        )
    e = _company_enrollment(line.org_id, user, program, lock=True)
    if e is not None and e.status in HAS_ACCESS:
        live = Allocation.objects.filter(
            enrollment=e, status=Allocation.Status.ACTIVE, line__cohort__isnull=False
        )
        if line.cohort_id and live.exclude(line__cohort_id=line.cohort_id).exists():
            raise ServiceError(
                "other_intake", f"{user.full_name or user.email} is already in another intake."
            )
        held = Allocation.objects.filter(enrollment=e, status=Allocation.Status.ACTIVE).select_related(
            "line__offer"
        )
        for a in held:  # a live seat covers recorded too; the whole program covers every module
            as_good = a.line.cohort_id is not None or not line.cohort_id
            if as_good and a.line.offer.module_key in (None, line.offer.module_key):
                raise ServiceError("already_has_seat", f"{user.full_name or user.email} already has this.")
    if e is None:
        e = learning.enrol(
            user=user, course=program, source=Enrollment.Source.ORGANIZATION, org_id=line.org_id
        )
    alloc = Allocation.objects.create(org_id=line.org_id, line=line, member=member, user=user, enrollment=e,
                                      allocated_by=actor)  # fmt: skip
    _resync(e)
    e.refresh_from_db()
    if line.cohort_id:
        selling._place(e, user, line.cohort, program, prefer_group_id=prefer_group_id)
    _event(
        line.org_id, Event.Action.ALLOCATED, actor=actor, line=line, allocation=alloc, target=user, note=note
    )
    from apps.engagement.notify import notify

    notify([user.id], "program_seat_given", {"program": program.title}, url="/learn",
           dedupe=f"seat:{alloc.id}")  # fmt: skip
    return alloc


@transaction.atomic
def allocate(*, request, scope: Scope, line_id, user_id) -> Allocation:
    line = _paid_line(scope.org_id, line_id, lock=True)
    member = (
        scope.members(OrgMember.objects.filter(user_id=user_id, removed_at__isnull=True))
        .select_related("user")
        .first()
    )
    if member is None:
        raise ServiceError("not_found", "Person not found in your area.", status=404)
    if used_seats([line.id]).get(line.id, 0) >= line.seats:
        raise ServiceError("no_seats_left", "Every seat on this line is taken. Buy more seats or swap one.")
    alloc = _give(line=line, member=member, actor=request.user)
    audit_request(request, "program_seat.allocated", "program_seat_allocation", alloc.id,
                  {"line": str(line.id), "user": str(member.user_id)})  # fmt: skip
    return alloc


def _seat(scope: Scope, allocation_id, *, lock: bool = True) -> Allocation:
    qs = Allocation.objects.select_related(
        "line__offer__program", "line__cohort", "enrollment", "user"
    ).filter(pk=allocation_id, org_id=scope.org_id)
    if lock:
        _lock_rows(Allocation, pk=allocation_id)
    alloc = qs.first()
    if alloc is None or not scope.members(OrgMember.objects.filter(pk=alloc.member_id)).exists():
        raise ServiceError("not_found", "Seat not found.", status=404)
    return alloc


@transaction.atomic
def release(*, request, scope: Scope, allocation_id) -> Allocation:
    """Undo a seat given by mistake: only before the learner has started. After that a seat
    moves only by a swap (D11)."""
    scope.require_admin()
    alloc = _seat(scope, allocation_id)
    if alloc.status != Allocation.Status.ACTIVE:
        raise ServiceError("not_active", "This seat is no longer held.")
    e = alloc.enrollment
    if e.last_accessed_at is not None or e.progress_pct > 0:
        raise ServiceError("already_started", "This learner has started. Request a swap instead.")
    if Swap.objects.filter(allocation=alloc, status__in=OPEN_SWAP).exists():
        raise ServiceError("swap_open", "A swap is waiting for this seat. Cancel it first.")
    Allocation.objects.filter(pk=alloc.pk).update(
        status=Allocation.Status.RELEASED, released_at=timezone.now(), released_by=request.user,
        updated_at=timezone.now(),
    )  # fmt: skip
    _resync(e)
    _event(scope.org_id, Event.Action.RELEASED, actor=request.user, line=alloc.line, allocation=alloc,
           previous=alloc.user)  # fmt: skip
    audit_request(request, "program_seat.released", "program_seat_allocation", alloc.id)
    alloc.status = Allocation.Status.RELEASED
    return alloc


# ================================================================ swaps (D11)
def week_of(start: date, today: date) -> int:
    return max((today - start).days // 7 + 1, 1)


def past_cutoff(alloc: Allocation, rule: ProgramSetting | None = None, today: date | None = None) -> bool:
    rule = rule or records.setting(alloc.line.offer.program_id)
    if rule.swap_cutoff_mode == ProgramSetting.SwapCutoff.NONE or not rule.swap_cutoff_value:
        return False
    if rule.swap_cutoff_mode == ProgramSetting.SwapCutoff.PROGRESS:
        return float(alloc.enrollment.progress_pct) >= rule.swap_cutoff_value
    today = today or timezone.localdate()
    start = (
        alloc.line.cohort.start_date if alloc.line.cohort_id else timezone.localtime(alloc.created_at).date()
    )
    return today >= start and week_of(start, today) >= rule.swap_cutoff_value


def _covers(scope: Scope, member_id) -> bool:
    return scope.is_admin or scope.members(OrgMember.objects.filter(pk=member_id)).exists()


def _company_approvers(org_id) -> list:
    return list(
        OrgMember.objects.filter(
            org_id=org_id, removed_at__isnull=True, role__in=(OrgMember.Role.OWNER, OrgMember.Role.ADMIN)
        ).values_list("user_id", flat=True)
    )


def _managers_of(member_id) -> list:
    """Users who manage a unit holding this member, or a unit above it."""
    from apps.org.models import UnitManager

    paths = list(MemberUnit.objects.filter(member_id=member_id).values_list("unit__path", flat=True))
    q = Q()
    for p in paths:
        q |= Q(unit__path__ancestor_of=p)
    if not paths:
        return []
    return list(
        UnitManager.objects.filter(q, member__removed_at__isnull=True).values_list(
            "member__user_id", flat=True
        )
    )


def _provider_approvers() -> list:
    from apps.identity.models import User
    from core.tenancy import tenant_context

    with tenant_context(staff=True):
        return list(
            User.objects.filter(is_staff=True, is_active=True)
            .filter(Q(is_superuser=True) | Q(staff_roles__role__permissions__contains=["seats.approve_swap"]))
            .values_list("id", flat=True)
            .distinct()
        )


def _tell(swap: Swap, alloc: Allocation) -> None:
    from apps.engagement.notify import notify

    ctx = {"program": alloc.line.offer.program.title, "from": alloc.user.full_name or alloc.user.email}
    if swap.status == Swap.Status.PENDING_COMPANY:
        notify(_company_approvers(swap.org_id) + _managers_of(swap.to_member_id), "seat_swap_company", ctx, url="/business/program-seats",
               dedupe=f"swap-company:{swap.id}")  # fmt: skip
    elif swap.status == Swap.Status.PENDING_PROVIDER:
        notify(_provider_approvers(), "seat_swap_provider", ctx, url="/console/seat-swaps",
               dedupe=f"swap-provider:{swap.id}")  # fmt: skip
    else:
        ctx["decision"] = "approved" if swap.status == Swap.Status.APPROVED else "not approved"
        notify([swap.requested_by_id], "seat_swap_decided", ctx, url="/business/program-seats",
               dedupe=f"swap-decided:{swap.id}")  # fmt: skip


@transaction.atomic
def request_swap(*, request, scope: Scope, allocation_id, to_user_id, reason: str) -> Swap:
    alloc = _seat(scope, allocation_id)
    if alloc.status != Allocation.Status.ACTIVE:
        raise ServiceError("not_active", "This seat is no longer held.")
    to = OrgMember.objects.filter(user_id=to_user_id, org_id=scope.org_id, removed_at__isnull=True).first()
    if to is None:
        raise ServiceError("not_found", "Person not found.", status=404)
    if to.user_id == alloc.user_id:
        raise ServiceError("same_person", "Choose someone else to take the seat.")
    if Allocation.objects.filter(
        line=alloc.line, user_id=to.user_id, status=Allocation.Status.ACTIVE
    ).exists():
        raise ServiceError("already_has_seat", "That person already has one of these seats.")
    if Swap.objects.filter(allocation=alloc, status__in=OPEN_SWAP).exists():
        raise ServiceError("swap_open", "A swap is already waiting for this seat.")
    reason = plain(reason or "").strip()[:2000]
    late = past_cutoff(alloc)
    if late and len(reason) < REASON_MIN:
        raise ServiceError("reason_required", "This seat is past the swap cut-off. Say why it needs to move.")
    company_ok = _covers(scope, to.id)
    now = timezone.now()
    swap = Swap.objects.create(
        org_id=scope.org_id, allocation=alloc, to_member=to, requested_by=request.user, reason=reason,
        after_cutoff=late, status=Swap.Status.PENDING_PROVIDER if company_ok else Swap.Status.PENDING_COMPANY,
        company_by=request.user if company_ok else None, company_at=now if company_ok else None,
    )  # fmt: skip
    _event(scope.org_id, Event.Action.SWAP_REQUESTED, actor=request.user, line=alloc.line, allocation=alloc,
           swap=swap, target=to.user, previous=alloc.user, note=reason)  # fmt: skip
    if company_ok:
        _event(scope.org_id, Event.Action.SWAP_COMPANY_APPROVED, actor=request.user, line=alloc.line,
               allocation=alloc, swap=swap)  # fmt: skip
    audit_request(request, "seat_swap.requested", "seat_swap", swap.id, {"after_cutoff": late})
    _tell(swap, alloc)
    return swap


def _open_swap(swap_id, *, org_id=None) -> Swap:
    _lock_rows(Swap, pk=swap_id)
    qs = Swap.objects.select_related(
        "allocation__line__offer__program", "allocation__line__cohort", "allocation__user", "allocation__enrollment",
        "to_member__user",
    ).filter(pk=swap_id)  # fmt: skip
    if org_id is not None:
        qs = qs.filter(org_id=org_id)
    swap = qs.first()
    if swap is None:
        raise ServiceError("not_found", "Swap request not found.", status=404)
    return swap


@transaction.atomic
def company_decide(*, request, scope: Scope, swap_id, approve: bool, note: str = "") -> Swap:
    swap = _open_swap(swap_id, org_id=scope.org_id)
    if swap.status != Swap.Status.PENDING_COMPANY:
        raise ServiceError("not_pending", "This request isn't waiting for the company.")
    if not _covers(scope, swap.to_member_id):
        raise ServiceError(
            "not_your_team", "Only an admin or the new person's manager can approve this.", status=403
        )
    now, note = timezone.now(), plain(note or "").strip()[:2000]
    if approve:
        swap.status, swap.company_by, swap.company_at = Swap.Status.PENDING_PROVIDER, request.user, now
        action = Event.Action.SWAP_COMPANY_APPROVED
    else:
        swap.status, swap.company_by, swap.company_at, swap.decision_note = (
            Swap.Status.REJECTED,
            request.user,
            now,
            note,
        )
        action = Event.Action.SWAP_REJECTED
    swap.save(update_fields=["status", "company_by", "company_at", "decision_note", "updated_at"])
    _event(scope.org_id, action, actor=request.user, line=swap.allocation.line, allocation=swap.allocation,
           swap=swap, note=note)  # fmt: skip
    audit_request(request, "seat_swap.company_decided", "seat_swap", swap.id, {"approve": approve})
    _tell(swap, swap.allocation)
    return swap


@transaction.atomic
def cancel_swap(*, request, scope: Scope, swap_id) -> Swap:
    swap = _open_swap(swap_id, org_id=scope.org_id)
    if swap.status not in OPEN_SWAP:
        raise ServiceError("not_pending", "This request has already been decided.")
    if swap.requested_by_id != request.user.id and not scope.is_admin:
        raise ServiceError(
            "forbidden", "Only the person who asked, or an admin, can cancel this.", status=403
        )
    swap.status = Swap.Status.CANCELLED
    swap.save(update_fields=["status", "updated_at"])
    _event(scope.org_id, Event.Action.SWAP_CANCELLED, actor=request.user, line=swap.allocation.line,
           allocation=swap.allocation, swap=swap)  # fmt: skip
    return swap


@transaction.atomic
def provider_decide(*, request, swap_id, approve: bool, note: str = "") -> Swap:
    """Console (staff context, seats.approve_swap checked by the endpoint). Approving moves the
    seat in this transaction: the old allocation is `swapped` and the old enrolment loses what
    the seat paid for (revoked when nothing else holds it; its progress stays on record)."""
    swap = _open_swap(swap_id)
    if swap.status != Swap.Status.PENDING_PROVIDER:
        raise ServiceError("not_pending", "This request isn't waiting for the provider.")
    old, now, note = swap.allocation, timezone.now(), plain(note or "").strip()[:2000]
    swap.provider_by, swap.provider_at, swap.decision_note = request.user, now, note
    if approve:
        _lock_rows(Allocation, pk=old.pk)
        old = Allocation.objects.select_related("line__offer__program", "line__cohort", "user").get(pk=old.pk)
        to = (
            OrgMember.objects.select_related("user")
            .filter(pk=swap.to_member_id, removed_at__isnull=True)
            .first()
        )
        if old.status != Allocation.Status.ACTIVE or to is None:
            raise ServiceError(
                "cannot_swap", "The seat or the new person has changed. Reject this request instead."
            )
        group_id = swap.allocation.enrollment.group_id
        Allocation.objects.filter(pk=old.pk).update(
            status=Allocation.Status.SWAPPED, released_at=now, released_by=request.user, updated_at=now
        )
        _resync(swap.allocation.enrollment)
        new = _give(line=old.line, member=to, actor=request.user, prefer_group_id=group_id,
                    note=f"Swap from {old.user.full_name or old.user.email}")  # fmt: skip
        swap.status, swap.new_allocation = Swap.Status.APPROVED, new
        action = Event.Action.SWAP_APPROVED
    else:
        swap.status = Swap.Status.REJECTED
        action = Event.Action.SWAP_REJECTED
    swap.save(
        update_fields=[
            "status",
            "provider_by",
            "provider_at",
            "decision_note",
            "new_allocation",
            "updated_at",
        ]
    )
    _event(swap.org_id, action, actor=request.user, line=old.line, allocation=old, swap=swap,
           target=swap.to_member.user, previous=old.user, note=note)  # fmt: skip
    audit_request(request, "seat_swap.provider_decided", "seat_swap", swap.id, {"approve": approve})
    _tell(swap, swap.allocation)
    return swap


# ================================================================ line manager view (D22)
def _scoped_seats(scope: Scope):
    qs = Allocation.objects.filter(org_id=scope.org_id, status=Allocation.Status.ACTIVE)
    if scope.unit_paths is not None:
        in_area = MemberUnit.objects.filter(
            member_id=OuterRef("member_id"), unit__path__descendant_of_any=list(scope.unit_paths)
        )
        qs = qs.filter(Exists(in_area))
    return qs


def _ksb_maps(programs: dict, rules: dict) -> dict:
    """{program_id: {ksb_item_id: {component keys}}} (D13: a KSB is met when its mapped live
    components are done). Two queries for the page, plus the component list of each program
    with a standard."""
    from apps.catalog.models import ComponentKsb, KsbItem

    with_std = {pid: rules[pid].ksb_standard_id for pid in programs if rules[pid].ksb_standard_id}
    if not with_std:
        return {}
    items: dict = {}
    for item_id, std in KsbItem.objects.filter(standard_id__in=set(with_std.values())).values_list(
        "id", "standard_id"
    ):
        items[item_id] = std
    out: dict = {pid: {} for pid in with_std}
    live = {pid: {c.key for c in records.components(programs[pid].live_version_id)} for pid in with_std}
    for pid, item_id, key in ComponentKsb.objects.filter(program_id__in=list(with_std)).values_list(
        "program_id", "item_id", "lecture_key"
    ):
        if items.get(item_id) == with_std[pid] and key in live[pid]:
            out[pid].setdefault(item_id, set()).add(key)
    return out


def team(scope: Scope, *, cursor=None, limit: int = 25) -> dict:
    """The seat holders the caller may see, one row per company enrolment, keyset by enrolment
    id. The queries per page don't grow with its rows (pinned by a test); they grow only with
    the number of programs on it (their component lists) and cohort schedules (cached)."""
    limit = max(1, min(limit, 50))
    seats = _scoped_seats(scope)
    qs = (
        Enrollment.objects.filter(org_id=scope.org_id)
        .filter(Exists(seats.filter(enrollment_id=OuterRef("pk"))))
        .select_related("user", "course", "cohort", "group")
        .order_by("id")
    )
    if cursor:
        qs = qs.filter(id__gt=cursor)
    page = list(qs[: limit + 1])
    more = len(page) > limit
    page = page[:limit]
    ids = [e.id for e in page]
    otj: dict = {}
    for r in (
        OtjEntry.objects.filter(enrollment_id__in=ids)
        .values("enrollment_id", "status")
        .annotate(m=Sum("minutes"))
    ):
        otj.setdefault(r["enrollment_id"], {})[r["status"]] = r["m"]
    done: dict = {}
    for eid, key in LectureProgress.objects.filter(
        enrollment_id__in=ids, completed_at__isnull=False
    ).values_list("enrollment_id", "lecture_key"):
        done.setdefault(eid, set()).add(key)
    attended = dict(
        SessionAttendance.objects.filter(enrollment_id__in=ids, minutes__gt=0)
        .values("enrollment_id")
        .annotate(n=Count("id"))
        .values_list("enrollment_id", "n")
    )
    from apps.delivery.models import LiveSession

    groups = {e.group_id for e in page if e.group_id}
    sessions: dict = {}
    for gid, at in LiveSession.objects.filter(
        group_id__in=groups, status=LiveSession.Status.SCHEDULED, starts_at__lt=timezone.now()
    ).values_list("group_id", "starts_at"):
        sessions.setdefault(gid, []).append(at)
    program_ids = {e.course_id for e in page}
    rules = _settings(program_ids)
    ksb_maps = _ksb_maps({e.course_id: e.course for e in page}, rules)
    modes = dict(
        seats.filter(enrollment_id__in=ids, line__cohort__isnull=False).values_list(
            "enrollment_id", "line__cohort_id"
        )
    )
    today = timezone.localdate()
    rows = []
    for e in page:
        s = rules[e.course_id]
        summary = records.otj_summary(e, today, by_status=otj.get(e.id, {}), program_setting=s)
        mapped = ksb_maps.get(e.course_id, {})
        mine = done.get(e.id, set())
        met = sum(1 for keys in mapped.values() if keys <= mine)
        past = sum(1 for at in sessions.get(e.group_id, []) if at >= e.enrolled_at) if e.group_id else 0
        rows.append({
            "enrollment": e, "live": e.id in modes, "otj": summary,
            "ksb_met": met, "ksb_total": len(mapped),
            "sessions_past": past, "sessions_attended": min(attended.get(e.id, 0), past),
        })  # fmt: skip
    return {"rows": rows, "next": str(page[-1].id) if more and page else None}
