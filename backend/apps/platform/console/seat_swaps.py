"""Console > Seat swaps (M22, D11): the provider's step of a company seat swap.

Needs `seats.approve_swap`. Waiting requests come first (oldest first, so nobody waits
longest); decided ones are listed newest first, keyset by creation time. Approving moves
the seat (apps.corporate.program_seats.provider_decide). Schema names start with ConsoleSeatSwap.
"""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema

from apps.corporate import program_seats as seats
from apps.corporate.models import SeatSwapRequest
from core.staff_perms import require_perm

from .common import ConsoleOkOut, router, staff

PERM = "seats.approve_swap"


class ConsoleSeatSwapOut(Schema):
    id: UUID
    status: str
    org_name: str
    program_title: str
    module_title: str | None
    mode: str
    cohort_name: str | None
    from_name: str
    from_email: str
    from_progress_pct: float
    to_name: str
    to_email: str
    reason: str
    after_cutoff: bool
    requested_by_name: str
    company_by_name: str | None
    created_at: datetime
    decision_note: str


class ConsoleSeatSwapsOut(Schema):
    items: list[ConsoleSeatSwapOut]
    next_cursor: str | None


class ConsoleSeatSwapDecideIn(Schema):
    approve: bool
    note: str = Field("", max_length=2000)


def _name(user) -> str:
    return (user.full_name or user.email) if user else ""


@router.get("/seat-swaps", response=ConsoleSeatSwapsOut)
def seat_swaps(request, waiting: bool = True, cursor: datetime | None = None, limit: int = 30):
    staff(request)
    require_perm(request, PERM)
    limit = max(1, min(limit, 100))
    qs = SeatSwapRequest.objects.select_related(
        "org", "allocation__user", "allocation__enrollment", "allocation__line__offer__program",
        "allocation__line__cohort", "to_member__user", "requested_by", "company_by",
    )  # fmt: skip
    if waiting:
        qs = qs.filter(status=SeatSwapRequest.Status.PENDING_PROVIDER).order_by("created_at", "id")
        if cursor:
            qs = qs.filter(created_at__gt=cursor)
    else:
        qs = qs.exclude(status__in=seats.OPEN_SWAP).order_by("-created_at", "-id")
        if cursor:
            qs = qs.filter(created_at__lt=cursor)
    rows = list(qs[: limit + 1])
    more = len(rows) > limit
    rows = rows[:limit]
    titles = seats._titles({s.allocation.line.offer.program for s in rows})
    items = []
    for s in rows:
        a = s.allocation
        offer = a.line.offer
        items.append({
            "id": s.id, "status": s.status, "org_name": s.org.name, "program_title": offer.program.title,
            "module_title": titles.get((offer.program_id, offer.module_key)) if offer.module_key else None,
            "mode": offer.mode, "cohort_name": a.line.cohort.name if a.line.cohort_id else None,
            "from_name": _name(a.user), "from_email": a.user.email,
            "from_progress_pct": float(a.enrollment.progress_pct),
            "to_name": _name(s.to_member.user), "to_email": s.to_member.user.email, "reason": s.reason,
            "after_cutoff": s.after_cutoff, "requested_by_name": _name(s.requested_by),
            "company_by_name": _name(s.company_by) or None, "created_at": s.created_at,
            "decision_note": s.decision_note,
        })  # fmt: skip
    return {"items": items, "next_cursor": rows[-1].created_at.isoformat() if more and rows else None}


@router.post("/seat-swaps/{swap_id}/decide", response=ConsoleOkOut)
def decide(request, swap_id: UUID, body: ConsoleSeatSwapDecideIn):
    staff(request)
    require_perm(request, PERM)
    seats.provider_decide(request=request, swap_id=swap_id, approve=body.approve, note=body.note)
    return {"ok": True}
