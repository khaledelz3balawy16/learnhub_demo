"""Console > Inclusion: edit the inclusion test and read learners' results.

Admins only (user decision 2026-11-25): superusers, and staff holding roles.manage, which
only the Admin role has, because whoever holds it can grant themselves anything else. Tutors,
other staff and employers never see this data. Every edit and every opened result is
written to the audit log, because the answers are special-category data (health and disability).
"""

from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Field, Schema

from apps.inclusion import results, selectors, services
from apps.inclusion.models import Question, Section
from core.staff_perms import require_perm

from ..services import audit_request
from .common import ConsoleIdOut, ConsoleOkOut, clamp, router, staff


def _admin(request) -> None:
    staff(request)
    require_perm(request, "roles.manage")


# ---------------------------------------------------------------- schemas
class ConsoleInclusionOptionSchema(Schema):
    label: str = Field(..., max_length=80)
    value: int


class ConsoleInclusionQuestionOut(Schema):
    id: UUID
    key: str
    text: str
    options: list[ConsoleInclusionOptionSchema]
    required: bool
    is_active: bool


class ConsoleInclusionSectionOut(Schema):
    id: UUID
    key: str
    title: str
    description: str
    flag_threshold: int | None
    is_active: bool
    max_score: int  # of its active questions
    questions: list[ConsoleInclusionQuestionOut]


class ConsoleInclusionEditorOut(Schema):
    sections: list[ConsoleInclusionSectionOut]
    default_options: list[ConsoleInclusionOptionSchema]


class ConsoleInclusionSectionIn(Schema):
    title: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=500)
    flag_threshold: int | None = Field(None, ge=0, le=1000)
    is_active: bool | None = None


class ConsoleInclusionQuestionIn(Schema):
    text: str | None = Field(None, max_length=500)
    options: list[ConsoleInclusionOptionSchema] | None = Field(None, max_length=services.MAX_OPTIONS)
    required: bool | None = None
    is_active: bool | None = None


class ConsoleInclusionOrderIn(Schema):
    ids: list[UUID] = Field(..., max_length=500)


# ---------------------------------------------------------------- editor
def _section_out(s: Section) -> dict:
    questions = list(s.questions.all())
    return {
        "id": s.id, "key": s.key, "title": s.title, "description": s.description,
        "flag_threshold": s.flag_threshold, "is_active": s.is_active, "questions": questions,
        "max_score": sum(max(o["value"] for o in q.options) for q in questions if q.is_active),
    }  # fmt: skip


@router.get("/inclusion/questions", response=ConsoleInclusionEditorOut)
def inclusion_editor(request):
    _admin(request)
    return {
        "sections": [_section_out(s) for s in selectors.editor()],
        "default_options": Question._meta.get_field("options").default(),
    }


@router.post("/inclusion/sections", response=ConsoleIdOut)
def inclusion_create_section(request, body: ConsoleInclusionSectionIn):
    _admin(request)
    s = services.create_section(
        title=body.title or "", description=body.description or "", flag_threshold=body.flag_threshold
    )
    audit_request(request, "inclusion.section_create", "inclusion_section", s.id, {"title": s.title})
    return {"id": s.id}


@router.patch("/inclusion/sections/{section_id}", response=ConsoleOkOut)
def inclusion_update_section(request, section_id: UUID, body: ConsoleInclusionSectionIn):
    _admin(request)
    section = get_object_or_404(Section, pk=section_id)
    fields = {k: getattr(body, k) for k in body.model_fields_set}  # flag_threshold: null turns the flag off
    services.update_section(section, fields=fields)
    audit_request(request, "inclusion.section_update", "inclusion_section", section.id,
                  {k: v for k, v in fields.items() if k != "description"})  # fmt: skip
    return {"ok": True}


@router.delete("/inclusion/sections/{section_id}", response=ConsoleOkOut)
def inclusion_delete_section(request, section_id: UUID):
    _admin(request)
    section = get_object_or_404(Section, pk=section_id)
    services.delete_section(section)
    audit_request(
        request, "inclusion.section_delete", "inclusion_section", section_id, {"title": section.title}
    )
    return {"ok": True}


@router.put("/inclusion/sections-order", response=ConsoleOkOut)
def inclusion_order_sections(request, body: ConsoleInclusionOrderIn):
    _admin(request)
    services.reorder(Section, body.ids)
    audit_request(request, "inclusion.section_order", "inclusion_section", None, None)
    return {"ok": True}


@router.post("/inclusion/sections/{section_id}/questions", response=ConsoleIdOut)
def inclusion_create_question(request, section_id: UUID, body: ConsoleInclusionQuestionIn):
    _admin(request)
    section = get_object_or_404(Section, pk=section_id)
    q = services.create_question(
        section, text=body.text or "", required=body.required is not False,
        options=[o.model_dump() for o in body.options] if body.options is not None else None,
    )  # fmt: skip
    audit_request(request, "inclusion.question_create", "inclusion_question", q.id, {"key": q.key})
    return {"id": q.id}


@router.patch("/inclusion/questions/{question_id}", response=ConsoleOkOut)
def inclusion_update_question(request, question_id: UUID, body: ConsoleInclusionQuestionIn):
    _admin(request)
    question = get_object_or_404(Question, pk=question_id)
    fields = body.model_dump(exclude_unset=True)
    services.update_question(question, fields=fields)
    audit_request(request, "inclusion.question_update", "inclusion_question", question.id,
                  {"key": question.key, "changed": sorted(fields)})  # fmt: skip
    return {"ok": True}


@router.delete("/inclusion/questions/{question_id}", response=ConsoleOkOut)
def inclusion_delete_question(request, question_id: UUID):
    _admin(request)
    question = get_object_or_404(Question, pk=question_id)
    question.delete()  # answers already given keep their own copy of the question
    audit_request(
        request, "inclusion.question_delete", "inclusion_question", question_id, {"key": question.key}
    )
    return {"ok": True}


@router.put("/inclusion/sections/{section_id}/questions-order", response=ConsoleOkOut)
def inclusion_order_questions(request, section_id: UUID, body: ConsoleInclusionOrderIn):
    _admin(request)
    services.reorder(Question, body.ids, section_id=section_id)
    audit_request(request, "inclusion.question_order", "inclusion_section", section_id, None)
    return {"ok": True}


# ---------------------------------------------------------------- results
@router.get("/inclusion/results", response=results.InclusionResultsOut)
def inclusion_results(request, q: str = "", flagged: bool | None = None, section: UUID | None = None,
                      cursor: str | None = None, limit: int = 30):  # fmt: skip
    _admin(request)
    out = results.list_results(q=q, flagged=flagged, section=section, cursor=cursor, limit=clamp(limit, 100))
    audit_request(request, "inclusion.results_list", "inclusion_attempt", None, {"rows": len(out["items"])})
    return out


@router.get("/inclusion/results/{attempt_id}", response=results.InclusionDetailOut)
def inclusion_result(request, attempt_id: UUID):
    _admin(request)
    a, out = results.result_detail(attempt_id)
    audit_request(request, "inclusion.result_view", "inclusion_attempt", a.id, {"user_id": str(a.user_id)})
    return out
