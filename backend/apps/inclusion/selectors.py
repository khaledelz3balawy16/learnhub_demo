"""Inclusion test reads."""

from __future__ import annotations

from django.db.models import Prefetch, Q

from core import cursor as keyset

from .models import Attempt, Question, Section


def questionnaire() -> list[Section]:
    """What a learner answers: active sections with at least one active question, in order.
    Each section gets `active_questions` (2 queries in all)."""
    sections = Section.objects.filter(is_active=True).prefetch_related(
        Prefetch("questions", queryset=Question.objects.filter(is_active=True), to_attr="active_questions")
    )
    return [s for s in sections if s.active_questions]


def editor() -> list[Section]:
    """Every section and question, hidden ones too (console editor)."""
    return list(Section.objects.prefetch_related("questions"))


def latest_results(*, q: str = "", flagged: bool | None = None, section_id: str | None = None,
                   cursor: str | None = None, limit: int = 30, user_ids=None):  # fmt: skip
    """Each learner's latest submitted attempt, newest first (keyset on submitted_at, id)."""
    rows = Attempt.objects.filter(is_latest=True).select_related("user")
    if user_ids is not None:
        rows = rows.filter(user_id__in=user_ids)
    if q:
        rows = rows.filter(Q(user__full_name__icontains=q) | Q(user__email__icontains=q))
    if flagged is True:
        rows = rows.filter(flag_count__gt=0)
    elif flagged is False:
        rows = rows.filter(flag_count=0)
    if section_id:
        rows = rows.filter(flagged__contains=[section_id])
    after = keyset.decode(cursor, 2)
    if after:
        rows = rows.filter(Q(submitted_at__lt=after[0]) | Q(submitted_at=after[0], id__lt=after[1]))
    page = list(rows.order_by("-submitted_at", "-id")[: limit + 1])
    more = len(page) > limit
    page = page[:limit]
    nxt = keyset.encode(page[-1].submitted_at.isoformat(), page[-1].id) if more and page else None
    return page, nxt


def summary(user_ids=None) -> dict:
    latest = Attempt.objects.filter(is_latest=True)
    if user_ids is not None:
        latest = latest.filter(user_id__in=user_ids)
    return {"learners": latest.count(), "flagged": latest.filter(flag_count__gt=0).count()}
