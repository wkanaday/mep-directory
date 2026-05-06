"""Unit tests for fast-path/campaign_loader.py.

Run as a script (`python test_campaign_loader.py`) or under pytest.
HTTP mocked via _SeqClient + _FakeResponse.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import campaign_loader  # noqa: E402
from campaign_loader import (  # noqa: E402
    CampaignResult,
    build_campaign_payload,
    build_lead_payload,
    create_campaign,
    discover_sending_accounts,
    load_campaign,
    upload_leads,
    write_result,
)
from exceptions import (  # noqa: E402
    AuthFailureError,
    CreditsExhaustedError,
    FastPathError,
    FastPathHttpError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self  # type: ignore[attr-defined]
            raise err


class _SeqClient:
    def __init__(self, queue):
        self._queue = list(queue)
        self.calls: list[tuple[str, str, Any]] = []

    def call(self, method, path, *, json=None, params=None, headers=None):  # noqa: A002
        self.calls.append((method, path, json))
        if not self._queue:
            raise FastPathHttpError(f"queue empty for {method} {path}")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _record(email: str, **overrides) -> dict:
    base = {
        "contact_id": "c1",
        "email": email,
        "first_name": "John", "last_name": "Smith",
        "company_name": "Timken", "company_domain": "timken.com",
        "email_1_subject": "subj1", "email_1_body": "body1",
        "email_2_subject": "subj2", "email_2_body": "body2",
        "email_3_subject": "subj3", "email_3_body": "body3",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Account discovery
# ---------------------------------------------------------------------------

def test_discover_filters_to_three_netgainiq_domains():
    body = {"items": [
        {"email": "wilson@netgainiqgroup.com"},
        {"email": "ben@netgainiqadvisory.com"},
        {"email": "team@netgainiqpartners.com"},
        {"email": "irrelevant@gmail.com"},
        {"email": "old@oldcompany.com"},
    ]}
    instantly = _SeqClient([_FakeResponse(200, body=body)])
    out = discover_sending_accounts(instantly)
    assert out == [
        "wilson@netgainiqgroup.com",
        "ben@netgainiqadvisory.com",
        "team@netgainiqpartners.com",
    ]


def test_discover_handles_bare_list_response():
    body = [{"email": "a@netgainiqgroup.com"}, {"email": "b@gmail.com"}]
    instantly = _SeqClient([_FakeResponse(200, body=body)])
    out = discover_sending_accounts(instantly)
    assert out == ["a@netgainiqgroup.com"]


def test_discover_unrecognized_shape_raises():
    body = "string body"
    instantly = _SeqClient([_FakeResponse(200, body=body)])
    try:
        discover_sending_accounts(instantly)
    except FastPathError as e:
        assert "unexpected shape" in str(e).lower() or "shape" in str(e).lower()
    else:
        raise AssertionError("expected FastPathError")


def test_discover_propagates_auth_failure():
    instantly = _SeqClient([AuthFailureError("401")])
    try:
        discover_sending_accounts(instantly)
    except AuthFailureError:
        return
    raise AssertionError("expected AuthFailureError to propagate")


# ---------------------------------------------------------------------------
# Campaign payload
# ---------------------------------------------------------------------------

def test_campaign_payload_status_paused():
    p = build_campaign_payload(name="X", accounts=["a@x.com"])
    assert p["status"] == "paused"


def test_campaign_payload_three_sequence_steps_with_correct_delays():
    p = build_campaign_payload(name="X", accounts=["a@x.com"])
    steps = p["sequences"][0]["steps"]
    assert len(steps) == 3
    assert [s["delay"] for s in steps] == [0, 3, 7]


def test_campaign_payload_steps_reference_subject_body_vars():
    p = build_campaign_payload(name="X", accounts=["a@x.com"])
    variants = [s["variants"][0] for s in p["sequences"][0]["steps"]]
    assert variants[0]["subject"] == "{{subject_1}}"
    assert variants[0]["body"] == "{{body_1}}"
    assert variants[2]["subject"] == "{{subject_3}}"
    assert variants[2]["body"] == "{{body_3}}"


def test_campaign_payload_send_window_tue_friday():
    p = build_campaign_payload(name="X", accounts=["a@x.com"])
    days = p["campaign_schedule"]["schedules"][0]["days"]
    assert "tuesday" in days and "friday" in days
    assert "monday" not in days


def test_campaign_payload_daily_limit_30_stop_on_reply_open_tracking():
    p = build_campaign_payload(name="X", accounts=["a@x.com"])
    assert p["daily_limit"] == 30
    assert p["stop_on_reply"] is True
    assert p["open_tracking"] is True
    assert p["link_tracking"] is False


def test_campaign_payload_includes_all_accounts():
    p = build_campaign_payload(
        name="X",
        accounts=["a@netgainiqgroup.com", "b@netgainiqadvisory.com"],
    )
    assert p["email_list"] == ["a@netgainiqgroup.com", "b@netgainiqadvisory.com"]


# ---------------------------------------------------------------------------
# create_campaign
# ---------------------------------------------------------------------------

def test_create_campaign_returns_id_from_response():
    instantly = _SeqClient([_FakeResponse(200, body={"id": "camp_123", "name": "X", "status": "paused"})])
    cid = create_campaign(instantly, name="X", accounts=["a@x.com"])
    assert cid == "camp_123"


def test_create_campaign_handles_nested_data_id():
    instantly = _SeqClient([_FakeResponse(200, body={"data": {"id": "camp_456"}})])
    cid = create_campaign(instantly, name="X", accounts=["a@x.com"])
    assert cid == "camp_456"


def test_create_campaign_no_id_raises():
    instantly = _SeqClient([_FakeResponse(200, body={"unexpected": "shape"})])
    try:
        create_campaign(instantly, name="X", accounts=["a@x.com"])
    except FastPathError as e:
        assert "no id" in str(e).lower() or "id" in str(e).lower()
    else:
        raise AssertionError("expected FastPathError")


# ---------------------------------------------------------------------------
# build_lead_payload
# ---------------------------------------------------------------------------

def test_lead_payload_custom_vars_match_subject_and_body_keys():
    rec = _record("john@timken.com")
    payload = build_lead_payload(rec, campaign_id="camp_x")
    cv = payload["custom_variables"]
    assert cv["subject_1"] == "subj1"
    assert cv["body_1"] == "body1"
    assert cv["subject_2"] == "subj2"
    assert cv["body_2"] == "body2"
    assert cv["subject_3"] == "subj3"
    assert cv["body_3"] == "body3"


def test_lead_payload_includes_campaign_id():
    rec = _record("a@b.com")
    payload = build_lead_payload(rec, campaign_id="C42")
    assert payload["campaign"] == "C42"


def test_lead_payload_includes_basic_lead_fields():
    rec = _record("john@timken.com")
    payload = build_lead_payload(rec, campaign_id="X")
    assert payload["email"] == "john@timken.com"
    assert payload["first_name"] == "John"
    assert payload["last_name"] == "Smith"
    assert payload["company_name"] == "Timken"


# ---------------------------------------------------------------------------
# upload_leads
# ---------------------------------------------------------------------------

def test_upload_leads_records_success_count():
    instantly = _SeqClient([
        _FakeResponse(200, body={"id": "L1"}),
        _FakeResponse(200, body={"id": "L2"}),
    ])
    success, errors = upload_leads(
        instantly,
        [_record("a@b.com"), _record("c@d.com")],
        campaign_id="X",
    )
    assert success == 2
    assert errors == []


def test_upload_leads_partial_failure_records_errors():
    err = requests.HTTPError("500")
    err.response = _FakeResponse(500)  # type: ignore[attr-defined]
    instantly = _SeqClient([
        _FakeResponse(200, body={"id": "L1"}),
        err,
    ])
    success, errors = upload_leads(
        instantly,
        [_record("a@b.com"), _record("c@d.com")],
        campaign_id="X",
    )
    assert success == 1
    assert len(errors) == 1
    assert "c@d.com" in errors[0]


def test_upload_leads_propagates_auth_failure():
    instantly = _SeqClient([AuthFailureError("401")])
    try:
        upload_leads(instantly, [_record("a@b.com")], campaign_id="X")
    except AuthFailureError:
        return
    raise AssertionError("expected AuthFailureError")


# ---------------------------------------------------------------------------
# Top-level load_campaign
# ---------------------------------------------------------------------------

def test_load_campaign_full_flow():
    instantly = _SeqClient([
        _FakeResponse(200, body={"items": [
            {"email": "a@netgainiqgroup.com"},
            {"email": "b@netgainiqadvisory.com"},
        ]}),
        _FakeResponse(200, body={"id": "camp_999", "status": "paused"}),
        _FakeResponse(200, body={"id": "L1"}),
    ])
    result = load_campaign(
        [_record("john@timken.com")],
        instantly,
        campaign_name="TEST-DELETE-ME",
    )
    assert result.campaign_id == "camp_999"
    assert result.name == "TEST-DELETE-ME"
    assert result.status == "paused"
    assert "a@netgainiqgroup.com" in result.accounts_attached
    assert result.leads_uploaded == 1


def test_load_campaign_no_matching_accounts_raises():
    instantly = _SeqClient([
        _FakeResponse(200, body={"items": [{"email": "outside@otherco.com"}]}),
    ])
    try:
        load_campaign([_record("a@b.com")], instantly)
    except FastPathError as e:
        assert "sending account" in str(e).lower()
    else:
        raise AssertionError("expected FastPathError")


def test_load_campaign_default_name_when_not_provided():
    import config as cfg
    instantly = _SeqClient([
        _FakeResponse(200, body={"items": [{"email": "a@netgainiqgroup.com"}]}),
        _FakeResponse(200, body={"id": "X"}),
    ])
    result = load_campaign([], instantly)
    assert result.name == cfg.DEFAULT_CAMPAIGN_NAME
    assert result.leads_uploaded == 0


# ---------------------------------------------------------------------------
# write_result
# ---------------------------------------------------------------------------

def test_write_result_persists_dated_json():
    with tempfile.TemporaryDirectory() as tmp:
        result = CampaignResult(
            campaign_id="X", name="N", status="paused",
            accounts_attached=["a@b.com"], leads_uploaded=5, errors=[],
        )
        path = write_result(result, out_dir=Path(tmp), today="2026-05-09")
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["campaign_id"] == "X"
        assert body["leads_uploaded"] == 5


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_discover_filters_to_three_netgainiq_domains,
        test_discover_handles_bare_list_response,
        test_discover_unrecognized_shape_raises,
        test_discover_propagates_auth_failure,
        test_campaign_payload_status_paused,
        test_campaign_payload_three_sequence_steps_with_correct_delays,
        test_campaign_payload_steps_reference_subject_body_vars,
        test_campaign_payload_send_window_tue_friday,
        test_campaign_payload_daily_limit_30_stop_on_reply_open_tracking,
        test_campaign_payload_includes_all_accounts,
        test_create_campaign_returns_id_from_response,
        test_create_campaign_handles_nested_data_id,
        test_create_campaign_no_id_raises,
        test_lead_payload_custom_vars_match_subject_and_body_keys,
        test_lead_payload_includes_campaign_id,
        test_lead_payload_includes_basic_lead_fields,
        test_upload_leads_records_success_count,
        test_upload_leads_partial_failure_records_errors,
        test_upload_leads_propagates_auth_failure,
        test_load_campaign_full_flow,
        test_load_campaign_no_matching_accounts_raises,
        test_load_campaign_default_name_when_not_provided,
        test_write_result_persists_dated_json,
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
