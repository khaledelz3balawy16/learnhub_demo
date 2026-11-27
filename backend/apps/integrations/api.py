"""HR system endpoints (M17), mounted at /api/v1/integrations/.

Every endpoint needs X-Org-Id and at least the manager role. Managers read (only people
inside their units); owners and admins change things, and every change is written to
the company's audit trail. The API key goes in once and never comes back out.
"""

from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Query, Router

from apps.compliance.models import Requirement
from apps.identity.schemas import OkOut
from apps.org.models import JobRole, Organization, OrgMember, OrgUnit
from apps.platform.services import audit_request
from core.auth import session_auth
from core.errors import ServiceError
from core.permissions import OrgRole, Scope, org_scope

from . import breathe, secrets, selectors, services
from .models import ExternalDepartment, ExternalPerson, HrConnection, HrSyncRun
from .schemas import (
    HrConnectIn,
    HrConnectionOut,
    HrDepartmentLinkIn,
    HrDepartmentOut,
    HrFeaturesIn,
    HrInviteIn,
    HrInviteOut,
    HrKeyIn,
    HrLeaveOut,
    HrMatchIn,
    HrMemberLinkOut,
    HrOverviewOut,
    HrPauseIn,
    HrPersonPage,
    HrRunOut,
    HrTrainingMapIn,
    HrTrainingMapOut,
    HrTrainingRecordOut,
    HrTrainingTitleOut,
)

router = Router(tags=["hr-system"], auth=session_auth)


# ---------------------------------------------------------------- helpers
def _admin(request) -> Scope:
    scope = org_scope(request, OrgRole.MANAGER)
    scope.require_admin()
    return scope


def _conn(scope: Scope) -> HrConnection:
    conn = selectors.connection_for(scope.org_id)
    if conn is None:
        raise ServiceError("not_connected", "No HR system is connected yet.", status=404)
    return conn


def _conn_out(c: HrConnection) -> dict:
    return {
        "id": c.id, "provider": c.provider, "account_name": c.account_name,
        "external_account_id": c.external_account_id,
        "environment": "sandbox" if c.base_url == breathe.SANDBOX else "production",
        "status": c.status, "features": list(c.enabled_features or []),
        "last_verified_at": c.last_verified_at, "last_sync_at": c.last_sync_at, "last_error": c.last_error,
    }  # fmt: skip


def _run_out(r: HrSyncRun) -> dict:
    by = r.triggered_by
    return {
        "id": r.id, "status": r.status, "trigger": r.trigger, "counts": r.counts or {},
        "error_message": r.error_message, "triggered_by": (by.full_name or by.email) if by else None,
        "created_at": r.created_at, "started_at": r.started_at, "finished_at": r.finished_at,
    }  # fmt: skip


def _member_ref(m: OrgMember | None) -> dict | None:
    return {"member_id": m.id, "name": m.user.full_name or m.user.email, "email": m.user.email} if m else None


def _leave_out(leave) -> dict:
    today = timezone.now().date()
    return {"member_id": leave.person.member_id, "starts_on": leave.starts_on, "ends_on": leave.ends_on,
            "leave_type": leave.leave_type, "current": leave.starts_on <= today}  # fmt: skip


# ---------------------------------------------------------------- the connection
@router.get("/hr", response=HrOverviewOut)
def overview(request):
    scope = org_scope(request, OrgRole.MANAGER)
    conn = selectors.connection_for(scope.org_id)
    out = {"configured": secrets.is_configured(), "can_manage": scope.is_admin, "connection": None,
           "counts": None, "latest_run": None}  # fmt: skip
    if conn is None:
        return out
    o = selectors.overview(conn)
    p, d, t = o["people"], o["departments"], o["training"]
    out["connection"] = _conn_out(conn)
    out["counts"] = {
        "people": p["total"], "to_review": p["to_review"], "linked": p["linked"], "invited": p["invited"],
        "leavers": p["leavers"], "departments": d["total"], "departments_linked": d["linked"],
        "training": t["total"], "training_applied": t["applied"], "on_leave": o["on_leave"],
    }  # fmt: skip
    out["latest_run"] = _run_out(o["latest_run"]) if o["latest_run"] else None
    return out


@router.post("/hr/connect", response=HrConnectionOut)
def connect(request, body: HrConnectIn):
    scope = _admin(request)
    conn = services.connect(org_id=scope.org_id, api_key=body.api_key, environment=body.environment,
                            features=body.features, by=request.user)  # fmt: skip
    audit_request(request, "hr.connect", "hr_connection", conn.id,
                  {"account": conn.external_account_id, "environment": body.environment, "features": conn.enabled_features})  # fmt: skip
    try:
        services.queue_sync(conn=conn, trigger="connect", by=request.user)  # the first sync starts at once
    except ServiceError:  # a reconnect while a sync is still running: that run carries on
        pass
    return _conn_out(conn)


@router.post("/hr/validate", response=HrConnectionOut)
def validate(request):
    scope = _admin(request)
    conn = services.validate(conn=_conn(scope))
    audit_request(request, "hr.validate", "hr_connection", conn.id)
    return _conn_out(conn)


@router.post("/hr/replace-key", response=HrConnectionOut)
def replace_key(request, body: HrKeyIn):
    scope = _admin(request)
    conn = services.replace_key(conn=HrConnection.objects.get(pk=_conn(scope).pk), api_key=body.api_key)
    audit_request(request, "hr.replace_key", "hr_connection", conn.id)  # never the key itself
    return _conn_out(conn)


@router.patch("/hr/features", response=HrConnectionOut)
def set_features(request, body: HrFeaturesIn):
    scope = _admin(request)
    conn = services.set_features(conn=HrConnection.objects.get(pk=_conn(scope).pk), features=body.features)
    audit_request(request, "hr.features", "hr_connection", conn.id, {"features": conn.enabled_features})
    return _conn_out(conn)


@router.post("/hr/pause", response=HrConnectionOut)
def pause(request, body: HrPauseIn):
    scope = _admin(request)
    conn = services.set_paused(conn=HrConnection.objects.get(pk=_conn(scope).pk), paused=body.paused)
    audit_request(request, "hr.pause" if body.paused else "hr.resume", "hr_connection", conn.id)
    return _conn_out(conn)


@router.delete("/hr", response=OkOut)
def disconnect(request):
    scope = _admin(request)
    conn = HrConnection.objects.get(pk=_conn(scope).pk)
    services.disconnect(conn=conn)
    audit_request(request, "hr.disconnect", "hr_connection", conn.id)
    return {"ok": True}


# ---------------------------------------------------------------- syncing
@router.post("/hr/sync", response=HrRunOut)
def sync_now(request):
    scope = _admin(request)
    run = services.queue_sync(conn=_conn(scope), trigger="manual", by=request.user)
    audit_request(request, "hr.sync", "hr_sync_run", run.id)
    return _run_out(run)


@router.get("/hr/runs", response=list[HrRunOut])
def runs(request):
    scope = org_scope(request, OrgRole.MANAGER)
    return [_run_out(r) for r in selectors.runs(_conn(scope))]


@router.get("/hr/runs/{run_id}", response=HrRunOut)
def run_detail(request, run_id: UUID):
    scope = org_scope(request, OrgRole.MANAGER)
    return _run_out(
        get_object_or_404(HrSyncRun.objects.select_related("triggered_by"), pk=run_id, org_id=scope.org_id)
    )


# ---------------------------------------------------------------- people
@router.get("/hr/people", response=HrPersonPage)
def people(
    request, status: str | None = None, q: str | None = None, cursor: str | None = None, limit: int = 50
):
    scope = org_scope(request, OrgRole.MANAGER)
    page, suggestions, next_cursor = selectors.people(
        scope,
        _conn(scope),
        status=status,
        q=(q or "").strip()[:100] or None,
        cursor=cursor,
        limit=max(1, min(limit, 100)),
    )
    items = [
        {"id": p.id, "external_employee_id": p.external_employee_id, "name": p.display_name, "email": p.email,
         "job_title": p.job_title, "department": p.department_name, "employment_status": p.employment_status,
         "start_date": p.start_date, "contracted_hours": float(p.contracted_hours) if p.contracted_hours is not None else None,
         "working_pattern": p.working_pattern, "status": p.mapping_status, "is_leaver": p.is_leaver,
         "member": _member_ref(p.member), "suggestion": _member_ref(suggestions.get(p.email.lower())) if p.email else None}
        for p in page
    ]  # fmt: skip
    return {"items": items, "next_cursor": next_cursor}


def _person(scope: Scope, person_id: UUID) -> ExternalPerson:
    return get_object_or_404(
        ExternalPerson.objects.select_related("connection"), pk=person_id, org_id=scope.org_id
    )


@router.post("/hr/people/{person_id}/match", response=OkOut)
def match(request, person_id: UUID, body: HrMatchIn):
    scope = _admin(request)
    person = _person(scope, person_id)
    member = get_object_or_404(OrgMember, pk=body.member_id, org_id=scope.org_id, removed_at__isnull=True)
    services.match_person(person=person, member=member)
    audit_request(request, "hr.person.match", "hr_person", person.id, {"member": str(member.id)})
    return {"ok": True}


@router.post("/hr/people/{person_id}/invite", response=HrInviteOut)
def invite(request, person_id: UUID, body: HrInviteIn):
    from apps.org.tasks import send_invite_task

    scope = _admin(request)
    person = _person(scope, person_id)
    unit = (
        get_object_or_404(OrgUnit, pk=body.unit_id, org_id=scope.org_id, archived_at__isnull=True)
        if body.unit_id
        else None
    )
    job_role = (
        get_object_or_404(JobRole, pk=body.job_role_id, org_id=scope.org_id) if body.job_role_id else None
    )
    with transaction.atomic():
        inv, token = services.invite_person(person=person, role=body.role, unit=unit, job_role=job_role,
                                            by=request.user, by_role=scope.role.value)  # fmt: skip
        org_name = Organization.objects.filter(pk=scope.org_id).values_list("name", flat=True).first()
        inviter = request.user.full_name or request.user.email
        transaction.on_commit(lambda: send_invite_task.delay(inv.email, org_name, inviter, token))
        audit_request(
            request, "invite.create", "invite", inv.id, {"email": inv.email, "role": inv.role, "from": "hr"}
        )
    return {"invite_id": inv.id, "email": inv.email}


@router.post("/hr/people/{person_id}/ignore", response=OkOut)
def ignore(request, person_id: UUID):
    scope = _admin(request)
    person = services.ignore_person(person=_person(scope, person_id))
    audit_request(request, "hr.person.ignore", "hr_person", person.id)
    return {"ok": True}


@router.post("/hr/people/{person_id}/reset", response=OkOut)
def reset(request, person_id: UUID):
    scope = _admin(request)
    person = services.reset_person(person=_person(scope, person_id))
    audit_request(request, "hr.person.reset", "hr_person", person.id)
    return {"ok": True}


# ---------------------------------------------------------------- departments
@router.get("/hr/departments", response=list[HrDepartmentOut])
def departments(request):
    scope = org_scope(request, OrgRole.MANAGER)
    return [
        {"id": r["dept"].id, "external_department_id": r["dept"].external_department_id, "name": r["dept"].name,
         "status": r["dept"].status, "unit_id": r["dept"].unit_id,
         "unit_name": r["dept"].unit.name if r["dept"].unit else None, "people": r["people"]}
        for r in selectors.departments(_conn(scope))
    ]  # fmt: skip


@router.put("/hr/departments/{dept_id}/unit", response=HrDepartmentOut)
def link_department(request, dept_id: UUID, body: HrDepartmentLinkIn):
    scope = _admin(request)
    dept = get_object_or_404(
        ExternalDepartment.objects.select_related("connection"), pk=dept_id, org_id=scope.org_id
    )
    if body.create or body.unit_id:
        unit = (
            get_object_or_404(OrgUnit, pk=body.unit_id, org_id=scope.org_id, archived_at__isnull=True)
            if body.unit_id
            else None
        )
        dept = services.link_department(dept=dept, unit=unit, create=body.create)
        audit_request(
            request,
            "hr.department.link",
            "hr_department",
            dept.id,
            {"unit": str(dept.unit_id), "created": body.create},
        )
    else:
        dept = services.unlink_department(dept=dept)
        audit_request(request, "hr.department.unlink", "hr_department", dept.id)
    people = ExternalPerson.objects.filter(
        connection=dept.connection, department_external_id=dept.external_department_id
    ).count()
    return {"id": dept.id, "external_department_id": dept.external_department_id, "name": dept.name, "status": dept.status,
            "unit_id": dept.unit_id, "unit_name": dept.unit.name if dept.unit else None, "people": people}  # fmt: skip


# ---------------------------------------------------------------- training
@router.get("/hr/training/titles", response=list[HrTrainingTitleOut])
def training_titles(request):
    scope = org_scope(request, OrgRole.MANAGER)
    return [
        {"title": t["title"], "records": t["records"], "applied": t["applied"],
         "requirement_id": t["map"].requirement_id if t["map"] else None,
         "requirement_name": t["map"].requirement.name if t["map"] else None}
        for t in selectors.training_titles(_conn(scope))
    ]  # fmt: skip


@router.put("/hr/training/map", response=HrTrainingMapOut)
def map_training(request, body: HrTrainingMapIn):
    scope = _admin(request)
    conn = _conn(scope)
    req = (
        get_object_or_404(Requirement, pk=body.requirement_id, org_id=scope.org_id, archived_at__isnull=True)
        if body.requirement_id
        else None
    )
    applied = services.map_training(conn=conn, title=body.title, requirement=req)
    audit_request(request, "hr.training.map", "hr_connection", conn.id,
                  {"title": body.title[:200], "requirement": str(req.id) if req else None, "applied": applied})  # fmt: skip
    return {"applied": applied}


@router.get("/hr/training/records", response=list[HrTrainingRecordOut])
def training_records(request):
    scope = org_scope(request, OrgRole.MANAGER)
    return [
        {"id": r.id, "person_name": r.person.display_name if r.person else None, "title": r.title,
         "completion_date": r.completion_date, "status": r.status, "applied": r.applied_record_id is not None}
        for r in selectors.training_records(scope, _conn(scope))
    ]  # fmt: skip


# ---------------------------------------------------------------- badges elsewhere
@router.get("/hr/leave", response=list[HrLeaveOut])
def leave(request, member_ids: list[UUID] = Query(...)):  # noqa: B008 - Ninja's query declaration
    """Current or next approved leave for the people on a page (one call per page)."""
    scope = org_scope(request, OrgRole.MANAGER)
    if selectors.connection_for(scope.org_id) is None:
        return []
    return [_leave_out(lv) for lv in selectors.leave_for_members(scope, member_ids[:200]).values()]


@router.get("/hr/members/{member_id}", response=HrMemberLinkOut)
def member_link(request, member_id: UUID):
    scope = org_scope(request, OrgRole.MANAGER)
    person = selectors.member_link(scope, member_id)
    if person is None:
        return {"linked": False}
    leave = selectors.leave_for_members(scope, [member_id]).get(person.member_id)
    return {
        "linked": True, "provider": person.connection.get_provider_display(),
        "external_employee_id": person.external_employee_id, "job_title": person.job_title,
        "department": person.department_name, "employment_status": person.employment_status,
        "start_date": person.start_date, "is_leaver": person.is_leaver,
        "leave": _leave_out(leave) if leave else None,
    }  # fmt: skip
