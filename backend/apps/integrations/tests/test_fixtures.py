"""A Breathe HR stand-in for tests: an httpx.MockTransport that serves the real JSON
envelopes, two pages per list with a `Link: <…>; rel="next"` header, and checks the
X-API-KEY header like Breathe does. Install it with
`mock.patch.object(apps.integrations.breathe, "transport", breathe_transport())`.

Test doubles live only in tests and tools/harness (CLAUDE.md); nothing here ships."""

from __future__ import annotations

import copy
from datetime import timedelta

import httpx
from django.utils import timezone

HOST = "api.sandbox.breathehr.info"
API_KEY = 'CHANGE_ME'  # a throwaway value, never a real key
ACCOUNT_ID = "4242"
ACCOUNT_NAME = "Acme Care Ltd"
LISTS = ("departments", "employees", "employee_training_courses", "leave_requests")


def default_data(account_id: str = ACCOUNT_ID, account_name: str = ACCOUNT_NAME) -> dict:
    """Four employees (one leaver), two departments, four training records (one not done)
    and four leave requests (two approved and current or upcoming). Dates are relative to
    today (UTC, as the sync uses), so the leave stays "current"."""
    today = timezone.now().date()

    def day(n: int) -> str:
        return (today + timedelta(days=n)).isoformat()

    return {
        "account": {"id": int(account_id), "name": account_name},
        "departments": [{"id": 11, "name": "Kitchen"}, {"id": 12, "name": "Care"}],
        "employees": [
            {"id": 101, "first_name": "Sara", "last_name": "Ahmed", "email": 'contact+6d840705b10d@example.com',
             "job_title": "Senior Carer", "department": {"id": 12, "name": "Care"},
             "line_manager": {"id": 102}, "join_date": "2021-04-01", "contracted_hours": "37.5",
             "working_pattern": {"name": "Full time"}, "status": "Active"},
            {"id": 102, "first_name": "Omar", "last_name": "Ali", "email": 'contact+d4c523bfc479@example.com',
             "job_title": "Head Chef", "department_id": 11, "department_name": "Kitchen",
             "join_date": "2019-09-02", "status": "Active"},
            {"id": 103, "first_name": "Nina", "last_name": "Patel", "email": 'contact+9e97169adf42@example.com',
             "job_title": "Care Assistant", "department": {"id": 12, "name": "Care"},
             "line_manager_id": 101, "status": "Active"},
            {"id": 104, "first_name": "Lee", "last_name": "Long", "email": 'contact+ca71cd647572@example.com',
             "job_title": "Porter", "department": {"id": 11, "name": "Kitchen"}, "status": "Leaver",
             "leaving_date": day(-60)},
        ],
        "employee_training_courses": [
            {"id": 501, "employee_id": 101, "title": "Fire Safety Awareness", "category": "Health and safety",
             "completed_on": day(-30), "status": "Completed", "certificate_reference": "FS-501"},
            {"id": 502, "employee": {"id": 102}, "training_course": {"name": "Food Hygiene"},
             "completion_date": day(-10), "status": "passed"},
            {"id": 503, "employee_id": 101, "title": "Manual Handling", "status": "Booked"},
            {"id": 504, "employee_id": 103, "title": "fire safety  awareness", "completed_on": day(-5),
             "status": "completed"},
        ],
        "leave_requests": [
            {"id": 901, "employee_id": 101, "start_date": day(-1), "end_date": day(4), "status": "Approved",
             "leave_type": "Holiday", "notes": "private reason"},
            {"id": 902, "employee_id": 102, "start_date": day(3), "end_date": day(5), "status": "pending",
             "leave_type": "Holiday"},
            {"id": 903, "employee_id": 102, "start_date": day(-20), "end_date": day(-15), "status": "approved",
             "leave_type": "Sick"},
            {"id": 904, "employee_id": 103, "start_date": day(10), "end_date": day(12), "status": "authorised",
             "leave_type": "Holiday"},
        ],
    }  # fmt: skip


def breathe_transport(
    data: dict | None = None,
    *,
    api_key: str | None = API_KEY,
    host: str = HOST,
    fail: dict[str, int] | None = None,
    on_request=None,
) -> httpx.MockTransport:
    """data: as default_data() (copied, so a test may change its own copy afterwards).
    api_key: the key Breathe accepts (None accepts any); a wrong key gets 401.
    fail: {"employees": 500, ...} answers that resource with the status (Retry-After: 0,
    so retries never sleep). on_request(request) is called first (to probe or change
    state mid-sync). Every request is recorded on `transport.requests`."""
    data = copy.deepcopy(data if data is not None else default_data())
    fail = dict(fail or {})
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if on_request is not None:
            on_request(request)
        if request.url.host != host:
            return httpx.Response(404, json={"error": "unknown host"})
        if api_key is not None and request.headers.get("X-API-KEY") != api_key:
            return httpx.Response(401, json={"error": {"type": "Unauthorised"}})
        name = request.url.path.removeprefix("/v1/")
        if name in fail:
            return httpx.Response(fail[name], headers={"Retry-After": "0"}, json={"error": "failed"})
        if name == "account":
            return httpx.Response(200, json={"account": data["account"]})
        if name not in data:
            return httpx.Response(404, json={"error": "not found"})
        rows = data[name]
        half = (len(rows) + 1) // 2
        page = int(request.url.params.get("page", "1"))
        headers = {}
        if page == 1:
            nxt = f"https://{host}/v1/{name}?page=2&per_page=100"
            headers["Link"] = f'<{nxt}>; rel="next", <{nxt}>; rel="last"'
        return httpx.Response(200, json={name: rows[:half] if page == 1 else rows[half:]}, headers=headers)

    transport = httpx.MockTransport(handler)
    transport.requests = seen
    return transport
