"""Inclusion test writes: the learner's draft and submission, and the console's editor.

Scores: a section's score is the sum of the chosen values of its active questions; its
maximum is the sum of each question's highest value. A section is flagged when its score is
at or above the section's flag_threshold (NULL: never flagged).
"""

from __future__ import annotations

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify

from core import html
from core.errors import ServiceError

from .models import Attempt, Question, Section
from .selectors import questionnaire

MAX_OPTIONS = 6
MAX_VALUE = 10


# ---------------------------------------------------------------- locks
FLAGS_LOCK = "inclusion:flags"


def _lock(key: str, *, shared: bool = False) -> None:
    """A transaction-scoped advisory lock. Per learner: a save and a submit (or two saves) run
    one after the other, so no second draft appears. FLAGS_LOCK: threshold edits run one at a
    time (exclusive) and a submission never scores against a threshold being changed (shared)."""
    fn = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    with connection.cursor() as cur:
        cur.execute(f"SELECT {fn}(hashtext(%s))", [key])


# ---------------------------------------------------------------- scoring
def flags_for(scores: list[dict], thresholds: dict[str, int | None]) -> list[str]:
    """Section ids flagged under `thresholds` ({section id: threshold}). A section that no
    longer exists has no threshold, so it is never flagged."""
    out = []
    for s in scores:
        limit = thresholds.get(s["section_id"])
        if limit is not None and s["score"] >= limit:
            out.append(s["section_id"])
    return out


def current_thresholds() -> dict[str, int | None]:
    return {str(i): t for i, t in Section.objects.values_list("id", "flag_threshold")}


@transaction.atomic
def refresh_flags() -> int:
    """After a threshold changes or a section goes: re-flag every submitted attempt.
    Returns how many changed."""
    _lock(FLAGS_LOCK)
    thresholds = current_thresholds()
    changed = []
    for a in (
        Attempt.objects.filter(submitted_at__isnull=False).only("id", "scores", "flagged").iterator(2000)
    ):
        flagged = flags_for(a.scores, thresholds)
        if flagged != a.flagged:
            a.flagged, a.flag_count = flagged, len(flagged)
            changed.append(a)
    Attempt.objects.bulk_update(changed, ["flagged", "flag_count"], batch_size=500)
    return len(changed)


# ---------------------------------------------------------------- learner
def _clean_answers(raw: dict, questions: dict[str, Question]) -> dict[str, int]:
    """Keep only answers to active questions, and refuse a value that isn't one of the
    question's choices."""
    out = {}
    for qid, value in (raw or {}).items():
        q = questions.get(str(qid))
        if q is None:
            continue  # a question removed since the page loaded: drop it quietly
        if value is None:
            continue
        if not isinstance(value, int) or value not in {o["value"] for o in q.options}:
            raise ServiceError(
                "bad_answer", "One of the answers isn't a valid choice.", details={"question": q.key}
            )
        out[str(q.id)] = value
    return out


def _active_questions() -> tuple[list[Section], dict[str, Question]]:
    sections = questionnaire()
    return sections, {str(q.id): q for s in sections for q in s.active_questions}


def _draft(user, *, consent: bool, lock: bool) -> Attempt:
    qs = Attempt.objects.select_for_update() if lock else Attempt.objects
    draft = qs.filter(user=user, submitted_at__isnull=True).first()
    if draft is not None:
        return draft
    if not consent:
        raise ServiceError("consent_needed", "Please agree to the note about how your answers are used.")
    return Attempt.objects.create(user=user, consented_at=timezone.now())


@transaction.atomic
def save_draft(*, user, answers: dict, consent: bool) -> Attempt:
    """Saves answers so far (the page saves as the learner goes)."""
    _lock(f"inclusion:user:{user.id}")
    _, questions = _active_questions()
    draft = _draft(user, consent=consent, lock=True)
    draft.answers = _clean_answers(answers, questions)
    draft.save(update_fields=["answers", "updated_at"])
    return draft


@transaction.atomic
def submit(*, user, answers: dict, consent: bool) -> Attempt:
    _lock(f"inclusion:user:{user.id}")
    _lock(FLAGS_LOCK, shared=True)
    sections, questions = _active_questions()
    if not questions:
        raise ServiceError("no_questions", "There are no questions to answer right now.")
    draft = _draft(user, consent=consent, lock=False)
    clean = _clean_answers(answers, questions)
    missing = [q.key for q in questions.values() if q.required and str(q.id) not in clean]
    if missing:
        raise ServiceError("unanswered", "Please answer every question.", details={"questions": missing})

    items, scores = [], []
    for s in sections:
        score = top = 0
        for q in s.active_questions:
            best = max(o["value"] for o in q.options)
            top += best
            value = clean.get(str(q.id))
            if value is None:
                continue
            score += value
            label = next(o["label"] for o in q.options if o["value"] == value)
            items.append({"question_id": str(q.id), "key": q.key, "section_id": str(s.id), "section": s.title,
                          "text": q.text, "value": value, "label": label, "max": best})  # fmt: skip
        scores.append({"section_id": str(s.id), "key": s.key, "title": s.title, "score": score, "max": top})

    flagged = flags_for(scores, {str(s.id): s.flag_threshold for s in sections})
    Attempt.objects.filter(user=user, is_latest=True).update(is_latest=False)
    draft.answers, draft.items, draft.scores = clean, items, scores
    draft.flagged, draft.flag_count = flagged, len(flagged)
    draft.submitted_at, draft.is_latest = timezone.now(), True
    draft.save()
    return draft


# ---------------------------------------------------------------- console editor
def clean_options(options: list[dict]) -> list[dict]:
    if not isinstance(options, list) or not 2 <= len(options) <= MAX_OPTIONS:
        raise ServiceError("bad_options", f"A question needs between 2 and {MAX_OPTIONS} answers.")
    out, seen = [], set()
    for o in options:
        label = html.plain(str((o or {}).get("label") or ""), 80).strip()
        value = (o or {}).get("value")
        if not label:
            raise ServiceError("bad_options", "Every answer needs a label.")
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_VALUE:
            raise ServiceError("bad_options", f"Answer scores must be whole numbers from 0 to {MAX_VALUE}.")
        if value in seen:
            raise ServiceError("bad_options", "Two answers can't have the same score.")
        seen.add(value)
        out.append({"label": label, "value": value})
    return sorted(out, key=lambda o: o["value"])


def _unique_key(base: str, taken) -> str:
    key, n = base, 2
    while taken(key):
        key, n = f"{base}-{n}"[:60], n + 1
    return key


@transaction.atomic
def create_section(*, title: str, description: str = "", flag_threshold: int | None = None) -> Section:
    title = html.plain(title, 120).strip()
    if not title:
        raise ServiceError("missing_title", "Give the section a title.")
    base = slugify(title)[:50] or "section"
    key = _unique_key(base, lambda k: Section.objects.filter(key=k).exists())
    last = Section.objects.aggregate(m=Max("position"))["m"] or 0
    return Section.objects.create(key=key, title=title, description=html.plain(description, 500),
                                  flag_threshold=flag_threshold, position=last + 1)  # fmt: skip


@transaction.atomic
def update_section(section: Section, *, fields: dict) -> Section:
    _lock(FLAGS_LOCK)  # before reading: the threshold change and its re-flag happen as one
    section.refresh_from_db()
    threshold_changed = "flag_threshold" in fields and fields["flag_threshold"] != section.flag_threshold
    if "title" in fields:
        section.title = html.plain(fields["title"] or "", 120).strip() or section.title
    if "description" in fields:
        section.description = html.plain(fields["description"] or "", 500)
    if "flag_threshold" in fields:
        section.flag_threshold = fields["flag_threshold"]
    if "is_active" in fields and fields["is_active"] is not None:
        section.is_active = fields["is_active"]
    section.save()
    if threshold_changed:
        refresh_flags()
    return section


@transaction.atomic
def delete_section(section: Section) -> None:
    """Answers already given keep their copy of the section; only the flag goes."""
    _lock(FLAGS_LOCK)
    section.delete()
    refresh_flags()


@transaction.atomic
def reorder(model, ids: list, **scope) -> None:
    rows = {str(r.id): r for r in model.objects.select_for_update().filter(**scope)}
    if sorted(rows) != sorted(str(i) for i in ids):
        raise ServiceError("bad_order", "The list changed while you were editing. Reload and try again.")
    for n, i in enumerate(ids, start=1):
        rows[str(i)].position = n
    model.objects.bulk_update(rows.values(), ["position"])


@transaction.atomic
def create_question(
    section: Section, *, text: str, options: list[dict] | None, required: bool = True
) -> Question:
    text = html.plain(text, 500).strip()
    if not text:
        raise ServiceError("missing_text", "Write the question.")
    prefix = (section.key.split("_")[0] or "q").upper()[:12]
    keys = set(Question.objects.filter(section=section).values_list("key", flat=True))
    n = len(keys) + 1
    key = _unique_key(f"{prefix}_{n:02d}", lambda k: k in keys or Question.objects.filter(key=k).exists())
    last = Question.objects.filter(section=section).aggregate(m=Max("position"))["m"] or 0
    return Question.objects.create(
        section=section, key=key, text=text, position=last + 1, required=required,
        options=clean_options(options) if options is not None else Question._meta.get_field("options").default(),
    )  # fmt: skip


@transaction.atomic
def update_question(question: Question, *, fields: dict) -> Question:
    if "text" in fields and fields["text"] is not None:
        question.text = html.plain(fields["text"], 500).strip() or question.text
    if fields.get("options") is not None:
        question.options = clean_options(fields["options"])
    for flag in ("required", "is_active"):
        if fields.get(flag) is not None:
            setattr(question, flag, fields[flag])
    question.save()
    return question
