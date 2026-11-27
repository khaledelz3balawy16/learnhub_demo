"""Program learner records (M19, plan D13-D15, D25): the off-the-job hours ledger, KSB status,
CPD roll-up and module certificates.

Writes: `sync_after_progress` (called from refresh_course_progress on every completion),
`log_hours`, `withdraw`, `decide`. Reads: `otj_summary`, `ksb_status`, `cpd_summary`, `record`.
Everything is keyed by lecture_key / module_key, so republishing a program never rewrites
a learner's history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import Course, Lecture, Module
from core import html
from core.errors import ServiceError

from .models import Enrollment, LectureProgress, ModuleCertificate, OtjEntry

COUNTED = (OtjEntry.Status.AUTO_APPROVED, OtjEntry.Status.APPROVED)


# ---------------------------------------------------------------- program content (one live version)
@dataclass(frozen=True)
class Component:
    key: uuid.UUID
    title: str
    module_id: uuid.UUID | None
    module_key: uuid.UUID | None
    module_title: str | None
    section_id: uuid.UUID
    required: bool
    otj_min: int
    cpd_min: int


def components(version_id) -> list[Component]:
    """The live version's components in order. One query."""
    rows = (
        Lecture.objects.filter(version_id=version_id)
        .order_by("section__position", "position")
        .values_list(
            "lecture_key",
            "title",
            "section__module_id",
            "section__module__module_key",
            "section__module__title",
            "section_id",
            "is_required",
            "expected_otj_min",
            "cpd_min",
        )
    )
    return [Component(*r) for r in rows]


def modules(version_id) -> list[Module]:
    return list(Module.objects.filter(version_id=version_id).order_by("position"))


def _done_keys(enrollment: Enrollment) -> set:
    return set(
        LectureProgress.objects.filter(enrollment=enrollment, completed_at__isnull=False).values_list(
            "lecture_key", flat=True
        )
    )


def setting(program_id):
    """The program's delivery settings, or an unsaved row holding the defaults."""
    from apps.delivery.models import ProgramSetting

    return ProgramSetting.objects.filter(program_id=program_id).first() or ProgramSetting(
        program_id=program_id
    )


# ---------------------------------------------------------------- writes
def sync_after_progress(enrollment: Enrollment, done: set | None = None) -> None:
    """Idempotent: an automatic OTJ entry for every completed component that expects OTJ
    minutes, and a certificate for every finished module. Programs only. Runs on every
    completion and heartbeat flush, so it inserts only what is new: four reads and no
    writes when nothing changed."""
    course = enrollment.course
    if course.kind != Course.Kind.PROGRAM or course.live_version_id is None:
        return
    done = _done_keys(enrollment) if done is None else done
    if not done:
        return
    parts = components(course.live_version_id)
    due = [c for c in parts if c.otj_min > 0 and c.key in done]
    if due:
        logged = set(
            OtjEntry.objects.filter(enrollment=enrollment, source=OtjEntry.Source.COMPONENT).values_list(
                "source_ref", flat=True
            )
        )
        due = [c for c in due if str(c.key) not in logged]
    today = timezone.localdate()
    auto = [
        OtjEntry(
            enrollment=enrollment, org_id=enrollment.org_id, user_id=enrollment.user_id,
            source=OtjEntry.Source.COMPONENT, source_ref=str(c.key), minutes=min(c.otj_min, 1440),
            occurred_on=today, status=OtjEntry.Status.AUTO_APPROVED, note=c.title[:1000],
        )
        for c in due
    ]  # fmt: skip
    if auto:
        OtjEntry.objects.bulk_create(auto, ignore_conflicts=True)  # unique (enrolment, source, ref)
    _issue_module_certificates(enrollment, parts, done)


def _issue_module_certificates(enrollment: Enrollment, parts: list[Component], done: set) -> None:
    have = set(ModuleCertificate.objects.filter(enrollment=enrollment).values_list("module_key", flat=True))
    by_module: dict = {}
    for c in parts:
        if c.module_key:
            by_module.setdefault(c.module_key, []).append(c)
    finished = [
        cs for key, cs in by_module.items()
        if key not in have and any(c.required for c in cs) and all(c.key in done for c in cs if c.required)
    ]  # fmt: skip
    if not finished:
        return
    now = timezone.now()
    name = enrollment.user.full_name or enrollment.user.email.split("@")[0]
    new = [
        ModuleCertificate(
            enrollment=enrollment, org_id=enrollment.org_id, user_id=enrollment.user_id,
            module_key=cs[0].module_key, module_title=(cs[0].module_title or "")[:200], recipient_name=name[:200],
            # the same sum as the CPD tab: every completed component of the module
            cpd_min=sum(c.cpd_min for c in cs if c.key in done), issued_at=now,
        )
        for cs in finished
    ]  # fmt: skip
    if new:
        ModuleCertificate.objects.bulk_create(new, ignore_conflicts=True)
        from apps.engagement import notify

        for cert in new:
            notify.notify([enrollment.user_id], "module_certificate_issued", {"module": cert.module_title},
                          url=f"/learn/{enrollment.course.slug}/record", dedupe=f"modcert:{enrollment.id}:{cert.module_key}")  # fmt: skip


def program_cpd_hours(enrollment: Enrollment) -> Decimal | None:
    """CPD hours printed on the program certificate: the completed components' CPD."""
    course = enrollment.course
    if course.kind != Course.Kind.PROGRAM or course.live_version_id is None:
        return None
    from .live import workshop_cpd_min

    done = _done_keys(enrollment)
    mins = sum(c.cpd_min for c in components(course.live_version_id) if c.key in done)
    mins += workshop_cpd_min(enrollment)  # attended workshops count too (D24)
    return (Decimal(mins) / 60).quantize(Decimal("0.1")) if mins else None


def _program_enrollment(enrollment: Enrollment) -> None:
    if enrollment.course.kind != Course.Kind.PROGRAM:
        raise ServiceError("not_program", "Off-the-job hours are recorded for programs only.")
    if enrollment.status not in (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED):
        raise ServiceError("no_access", "This enrolment is not active.", status=403)


@transaction.atomic
def log_hours(*, enrollment: Enrollment, occurred_on: date, minutes: int, note: str) -> OtjEntry:
    """A learner's own off-the-job log: waits for their tutor's approval."""
    _program_enrollment(enrollment)
    # one learner logs at a time per enrolment, so the daily cap can't be beaten by racing
    Enrollment.objects.select_for_update().filter(pk=enrollment.pk).values_list("pk").first()
    today = timezone.localdate()
    if occurred_on > today:
        raise ServiceError("future_date", "You can't log hours for a day that hasn't happened yet.")
    if occurred_on < timezone.localtime(enrollment.enrolled_at).date():
        raise ServiceError("too_early", "That day is before you joined the program.")
    text = html.plain(note, 1000).strip()
    if len(text) < 3:
        raise ServiceError("missing_note", "Say what you did.")
    cap = setting(enrollment.course_id).otj_daily_cap_min
    logged = (
        OtjEntry.objects.filter(enrollment=enrollment, source=OtjEntry.Source.MANUAL, occurred_on=occurred_on)
        .exclude(status=OtjEntry.Status.REJECTED)
        .aggregate(m=Sum("minutes"))["m"]
        or 0
    )
    if minutes < 1 or logged + minutes > cap:
        left = max(cap - logged, 0)
        raise ServiceError("daily_cap", f"You can log up to {left} more minutes for that day.")
    return OtjEntry.objects.create(
        enrollment=enrollment, org_id=enrollment.org_id, user_id=enrollment.user_id,
        source=OtjEntry.Source.MANUAL, source_ref=str(uuid.uuid4()), minutes=minutes,
        occurred_on=occurred_on, status=OtjEntry.Status.PENDING, note=text,
    )  # fmt: skip


@transaction.atomic
def withdraw(*, entry: OtjEntry) -> None:
    entry = OtjEntry.objects.select_for_update().get(pk=entry.pk)
    if entry.source != OtjEntry.Source.MANUAL or entry.status != OtjEntry.Status.PENDING:
        raise ServiceError("not_pending", "Only a log that is still waiting can be withdrawn.")
    entry.delete()


@transaction.atomic
def decide(*, entry: OtjEntry, approve: bool, note: str, by) -> OtjEntry:
    """A tutor's or cohort manager's decision on a learner log (callers check who)."""
    entry = OtjEntry.objects.select_for_update().select_related("enrollment__course").get(pk=entry.pk)
    if entry.user_id == by.id:
        raise ServiceError("own_entry", "You can't approve your own hours.", status=403)
    if entry.status != OtjEntry.Status.PENDING:
        raise ServiceError("already_decided", "This log has already been decided.")
    note = html.plain(note, 500).strip()
    if not approve and len(note) < 3:
        raise ServiceError("missing_reason", "Tell the learner why it wasn't approved.")
    entry.status = OtjEntry.Status.APPROVED if approve else OtjEntry.Status.REJECTED
    entry.decided_by, entry.decided_at, entry.decision_note = by, timezone.now(), note
    entry.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    from apps.engagement import notify

    code = "otj_approved" if approve else "otj_rejected"
    notify.notify([entry.user_id], code, {"minutes": entry.minutes, "day": f"{entry.occurred_on.day} {entry.occurred_on:%b %Y}", "note": note},
                  url=f"/learn/{entry.enrollment.course.slug}/record", dedupe=f"otj:{entry.id}")  # fmt: skip
    return entry


# ---------------------------------------------------------------- reads
def otj_summary(
    enrollment: Enrollment, today: date | None = None, *, by_status: dict | None = None, program_setting=None
) -> dict:
    """Counted minutes, pending minutes, expected-so-far and the RAG (D14). A list page passes
    `by_status` ({status: minutes}) and the program setting it fetched for the whole page."""
    today = today or timezone.localdate()
    if by_status is None:
        rows = OtjEntry.objects.filter(enrollment=enrollment).values("status").annotate(m=Sum("minutes"))
        by_status = {r["status"]: r["m"] for r in rows}
    actual = sum(by_status.get(s, 0) for s in COUNTED)
    s = program_setting if program_setting is not None else setting(enrollment.course_id)
    expected = target = None
    if s.otj_target_mode != "none" and s.otj_target_value and enrollment.cohort_id:
        from apps.delivery import selectors as delivery

        cohort = enrollment.cohort
        cohort.program = enrollment.course
        weeks = [w for m in delivery.schedule(cohort).modules for w in m.weeks]
        # Only the learner's own span counts (a late joiner can't log days before they joined),
        # and a week is owed once it has ended, not on its first day.
        joined = timezone.localtime(enrollment.enrolled_at).date()
        mine = [w for w in weeks if w.ends_on >= joined]
        elapsed = sum(1 for w in mine if w.ends_on < today)
        value = float(s.otj_target_value) * 60
        if s.otj_target_mode == "hours_per_week":
            expected, target = round(value * elapsed), round(value * len(mine))
        elif weeks:
            share = value * len(mine) / len(weeks)  # total hours, pro-rated to the learner's span
            expected = round(share * elapsed / len(mine)) if mine else 0
            target = round(share)
    rag = None
    if expected is not None:
        if actual >= expected:
            rag = "on_track"
        elif expected and actual * 100 >= expected * s.otj_amber_pct:
            rag = "behind"
        else:
            rag = "at_risk"
    return {
        "counted_min": actual,
        "pending_min": by_status.get(OtjEntry.Status.PENDING, 0),
        "expected_min": expected,
        "target_min": target,
        "target_mode": s.otj_target_mode,
        "rag": rag,
        "daily_cap_min": s.otj_daily_cap_min,
    }


def ksb_status(
    enrollment: Enrollment, done: set | None = None, parts: list[Component] | None = None
) -> list[dict]:
    """Every KSB of the program's standard, with its status from completion (D13). Two
    queries plus the shared component list."""
    from apps.catalog.models import ComponentKsb, KsbItem

    s = setting(enrollment.course_id)
    if s.ksb_standard_id is None:
        return []
    parts = parts if parts is not None else components(enrollment.course.live_version_id)
    live = {c.key for c in parts}
    done = _done_keys(enrollment) if done is None else done
    mapped: dict = {}
    for item_id, key in ComponentKsb.objects.filter(program_id=enrollment.course_id).values_list(
        "item_id", "lecture_key"
    ):
        if key in live:  # a mapping to a component no longer in the live version doesn't count
            mapped.setdefault(item_id, set()).add(key)
    out = []
    for item in KsbItem.objects.filter(standard_id=s.ksb_standard_id).order_by("position", "code"):
        keys = mapped.get(item.id, set())
        n = len(keys & done)
        status = (
            "not_mapped" if not keys else "met" if n == len(keys) else "in_progress" if n else "not_started"
        )
        out.append({"id": item.id, "code": item.code, "kind": item.kind, "text": item.text,
                    "status": status, "done": n, "total": len(keys)})  # fmt: skip
    return out


def cpd_summary(
    enrollment: Enrollment, done: set | None = None, parts: list[Component] | None = None
) -> dict:
    version_id = enrollment.course.live_version_id
    parts = parts if parts is not None else components(version_id)
    done = _done_keys(enrollment) if done is None else done
    rows = []
    for m in modules(version_id):
        mine = [c for c in parts if c.module_id == m.id]
        rows.append({"module_key": m.module_key, "title": m.title,
                     "earned_min": sum(c.cpd_min for c in mine if c.key in done),
                     "available_min": sum(c.cpd_min for c in mine)})  # fmt: skip
    from .live import workshop_cpd_min

    workshops = workshop_cpd_min(enrollment)
    return {
        "earned_min": sum(r["earned_min"] for r in rows) + workshops,
        "available_min": sum(r["available_min"] for r in rows),
        "workshops_min": workshops,
        "modules": rows,
    }


def record(enrollment: Enrollment) -> dict:
    """Everything the learner record page shows, sharing one component list and one
    completion set."""
    if enrollment.course.kind != Course.Kind.PROGRAM or enrollment.course.live_version_id is None:
        raise ServiceError("not_program", "This record is for programs only.")
    parts = components(enrollment.course.live_version_id)
    done = _done_keys(enrollment)
    certs = ModuleCertificate.objects.filter(enrollment=enrollment).order_by("issued_at")
    return {
        "enrollment_id": enrollment.id,
        "program_title": enrollment.course.title,
        "slug": enrollment.course.slug,
        "otj": otj_summary(enrollment),
        "ksbs": ksb_status(enrollment, done, parts),
        "cpd": cpd_summary(enrollment, done, parts),
        "certificates": [
            {
                "module_key": c.module_key,
                "module_title": c.module_title,
                "cpd_min": c.cpd_min,
                "verification_code": c.verification_code,
                "issued_at": c.issued_at,
            }
            for c in certs
        ],  # fmt: skip
    }
