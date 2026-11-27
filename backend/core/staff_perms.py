"""Provider staff permissions (Programs plan D20).

Roles are data (identity.StaffRole, edited in the console); the permission CODES are
code, because each one is checked by an endpoint. A milestone that adds a guarded action
adds its code here, with a plain-English label for the console checklist.

Rules:
  * superusers hold every permission;
  * anyone else must be staff AND hold the code through one of their roles;
  * the result is computed once per request (request._staff_perms).
"""

from __future__ import annotations

from core.errors import ServiceError

PERMISSIONS: dict[str, str] = {
    "programs.build": "Build programs (modules, weeks and components)",
    "cohorts.manage": "Manage cohorts, groups, closures and learner placement",
    "groups.teach": "Teach groups (can be chosen as a group's tutor)",
    "roles.manage": "Manage staff roles and who holds them",
    "reports.view": "See program reports",
    "seats.approve_swap": "Approve company seat swaps",
}

# The console's defaults (and tests). identity migration 0006 seeds a FROZEN copy of
# this list; the provider may reshape the roles afterwards.
DEFAULT_ROLES: list[tuple[str, str, list[str]]] = [
    ("Admin", "Everything, including staff roles.", list(PERMISSIONS)),
    ("Curriculum designer", "Builds programs and their content.", ["programs.build", "reports.view"]),
    ("Cohort manager", "Runs cohorts, groups and learner placement.", ["cohorts.manage", "reports.view"]),
    ("Tutor", "Teaches groups.", ["groups.teach"]),
]


def user_permissions(user) -> frozenset[str]:
    if not (user and user.is_authenticated and user.is_active):
        return frozenset()
    if user.is_superuser:
        return frozenset(PERMISSIONS)
    if not user.is_staff:
        return frozenset()
    from apps.identity.models import StaffRole

    codes = StaffRole.objects.filter(assignments__user_id=user.id).values_list("permissions", flat=True)
    return frozenset(c for perms in codes for c in perms if c in PERMISSIONS)


def permissions_for(request) -> frozenset[str]:
    cached = getattr(request, "_staff_perms", None)
    if cached is None:
        cached = user_permissions(request.user)
        request._staff_perms = cached
    return cached


def has_perm(request, code: str) -> bool:
    if code not in PERMISSIONS:  # a typo must never silently grant or deny
        raise ValueError(f"Unknown staff permission: {code}")
    return code in permissions_for(request)


def require_perm(request, code: str) -> None:
    if not has_perm(request, code):
        raise ServiceError("forbidden", "You don't have permission to do this.", status=403)
