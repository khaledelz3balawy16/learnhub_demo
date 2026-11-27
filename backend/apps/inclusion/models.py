"""Inclusion test: a self-report questionnaire that helps the provider spot learners who may
need support (technology, vision and hearing, dyslexia, ADHD, social anxiety, mood).

Postgres schema: inclusion.
    sections, questions   REFERENCE (core.rls.reference): every signed-in request reads them,
                          only staff write them (console > Inclusion questions).
    attempts              PERSONAL (core.rls.personal): only the learner and staff see a row.
                          The console further limits reading to admins (roles.manage).

The answers are special-category data (health and disability, UK GDPR art. 9), so:
  * nothing here is ever linked to a company, so an employer can never read it;
  * each attempt keeps a copy of the questions and answers as they were, so editing the
    questionnaire later never changes what a learner said;
  * a learner's flag ("may need support") is worked out from the section's CURRENT threshold,
    which admins edit; `flagged` is refreshed whenever a threshold changes.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.db import table
from core.models import BaseModel

SCHEMA = "inclusion"
User = settings.AUTH_USER_MODEL


class Section(BaseModel):
    key = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    position = models.PositiveIntegerField(default=0)
    # a section scoring at or above this is flagged "may need support"; NULL turns it off
    flag_threshold = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = table(SCHEMA, "sections")
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.title


def default_options() -> list[dict]:
    return [
        {"label": "Never / No", "value": 0},
        {"label": "Sometimes / Unsure", "value": 1},
        {"label": "Often", "value": 2},
        {"label": "Very often / Yes", "value": 3},
    ]


class Question(BaseModel):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="questions")
    key = models.CharField(max_length=40, unique=True)
    text = models.CharField(max_length=500)
    # [{"label": str, "value": int}], 2 to 6 choices with distinct values 0..10
    options = models.JSONField(default=default_options)
    position = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = table(SCHEMA, "questions")
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.key


class Attempt(BaseModel):
    """One go at the questionnaire. A draft (submitted_at NULL) keeps answers between visits;
    at most one draft and one latest submitted attempt per learner."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inclusion_attempts")
    consented_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_latest = models.BooleanField(default=False)
    answers = models.JSONField(default=dict)  # {"<question id>": value}, kept after submitting
    # on submit, a copy of each answered question as the learner saw it:
    # [{"question_id", "key", "section_id", "section", "text", "value", "label", "max"}]
    items = models.JSONField(default=list)
    # [{"section_id", "key", "title", "score", "max"}] in section order, set on submit
    scores = models.JSONField(default=list)
    flagged = models.JSONField(default=list)  # ids of the sections flagged under current thresholds
    flag_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = table(SCHEMA, "attempts")
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["user", "-submitted_at"], name="inc_attempt_user_idx"),
            models.Index(
                fields=["-submitted_at", "-id"], name="inc_attempt_latest_idx", condition=Q(is_latest=True)
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=Q(submitted_at__isnull=True), name="inc_one_draft"
            ),
            models.UniqueConstraint(fields=["user"], condition=Q(is_latest=True), name="inc_one_latest"),
        ]
