"""Company program seats (M22). Mounted at /api/v1/corporate/program-seats/.

Signup needs only a signed-in user. Setting up (catalogue, draft, checkout) is for the
company's owner or admins and works while the workspace is still locked. Everything else
needs an active workspace: owners and admins see the whole company, managers their units.
Schema names start with `Seat` (unique across the API).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from ninja import Router, Schema
from pydantic import Field

from apps.org.models import Organization, OrgMember
from core.auth import session_auth
from core.permissions import OrgRole, org_scope, require_org, require_org_role

from . import program_seats as svc
from .models import ProgramSeatAllocation, ProgramSeatLine, ProgramSeatOrder, SeatSwapRequest

router = Router(tags=["corporate"], auth=session_auth)


# ---------------------------------------------------------------- schemas
class SeatSignupIn(Schema):
    name: str = Field(..., min_length=2, max_length=200)
    currency: str = Field("GBP", min_length=3, max_length=3)


class SeatSignupOut(Schema):
    org_id: UUID
    name: str
    onboarding_state: str


class SeatOfferOut(Schema):
    id: UUID
    module_key: UUID | None
    module_title: str | None
    mode: str
    unit_minor: int


class SeatIntakeOut(Schema):
    id: UUID
    name: str
    start_date: date
    end_date: date | None
    places_left: int | None


class SeatProgramOut(Schema):
    id: UUID
    title: str
    slug: str
    min_seats: int
    offers: list[SeatOfferOut]
    intakes: list[SeatIntakeOut]


class SeatCatalogueOut(Schema):
    currency: str
    exponent: int
    programs: list[SeatProgramOut]


class SeatLineOut(Schema):
    id: UUID
    offer_id: UUID
    program_id: UUID
    program_title: str
    module_key: UUID | None
    module_title: str | None
    mode: str
    cohort_id: UUID | None
    cohort_name: str | None
    cohort_start: date | None
    seats: int
    used: int
    unit_minor: int
    total_minor: int


class SeatOrderOut(Schema):
    id: UUID
    status: str
    currency: str
    total_minor: int
    created_at: datetime
    paid_at: datetime | None
    lines: list[SeatLineOut]


class SeatSetupOut(Schema):
    org_name: str
    onboarding_state: str
    currency: str
    exponent: int
    draft: SeatOrderOut | None


class SeatOrdersOut(Schema):
    exponent: int
    can_buy: bool
    items: list[SeatOrderOut]


class SeatDraftLineIn(Schema):
    offer_id: UUID
    cohort_id: UUID | None = None
    seats: int = Field(..., ge=1, le=500)


class SeatDraftIn(Schema):
    lines: list[SeatDraftLineIn] = Field(..., min_length=1, max_length=20)


class SeatCheckoutOut(Schema):
    checkout_url: str


class SeatAllocateIn(Schema):
    line_id: UUID
    user_id: UUID


class SeatHolderOut(Schema):
    id: UUID
    line_id: UUID
    user_id: UUID
    name: str
    email: str
    status: str
    progress_pct: float
    started: bool
    past_cutoff: bool
    open_swap_id: UUID | None
    allocated_at: datetime


class SeatHoldersOut(Schema):
    items: list[SeatHolderOut]
    can_release: bool


class SeatSwapIn(Schema):
    to_user_id: UUID
    reason: str = Field("", max_length=2000)


class SeatDecideIn(Schema):
    approve: bool
    note: str = Field("", max_length=2000)


class SeatSwapOut(Schema):
    id: UUID
    status: str
    program_title: str
    module_title: str | None
    from_name: str
    from_email: str
    to_name: str
    to_email: str
    reason: str
    after_cutoff: bool
    requested_by_name: str
    created_at: datetime
    decision_note: str
    can_decide: bool
    can_cancel: bool


class SeatSwapsOut(Schema):
    items: list[SeatSwapOut]


class SeatTeamRowOut(Schema):
    enrollment_id: UUID
    user_id: UUID
    name: str
    email: str
    program_title: str
    slug: str
    live: bool
    cohort_name: str | None
    group_name: str | None
    progress_pct: float
    ksb_met: int
    ksb_total: int
    otj_rag: str | None
    otj_counted_min: int
    otj_expected_min: int | None
    sessions_past: int
    sessions_attended: int


class SeatTeamOut(Schema):
    items: list[SeatTeamRowOut]
    next_cursor: str | None


# ---------------------------------------------------------------- helpers
def _org(request, *, allow_setup: bool) -> Organization:
    require_org_role(request, OrgRole.ADMIN, allow_setup=allow_setup)
    return Organization.objects.get(pk=require_org(request))


def _exponent(code: str) -> int:
    from apps.commerce.models import Currency

    return (Currency.objects.filter(code=code).values_list("exponent", flat=True).first()) or 2


def _name(user) -> str:
    return user.full_name or user.email


def _order_out(o: ProgramSeatOrder, lines: list) -> dict:
    return {
        "id": o.id, "status": o.status, "currency": o.currency, "total_minor": o.total_minor,
        "created_at": o.created_at, "paid_at": o.paid_at,
        "lines": [_line_out(ln, title, used) for ln, title, used in lines],
    }  # fmt: skip


def _line_out(ln: ProgramSeatLine, module_title, used: int) -> dict:
    o = ln.offer
    return {
        "id": ln.id, "offer_id": o.id, "program_id": o.program_id, "program_title": o.program.title,
        "module_key": o.module_key, "module_title": module_title, "mode": o.mode, "cohort_id": ln.cohort_id,
        "cohort_name": ln.cohort.name if ln.cohort_id else None,
        "cohort_start": ln.cohort.start_date if ln.cohort_id else None,
        "seats": ln.seats, "used": used, "unit_minor": ln.unit_minor, "total_minor": ln.total_minor,
    }  # fmt: skip


# ---------------------------------------------------------------- signup and setup (D8, D9)
@router.post("/signup", response=SeatSignupOut)
def signup(request, body: SeatSignupIn):
    org = svc.signup(user=request.user, name=body.name, currency=body.currency)
    return {"org_id": org.id, "name": org.name, "onboarding_state": org.onboarding_state}


@router.get("/setup", response=SeatSetupOut)
def setup(request):
    org = _org(request, allow_setup=True)
    found = [x for x in svc.orders(org.id) if x["order"].status in ("draft", "pending")]
    draft = _order_out(found[0]["order"], found[0]["lines"]) if found else None
    return {"org_name": org.name, "onboarding_state": org.onboarding_state, "currency": org.billing_currency,
            "exponent": _exponent(org.billing_currency), "draft": draft}  # fmt: skip


@router.get("/catalogue", response=SeatCatalogueOut)
def catalogue(request):
    return svc.catalogue(_org(request, allow_setup=True))


@router.put("/draft", response=SeatSetupOut)
def save_draft(request, body: SeatDraftIn):
    org = _org(request, allow_setup=True)
    svc.save_draft(org=org, user=request.user, lines=[ln.dict() for ln in body.lines])
    return setup(request)


@router.post("/draft/checkout", response=SeatCheckoutOut)
def checkout(request):
    org = _org(request, allow_setup=True)
    return svc.checkout(org=org, user=request.user)


# ---------------------------------------------------------------- orders and seats
@router.get("/orders", response=SeatOrdersOut)
def orders(request):
    scope = org_scope(request)
    org = Organization.objects.only("billing_currency").get(pk=scope.org_id)
    return {"exponent": _exponent(org.billing_currency), "can_buy": scope.is_admin,
            "items": [_order_out(x["order"], x["lines"]) for x in svc.orders(scope.org_id)]}  # fmt: skip


@router.get("/lines/{line_id}/holders", response=SeatHoldersOut)
def holders(request, line_id: UUID):
    scope = org_scope(request)
    line = svc._paid_line(scope.org_id, line_id, lock=False)
    rule = svc.records.setting(line.offer.program_id)
    in_area = scope.members(OrgMember.objects.all()).values("id")
    rows = list(
        ProgramSeatAllocation.objects.filter(line=line, member_id__in=in_area)
        .select_related("user", "enrollment", "line__offer", "line__cohort")
        .order_by("-created_at")[:500]
    )
    rows.sort(key=lambda a: a.status != ProgramSeatAllocation.Status.ACTIVE)  # held seats first, newest first
    open_swaps = dict(
        SeatSwapRequest.objects.filter(allocation__in=rows, status__in=svc.OPEN_SWAP).values_list(
            "allocation_id", "id"
        )
    )
    return {"can_release": scope.is_admin, "items": [{
        "id": a.id, "line_id": a.line_id, "user_id": a.user_id, "name": _name(a.user), "email": a.user.email,
        "status": a.status, "progress_pct": float(a.enrollment.progress_pct),
        "started": a.enrollment.last_accessed_at is not None or a.enrollment.progress_pct > 0,
        "past_cutoff": a.status == "active" and svc.past_cutoff(a, rule), "open_swap_id": open_swaps.get(a.id),
        "allocated_at": a.created_at,
    } for a in rows]}  # fmt: skip


@router.post("/allocate", response=SeatHolderOut)
def allocate(request, body: SeatAllocateIn):
    scope = org_scope(request)
    a = svc.allocate(request=request, scope=scope, line_id=body.line_id, user_id=body.user_id)
    a.enrollment.refresh_from_db()
    return {"id": a.id, "line_id": a.line_id, "user_id": a.user_id, "name": _name(a.user), "email": a.user.email,
            "status": a.status, "progress_pct": float(a.enrollment.progress_pct), "started": False,
            "past_cutoff": False, "open_swap_id": None, "allocated_at": a.created_at}  # fmt: skip


class SeatOkOut(Schema):
    ok: bool


@router.post("/allocations/{allocation_id}/release", response=SeatOkOut)
def release(request, allocation_id: UUID):
    svc.release(request=request, scope=org_scope(request), allocation_id=allocation_id)
    return {"ok": True}


# ---------------------------------------------------------------- swaps (D11)
def _swap_out(s: SeatSwapRequest, *, can_decide: bool, can_cancel: bool, titles: dict | None = None) -> dict:
    a = s.allocation
    offer = a.line.offer
    return {
        "id": s.id, "status": s.status, "program_title": offer.program.title,
        "module_title": (titles or {}).get((offer.program_id, offer.module_key)) if offer.module_key else None,
        "from_name": _name(a.user), "from_email": a.user.email,
        "to_name": _name(s.to_member.user), "to_email": s.to_member.user.email, "reason": s.reason,
        "after_cutoff": s.after_cutoff, "requested_by_name": _name(s.requested_by), "created_at": s.created_at,
        "decision_note": s.decision_note, "can_decide": can_decide, "can_cancel": can_cancel,
    }  # fmt: skip


SWAP_RELATED = ("allocation__user", "allocation__line__offer__program", "to_member__user", "requested_by")


@router.post("/allocations/{allocation_id}/swap", response=SeatSwapOut)
def request_swap(request, allocation_id: UUID, body: SeatSwapIn):
    scope = org_scope(request)
    s = svc.request_swap(request=request, scope=scope, allocation_id=allocation_id, to_user_id=body.to_user_id,
                         reason=body.reason)  # fmt: skip
    s = SeatSwapRequest.objects.select_related(*SWAP_RELATED).get(pk=s.pk)
    return _swap_out(s, can_decide=False, can_cancel=True)


@router.get("/swaps", response=SeatSwapsOut)
def swaps(request, open: bool = True):
    """Swaps touching the caller's area (the seat holder or the new person), newest first."""
    scope = org_scope(request)
    in_area = scope.members(OrgMember.objects.all()).values("id")
    qs = SeatSwapRequest.objects.filter(org_id=scope.org_id).select_related(*SWAP_RELATED)
    if scope.unit_paths is not None:
        from django.db.models import Q

        qs = qs.filter(Q(allocation__member_id__in=in_area) | Q(to_member_id__in=in_area))
    if open:
        qs = qs.filter(status__in=svc.OPEN_SWAP)
    rows = list(qs.order_by("-created_at")[:100])
    mine = set(
        scope.members(OrgMember.objects.filter(id__in=[s.to_member_id for s in rows])).values_list(
            "id", flat=True
        )
    )
    titles = svc._titles({s.allocation.line.offer.program for s in rows})
    return {"items": [_swap_out(
        s, titles=titles,
        can_decide=s.status == "pending_company" and (scope.is_admin or s.to_member_id in mine),
        can_cancel=s.status in svc.OPEN_SWAP and (scope.is_admin or s.requested_by_id == request.user.id),
    ) for s in rows]}  # fmt: skip


@router.post("/swaps/{swap_id}/decide", response=SeatOkOut)
def company_decide(request, swap_id: UUID, body: SeatDecideIn):
    svc.company_decide(request=request, scope=org_scope(request), swap_id=swap_id, approve=body.approve,
                       note=body.note)  # fmt: skip
    return {"ok": True}


@router.post("/swaps/{swap_id}/cancel", response=SeatOkOut)
def cancel_swap(request, swap_id: UUID):
    svc.cancel_swap(request=request, scope=org_scope(request), swap_id=swap_id)
    return {"ok": True}


# ---------------------------------------------------------------- line manager view (D22)
@router.get("/team", response=SeatTeamOut)
def team(request, cursor: UUID | None = None, limit: int = 25):
    scope = org_scope(request)
    page = svc.team(scope, cursor=cursor, limit=limit)
    items = []
    for r in page["rows"]:
        e, otj = r["enrollment"], r["otj"]
        items.append({
            "enrollment_id": e.id, "user_id": e.user_id, "name": _name(e.user), "email": e.user.email,
            "program_title": e.course.title, "slug": e.course.slug, "live": r["live"],
            "cohort_name": e.cohort.name if e.cohort_id else None, "group_name": e.group.name if e.group_id else None,
            "progress_pct": float(e.progress_pct), "ksb_met": r["ksb_met"], "ksb_total": r["ksb_total"],
            "otj_rag": otj["rag"], "otj_counted_min": otj["counted_min"], "otj_expected_min": otj["expected_min"],
            "sessions_past": r["sessions_past"], "sessions_attended": r["sessions_attended"],
        })  # fmt: skip
    return {"items": items, "next_cursor": page["next"]}
