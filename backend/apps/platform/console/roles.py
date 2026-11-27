"""Console > Staff roles (M18, Programs plan D20): permission-based roles for provider staff.

Every endpoint needs roles.manage. Safety rules:
  * system roles (the seeded defaults) can be edited but not deleted;
  * a change may never leave the provider with no staff member holding roles.manage
    through a role, so staff can't lock themselves out (superusers don't count: they are
    a break-glass account, not the provider's admin);
  * only staff accounts can hold roles.
"""

from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from ninja import Field, Schema

from apps.identity.models import StaffRole, StaffRoleAssignment, User
from core import html
from core.errors import ServiceError
from core.staff_perms import PERMISSIONS, require_perm

from ..services import audit_request
from .common import ConsoleIdOut, ConsoleOkOut, router, staff

MANAGE = "roles.manage"


def _admin(request) -> None:
    staff(request)
    require_perm(request, MANAGE)


class ConsoleStaffPermissionOut(Schema):
    code: str
    label: str


class ConsoleStaffRoleOut(Schema):
    id: UUID
    name: str
    description: str
    permissions: list[str]
    is_system: bool
    member_count: int


class ConsoleStaffRolesOut(Schema):
    roles: list[ConsoleStaffRoleOut]
    permissions: list[ConsoleStaffPermissionOut]


class ConsoleStaffRoleIn(Schema):
    name: str | None = Field(None, min_length=2, max_length=80)
    description: str | None = Field(None, max_length=300)
    permissions: list[str] | None = Field(None, max_length=len(PERMISSIONS))


class ConsoleStaffRoleMemberOut(Schema):
    user_id: UUID
    name: str
    email: str


class ConsoleStaffRoleMemberIn(Schema):
    email: str = Field(..., min_length=3, max_length=320)


def _clean_perms(codes: list[str]) -> list[str]:
    unknown = [c for c in codes if c not in PERMISSIONS]
    if unknown:
        raise ServiceError("bad_permission", f"Unknown permission: {unknown[0]}")
    return sorted(set(codes))


def _lock_managers(role_id: UUID | None = None) -> None:
    """Take row locks on every role that grants roles.manage (and on `role_id`), in id
    order, BEFORE a change that could remove a manager. Two managers removing each other at
    once then run one after the other, so the second sees the first change (no write skew)."""
    ids = StaffRole.objects.filter(permissions__contains=[MANAGE]).values_list("id", flat=True)
    wanted = sorted({*ids, *([role_id] if role_id else [])})
    list(StaffRole.objects.select_for_update().filter(id__in=wanted).order_by("id").values_list("id"))


def _ensure_manager_left() -> None:
    """Called inside the change's transaction, after the change (and _lock_managers):
    refuse if no active staff member would still hold roles.manage."""
    left = StaffRoleAssignment.objects.filter(
        role__permissions__contains=[MANAGE], user__is_staff=True, user__is_active=True
    ).exists()
    if not left:
        raise ServiceError("last_manager", "Someone must still be able to manage staff roles.")


@router.get("/roles", response=ConsoleStaffRolesOut)
def roles(request):
    _admin(request)
    rows = StaffRole.objects.annotate(member_count=Count("assignments")).order_by("name")
    return {
        "roles": list(rows),
        "permissions": [{"code": c, "label": label} for c, label in PERMISSIONS.items()],
    }


@router.post("/roles", response=ConsoleIdOut)
def create_role(request, body: ConsoleStaffRoleIn):
    _admin(request)
    name = html.plain(body.name or "", 80).strip()
    if not name:
        raise ServiceError("missing_name", "Give the role a name.")
    try:
        with transaction.atomic():
            role = StaffRole.objects.create(
                name=name, description=html.plain(body.description or "", 300),
                permissions=_clean_perms(body.permissions or []),
            )  # fmt: skip
    except IntegrityError:
        raise ServiceError("duplicate", "A role with that name already exists.") from None
    audit_request(
        request, "role.create", "staff_role", role.id, {"name": name, "permissions": role.permissions}
    )
    return {"id": role.id}


@router.patch("/roles/{role_id}", response=ConsoleOkOut)
@transaction.atomic
def update_role(request, role_id: UUID, body: ConsoleStaffRoleIn):
    _admin(request)
    _lock_managers(role_id)
    role = get_object_or_404(StaffRole, pk=role_id)
    if body.name is not None:
        role.name = html.plain(body.name, 80).strip() or role.name
    if body.description is not None:
        role.description = html.plain(body.description, 300)
    if body.permissions is not None:
        role.permissions = _clean_perms(body.permissions)
    try:
        with transaction.atomic():
            role.save()
    except IntegrityError:
        raise ServiceError("duplicate", "A role with that name already exists.") from None
    _ensure_manager_left()
    audit_request(
        request, "role.update", "staff_role", role.id, {"name": role.name, "permissions": role.permissions}
    )
    return {"ok": True}


@router.delete("/roles/{role_id}", response=ConsoleOkOut)
@transaction.atomic
def delete_role(request, role_id: UUID):
    _admin(request)
    _lock_managers(role_id)
    role = get_object_or_404(StaffRole, pk=role_id)
    if role.is_system:
        raise ServiceError("system_role", "Built-in roles can be changed but not deleted.")
    role.delete()
    _ensure_manager_left()
    audit_request(request, "role.delete", "staff_role", role_id, {"name": role.name})
    return {"ok": True}


@router.get("/roles/{role_id}/members", response=list[ConsoleStaffRoleMemberOut])
def role_members(request, role_id: UUID):
    _admin(request)
    links = (
        StaffRoleAssignment.objects.filter(role_id=role_id).select_related("user").order_by("user__full_name")
    )
    return [{"user_id": a.user_id, "name": a.user.full_name or a.user.email, "email": a.user.email}
            for a in links[:500]]  # fmt: skip


@router.post("/roles/{role_id}/members", response=ConsoleOkOut)
def add_role_member(request, role_id: UUID, body: ConsoleStaffRoleMemberIn):
    _admin(request)
    role = get_object_or_404(StaffRole, pk=role_id)
    user = User.objects.filter(email=body.email.strip().lower(), is_active=True).first()
    if user is None or not user.is_staff:
        raise ServiceError("not_staff", "Only staff accounts can hold a staff role.")
    StaffRoleAssignment.objects.get_or_create(user=user, role=role, defaults={"assigned_by": request.user})
    audit_request(request, "role.add_member", "staff_role", role.id, {"user_id": str(user.id)})
    return {"ok": True}


@router.delete("/roles/{role_id}/members/{user_id}", response=ConsoleOkOut)
@transaction.atomic
def remove_role_member(request, role_id: UUID, user_id: UUID):
    _admin(request)
    _lock_managers(role_id)
    deleted, _ = StaffRoleAssignment.objects.filter(role_id=role_id, user_id=user_id).delete()
    if not deleted:
        raise ServiceError("not_found", "That person doesn't hold this role.", status=404)
    _ensure_manager_left()
    audit_request(request, "role.remove_member", "staff_role", role_id, {"user_id": str(user_id)})
    return {"ok": True}
