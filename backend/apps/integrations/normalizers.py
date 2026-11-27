"""Breathe rows -> the plain fields LearnHub keeps (client question 23: name, email, job
title, department, manager, employment status, start date, hours, working pattern).

Breathe's field names vary a little between endpoints and API versions, so each value
is looked up under its known aliases. A row without an id is dropped (returns None).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

APPROVED = {"approved", "authorised", "authorized"}
LEAVER = {"leaver", "left", "former", "terminated", "inactive", "ex-employee"}
DONE = {"", "complete", "completed", "passed", "attended", "done"}


def _get(row: dict, *names):
    for name in names:
        value = row.get(name)
        if isinstance(value, dict):  # {"department": {"id": 3, "name": "Kitchen"}}
            continue
        if value not in (None, ""):
            return value
    return ""


def _nested(row: dict, key: str, field: str):
    value = row.get(key)
    return value.get(field, "") if isinstance(value, dict) else ""


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if 0 <= d < 10000 else None


def _unwrap(raw, key: str) -> dict:
    if not isinstance(raw, dict):
        return {}
    inner = raw.get(key)
    return inner if isinstance(inner, dict) else raw


def employee(raw) -> dict | None:
    row = _unwrap(raw, "employee")
    ext_id = _text(_get(row, "id", "employee_id"), 64)
    if not ext_id:
        return None
    first, last = (
        _text(_get(row, "first_name", "firstName"), 100),
        _text(_get(row, "last_name", "lastName"), 100),
    )
    name = (
        " ".join(p for p in (first, last) if p)
        or _text(_get(row, "name", "full_name"), 200)
        or f"Employee {ext_id}"
    )
    pattern = row.get("working_pattern")
    status = _text(_get(row, "status", "employment_status"), 40)
    return {
        "external_employee_id": ext_id,
        "email": _text(_get(row, "email", "work_email"), 254).lower(),
        "display_name": name[:200],
        "job_title": _text(_get(row, "job_title", "position"), 120),
        "department_external_id": _text(_get(row, "department_id") or _nested(row, "department", "id"), 64),
        "department_name": _text(_get(row, "department_name") or _nested(row, "department", "name"), 160),
        "manager_external_id": _text(
            _get(row, "line_manager_id", "manager_id") or _nested(row, "line_manager", "id"), 64
        ),
        "employment_status": status,
        "start_date": _date(_get(row, "join_date", "start_date", "employment_start_date")),
        "contracted_hours": _decimal(_get(row, "contracted_hours", "hours_per_week", "working_hours")),
        "working_pattern": _text(pattern.get("name", "") if isinstance(pattern, dict) else pattern, 120),
        "source_updated_at": _date(_get(row, "updated_at")),
        "is_leaver": status.lower() in LEAVER or bool(_get(row, "leaving_date", "termination_date")),
    }


def department(raw) -> dict | None:
    row = _unwrap(raw, "department")
    ext_id = _text(_get(row, "id", "department_id"), 64)
    if not ext_id:
        return None
    return {
        "external_department_id": ext_id,
        "name": _text(_get(row, "name", "title"), 160) or f"Department {ext_id}",
    }


def training(raw) -> dict | None:
    row = _unwrap(raw, "employee_training_course")
    ext_id = _text(_get(row, "id", "training_id"), 64)
    title = _text(_get(row, "title", "name", "course_name") or _nested(row, "training_course", "name"), 200)
    if not ext_id or not title:
        return None
    return {
        "external_training_id": ext_id,
        "external_employee_id": _text(_get(row, "employee_id") or _nested(row, "employee", "id"), 64),
        "title": title,
        "title_key": title_key(title),
        "category": _text(_get(row, "category", "training_type"), 120),
        "completion_date": _date(_get(row, "completed_on", "completion_date", "completed_at", "end_date")),
        "status": _text(_get(row, "status", "state"), 40),
        "certificate_ref": _text(_get(row, "certificate_reference", "certificate_ref"), 120),
    }


def leave(raw) -> dict | None:
    """Approved leave only. Only the type is kept, never the free-text reason."""
    row = _unwrap(raw, "leave_request")
    if _text(_get(row, "status", "approval_status"), 40).lower() not in APPROVED:
        return None
    ref = _text(_get(row, "id", "leave_request_id"), 64)
    start = _date(_get(row, "start_date", "from"))
    end = _date(_get(row, "end_date", "to")) or start
    if not ref or not start or not end:
        return None
    return {
        "source_ref": ref,
        "external_employee_id": _text(_get(row, "employee_id") or _nested(row, "employee", "id"), 64),
        "starts_on": start,
        "ends_on": max(start, end),
        "leave_type": _text(_get(row, "leave_type", "type", "reason_type"), 64),
    }


def title_key(title: str) -> str:
    return " ".join(str(title).lower().split())[:200]


def counts_as_done(status: str) -> bool:
    return status.strip().lower() in DONE
