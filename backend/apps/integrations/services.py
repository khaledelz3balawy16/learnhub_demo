"""HR system writes (M17). Endpoints and Celery tasks call these; Ninja stays out.

Everything runs inside the company's RLS context. Every error a person can see is a
ServiceError. Breathe is only ever read; nothing is written back to it.

Client decisions (docs/client-questions.md 23-28): the listed employee fields are
imported; an hourly sync plus "Sync now"; an email match is only a suggestion an admin
confirms; an admin maps each Breathe training title to a requirement and imported
records follow that requirement's renewal rule; leavers are flagged, never removed;
approved leave is shown to admins and managers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.compliance import engine
from apps.compliance.models import CompletionRecord, MemberStatus, Requirement
from apps.compliance.services import _add_months
from apps.org import services as org_services
from apps.org.models import Invite, OrgMember, OrgUnit, UnitManager
from core.errors import ServiceError
from core.tenancy import tenant_context

from . import breathe, normalizers, secrets
from .models import (
    ExternalDepartment,
    ExternalLeave,
    ExternalPerson,
    ExternalTrainingRecord,
    HrConnection,
    HrSyncRun,
    HrTrainingMap,
)

log = logging.getLogger(__name__)

HR_URL = "/business/hr-system"
PROVIDER = "Breathe HR"
STALE_RUN = timedelta(minutes=30)  # a run "running" longer than this is treated as dead
STOPPED = (HrConnection.Status.DISABLED, HrConnection.Status.PAUSED)  # an admin stopped syncing


# ---------------------------------------------------------------- helpers
def _base_url(environment: str) -> str:
    return breathe.SANDBOX if environment == "sandbox" else breathe.PRODUCTION


def _features(features) -> list[str]:
    return [f for f in HrConnection.FEATURES if f in set(features or ())]


def _clean_key(api_key: str) -> str:
    api_key = (api_key or "").strip()
    if len(api_key) < 8 or len(api_key) > 200:
        raise ServiceError("bad_key", "Paste the full API key from Breathe (Settings > API).")
    secrets.encrypt("check")  # fails early with 503 when the server has no encryption key
    return api_key


def _read_account(base_url: str, api_key: str) -> tuple[str, str]:
    """(account id, account name) as Breathe reports them; translates client errors.
    Called on web requests BEFORE any database write, with short timeouts."""
    try:
        with breathe.BreatheClient.for_request(base_url, api_key) as client:
            acc = client.account()
    except breathe.BreatheError as exc:
        status = 400 if exc.code in ("bad_key", "bad_origin") else 502
        raise ServiceError(exc.code, str(exc), status=status) from exc
    acc_id = str(acc.get("id") or acc.get("account_id") or "").strip()[:64]
    if not acc_id:
        raise ServiceError("bad_reply", "Breathe did not say which account this key belongs to.", status=502)
    name = str(acc.get("name") or acc.get("company_name") or acc.get("account_name") or "").strip()[:200]
    return acc_id, name or f"Breathe account {acc_id}"


def admins_of(org_id) -> list:
    return list(
        OrgMember.objects.filter(
            org_id=org_id, removed_at__isnull=True, role__in=("owner", "admin")
        ).values_list("user_id", flat=True)
    )


def _tell_admins(org_id, code: str, context: dict, dedupe: str) -> None:
    from apps.engagement.notify import notify

    users = admins_of(org_id)
    transaction.on_commit(
        lambda: notify(users, code, {"provider": PROVIDER, **context}, url=HR_URL, dedupe=dedupe)
    )


# ---------------------------------------------------------------- connection
def connect(*, org_id, api_key: str, environment: str, features, by) -> HrConnection:
    """Check the key with Breathe, then create (or re-open) the company's one connection."""
    api_key = _clean_key(api_key)
    base_url = _base_url(environment)
    acc_id, acc_name = _read_account(base_url, api_key)  # Breathe first, then the short write
    with transaction.atomic():
        return _save_connection(org_id, acc_id, acc_name, base_url, api_key, features, by)


def _save_connection(org_id, acc_id, acc_name, base_url, api_key, features, by) -> HrConnection:
    conn = HrConnection.objects.select_for_update().filter(org_id=org_id).first()
    if conn and conn.external_account_id != acc_id and conn.people.exists():
        raise ServiceError(
            "different_account",
            "This company's people came from a different Breathe account. Ask the platform team to reset the link first.",
            status=409,
        )
    conn = conn or HrConnection(org_id=org_id, provider=HrConnection.Provider.BREATHE, created_by=by)
    conn.external_account_id, conn.account_name, conn.base_url = acc_id, acc_name, base_url
    conn.secret_ciphertext = secrets.encrypt(api_key)
    conn.status, conn.last_error = HrConnection.Status.ACTIVE, ""
    conn.enabled_features = _features(features)
    conn.last_verified_at = timezone.now()
    try:
        with transaction.atomic():
            conn.save()
    except IntegrityError as exc:
        if "uq_hrconn_account" not in str(exc):
            raise
        # another company already connected this Breathe account (RLS hides it)
        raise ServiceError(
            "account_in_use", "This Breathe account is already connected to another company.", status=409
        ) from None
    return conn


def validate(*, conn: HrConnection) -> HrConnection:
    acc_id, acc_name = _read_account(conn.base_url, secrets.decrypt(conn.secret_ciphertext))
    if acc_id != conn.external_account_id:
        raise ServiceError(
            "different_account", "The key now belongs to a different Breathe account.", status=409
        )
    conn.account_name, conn.last_verified_at, conn.last_error = acc_name, timezone.now(), ""
    if conn.status == HrConnection.Status.ATTENTION:
        conn.status = HrConnection.Status.ACTIVE
    conn.save(update_fields=["account_name", "last_verified_at", "last_error", "status", "updated_at"])
    return conn


def replace_key(*, conn: HrConnection, api_key: str) -> HrConnection:
    api_key = _clean_key(api_key)
    acc_id, acc_name = _read_account(conn.base_url, api_key)
    if acc_id != conn.external_account_id:
        raise ServiceError(
            "different_account", "That key belongs to a different Breathe account.", status=409
        )
    conn.secret_ciphertext = secrets.encrypt(api_key)
    conn.account_name, conn.last_verified_at, conn.last_error = acc_name, timezone.now(), ""
    if conn.status in (HrConnection.Status.ATTENTION, HrConnection.Status.DISABLED):
        conn.status = HrConnection.Status.ACTIVE
    conn.save()
    return conn


def set_features(*, conn: HrConnection, features) -> HrConnection:
    conn.enabled_features = _features(features)
    conn.save(update_fields=["enabled_features", "updated_at"])
    return conn


def set_paused(*, conn: HrConnection, paused: bool) -> HrConnection:
    if conn.status == HrConnection.Status.DISABLED:
        raise ServiceError("disconnected", "Connect again first.", status=409)
    conn.status = HrConnection.Status.PAUSED if paused else HrConnection.Status.ACTIVE
    conn.save(update_fields=["status", "updated_at"])
    return conn


def disconnect(*, conn: HrConnection) -> None:
    """Stop syncing and forget the key. Imported people, links and records stay."""
    conn.status, conn.secret_ciphertext = HrConnection.Status.DISABLED, ""
    with transaction.atomic():
        conn.save(update_fields=["status", "secret_ciphertext", "updated_at"])
        _cancel_runs(conn, statuses=(HrSyncRun.Status.QUEUED,))


# ---------------------------------------------------------------- syncing
@transaction.atomic
def queue_sync(*, conn: HrConnection, trigger: str = "manual", by=None, key: str = "") -> HrSyncRun:
    # the row lock makes two "Sync now" clicks (or a click and the hourly beat) take turns
    conn = HrConnection.objects.select_for_update().only("id", "org_id", "status").get(pk=conn.pk)
    if conn.status in STOPPED:
        raise ServiceError("not_active", "Syncing is paused or disconnected.", status=409)
    busy = HrSyncRun.objects.filter(
        connection=conn, status__in=(HrSyncRun.Status.QUEUED, HrSyncRun.Status.RUNNING),
        created_at__gt=timezone.now() - STALE_RUN,
    ).first()  # fmt: skip
    if busy:
        raise ServiceError("already_running", "A sync is already running.", status=409)
    key = key or f"{trigger}:{timezone.now().isoformat()}"
    run, created = HrSyncRun.objects.get_or_create(
        connection=conn, idempotency_key=key[:120],
        defaults={"org_id": conn.org_id, "trigger": trigger, "triggered_by": by},
    )  # fmt: skip
    if created:
        from .tasks import hr_sync_run_task

        transaction.on_commit(lambda: hr_sync_run_task.delay(str(run.org_id), str(run.id)))
    return run


def process_sync(run_id, *, org_id) -> HrSyncRun:
    """Read everything enabled from Breathe and bring LearnHub in step. Runs in a task.

    Three steps, so no database transaction is ever held open while Breathe answers
    (lms_app ends a transaction left idle for 30 s): claim the run and read the key in
    one short transaction; fetch every page with no transaction open; write it all in
    one transaction. A failure marks the run failed and the connection "needs
    attention", and tells the company's admins. A paused or disconnected connection's
    run is cancelled instead, and nothing is written."""
    with tenant_context(org_id=org_id):
        run = HrSyncRun.objects.select_related("connection").get(pk=run_id)
        conn = run.connection
        if conn.status in STOPPED:
            _cancel_runs(conn, run_id=run.pk)
            run.refresh_from_db()
            return run
        claimed = HrSyncRun.objects.filter(pk=run.pk, status=HrSyncRun.Status.QUEUED).update(
            status=HrSyncRun.Status.RUNNING, started_at=timezone.now()
        )
        if not claimed:  # another worker has it, or it already finished
            return run
        ciphertext = conn.secret_ciphertext
    try:
        fetched = _fetch(conn, secrets.decrypt(ciphertext))
    except (breathe.BreatheError, ServiceError) as exc:
        return _fail(run, conn, getattr(exc, "code", "error"), str(exc))
    except Exception:  # noqa: BLE001 - any crash must still close the run and warn the admins
        log.exception("HR sync %s crashed while reading Breathe", run.id)
        return _fail(run, conn, "crashed", "Something went wrong while syncing. Try again shortly.")
    try:
        with tenant_context(org_id=org_id):
            engine.allow_long_statements()
            # paused or disconnected while Breathe was being read: keep what is there
            conn = HrConnection.objects.select_for_update().get(pk=conn.pk)
            if conn.status in STOPPED:
                _cancel_runs(conn, run_id=run.pk)
            else:
                _finish(run, conn, _write(conn, fetched))
    except Exception:  # noqa: BLE001
        log.exception("HR sync %s crashed while saving", run.id)
        return _fail(run, conn, "crashed", "Something went wrong while syncing. Try again shortly.")
    with tenant_context(org_id=org_id):
        run.refresh_from_db()
    return run


def _cancel_runs(
    conn: HrConnection, *, run_id=None, statuses=(HrSyncRun.Status.QUEUED, HrSyncRun.Status.RUNNING)
):
    """Close runs of a paused or disconnected connection (failed, code "cancelled"; nobody
    is notified: an admin chose this)."""
    runs = HrSyncRun.objects.filter(connection=conn, status__in=statuses)
    if run_id is not None:
        runs = runs.filter(pk=run_id)
    runs.update(
        status=HrSyncRun.Status.FAILED, error_code="cancelled", finished_at=timezone.now(),
        error_message="Stopped because syncing was paused or disconnected.",
    )  # fmt: skip


def _finish(run: HrSyncRun, conn: HrConnection, counts: dict) -> None:
    last = (
        HrSyncRun.objects.filter(connection=conn, status=HrSyncRun.Status.COMPLETED)
        .exclude(pk=run.pk)
        .order_by("-created_at")
        .values_list("counts", flat=True)
        .first()
    )
    before = (last or {}).get("to_review")
    now = timezone.now()
    HrSyncRun.objects.filter(pk=run.pk).update(
        status=HrSyncRun.Status.COMPLETED, counts=counts, finished_at=now
    )
    HrConnection.objects.filter(pk=conn.pk).update(last_sync_at=now, last_error="", updated_at=now)
    # only "needs attention" recovers; a status an admin set is never overwritten
    HrConnection.objects.filter(pk=conn.pk, status=HrConnection.Status.ATTENTION).update(
        status=HrConnection.Status.ACTIVE
    )
    if counts["new_people"] and counts["to_review"] and before != counts["to_review"]:
        _tell_admins(conn.org_id, "hr_people_to_review", {"count": counts["to_review"]},
                     dedupe=f"hr-review:{conn.id}:{now:%Y-%m-%d}")  # fmt: skip


def _fail(run: HrSyncRun, conn: HrConnection, code: str, message: str) -> HrSyncRun:
    with tenant_context(org_id=conn.org_id):
        now = timezone.now()
        HrSyncRun.objects.filter(pk=run.pk).update(
            status=HrSyncRun.Status.FAILED, error_code=code[:40], error_message=message[:300], finished_at=now
        )
        # a paused or disconnected connection stays as the admin left it, and nobody is told
        flagged = HrConnection.objects.filter(
            pk=conn.pk, status__in=(HrConnection.Status.ACTIVE, HrConnection.Status.ATTENTION)
        ).update(status=HrConnection.Status.ATTENTION, last_error=message[:300], updated_at=now)
        if flagged and code == "bad_key":
            _tell_admins(
                conn.org_id, "hr_connection_attention", {}, dedupe=f"hr-key:{conn.id}:{now:%Y-%m-%d}"
            )
        elif flagged:
            _tell_admins(conn.org_id, "hr_sync_failed", {"error": message},
                         dedupe=f"hr-fail:{conn.id}:{now:%Y-%m-%dT%H}")  # fmt: skip
        run.refresh_from_db()
    return run


def _fetch(conn: HrConnection, api_key: str) -> dict:
    """Every enabled resource from Breathe, normalised. No database access here."""

    def rows(client, resource, normalize):
        return [r for r in map(normalize, client.list(resource)) if r is not None]

    out = {"departments": [], "employees": [], "training": [], "leave": []}
    with breathe.BreatheClient(conn.base_url, api_key) as client:
        if conn.has("departments") or conn.has("managers"):
            out["departments"] = rows(client, "departments", normalizers.department)
        out["employees"] = rows(client, "employees", normalizers.employee)
        if conn.has("training"):
            out["training"] = rows(client, "training", normalizers.training)
        if conn.has("leave"):
            out["leave"] = rows(client, "leave", normalizers.leave)
    return out


def _write(conn: HrConnection, fetched: dict) -> dict:
    now = timezone.now()
    counts = {
        "people": 0,
        "new_people": 0,
        "leavers": 0,
        "departments": 0,
        "training": 0,
        "applied": 0,
        "leave": 0,
    }
    if conn.has("departments") or conn.has("managers"):
        for row in fetched["departments"]:
            ExternalDepartment.objects.update_or_create(
                connection=conn, external_department_id=row["external_department_id"],
                defaults={"org_id": conn.org_id, "name": row["name"], "last_seen_at": now},
            )  # fmt: skip
            counts["departments"] += 1
        _auto_link_departments(conn)

    for row in fetched["employees"]:
        row = dict(row)
        _, created = ExternalPerson.objects.update_or_create(
            connection=conn, external_employee_id=row.pop("external_employee_id"),
            defaults={"org_id": conn.org_id, "last_seen_at": now, **row},
        )  # fmt: skip
        counts["people"] += 1
        counts["new_people"] += created
        counts["leavers"] += row["is_leaver"]

    people = dict(ExternalPerson.objects.filter(connection=conn).values_list("external_employee_id", "id"))
    if conn.has("training"):
        for row in fetched["training"]:
            row = dict(row)
            ExternalTrainingRecord.objects.update_or_create(
                connection=conn, external_training_id=row.pop("external_training_id"),
                defaults={"org_id": conn.org_id, "person_id": people.get(row["external_employee_id"]), **row},
            )  # fmt: skip
            counts["training"] += 1

    if conn.has("leave"):
        seen: list[str] = []
        for row in fetched["leave"]:
            if row["ends_on"] < now.date():
                continue  # only current and future leave matters
            row = dict(row)
            ref = row.pop("source_ref")
            ExternalLeave.objects.update_or_create(
                connection=conn, source_ref=ref,
                defaults={"org_id": conn.org_id, "person_id": people.get(row["external_employee_id"]), **row},
            )  # fmt: skip
            seen.append(ref)
            counts["leave"] += 1
        # leave that was cancelled in Breathe, or has ended, stops showing
        ExternalLeave.objects.filter(connection=conn).filter(
            Q(ends_on__lt=now.date()) | ~Q(source_ref__in=seen)
        ).delete()

    placed = [
        person.member_id
        for person in ExternalPerson.objects.filter(connection=conn, member__isnull=False)
        if _place_in_department(conn, person)
    ]
    _assign_now(conn.org_id, placed)
    counts["applied"] = apply_training_records(conn=conn)
    counts["to_review"] = ExternalPerson.objects.filter(
        connection=conn, mapping_status=ExternalPerson.Mapping.PENDING, is_leaver=False
    ).count()
    return counts


# ---------------------------------------------------------------- departments
def _root(org_id) -> OrgUnit:
    return OrgUnit.objects.get(org_id=org_id, parent__isnull=True)


def _auto_link_departments(conn: HrConnection) -> None:
    """A department whose id matches a unit's code (set when we created it) links itself."""
    for dept in ExternalDepartment.objects.filter(connection=conn, status=ExternalDepartment.Link.PENDING):
        unit = OrgUnit.objects.filter(
            org_id=conn.org_id,
            code=dept.external_department_id,
            kind=OrgUnit.Kind.DEPARTMENT,
            archived_at__isnull=True,
        ).first()
        if unit:
            dept.unit, dept.status = unit, ExternalDepartment.Link.LINKED
            dept.save(update_fields=["unit", "status", "updated_at"])


@transaction.atomic
def link_department(
    *, dept: ExternalDepartment, unit: OrgUnit | None = None, create: bool = False
) -> ExternalDepartment:
    if create:
        code = dept.external_department_id[:32]
        unit = OrgUnit.objects.filter(
            org_id=dept.org_id, code=code, kind=OrgUnit.Kind.DEPARTMENT, archived_at__isnull=True
        ).first() or org_services.create_unit(
            parent=_root(dept.org_id), kind=OrgUnit.Kind.DEPARTMENT, name=dept.name[:160], code=code
        )
    if unit is None or unit.org_id != dept.org_id or unit.archived_at:
        raise ServiceError("bad_unit", "Choose a team or location in this company.")
    dept.unit, dept.status = unit, ExternalDepartment.Link.LINKED
    dept.save(update_fields=["unit", "status", "updated_at"])
    conn = dept.connection
    placed = [
        person
        for person in ExternalPerson.objects.filter(
            connection=conn, member__isnull=False, department_external_id=dept.external_department_id
        )
        if _place_in_department(conn, person)
    ]
    if placed:
        _assign_now(conn.org_id, [p.member_id for p in placed])
        apply_training_records(conn=conn, person_ids=[p.id for p in placed])
    return dept


def unlink_department(*, dept: ExternalDepartment) -> ExternalDepartment:
    """Stops future placement. People already placed stay where they are."""
    dept.unit, dept.status = None, ExternalDepartment.Link.PENDING
    dept.save(update_fields=["unit", "status", "updated_at"])
    return dept


def _place_in_department(conn: HrConnection, person: ExternalPerson) -> bool:
    """Matched people join their Breathe department's unit; their Breathe line manager
    becomes a manager of it. Add only: nothing set by hand is ever removed. True when
    the person was added to a unit."""
    if not person.member_id or not person.department_external_id:
        return False
    dept = ExternalDepartment.objects.filter(
        connection=conn, external_department_id=person.department_external_id, unit__isnull=False,
        unit__archived_at__isnull=True,
    ).select_related("unit").first()  # fmt: skip
    if dept is None:
        return False
    member = OrgMember.objects.filter(pk=person.member_id, removed_at__isnull=True).first()
    if member is None:
        return False
    placed = False
    if conn.has("departments") and not member.unit_links.filter(unit=dept.unit).exists():
        org_services.add_member_to_unit(member=member, unit=dept.unit)
        placed = True
    if conn.has("managers") and person.manager_external_id:
        boss = ExternalPerson.objects.filter(
            connection=conn, external_employee_id=person.manager_external_id, member__isnull=False,
            member__removed_at__isnull=True,
        ).select_related("member").first()  # fmt: skip
        if boss and not UnitManager.objects.filter(unit=dept.unit, member=boss.member).exists():
            current = list(OrgMember.objects.filter(managed_units__unit=dept.unit))
            org_services.set_unit_managers(unit=dept.unit, members=[*current, boss.member])
    return placed


def _assign_now(org_id, member_ids) -> None:
    """Compliance normally assigns training after commit (org.signals.structure_changed).
    Do it now for these people, so their Breathe records can count in this transaction."""
    member_ids = [m for m in member_ids if m]
    if member_ids:
        engine.lock_org(org_id)
        engine.sync_assignments(org_id, member_ids=member_ids)


# ---------------------------------------------------------------- people
@transaction.atomic
def match_person(*, person: ExternalPerson, member: OrgMember) -> ExternalPerson:
    if member.org_id != person.org_id or member.removed_at:
        raise ServiceError("bad_member", "Choose someone in this company.")
    taken = (
        ExternalPerson.objects.filter(connection=person.connection, member=member)
        .exclude(pk=person.pk)
        .first()
    )
    if taken:
        raise ServiceError(
            "already_linked", f"{taken.display_name} is already linked to this person.", status=409
        )
    person.member, person.mapping_status = member, ExternalPerson.Mapping.MATCHED
    person.save(update_fields=["member", "mapping_status", "updated_at"])
    changed = []
    if not member.employee_ref:
        member.employee_ref = person.external_employee_id[:64]
        changed.append("employee_ref")
    if not member.job_title and person.job_title:
        member.job_title = person.job_title[:120]
        changed.append("job_title")
    if changed:
        member.save(update_fields=[*changed, "updated_at"])
    _place_in_department(person.connection, person)
    _assign_now(person.org_id, [member.id])
    apply_training_records(conn=person.connection, person_ids=[person.id])
    return person


@transaction.atomic
def invite_person(
    *, person: ExternalPerson, role: str, unit, job_role, by, by_role: str
) -> tuple[Invite, str]:
    if not person.email:
        raise ServiceError("no_email", "Breathe has no email address for this person.")
    if unit is None and person.department_external_id:
        dept = ExternalDepartment.objects.filter(
            connection=person.connection,
            external_department_id=person.department_external_id,
            unit__isnull=False,
            unit__archived_at__isnull=True,
        ).first()
        unit = dept.unit if dept else None
    inv, token = org_services.invite(
        org_id=person.org_id,
        email=person.email,
        role=role,
        invited_by=by,
        by_role=by_role,
        unit=unit,
        job_role=job_role,
    )
    person.invite, person.mapping_status = inv, ExternalPerson.Mapping.INVITED
    person.save(update_fields=["invite", "mapping_status", "updated_at"])
    return inv, token


def ignore_person(*, person: ExternalPerson) -> ExternalPerson:
    person.mapping_status = ExternalPerson.Mapping.IGNORED
    person.save(update_fields=["mapping_status", "updated_at"])
    return person


def reset_person(*, person: ExternalPerson) -> ExternalPerson:
    """Back to "to review": unlinks the account (nothing in LearnHub is undone)."""
    person.member, person.invite, person.mapping_status = None, None, ExternalPerson.Mapping.PENDING
    person.save(update_fields=["member", "invite", "mapping_status", "updated_at"])
    return person


def reconcile_members(*, org_id, member_ids) -> int:
    """An invited Breathe employee who accepted their invitation becomes linked."""
    members = {
        m.user.email.lower(): m
        for m in OrgMember.objects.filter(
            org_id=org_id, pk__in=member_ids, removed_at__isnull=True
        ).select_related("user")
    }
    if not members:
        return 0
    done = 0
    for person in ExternalPerson.objects.filter(
        org_id=org_id, mapping_status=ExternalPerson.Mapping.INVITED, member__isnull=True
    ).select_related("connection"):
        member = members.get(person.email.lower())
        if member is None:
            continue
        with transaction.atomic():
            person.member, person.mapping_status = member, ExternalPerson.Mapping.MATCHED
            person.save(update_fields=["member", "mapping_status", "updated_at"])
            if not member.employee_ref:
                OrgMember.objects.filter(pk=member.pk).update(employee_ref=person.external_employee_id[:64])
            _place_in_department(person.connection, person)
            _assign_now(org_id, [member.id])
            apply_training_records(conn=person.connection, person_ids=[person.id])
        done += 1
    return done


# ---------------------------------------------------------------- training
@transaction.atomic
def map_training(*, conn: HrConnection, title: str, requirement: Requirement | None) -> int:
    """Count a Breathe training title as evidence for a requirement (None removes the
    mapping; records already imported stay). Returns how many records were applied."""
    key = normalizers.title_key(title)
    if not key:
        raise ServiceError("bad_title", "Choose a training title.")
    if requirement is None:
        HrTrainingMap.objects.filter(connection=conn, title_key=key).delete()
        return 0
    if requirement.org_id != conn.org_id or requirement.archived_at:
        raise ServiceError("bad_requirement", "Choose a requirement in this company.")
    HrTrainingMap.objects.update_or_create(
        connection=conn,
        title_key=key,
        defaults={"org_id": conn.org_id, "title": title.strip()[:200], "requirement": requirement},
    )
    return apply_training_records(conn=conn)


@transaction.atomic
def apply_training_records(*, conn: HrConnection, person_ids=None) -> int:
    """Turn completed Breathe training into compliance completion records (source
    "import"), for linked people whose requirement applies to them. The record expires
    by the requirement's own renewal rule (client question 26)."""
    if not conn.has("training"):
        return 0
    maps = dict(HrTrainingMap.objects.filter(connection=conn).values_list("title_key", "requirement_id"))
    if not maps:
        return 0
    # the company's compliance lock BEFORE reading unapplied rows: a sync, a map and a match
    # running together take turns, so a record is never imported twice
    engine.lock_org(conn.org_id)
    qs = ExternalTrainingRecord.objects.filter(
        connection=conn, applied_record__isnull=True, title_key__in=list(maps), completion_date__isnull=False,
        person__member__isnull=False, person__member__removed_at__isnull=True,
    ).select_related("person")  # fmt: skip
    if person_ids is not None:
        qs = qs.filter(person_id__in=person_ids)
    records = [r for r in qs if normalizers.counts_as_done(r.status)]
    if not records:
        return 0
    statuses = {
        (s.requirement_id, s.member_id): s
        for s in MemberStatus.objects.filter(
            requirement_id__in={maps[r.title_key] for r in records},
            member_id__in={r.person.member_id for r in records},
        ).select_related("requirement")
    }
    today = timezone.now().date()
    members = set()
    applied = 0
    for rec in records:
        status = statuses.get((maps[rec.title_key], rec.person.member_id))
        if status is None or rec.completion_date > today:
            continue  # the requirement doesn't apply to them (yet), or the date is wrong
        done_at = datetime.combine(rec.completion_date, time(12), tzinfo=UTC)
        note = f"Breathe: {rec.title}" + (
            f" (certificate {rec.certificate_ref})" if rec.certificate_ref else ""
        )
        record = CompletionRecord.objects.create(
            org_id=conn.org_id, requirement_id=status.requirement_id, member_id=status.member_id,
            source=CompletionRecord.Source.IMPORT, completed_at=done_at,
            expires_at=_add_months(done_at, status.requirement.renewal_months), note=note[:500],
        )  # fmt: skip
        ExternalTrainingRecord.objects.filter(pk=rec.pk).update(
            applied_record=record, applied_at=timezone.now()
        )
        members.add(status.member_id)
        applied += 1
    if members:
        engine.recompute(conn.org_id, member_ids=list(members))
        engine.open_renewals(conn.org_id, member_ids=list(members))
    return applied
