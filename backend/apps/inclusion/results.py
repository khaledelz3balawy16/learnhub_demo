"""Reading inclusion results, shared by the platform console (every learner) and a company's
workspace (its own current members, owners and admins only: user decision 2026-11-25).

`members` limits everything to the users of one company: a subquery of user ids. The
database enforces the same limit for companies (migration 0004), so a bug here can't widen it.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Schema

from . import selectors, services
from .models import Attempt, Section


class InclusionScoreOut(Schema):
    section_id: str
    title: str
    score: int
    max: int
    threshold: int | None  # the section's current threshold (None: no flag, or section removed)
    flagged: bool


class InclusionResultOut(Schema):
    attempt_id: UUID
    user_id: UUID
    name: str
    email: str
    submitted_at: datetime
    flag_count: int
    scores: list[InclusionScoreOut]


class InclusionSummaryOut(Schema):
    learners: int
    flagged: int


class InclusionSectionRefOut(Schema):
    id: UUID
    title: str


class InclusionResultsOut(Schema):
    items: list[InclusionResultOut]
    next_cursor: str | None
    summary: InclusionSummaryOut
    sections: list[InclusionSectionRefOut]  # for the "flagged in" filter


class InclusionAnswerOut(Schema):
    key: str
    text: str
    value: int
    label: str
    max: int


class InclusionAnswerGroupOut(Schema):
    section_id: str
    title: str
    score: int
    max: int
    threshold: int | None
    flagged: bool
    answers: list[InclusionAnswerOut]


class InclusionHistoryOut(Schema):
    attempt_id: UUID
    submitted_at: datetime
    flag_count: int


class InclusionDetailOut(Schema):
    attempt_id: UUID
    user_id: UUID
    name: str
    email: str
    consented_at: datetime
    submitted_at: datetime
    is_latest: bool
    flag_count: int
    groups: list[InclusionAnswerGroupOut]
    history: list[InclusionHistoryOut]


def _scores(attempt: Attempt, thresholds: dict) -> list[dict]:
    flagged = set(attempt.flagged)
    return [{**s, "threshold": thresholds.get(s["section_id"]), "flagged": s["section_id"] in flagged}
            for s in attempt.scores]  # fmt: skip


def list_results(*, members=None, q: str = "", flagged: bool | None = None, section: UUID | None = None,
                 cursor: str | None = None, limit: int = 30) -> dict:  # fmt: skip
    page, nxt = selectors.latest_results(
        q=q.strip()[:100], flagged=flagged, section_id=str(section) if section else None,
        cursor=cursor, limit=limit, user_ids=members,
    )  # fmt: skip
    thresholds = services.current_thresholds()
    return {
        "items": [
            {
                "attempt_id": a.id,
                "user_id": a.user_id,
                "name": a.user.full_name or a.user.email,
                "email": a.user.email,
                "submitted_at": a.submitted_at,
                "flag_count": a.flag_count,
                "scores": _scores(a, thresholds),
            }
            for a in page
        ],  # fmt: skip
        "next_cursor": nxt,
        "summary": selectors.summary(user_ids=members),
        "sections": list(Section.objects.order_by("position", "id").values("id", "title")),
    }


def result_detail(attempt_id: UUID, *, members=None) -> tuple[Attempt, dict]:
    rows = Attempt.objects.select_related("user").filter(submitted_at__isnull=False)
    if members is not None:
        rows = rows.filter(user_id__in=members)
    a = get_object_or_404(rows, pk=attempt_id)
    thresholds = services.current_thresholds()
    groups = [{**s, "answers": [i for i in a.items if i["section_id"] == s["section_id"]]}
              for s in _scores(a, thresholds)]  # fmt: skip
    history = (
        Attempt.objects.filter(user_id=a.user_id, submitted_at__isnull=False)
        .order_by("-submitted_at")
        .values("id", "submitted_at", "flag_count")[:50]
    )
    return a, {
        "attempt_id": a.id, "user_id": a.user_id, "name": a.user.full_name or a.user.email, "email": a.user.email,
        "consented_at": a.consented_at, "submitted_at": a.submitted_at, "is_latest": a.is_latest,
        "flag_count": a.flag_count, "groups": groups,
        "history": [{"attempt_id": h["id"], "submitted_at": h["submitted_at"], "flag_count": h["flag_count"]}
                    for h in history],
    }  # fmt: skip
