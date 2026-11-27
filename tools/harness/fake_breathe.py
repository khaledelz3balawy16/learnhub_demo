"""HARNESS ONLY (not part of the app): a deterministic stand-in for the Breathe HR API, so
the M17 browser test can connect, sync and import without a real Breathe key.

It is an httpx.MockTransport installed on `apps.integrations.breathe.transport` (the
hook the client exposes for exactly this). It answers like Breathe: the same JSON
envelopes, two pages per list joined by a `Link: <...>; rel="next"` header, and a 401
for any key other than FAKE_KEY. The data has the same shape as the backend test
fixture (apps/integrations/tests/test_fixtures.py). Dates are relative to today (UTC)
so the leave stays "current".

    from tools.harness import fake_breathe   # or: import fake_breathe (sys.path)
    fake_breathe.install()                    # after Django is set up

Enter FAKE_KEY on /business/hr-system and choose "Sandbox". Nothing is sent anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

FAKE_KEY = "e2e-fake-breathe-key-0001"  # not a secret: only this fake accepts it
HOSTS = ("api.sandbox.breathehr.info", "api.breathehr.com")


def data() -> dict:
    """Matches the E2E story: Sara and Omar have LearnHub accounts (email suggestions),
    Nina is invited, Lee is a leaver; Fire Safety Awareness maps to a requirement."""
    today = datetime.now(UTC).date()

    def day(n: int) -> str:
        return (today + timedelta(days=n)).isoformat()

    return {
        "account": {"id": 4242, "name": "Acme Care Ltd (Breathe sandbox)"},
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
            {"id": 504, "employee_id": 103, "title": "Fire Safety Awareness", "completed_on": day(-5),
             "status": "completed"},
        ],
        "leave_requests": [
            {"id": 901, "employee_id": 101, "start_date": day(-1), "end_date": day(4), "status": "Approved",
             "leave_type": "Holiday"},
            {"id": 902, "employee_id": 102, "start_date": day(3), "end_date": day(5), "status": "pending",
             "leave_type": "Holiday"},
            {"id": 903, "employee_id": 102, "start_date": day(-20), "end_date": day(-15), "status": "approved",
             "leave_type": "Sick"},
            {"id": 904, "employee_id": 103, "start_date": day(10), "end_date": day(12), "status": "authorised",
             "leave_type": "Holiday"},
        ],
    }  # fmt: skip


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.host not in HOSTS:
        return httpx.Response(404, json={"error": "unknown host"})
    if request.headers.get("X-API-KEY") != FAKE_KEY:
        return httpx.Response(401, json={"error": {"type": "Unauthorised"}})
    rows_by_name = data()
    name = request.url.path.removeprefix("/v1/")
    if name == "account":
        return httpx.Response(200, json={"account": rows_by_name["account"]})
    if name not in rows_by_name:
        return httpx.Response(404, json={"error": "not found"})
    rows = rows_by_name[name]
    half = (len(rows) + 1) // 2
    page = int(request.url.params.get("page", "1"))
    headers = {}
    if page == 1:
        nxt = f"https://{request.url.host}/v1/{name}?page=2&per_page=100"
        headers["Link"] = f'<{nxt}>; rel="next", <{nxt}>; rel="last"'
    return httpx.Response(
        200, json={name: rows[:half] if page == 1 else rows[half:]}, headers=headers
    )


def transport() -> httpx.MockTransport:
    return httpx.MockTransport(_handler)


def install() -> None:
    """Point the Breathe client at this fake (call once Django is set up)."""
    from apps.integrations import breathe

    breathe.transport = transport()
