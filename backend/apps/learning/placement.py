"""Placing learners into program cohorts and groups (M18, Programs plan D3).

A placement is two columns on the learner's enrolment (cohort, group): one row per
learner and program, never a copy. Staff place learners from the console (cohorts.manage);
B2C checkout (M21) and B2B seat allocation (M22) will call the same functions.

Rules:
  * the group must be active and belong to an open/planned/running cohort of the program;
  * group and cohort capacity are enforced under a row lock (no oversubscription when two
    staff add people at once);
  * removing someone clears the placement only: progress is never deleted.
"""

from __future__ import annotations

from django.db import transaction

from apps.delivery.models import Cohort, Group
from core.errors import ServiceError

from .models import Enrollment
from .services import enrol

PLACEABLE = (Cohort.Status.PLANNED, Cohort.Status.OPEN, Cohort.Status.RUNNING)
COUNTED = (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED)


def _advisory(key: str) -> None:
    """Placement locks are advisory (per group, per cohort): a row lock (FOR UPDATE) would need
    write rights on delivery's reference tables, which a company or a learner never has (RLS),
    yet a company seat (M22) and a B2C checkout both place learners."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


def _locked_group(group_id) -> Group:
    _advisory(f"placement-group:{group_id}")
    group = Group.objects.select_related("cohort__program").filter(pk=group_id).first()
    if group is None:
        raise ServiceError("not_found", "Group not found.", status=404)
    if group.status != Group.Status.ACTIVE:
        raise ServiceError("group_closed", "This group is closed.")
    if group.cohort.status not in PLACEABLE:
        raise ServiceError("cohort_closed", "This cohort isn't taking learners.")
    return group


def _placed(cohort_id) -> dict:
    """{group_id: placed} for one cohort, counted over EVERY enrolment (personal and every
    company's) through the SECURITY DEFINER count: under RLS a company or a learner sees only
    its own rows, and a capacity check must never be fooled by that. Sees this transaction's
    own writes."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT group_id, placed FROM learning.cohort_seat_counts(%s::uuid[])", [[str(cohort_id)]]
        )
        return dict(cur.fetchall())


def _check_capacity(group: Group, adding: int, adding_to_cohort: int) -> None:
    counts = _placed(group.cohort_id)
    if group.capacity is not None:
        placed = counts.get(group.id, 0)
        if placed + adding > group.capacity:
            raise ServiceError(
                "group_full", f"“{group.name}” has room for {max(group.capacity - placed, 0)} more."
            )
    cohort = group.cohort
    if cohort.capacity is not None and adding_to_cohort:
        _advisory(f"placement-cohort:{cohort.pk}")  # serialise cohort-wide checks
        placed = sum(_placed(cohort.pk).values())
        if placed + adding_to_cohort > cohort.capacity:
            raise ServiceError(
                "cohort_full", f"This cohort has room for {max(cohort.capacity - placed, 0)} more."
            )


@transaction.atomic
def place(*, group_id, users: list, org_id=None) -> list[Enrollment]:
    """Put each user in the group (creating a personal enrolment when they have none; with
    `org_id`, their enrolment in that company: M22 seats). Someone already in another group
    of the same cohort is moved; someone in another cohort of the same program is moved too
    (their progress follows them)."""
    group = _locked_group(group_id)
    program = group.cohort.program
    current = {
        e.user_id: e
        for e in Enrollment.objects.filter(course=program, user__in=users, org_id=org_id).exclude(
            status=Enrollment.Status.SUPERSEDED
        )
    }
    if org_id is None:
        # staff placing someone who holds a company seat (M22: every group was full when the
        # seat was given) place that company enrolment; never a free personal one beside it
        # (also when their personal enrolment has ended: a refund never hides a paid seat)
        ended = {uid for uid, e in current.items() if e.status not in COUNTED}
        for e in Enrollment.objects.filter(
            course=program, user__in=[u for u in users if u.id not in current or u.id in ended],
            org__isnull=False, status__in=COUNTED,
        ).order_by("-enrolled_at"):  # fmt: skip
            if e.user_id in ended:
                current[e.user_id] = e
                ended.discard(e.user_id)
            else:
                current.setdefault(e.user_id, e)
    newcomers = [u for u in users if getattr(current.get(u.id), "group_id", None) != group.id]
    joining_cohort = sum(
        1 for u in newcomers if getattr(current.get(u.id), "cohort_id", None) != group.cohort_id
    )
    _check_capacity(group, len(newcomers), joining_cohort)
    out = []
    for user in newcomers:
        e = current.get(user.id) or enrol(
            user=user, course=program, source=Enrollment.Source.ADMIN_GRANT, org_id=org_id
        )
        if e.status in (Enrollment.Status.REVOKED, Enrollment.Status.EXPIRED):
            raise ServiceError("enrolment_ended", f"{user.email}'s access to this program has ended.")
        Enrollment.objects.filter(pk=e.pk).update(cohort_id=group.cohort_id, group_id=group.id)
        e.cohort_id, e.group_id = group.cohort_id, group.id
        out.append(e)
    return out


@transaction.atomic
def remove(*, enrollment: Enrollment) -> None:
    Enrollment.objects.filter(pk=enrollment.pk).update(cohort_id=None, group_id=None)
