"""The Breathe client's safety rules: official HTTPS origins only, Link-header paging that
never leaves the origin or loops, no redirects, and capped 429/5xx retries that honour
Retry-After (with an injected sleep, so nothing waits). No database needed."""

from unittest import mock

import httpx
from django.test import SimpleTestCase

from apps.integrations import breathe
from apps.integrations.breathe import BreatheClient, BreatheError, validated_base_url

from .test_fixtures import API_KEY, HOST, breathe_transport

BASE = f"https://{HOST}/"


def scripted(*responses):
    """A transport that answers each request with the next response in order."""
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return queue.pop(0) if queue else httpx.Response(500)

    t = httpx.MockTransport(handler)
    t.requests = seen
    return t


class ClientBase(SimpleTestCase):
    def use(self, transport):
        patcher = mock.patch.object(breathe, "transport", transport)
        patcher.start()
        self.addCleanup(patcher.stop)
        return transport

    def client_(self, **kw):
        self.sleeps: list[float] = []
        return BreatheClient(BASE, API_KEY, sleep=self.sleeps.append, **kw)


class OriginTest(SimpleTestCase):
    def test_only_official_https_origins(self):
        self.assertEqual(validated_base_url("https://api.breathehr.com"), "https://api.breathehr.com/")
        self.assertEqual(validated_base_url(breathe.SANDBOX), breathe.SANDBOX)
        self.assertEqual(validated_base_url("https://api.breathehr.com:443/"), "https://api.breathehr.com/")
        bad = [
            "http://api.breathehr.com/",  # not HTTPS
            "https://evil.example.com/",  # not on the allow-list
            "https://api.breathehr.com.evil.example.com/",
            "https://api.breathehr.com:8443/",  # another port
            'https://CHANGE_ME@example.com/',  # credentials in the URL
            "https://api.breathehr.com/v1/",  # a path
            "https://api.breathehr.com/?x=1",  # a query
            "https://api.breathehr.com/#frag",
            "ftp://api.breathehr.com/",
            "",
            "not a url",
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(BreatheError) as ctx:
                validated_base_url(value)
            self.assertEqual(ctx.exception.code, "bad_origin")

    def test_client_refuses_a_bad_origin(self):
        with self.assertRaises(BreatheError) as ctx:
            BreatheClient("https://example.com/", API_KEY)
        self.assertEqual(ctx.exception.code, "bad_origin")

    def test_no_key_never_calls_out(self):
        with mock.patch.object(breathe, "transport", breathe_transport()) as t:
            with self.assertRaises(BreatheError) as ctx:
                BreatheClient(BASE, "").account()
        self.assertEqual(ctx.exception.code, "no_key")
        self.assertEqual(t.requests, [])


class PagingTest(ClientBase):
    def test_follows_the_link_header_across_two_pages(self):
        t = self.use(breathe_transport())
        with self.client_() as client:
            rows = list(client.list("employees"))
            account = client.account()
        self.assertEqual([r["id"] for r in rows], [101, 102, 103, 104])
        self.assertEqual(account["name"], "Acme Care Ltd")
        first, second = t.requests[0], t.requests[1]
        self.assertEqual(first.url.path, "/v1/employees")
        self.assertEqual(dict(first.url.params), {"page": "1", "per_page": "100"})
        # the next link carries its own query: no doubled page parameters
        self.assertEqual(str(second.url), f"https://{HOST}/v1/employees?page=2&per_page=100")
        for r in t.requests:
            self.assertEqual(r.headers["X-API-KEY"], API_KEY)  # the key goes in a header...
            self.assertNotIn(API_KEY, str(r.url))  # ...never in the address
        self.assertEqual(self.sleeps, [])

    def test_every_resource_reads_its_envelope(self):
        self.use(breathe_transport())
        with self.client_() as client:
            counts = {name: len(list(client.list(name))) for name in ("departments", "training", "leave")}
        self.assertEqual(counts, {"departments": 2, "training": 4, "leave": 4})

    def test_off_origin_next_link_is_not_followed(self):
        for link in (
            '<https://evil.example.com/v1/employees?page=2>; rel="next"',
            '<http://api.sandbox.breathehr.info/v1/employees?page=2>; rel="next"',
            '<https://api.sandbox.breathehr.info/admin/export>; rel="next"',  # outside /v1/
            '<https://api.sandbox.breathehr.info:8443/v1/employees?page=2>; rel="next"',
        ):
            with self.subTest(link=link):
                t = self.use(
                    scripted(httpx.Response(200, json={"employees": [{"id": 1}]}, headers={"Link": link}))
                )
                with self.client_() as client, self.assertRaises(BreatheError) as ctx:
                    list(client.list("employees"))
                self.assertEqual(ctx.exception.code, "bad_link")
                self.assertEqual(len(t.requests), 1)  # the key never went to the other address

    def test_a_paging_loop_stops(self):
        loop = f'<https://{HOST}/v1/employees?page=2>; rel="next"'
        page = httpx.Response(200, json={"employees": [{"id": 1}]}, headers={"Link": loop})
        self.use(scripted(page, page, page))
        with self.client_() as client, self.assertRaises(BreatheError) as ctx:
            list(client.list("employees"))
        self.assertEqual(ctx.exception.code, "paging_loop")


class ResponseHandlingTest(ClientBase):
    def test_redirects_are_refused(self):
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                t = self.use(
                    scripted(
                        httpx.Response(status, headers={"Location": "https://evil.example.com/v1/account"})
                    )
                )
                with self.client_() as client, self.assertRaises(BreatheError) as ctx:
                    client.account()
                self.assertEqual((ctx.exception.code, ctx.exception.status), ("redirect", status))
                self.assertEqual(len(t.requests), 1)  # the Location was never requested

    def test_429_waits_for_retry_after_then_succeeds(self):
        t = self.use(
            scripted(
                httpx.Response(429, headers={"Retry-After": "7"}),
                httpx.Response(429, headers={"Retry-After": "600"}),  # capped at a minute
                httpx.Response(503),  # no header: exponential back-off (2 ** attempt)
                httpx.Response(200, json={"account": {"id": 1, "name": "A"}}),
            )
        )
        with self.client_() as client:
            self.assertEqual(client.account()["id"], 1)
        self.assertEqual(self.sleeps, [7.0, 60.0, 4])
        self.assertEqual(len(t.requests), 4)

    def test_retries_are_capped(self):
        t = self.use(scripted(*[httpx.Response(429, headers={"Retry-After": "1"})] * 10))
        with self.client_() as client, self.assertRaises(BreatheError) as ctx:
            client.account()
        self.assertEqual(ctx.exception.code, "busy")
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(t.requests), 4)  # the first try + 3 retries
        self.assertEqual(self.sleeps, [1.0, 1.0, 1.0])

    def test_a_garbled_retry_after_falls_back(self):
        self.use(
            scripted(
                httpx.Response(429, headers={"Retry-After": "soon"}),
                httpx.Response(200, json={"account": {"id": 2}}),
            )
        )
        with self.client_() as client:
            client.account()
        self.assertEqual(self.sleeps, [1])

    def test_refused_key_and_other_errors(self):
        self.use(breathe_transport(api_key='CHANGE_ME'))
        with self.client_() as client, self.assertRaises(BreatheError) as ctx:
            client.account()
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("bad_key", 401))

        self.use(scripted(httpx.Response(404)))
        with self.client_() as client, self.assertRaises(BreatheError) as ctx:
            client.account()
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("refused", 404))

        self.use(scripted(httpx.Response(200, content=b"<html>not json</html>")))
        with self.client_() as client, self.assertRaises(BreatheError) as ctx:
            client.account()
        self.assertEqual(ctx.exception.code, "bad_reply")

    def test_network_errors_retry_then_give_up(self):
        def boom(request):
            raise httpx.ConnectError("down", request=request)

        self.use(httpx.MockTransport(boom))
        with self.client_() as client, self.assertRaises(BreatheError) as ctx:
            client.account()
        self.assertEqual(ctx.exception.code, "unreachable")
        self.assertEqual(self.sleeps, [1, 2, 4])

    def test_client_side_rate_limit_waits(self):
        self.use(breathe_transport())
        with mock.patch("apps.integrations.breathe.time.monotonic", return_value=1000.0):
            with self.client_(max_requests=2, window=60) as client:
                client.account()
                client.account()
                # a third call inside the window must wait; the sleep is injected, and the
                # clock is frozen, so make the wait "pass" by forgetting the oldest call
                client.sleep = lambda s: (self.sleeps.append(s), client._sent.popleft())
                client.account()
        self.assertEqual(self.sleeps, [60.0])


class RequestPathTest(ClientBase):
    def test_web_requests_use_short_timeouts_one_retry_and_a_5s_cap(self):
        t = self.use(scripted(*[httpx.Response(429, headers={"Retry-After": "600"})] * 5))
        sleeps: list[float] = []
        with BreatheClient.for_request(BASE, API_KEY, sleep=sleeps.append) as client:
            self.assertEqual(client._http.timeout.read, 8)
            with self.assertRaises(BreatheError) as ctx:
                client.account()
        self.assertEqual(ctx.exception.code, "busy")
        self.assertEqual(len(t.requests), 2)  # one retry only
        self.assertEqual(sleeps, [5])  # Retry-After capped: worst case ~8 + 5 + 8 s
