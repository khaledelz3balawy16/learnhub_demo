"""Learner-side schemas (the console's live in apps/platform/console/inclusion.py)."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema


class InclusionOptionOut(Schema):
    label: str
    value: int


class InclusionQuestionOut(Schema):
    id: UUID
    text: str
    required: bool
    options: list[InclusionOptionOut]


class InclusionSectionOut(Schema):
    id: UUID
    title: str
    description: str
    questions: list[InclusionQuestionOut]


class InclusionMeOut(Schema):
    sections: list[InclusionSectionOut]
    answers: dict[str, int]  # question id -> value: the draft, or the last answers to start from
    has_draft: bool
    consented: bool  # has agreed before (a draft or an earlier submission)
    last_submitted_at: datetime | None
    attempts: int


class InclusionAnswersIn(Schema):
    answers: dict[str, int | None] = Field(default_factory=dict, max_length=500)
    consent: bool = False


class InclusionSavedOut(Schema):
    ok: bool
    saved_at: datetime


class InclusionSubmittedOut(Schema):
    ok: bool
    submitted_at: datetime
