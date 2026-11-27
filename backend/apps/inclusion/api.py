"""Learner endpoints for the inclusion test, at /api/v1/inclusion/.

A learner only ever reads and writes their own attempt (user=request.user here, and RLS's
personal policy underneath). They never see scores or flags.

/company/results: a company's owners and admins read their CURRENT members' latest answers
(user decision 2026-11-25). Managers and learners can't; the database enforces the same rule
(migration 0004). Every list and every opened result goes in the audit log.
"""

from uuid import UUID

from ninja import Router

from core.auth import session_auth
from core.permissions import OrgRole, require_org_role

from . import results, services
from .models import Attempt
from .schemas import InclusionAnswersIn, InclusionMeOut, InclusionSavedOut, InclusionSubmittedOut
from .selectors import questionnaire

router = Router(tags=["inclusion"], auth=session_auth)


@router.get("/me", response=InclusionMeOut)
def me(request):
    sections = questionnaire()
    active = {str(q.id) for s in sections for q in s.active_questions}
    mine = list(Attempt.objects.filter(user=request.user).only("id", "submitted_at", "is_latest", "answers"))
    draft = next((a for a in mine if a.submitted_at is None), None)
    latest = next((a for a in mine if a.is_latest), None)
    # a retake starts from the last answers, so the learner only changes what's different
    start = draft or latest
    answers = {k: v for k, v in (start.answers if start else {}).items() if k in active}
    return {
        "sections": [
            {"id": s.id, "title": s.title, "description": s.description, "questions": s.active_questions}
            for s in sections
        ],
        "answers": answers,
        "has_draft": draft is not None,
        "consented": bool(mine),
        "last_submitted_at": latest.submitted_at if latest else None,
        "attempts": sum(1 for a in mine if a.submitted_at),
    }


@router.put("/me/draft", response=InclusionSavedOut)
def save_draft(request, body: InclusionAnswersIn):
    draft = services.save_draft(user=request.user, answers=body.answers, consent=body.consent)
    return {"ok": True, "saved_at": draft.updated_at}


@router.post("/me/submit", response=InclusionSubmittedOut)
def submit(request, body: InclusionAnswersIn):
    attempt = services.submit(user=request.user, answers=body.answers, consent=body.consent)
    return {"ok": True, "submitted_at": attempt.submitted_at}


# ---------------------------------------------------------------- company owners and admins
def _company_members(request):
    from apps.org.models import OrgMember

    require_org_role(request, OrgRole.ADMIN)
    return OrgMember.objects.filter(org_id=request.org_id, removed_at__isnull=True).values("user_id")


@router.get("/company/results", response=results.InclusionResultsOut)
def company_results(request, q: str = "", flagged: bool | None = None, section: UUID | None = None,
                    cursor: str | None = None, limit: int = 30):  # fmt: skip
    from apps.platform.services import audit_request

    members = _company_members(request)
    out = results.list_results(members=members, q=q, flagged=flagged, section=section, cursor=cursor,
                               limit=max(1, min(limit, 100)))  # fmt: skip
    audit_request(
        request, "inclusion.company_results_list", "inclusion_attempt", None, {"rows": len(out["items"])}
    )
    return out


@router.get("/company/results/{attempt_id}", response=results.InclusionDetailOut)
def company_result(request, attempt_id: UUID):
    from apps.platform.services import audit_request

    a, out = results.result_detail(attempt_id, members=_company_members(request))
    audit_request(
        request, "inclusion.company_result_view", "inclusion_attempt", a.id, {"user_id": str(a.user_id)}
    )
    return out
