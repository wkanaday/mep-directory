"""Unit tests for fast-path/api_client.py.

Run as a script (`python test_api_client.py`) or under pytest.
HTTP and time.sleep are stubbed — no real network calls, no real waits.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api_client import FastPathApiClient  # noqa: E402
from exceptions import (  # noqa: E402
    AuthFailureError,
    CreditsExhaustedError,
    FastPathHttpError,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal stand-in for requests.Response.

    Pattern matches scanner-engine/tests/test_rss.py:415-428 (the existing
    codebase idiom for HTTP test fixtures).
    """

    def __init__(self, status_code: int = 200, body: Any = None, headers: dict | None = None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self) -> Any:
        return self._body

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 600:
            raise requests.HTTPError(f"{self.status_code} response")


def _make_client(**overrides: Any) -> FastPathApiClient:
    defaults = dict(
        base_url="https://api.example.com",
        headers={"x-api-key": "test-key"},
        delay_s=0.1,
        backoff_schedule=[1, 2, 3],
        name="test",
    )
    defaults.update(overrides)
    return FastPathApiClient(**defaults)  # type: ignore[arg-type]


def _seq_responder(*responses: _FakeResponse | Exception):
    """Return a side_effect that yields the given responses/exceptions in order.
    Raises StopIteration if called more times than responses provided.
    """
    it = iter(responses)

    def _request(method, url, **kwargs):  # noqa: ARG001
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    return _request


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_200_first_try_returns_response():
    client = _make_client()
    fake = _FakeResponse(status_code=200, body={"ok": True})
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep") as sleep_mock:
        resp = client.call("GET", "/endpoint")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    sleep_mock.assert_called_once_with(0.1)  # only the inter-call delay, no backoff


def test_inter_call_delay_applied_before_request():
    client = _make_client(delay_s=0.5)
    fake = _FakeResponse(status_code=200)
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep") as sleep_mock:
        client.call("GET", "/x")
    assert sleep_mock.call_args_list[0] == mock.call(0.5)


def test_path_joined_correctly_with_leading_slash():
    client = _make_client(base_url="https://api.example.com")
    fake = _FakeResponse(200)
    with mock.patch("api_client.requests.request", return_value=fake) as req_mock, \
         mock.patch("api_client.time.sleep"):
        client.call("GET", "/foo/bar")
    assert req_mock.call_args.args[1] == "https://api.example.com/foo/bar"


def test_path_joined_correctly_without_leading_slash():
    client = _make_client(base_url="https://api.example.com")
    fake = _FakeResponse(200)
    with mock.patch("api_client.requests.request", return_value=fake) as req_mock, \
         mock.patch("api_client.time.sleep"):
        client.call("GET", "foo/bar")
    assert req_mock.call_args.args[1] == "https://api.example.com/foo/bar"


def test_default_headers_merged_into_request():
    client = _make_client(headers={"x-api-key": "abc123"})
    fake = _FakeResponse(200)
    with mock.patch("api_client.requests.request", return_value=fake) as req_mock, \
         mock.patch("api_client.time.sleep"):
        client.call("POST", "/x", headers={"Content-Type": "application/json"})
    sent_headers = req_mock.call_args.kwargs["headers"]
    assert sent_headers["x-api-key"] == "abc123"
    assert sent_headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# Retry: 429
# ---------------------------------------------------------------------------

def test_429_first_then_200_uses_backoff_zero():
    client = _make_client(delay_s=0.0, backoff_schedule=[10, 20, 30])
    side = _seq_responder(_FakeResponse(429), _FakeResponse(200, {"ok": True}))
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep") as sleep_mock:
        resp = client.call("GET", "/x")
    assert resp.status_code == 200
    sleeps = [c.args[0] for c in sleep_mock.call_args_list]
    # delay_s pre-call + backoff[0] + delay_s pre-call
    assert sleeps == [0.0, 10, 0.0]


def test_429_twice_then_200_uses_backoff_zero_then_one():
    client = _make_client(delay_s=0.0, backoff_schedule=[10, 20, 30])
    side = _seq_responder(_FakeResponse(429), _FakeResponse(429), _FakeResponse(200))
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep") as sleep_mock:
        client.call("GET", "/x")
    sleeps = [c.args[0] for c in sleep_mock.call_args_list]
    assert 10 in sleeps and 20 in sleeps
    # 20 should appear after 10
    assert sleeps.index(20) > sleeps.index(10)


def test_429_retry_after_header_wins_when_longer():
    client = _make_client(delay_s=0.0, backoff_schedule=[10, 20, 30])
    side = _seq_responder(
        _FakeResponse(429, headers={"Retry-After": "120"}),
        _FakeResponse(200),
    )
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep") as sleep_mock:
        client.call("GET", "/x")
    sleeps = [c.args[0] for c in sleep_mock.call_args_list]
    assert 120 in sleeps  # Retry-After (120) > backoff[0] (10)


def test_429_backoff_wins_when_retry_after_is_smaller():
    client = _make_client(delay_s=0.0, backoff_schedule=[60, 120, 300])
    side = _seq_responder(
        _FakeResponse(429, headers={"Retry-After": "5"}),
        _FakeResponse(200),
    )
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep") as sleep_mock:
        client.call("GET", "/x")
    sleeps = [c.args[0] for c in sleep_mock.call_args_list]
    assert 60 in sleeps and 5 not in sleeps  # backoff (60) > Retry-After (5)


def test_429_exhausted_raises_fast_path_http_error():
    client = _make_client(delay_s=0.0, backoff_schedule=[1, 1, 1])
    side = _seq_responder(*[_FakeResponse(429) for _ in range(4)])
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("GET", "/x")
        except FastPathHttpError as e:
            assert "429" in str(e)
        else:
            raise AssertionError("expected FastPathHttpError")


# ---------------------------------------------------------------------------
# Retry: 5xx
# ---------------------------------------------------------------------------

def test_500_then_200_retries_and_returns():
    client = _make_client(delay_s=0.0, backoff_schedule=[1, 2, 3])
    side = _seq_responder(_FakeResponse(503), _FakeResponse(200))
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep"):
        resp = client.call("GET", "/x")
    assert resp.status_code == 200


def test_500_exhausted_raises_fast_path_http_error():
    client = _make_client(delay_s=0.0, backoff_schedule=[1, 1, 1])
    side = _seq_responder(*[_FakeResponse(500) for _ in range(4)])
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("GET", "/x")
        except FastPathHttpError as e:
            assert "500" in str(e)
        else:
            raise AssertionError("expected FastPathHttpError")


# ---------------------------------------------------------------------------
# Retry: network errors
# ---------------------------------------------------------------------------

def test_network_error_then_200_retries():
    client = _make_client(delay_s=0.0, backoff_schedule=[1, 2, 3])
    side = _seq_responder(requests.ConnectionError("boom"), _FakeResponse(200))
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep"):
        resp = client.call("GET", "/x")
    assert resp.status_code == 200


def test_network_error_exhausted_raises():
    client = _make_client(delay_s=0.0, backoff_schedule=[1, 1, 1])
    side = _seq_responder(*[requests.Timeout("slow") for _ in range(4)])
    with mock.patch("api_client.requests.request", side_effect=side), \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("GET", "/x")
        except FastPathHttpError:
            pass
        else:
            raise AssertionError("expected FastPathHttpError")


# ---------------------------------------------------------------------------
# Terminal: 401, 402, 4xx
# ---------------------------------------------------------------------------

def test_401_raises_auth_failure_error():
    client = _make_client()
    fake = _FakeResponse(401)
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("GET", "/x")
        except AuthFailureError as e:
            assert "401" in str(e)
        else:
            raise AssertionError("expected AuthFailureError")


def test_402_raises_credits_exhausted_error():
    client = _make_client()
    fake = _FakeResponse(402)
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("POST", "/x")
        except CreditsExhaustedError as e:
            assert "402" in str(e)
        else:
            raise AssertionError("expected CreditsExhaustedError")


def test_403_raises_http_error_not_retried():
    client = _make_client(backoff_schedule=[1, 2, 3])
    fake = _FakeResponse(403)
    with mock.patch("api_client.requests.request", return_value=fake) as req_mock, \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("GET", "/x")
        except requests.HTTPError:
            pass
        else:
            raise AssertionError("expected HTTPError")
    # 4xx (other than 401/402/429) is terminal — only one HTTP call
    assert req_mock.call_count == 1


def test_404_raises_http_error_not_retried():
    client = _make_client()
    fake = _FakeResponse(404)
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep"):
        try:
            client.call("GET", "/x")
        except requests.HTTPError:
            pass
        else:
            raise AssertionError("expected HTTPError")


# ---------------------------------------------------------------------------
# Credit extractor + logging
# ---------------------------------------------------------------------------

def test_credit_extractor_called_and_logged(caplog=None):
    extractor_calls: list[Any] = []

    def extractor(resp):
        extractor_calls.append(resp)
        return 1234

    client = _make_client(credit_extractor=extractor, name="leadmagic")
    fake = _FakeResponse(200, body={"credits_remaining": 1234})
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep"):
        with _capture_logs("fast_path.api_client") as records:
            client.call("POST", "/v1/x")
    assert len(extractor_calls) == 1
    assert any("credits_remaining=1234" in r.getMessage() for r in records)


def test_credit_extractor_failure_does_not_break_call():
    def extractor(resp):  # noqa: ARG001
        raise RuntimeError("oops")

    client = _make_client(credit_extractor=extractor)
    fake = _FakeResponse(200)
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep"):
        # Should not raise — extractor failures are swallowed.
        resp = client.call("GET", "/x")
    assert resp.status_code == 200


def test_log_records_method_url_status():
    client = _make_client(name="apollo")
    fake = _FakeResponse(200)
    with mock.patch("api_client.requests.request", return_value=fake), \
         mock.patch("api_client.time.sleep"):
        with _capture_logs("fast_path.api_client") as records:
            client.call("POST", "/api/v1/x")
    msgs = [r.getMessage() for r in records]
    assert any("apollo" in m and "POST" in m and "200" in m for m in msgs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _capture_logs:
    """Context manager that captures all log records for the given logger name."""

    def __init__(self, logger_name: str) -> None:
        self.logger_name = logger_name
        self.records: list[logging.LogRecord] = []
        self._handler: logging.Handler | None = None

    def __enter__(self) -> list[logging.LogRecord]:
        logger = logging.getLogger(self.logger_name)
        logger.setLevel(logging.DEBUG)
        self._handler = _ListHandler(self.records)
        logger.addHandler(self._handler)
        return self.records

    def __exit__(self, *args) -> None:
        if self._handler is not None:
            logging.getLogger(self.logger_name).removeHandler(self._handler)


class _ListHandler(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self.records = records

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_200_first_try_returns_response,
        test_inter_call_delay_applied_before_request,
        test_path_joined_correctly_with_leading_slash,
        test_path_joined_correctly_without_leading_slash,
        test_default_headers_merged_into_request,
        test_429_first_then_200_uses_backoff_zero,
        test_429_twice_then_200_uses_backoff_zero_then_one,
        test_429_retry_after_header_wins_when_longer,
        test_429_backoff_wins_when_retry_after_is_smaller,
        test_429_exhausted_raises_fast_path_http_error,
        test_500_then_200_retries_and_returns,
        test_500_exhausted_raises_fast_path_http_error,
        test_network_error_then_200_retries,
        test_network_error_exhausted_raises,
        test_401_raises_auth_failure_error,
        test_402_raises_credits_exhausted_error,
        test_403_raises_http_error_not_retried,
        test_404_raises_http_error_not_retried,
        test_credit_extractor_called_and_logged,
        test_credit_extractor_failure_does_not_break_call,
        test_log_records_method_url_status,
    ]
    n_passed = 0
    n_failed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            n_passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            n_failed += 1
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {type(e).__name__}: {e}")
            n_failed += 1
    print(f"\nResults: {n_passed} passed, {n_failed} failed")
    return n_failed == 0


if __name__ == "__main__":
    raise SystemExit(0 if run_all_tests() else 1)
