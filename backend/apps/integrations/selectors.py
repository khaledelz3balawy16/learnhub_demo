"""HR system reads (M17): a fixed number of queries per page, whatever its size.
The encrypted API key is never selected for a response."""

from __future__ import annotations

from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.org.models import OrgMember
from core import cursor as keyset
from core.permissions import Scope

from .models import (
    ExternalDepartment,
    ExternalLeave,
    ExternalPerson,
    ExternalTrainingRecord,
    HrConnection,
    HrSyncRun,
    HrTrainingMap,
)

SAFE_FIELDS = (
    "id", "org_id", "provider", "external_account_id", "account_name", "base_url", "status",
    "enabled_features", "last_verified_at", "last_sync_at", "last_error", "created_at",
)  # fmt: skip


def connection_for(org_id) -> HrConnection | None:
    return HrConnection.objects.filter(org_id=org_id).only(*SAFE_FIELDS).first()


def overview(conn: HrConnection) -> dict:
    """The headline counts, in one query per table."""
    people = ExternalPerson.objects.filter(connection=conn).aggregate(
        total=Count("id"),
        to_review=Count("id", filter=Q(mapping_status="pending", is_leaver=False)),
        linked=Count("id", filter=Q(mapping_status="matched")),
        invited=Count("id", filter=Q(mapping_status="invited")),
        leavers=Count("id", filter=Q(is_leaver=True)),
    )
    depts = ExternalDepartment.objects.filter(connection=conn).aggregate(
        total=Count("id"), linked=Count("id", filter=Q(status="linked"))
    )
    training = ExternalTrainingRecord.objects.filter(connection=conn).aggregate(
        total=Count("id"), applied=Count("id", filter=Q(applied_record__isnull=False))
    )
    today = timezone.now().date()
    on_leave = (
        ExternalLeave.objects.filter(connection=conn, starts_on__lte=today, ends_on__gte=today)
        .values("person_id")
        .distinct()
        .count()
    )
    run = HrSyncRun.objects.filter(connection=conn).order_by("-created_at").first()
    return {
        "people": people,
        "departments": depts,
        "training": training,
        "on_leave": on_leave,
        "latest_run": run,
    }


def people(
    scope: Scope, conn: HrConnection, *, status: str | None, q: str | None, cursor: str | None, limit: int
):
    """Breathe people A-Z, one keyset page. Managers see only people linked to members
    inside their units. Email matches are suggested with ONE extra query."""
    qs = ExternalPerson.objects.filter(org_id=scope.org_id, connection=conn).select_related("member__user")
    if not scope.is_admin:
        qs = qs.filter(member__in=scope.members(OrgMember.objects.filter(org_id=scope.org_id)))
    if status == "leaver":
        qs = qs.filter(is_leaver=True)
    elif status:
        qs = qs.filter(mapping_status=status)
    if q:
        qs = qs.filter(Q(display_name__icontains=q) | Q(email__icontains=q) | Q(job_title__icontains=q))
    after = keyset.decode(cursor, 2)
    if after:
        qs = qs.filter(Q(display_name__gt=after[0]) | Q(display_name=after[0], id__gt=after[1]))
    rows = list(qs.order_by("display_name", "id")[: limit + 1])
    page = rows[:limit]
    emails = {p.email.lower() for p in page if p.email and p.member_id is None}
    suggestions = {}
    if emails and scope.is_admin:
        linked = set(
            ExternalPerson.objects.filter(connection=conn, member__isnull=False).values_list(
                "member_id", flat=True
            )
        )
        for m in (
            OrgMember.objects.annotate(email_key=Lower("user__email"))
            .filter(org_id=scope.org_id, removed_at__isnull=True, email_key__in=emails)
            .select_related("user")
        ):
            if m.id not in linked:
                suggestions[m.user.email.lower()] = m
    return page, suggestions, keyset.encode(page[-1].display_name, page[-1].id) if len(rows) > limit else None


def runs(conn: HrConnection, limit: int = 20) -> list[HrSyncRun]:
    return list(
        HrSyncRun.objects.filter(connection=conn)
        .select_related("triggered_by")
        .order_by("-created_at")[:limit]
    )


def departments(conn: HrConnection) -> list[dict]:
    counts = dict(
        ExternalPerson.objects.filter(connection=conn)
        .values_list("department_external_id")
        .annotate(n=Count("id"))
        .values_list("department_external_id", "n")
    )
    return [
        {"dept": d, "people": counts.get(d.external_department_id, 0)}
        for d in ExternalDepartment.objects.filter(connection=conn)
        .select_related("unit")
        .order_by("name", "id")
    ]


def training_titles(conn: HrConnection) -> list[dict]:
    rows = (
        ExternalTrainingRecord.objects.filter(connection=conn)
        .values("title_key")
        .annotate(records=Count("id"), applied=Count("id", filter=Q(applied_record__isnull=False)))
        .order_by("title_key")
    )
    titles: dict[str, str] = {}
    for key, title in (
        ExternalTrainingRecord.objects.filter(connection=conn)
        .order_by("id")
        .values_list("title_key", "title")
    ):
        titles.setdefault(key, title)  # the first spelling Breathe sent, whatever the order of rows
    maps = {
        m.title_key: m for m in HrTrainingMap.objects.filter(connection=conn).select_related("requirement")
    }
    return [
        {"title": titles.get(r["title_key"], r["title_key"]), "records": r["records"], "applied": r["applied"],
         "map": maps.get(r["title_key"])}
        for r in rows
    ]  # fmt: skip


def training_records(scope: Scope, conn: HrConnection, limit: int = 100) -> list[ExternalTrainingRecord]:
    """Newest first. Managers see only records of linked people inside their units."""
    qs = ExternalTrainingRecord.objects.filter(org_id=scope.org_id, connection=conn)
    if not scope.is_admin:
        qs = qs.filter(person__member__in=scope.members(OrgMember.objects.filter(org_id=scope.org_id)))
    return list(qs.select_related("person", "applied_record").order_by("-completion_date", "-id")[:limit])


def leave_for_members(scope: Scope, member_ids: list) -> dict:
    """Current or next approved leave per member (for the "On leave" badges)."""
    today = timezone.now().date()
    allowed = scope.members(OrgMember.objects.filter(org_id=scope.org_id, pk__in=member_ids)).values("id")
    out: dict = {}
    for leave in (
        ExternalLeave.objects.filter(person__member_id__in=allowed, ends_on__gte=today)
        .select_related("person")
        .order_by("starts_on")
    ):
        out.setdefault(leave.person.member_id, leave)
    return out


def member_link(scope: Scope, member_id) -> ExternalPerson | None:
    allowed = scope.members(OrgMember.objects.filter(org_id=scope.org_id, pk=member_id)).values("id")
    return (
        ExternalPerson.objects.filter(member_id__in=allowed)
        .select_related("connection")
        .only("id", "external_employee_id", "display_name", "job_title", "department_name", "employment_status",
              "start_date", "is_leaver", "member_id", "connection__provider", "connection__status")
        .first()
    )  # fmt: skip
