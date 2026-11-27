"""Console > Programs (M19): program settings, KSB standards and mapping, off-the-job hour
approvals and a learner's record.

Permissions (core.staff_perms):
  * settings and KSB mapping: read with programs.build OR cohorts.manage, write with programs.build;
  * KSB standards: programs.build;
  * approvals and a learner's record: cohorts.manage (any learner), or groups.teach for
    learners in groups the person tutors.
Every change is audited. Schema names start with ConsoleProgram / ConsoleKsb / ConsoleOtj.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Field, Schema

from apps.catalog import ksb_import
from apps.catalog.models import ComponentKsb, Course, KsbStandard
from apps.delivery import services as delivery_svc
from apps.learning import records
from apps.learning.models import Enrollment, OtjEntry
from core import cursor as keyset
from core.errors import ServiceError
from core.staff_perms import has_perm, require_perm

from ..services import audit_request
from .common import ConsoleIdOut, ConsoleOkOut, clamp, router, staff

BUILD, MANAGE, TEACH = "programs.build", "cohorts.manage", "groups.teach"


def _reader(request) -> None:
    staff(request)
    if not (has_perm(request, BUILD) or has_perm(request, MANAGE)):
        raise ServiceError("forbidden", "You don't have permission to do this.", status=403)


def _builder(request) -> None:
    staff(request)
    require_perm(request, BUILD)


def _program(program_id) -> Course:
    return get_object_or_404(Course, pk=program_id, kind=Course.Kind.PROGRAM, deleted_at__isnull=True)


def _learners_scope(request) -> Q:
    """Which enrolments this person may review: every one (cohorts.manage) or those in groups
    they tutor (groups.teach). Anyone else: 403."""
    staff(request)
    if has_perm(request, MANAGE):
        return Q()
    if has_perm(request, TEACH):
        return Q(group__tutor_id=request.user.id)
    raise ServiceError("forbidden", "You don't have permission to do this.", status=403)


# ---------------------------------------------------------------- schemas
class ConsoleProgramSettingsOut(Schema):
    ksb_standard_id: UUID | None
    otj_target_mode: str
    otj_target_value: float
    otj_amber_pct: int
    otj_daily_cap_min: int
    min_seats_per_line: int
    swap_cutoff_mode: str
    swap_cutoff_value: int
    can_build: bool


class ConsoleProgramSettingsIn(Schema):
    ksb_standard_id: UUID | None = None
    clear_ksb_standard: bool = False
    otj_target_mode: str | None = None
    otj_target_value: Decimal | None = Field(None, ge=0, le=10000)
    otj_amber_pct: int | None = Field(None, ge=1, le=100)
    otj_daily_cap_min: int | None = Field(None, ge=15, le=1440)
    min_seats_per_line: int | None = Field(None, ge=1, le=500)
    swap_cutoff_mode: str | None = None
    swap_cutoff_value: int | None = Field(None, ge=0, le=520)


class ConsoleKsbStandardOut(Schema):
    id: UUID
    code: str
    title: str
    version: str
    level: int | None
    source: str
    item_count: int


class ConsoleKsbItemOut(Schema):
    id: UUID
    code: str
    kind: str
    text: str


class ConsoleKsbStandardDetailOut(ConsoleKsbStandardOut):
    items: list[ConsoleKsbItemOut]


class ConsoleKsbFetchIn(Schema):
    code: str = Field(..., min_length=3, max_length=20)


class ConsoleKsbUploadIn(Schema):
    standard: dict[str, Any] | list[dict[str, Any]]  # a saved feed answer may be a list


class ConsoleKsbSavedOut(Schema):
    id: UUID
    added: int


class ConsoleKsbCustomIn(Schema):
    code: str = Field(..., min_length=2, max_length=40)
    title: str = Field(..., min_length=3, max_length=300)


class ConsoleKsbItemIn(Schema):
    kind: str
    text: str = Field(..., min_length=3, max_length=4000)


class ConsoleKsbComponentOut(Schema):
    lecture_key: UUID
    title: str
    kind: str
    week: str
    module: str | None
    item_ids: list[UUID]


class ConsoleKsbMapOut(Schema):
    standard: ConsoleKsbStandardDetailOut | None
    components: list[ConsoleKsbComponentOut]
    can_build: bool


class ConsoleKsbMapIn(Schema):
    item_ids: list[UUID] = Field(..., max_length=ksb_import.MAX_ITEMS)


class ConsoleOtjPendingOut(Schema):
    id: UUID
    enrollment_id: UUID
    learner_name: str
    learner_email: str
    program_title: str
    group_name: str | None
    occurred_on: date
    minutes: int
    note: str
    created_at: datetime


class ConsoleOtjPendingPageOut(Schema):
    items: list[ConsoleOtjPendingOut]
    next_cursor: str | None


class ConsoleOtjDecideIn(Schema):
    approve: bool
    note: str = Field("", max_length=500)


class ConsoleOtjSummaryOut(Schema):
    counted_min: int
    pending_min: int
    expected_min: int | None
    target_min: int | None
    target_mode: str
    rag: str | None
    daily_cap_min: int


class ConsoleRecordKsbOut(Schema):
    id: UUID
    code: str
    kind: str
    text: str
    status: str
    done: int
    total: int


class ConsoleRecordCpdModuleOut(Schema):
    module_key: UUID
    title: str
    earned_min: int
    available_min: int


class ConsoleRecordCpdOut(Schema):
    workshops_min: int = 0
    earned_min: int
    available_min: int
    modules: list[ConsoleRecordCpdModuleOut]


class ConsoleRecordCertificateOut(Schema):
    module_key: UUID
    module_title: str
    cpd_min: int
    verification_code: str
    issued_at: datetime


class ConsoleLearnerRecordOut(Schema):
    enrollment_id: UUID
    learner_name: str
    learner_email: str
    program_title: str
    slug: str
    otj: ConsoleOtjSummaryOut
    ksbs: list[ConsoleRecordKsbOut]
    cpd: ConsoleRecordCpdOut
    certificates: list[ConsoleRecordCertificateOut]


# ---------------------------------------------------------------- program settings
def _settings_out(request, program_id) -> dict:
    s = records.setting(program_id)
    return {
        "ksb_standard_id": s.ksb_standard_id, "otj_target_mode": s.otj_target_mode,
        "otj_target_value": float(s.otj_target_value), "otj_amber_pct": s.otj_amber_pct,
        "otj_daily_cap_min": s.otj_daily_cap_min, "min_seats_per_line": s.min_seats_per_line,
        "swap_cutoff_mode": s.swap_cutoff_mode, "swap_cutoff_value": s.swap_cutoff_value,
        "can_build": has_perm(request, BUILD),
    }  # fmt: skip


@router.get("/programs/{program_id}/settings", response=ConsoleProgramSettingsOut)
def program_settings(request, program_id: UUID):
    _reader(request)
    _program(program_id)
    return _settings_out(request, program_id)


@router.put("/programs/{program_id}/settings", response=ConsoleProgramSettingsOut)
def save_program_settings(request, program_id: UUID, body: ConsoleProgramSettingsIn):
    _builder(request)
    fields = body.dict(exclude={"clear_ksb_standard", "ksb_standard_id"}, exclude_none=True)
    if body.clear_ksb_standard:
        fields["ksb_standard_id"] = None
    elif body.ksb_standard_id is not None:
        fields["ksb_standard_id"] = body.ksb_standard_id
    delivery_svc.save_program_settings(program_id=program_id, by=request.user, **fields)
    audit_request(request, "program.settings", "course", program_id,
                  {k: str(v) for k, v in fields.items()})  # fmt: skip
    return _settings_out(request, program_id)


# ---------------------------------------------------------------- KSB standards
def _standard_row(s: KsbStandard, count: int) -> dict:
    return {"id": s.id, "code": s.code, "title": s.title, "version": s.version, "level": s.level,
            "source": s.source, "item_count": count}  # fmt: skip


def _standard_detail(s: KsbStandard) -> dict:
    items = list(s.items.order_by("position", "code").values("id", "code", "kind", "text"))
    return {**_standard_row(s, len(items)), "items": items}


@router.get("/ksb-standards", response=list[ConsoleKsbStandardOut])
def ksb_standards(request, q: str = ""):
    _reader(request)
    from django.db.models import Count

    qs = KsbStandard.objects.annotate(n=Count("items")).order_by("code", "-version")
    if q.strip():
        term = q.strip()[:80]
        qs = qs.filter(Q(code__icontains=term) | Q(title__icontains=term))
    return [_standard_row(s, s.n) for s in qs[:200]]


@router.get("/ksb-standards/{standard_id}", response=ConsoleKsbStandardDetailOut)
def ksb_standard(request, standard_id: UUID):
    _reader(request)
    return _standard_detail(get_object_or_404(KsbStandard, pk=standard_id))


@router.post("/ksb-imports/fetch", response=ConsoleKsbSavedOut)
def fetch_standard(request, body: ConsoleKsbFetchIn):
    _builder(request)
    parsed = ksb_import.fetch(body.code)
    std, added = ksb_import.save_standard(parsed, by=request.user)
    audit_request(request, "ksb.import", "ksb_standard", std.id, {"code": std.code, "added": added})
    return {"id": std.id, "added": added}


@router.post("/ksb-imports/upload", response=ConsoleKsbSavedOut)
def upload_standard(request, body: ConsoleKsbUploadIn):
    _builder(request)
    data = body.standard[0] if isinstance(body.standard, list) and body.standard else body.standard
    std, added = ksb_import.save_standard(ksb_import.parse(data), by=request.user)
    audit_request(request, "ksb.upload", "ksb_standard", std.id, {"code": std.code, "added": added})
    return {"id": std.id, "added": added}


@router.post("/ksb-standards", response=ConsoleIdOut)
def create_custom_standard(request, body: ConsoleKsbCustomIn):
    _builder(request)
    std = ksb_import.create_custom(code=body.code, title=body.title, by=request.user)
    audit_request(request, "ksb.create", "ksb_standard", std.id, {"code": std.code})
    return {"id": std.id}


@router.post("/ksb-standards/{standard_id}/items", response=ConsoleIdOut)
def add_custom_item(request, standard_id: UUID, body: ConsoleKsbItemIn):
    _builder(request)
    item = ksb_import.add_item(
        standard=get_object_or_404(KsbStandard, pk=standard_id), kind=body.kind, text=body.text
    )
    audit_request(request, "ksb.add_item", "ksb_standard", standard_id, {"code": item.code})
    return {"id": item.id}


# ---------------------------------------------------------------- KSB mapping
@router.get("/programs/{program_id}/ksb-map", response=ConsoleKsbMapOut)
def ksb_map(request, program_id: UUID):
    _reader(request)
    program = _program(program_id)
    s = records.setting(program_id)
    standard = KsbStandard.objects.filter(pk=s.ksb_standard_id).first() if s.ksb_standard_id else None
    mapped: dict = {}
    if standard:
        for key, item_id in ComponentKsb.objects.filter(
            program=program, item__standard_id=standard.id
        ).values_list("lecture_key", "item_id"):
            mapped.setdefault(key, []).append(item_id)
    return {
        "standard": _standard_detail(standard) if standard else None,
        "components": [
            {"lecture_key": c["lecture_key"], "title": c["title"], "kind": c["kind"], "week": c["section__title"],
             "module": c["section__module__title"], "item_ids": mapped.get(c["lecture_key"], [])}
            for c in ksb_import.program_components(program)
        ],
        "can_build": has_perm(request, BUILD),
    }  # fmt: skip


@router.put("/programs/{program_id}/ksb-map/{lecture_key}", response=ConsoleOkOut)
def set_ksb_map(request, program_id: UUID, lecture_key: UUID, body: ConsoleKsbMapIn):
    _builder(request)
    program = _program(program_id)
    n = ksb_import.set_component_ksbs(
        program=program, lecture_key=lecture_key, item_ids=body.item_ids,
        standard_id=records.setting(program_id).ksb_standard_id,
    )  # fmt: skip
    audit_request(request, "ksb.map", "course", program_id, {"lecture_key": str(lecture_key), "count": n})
    return {"ok": True}


# ---------------------------------------------------------------- off-the-job approvals
@router.get("/otj-pending", response=ConsoleOtjPendingPageOut)
def otj_pending(request, cursor: str | None = None, limit: int = 50):
    """Learner logs waiting for a decision, oldest first."""
    scope = _learners_scope(request)
    limit = clamp(limit, 100)
    enrolments = Enrollment.objects.filter(scope).values("id")
    qs = (
        OtjEntry.objects.filter(status=OtjEntry.Status.PENDING, enrollment_id__in=enrolments)
        .exclude(user_id=request.user.id)  # nobody approves their own hours
        .select_related("enrollment__user", "enrollment__course", "enrollment__group")
        .order_by("created_at", "id")
    )
    after = keyset.decode(cursor, 2)
    if after:
        qs = qs.filter(Q(created_at__gt=after[0]) | Q(created_at=after[0], id__gt=after[1]))
    rows = list(qs[: limit + 1])
    page = rows[:limit]
    return {
        "items": [
            {"id": e.id, "enrollment_id": e.enrollment_id, "learner_name": e.enrollment.user.full_name,
             "learner_email": e.enrollment.user.email, "program_title": e.enrollment.course.title,
             "group_name": e.enrollment.group.name if e.enrollment.group_id else None,
             "occurred_on": e.occurred_on, "minutes": e.minutes, "note": e.note, "created_at": e.created_at}
            for e in page
        ],
        "next_cursor": keyset.encode(page[-1].created_at.isoformat(), page[-1].id) if len(rows) > limit else None,
    }  # fmt: skip


@router.post("/otj/{entry_id}/decide", response=ConsoleOkOut)
def decide_otj(request, entry_id: UUID, body: ConsoleOtjDecideIn):
    scope = _learners_scope(request)
    entry = get_object_or_404(OtjEntry, pk=entry_id, enrollment__in=Enrollment.objects.filter(scope))
    records.decide(entry=entry, approve=body.approve, note=body.note, by=request.user)
    audit_request(request, "otj.approve" if body.approve else "otj.reject", "otj_entry", entry_id,
                  {"minutes": entry.minutes})  # fmt: skip
    return {"ok": True}


@router.get("/program-enrollments/{enrollment_id}/record", response=ConsoleLearnerRecordOut)
def learner_record(request, enrollment_id: UUID):
    scope = _learners_scope(request)
    e = get_object_or_404(
        Enrollment.objects.filter(scope).select_related("course", "user", "cohort"), pk=enrollment_id
    )
    return {**records.record(e), "learner_name": e.user.full_name, "learner_email": e.user.email}
