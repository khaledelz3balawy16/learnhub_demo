"""Breathe HR API client (read only), ported from LMS_v2 onto httpx.

Safety rules, all enforced here:
- only the official HTTPS origins in settings.HR_INTEGRATION["ALLOWED_HOSTS"];
- redirects are refused (a redirect could carry the API key to another host);
- every pagination link must stay on the same origin and under /v1/;
- a client-side rate limit (Breathe allows about 60 requests a minute) and capped
  retries on 429 / 5xx, honouring Retry-After.

Request paths (connect, check, replace key) use `BreatheClient.for_request(...)`: short
timeouts, one retry and a 5 s wait cap, so a slow Breathe never holds a web request (and
its database transaction) near lms_app's 30 s idle-in-transaction limit.

`transport` lets tests and the E2E harness inject an httpx.MockTransport (the pattern
of core/storage.py); production leaves it None.
"""

from __future__ import annotations

import re
import time
from collections import deque
from urllib.parse import urljoin, urlsplit

import httpx
from django.conf import settings

transport = None  # tests and tools/harness inject an httpx.MockTransport

SANDBOX = "https://api.sandbox.breathehr.info/"
PRODUCTION = "https://api.breathehr.com/"

RESOURCE_PATHS = {
    "account": "/v1/account",
    "employees": "/v1/employees",
    "departments": "/v1/departments",
    "training": "/v1/employee_training_courses",
    "leave": "/v1/leave_requests",
}
# where each resource's rows sit in Breathe's JSON envelope
ENVELOPE = {
    "employees": "employees",
    "departments": "departments",
    "training": "employee_training_courses",
    "leave": "leave_requests",
}


class BreatheError(RuntimeError):
    def __init__(
        self, message: str, *, code: str = "breathe_error", status: int | None = None, retryable: bool = False
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def validated_base_url(value: str) -> str:
    try:
        p = urlsplit(str(value))
        valid = (
            p.scheme == "https"
            and p.hostname in settings.HR_INTEGRATION["ALLOWED_HOSTS"]
            and p.port in (None, 443)
            and not p.username
            and not p.password
            and p.path in ("", "/")
            and not p.query
            and not p.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise BreatheError("Use an official Breathe API address.", code="bad_origin")
    return f"https://{p.hostname}/"


class BreatheClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        sleep=time.sleep,
        max_requests: int = 40,
        window: float = 60,
        timeout: float = 30,
        retries: int = 3,
        max_wait: float = 60,
    ):
        self.base_url = validated_base_url(base_url)
        self.host = urlsplit(self.base_url).hostname
        self.api_key = api_key
        self.sleep = sleep
        self.max_requests = max_requests
        self.window = window
        self.retries = retries
        self.max_wait = max_wait
        self._sent: deque[float] = deque()
        self._http = httpx.Client(follow_redirects=False, timeout=timeout, transport=transport)

    @classmethod
    def for_request(cls, base_url: str, api_key: str, **kw) -> BreatheClient:
        """Worst case about 8 + 5 + 8 s: well inside a web request's 30 s budget."""
        return cls(base_url, api_key, **{"timeout": 8, "retries": 1, "max_wait": 5, **kw})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._http.close()

    # ------------------------------------------------------------ plumbing
    def _rate_limit(self) -> None:
        while True:
            now = time.monotonic()
            while self._sent and now - self._sent[0] >= self.window:
                self._sent.popleft()
            if len(self._sent) < self.max_requests:
                self._sent.append(now)
                return
            self.sleep(max(0.05, self.window - (now - self._sent[0])))

    def _check_url(self, url: str) -> None:
        try:
            p = urlsplit(url)
            ok = (
                p.scheme == "https"
                and p.hostname == self.host
                and p.port in (None, 443)
                and not p.username
                and not p.password
                and p.path.startswith("/v1/")
                and not p.fragment
            )
        except ValueError:
            ok = False
        if not ok:
            raise BreatheError(
                "Breathe sent a link to another address; it was not followed.", code="bad_link"
            )

    def get(self, path: str, *, params: dict | None = None) -> tuple[object, httpx.Headers]:
        retries = self.retries
        if not self.api_key:
            raise BreatheError("No API key.", code="no_key")
        url = urljoin(self.base_url, path)
        self._check_url(url)
        for attempt in range(retries + 1):
            self._rate_limit()
            try:
                r = self._http.get(
                    url, params=params, headers={"X-API-KEY": self.api_key, "Accept": "application/json"}
                )
            except httpx.HTTPError as exc:
                if attempt >= retries:
                    raise BreatheError(
                        "Breathe could not be reached.", code="unreachable", retryable=True
                    ) from exc
                self.sleep(min(2**attempt, self.max_wait))
                continue
            if r.is_redirect:
                raise BreatheError(
                    "Breathe redirected the request; redirects are not followed.",
                    code="redirect",
                    status=r.status_code,
                )
            if r.status_code == 429 or r.status_code >= 500:
                if attempt >= retries:
                    raise BreatheError(
                        "Breathe is busy. Try again shortly.",
                        code="busy",
                        status=r.status_code,
                        retryable=True,
                    )
                try:
                    delay = float(r.headers.get("Retry-After") or 2**attempt)
                except ValueError:
                    delay = 2**attempt
                self.sleep(max(0.0, min(delay, self.max_wait)))
                continue
            if r.status_code in (401, 403):
                raise BreatheError(
                    "Breathe did not accept the API key.", code="bad_key", status=r.status_code
                )
            if r.status_code >= 400:
                raise BreatheError(
                    f"Breathe refused the request ({r.status_code}).", code="refused", status=r.status_code
                )
            try:
                return r.json(), r.headers
            except ValueError as exc:
                raise BreatheError("Breathe sent a reply that could not be read.", code="bad_reply") from exc
        raise BreatheError("Breathe is busy. Try again shortly.", code="busy", retryable=True)

    # ------------------------------------------------------------ resources
    def account(self) -> dict:
        payload, _ = self.get(RESOURCE_PATHS["account"])
        if not isinstance(payload, dict):
            raise BreatheError("Breathe sent account details that could not be read.", code="bad_reply")
        inner = payload.get("account")
        if isinstance(inner, list) and inner and isinstance(inner[0], dict):
            return inner[0]
        return inner if isinstance(inner, dict) else payload

    def list(self, resource: str, *, per_page: int = 100):
        """Every row of a resource, following the Link: rel="next" header page by page."""
        path: str | None = RESOURCE_PATHS[resource]
        params: dict | None = {"page": 1, "per_page": max(1, min(per_page, 100))}
        visited: set[str] = set()
        while path:
            if path in visited or len(visited) >= 1000:
                raise BreatheError("Breathe paging did not end.", code="paging_loop")
            visited.add(path)
            payload, headers = self.get(path, params=params)
            yield from _rows(payload, ENVELOPE[resource])
            path = _next_link(headers.get("link"))
            params = None  # the next link carries its own query


def _rows(payload, key: str) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    if isinstance(value, list):
        return value
    return next((v for v in payload.values() if isinstance(v, list)), [])


def _next_link(value: str | None) -> str | None:
    for part in str(value or "").split(","):
        m = re.search(r'<([^>]+)>\s*;\s*rel="?next"?', part, re.I)
        if m:
            return m.group(1)
    return None
