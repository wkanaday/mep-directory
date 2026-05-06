"""Unit tests for fast-path/preflight.py.

Run as a script (`python test_preflight.py`) or under pytest. HTTP is
stubbed via _FakeResponse + a hand-rolled _FakeClient (no real network).
File I/O uses tempfile.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import preflight  # noqa: E402
from exceptions import (  # noqa: E402
    AuthFailureError,
    CreditsExhaustedError,
    FastPathHttpError,
)
from config import PipelineConfig  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            err = requests.HTTPError(f"{self.status_code} response")
            err.response = self  # type: ignore[attr-defined]
            raise err


class _FakeClient:
    """Stand-in for FastPathApiClient with deterministic responses."""

    def __init__(self, *, response=None, exception=None):
        self._response = response
        self._exception = exception

    def call(self, method, path, **kwargs):  # noqa: ARG002
        if self._exception is not None:
            raise self._exception
        return self._response


def _make_pipeline_config(*, tam: Path, persona: Path, template: Path,
                          excl: Path, lookalikes: Path) -> PipelineConfig:
    return PipelineConfig(
        tam_path=tam,
        persona_path=persona,
        template_path=template,
        exclusions_path=excl,
        lookalikes_path=lookalikes,
        max_contacts=30,
        max_per_company=2,
        warn_below_hit_rate=0.5,
    )


_GOOD_TEMPLATE = """\
---
title: "Test Template"
---

## Angle 1 — Test

### Email 1 — Data-Rich Version

**Subject lines:**
1. invoice errors
2. contract drift

**Body:**

Hi {first_name},

{Your operations team at {company_name}|Folks at {company_name}} look like they have {facility_count} sites and the contracts are messy. Worth a 15 min check?

{sender_name}
NetGainIQ
"""

_TEMPLATE_NESTED_SPINTAX = """\
## Angle 1

**Body:**

Hi {first_name}, {{a|b}|c} test.
"""

_TEMPLATE_EMPTY_OPTION = """\
## Angle 1

**Body:**

Hi {first_name}, {a|} test.
"""

_TEMPLATE_UNKNOWN_VAR = """\
## Angle 1

**Body:**

Hi {first_name}, {company_name} has {totally_made_up_field} stuff.
"""

_TAM_GOOD = """\
# Sub-Segment TAM

```json
{
  "filters": {
    "sic_codes": ["3541", "3544"],
    "naics_codes": ["333515"],
    "employee_count": {"min": 2000, "max": 20000},
    "revenue_range": {"min": 500000000, "max": 5000000000, "currency": "USD"}
  }
}
```

Lincoln Electric, Timken, Materion are anchors.
"""

_TAM_MISSING_KEYS = """\
```json
{
  "filters": {
    "sic_codes": ["3541"]
  }
}
```
"""

_TAM_NO_JSON = """\
# TAM

Just text, no JSON here.
"""

_LOOKALIKES_3 = json.dumps({
    "companies": [
        {"name": "Lincoln Electric", "domain": "lincolnelectric.com"},
        {"name": "Timken", "domain": "timken.com"},
        {"name": "Materion", "domain": "materion.com"},
    ]
})

_LOOKALIKES_WITH_MISSING = json.dumps({
    "companies": [
        {"name": "Lincoln Electric", "domain": "lincolnelectric.com"},
        {"name": "FakeCo Industries", "domain": "fakeco.com"},
    ]
})


# ---------------------------------------------------------------------------
# Layer 1 — env
# ---------------------------------------------------------------------------

def test_env_all_three_present_passes():
    r = preflight.check_env({
        "APOLLO_API_KEY": "a",
        "LEADMAGIC_API_KEY": "b",
        "INSTANTLY_API_KEY": "c",
    })
    assert r.status == "pass", r.detail


def test_env_missing_one_key_fails():
    r = preflight.check_env({"APOLLO_API_KEY": "a", "LEADMAGIC_API_KEY": "b"})
    assert r.status == "fail"
    assert "INSTANTLY_API_KEY" in r.detail


def test_env_empty_value_fails():
    r = preflight.check_env({"APOLLO_API_KEY": "", "LEADMAGIC_API_KEY": "b", "INSTANTLY_API_KEY": "c"})
    assert r.status == "fail"
    assert "APOLLO_API_KEY" in r.detail


# ---------------------------------------------------------------------------
# Layer 2 — Apollo plan tier
# ---------------------------------------------------------------------------

def test_apollo_basic_plan_passes():
    fake = _FakeResponse(200, body={"pagination": {"total_entries": 17}, "people": []})
    r = preflight.check_apollo_plan(_FakeClient(response=fake))
    assert r.status == "pass"
    assert "17" in r.detail or "Basic" in r.detail


def test_apollo_free_plan_fails_with_403():
    err = requests.HTTPError("403")
    err.response = _FakeResponse(403)  # type: ignore[attr-defined]
    r = preflight.check_apollo_plan(_FakeClient(exception=err))
    assert r.status == "fail"
    assert "403" in r.detail


def test_apollo_bad_key_fails_with_401():
    r = preflight.check_apollo_plan(_FakeClient(exception=AuthFailureError("401")))
    assert r.status == "fail"
    assert "401" in r.detail


def test_apollo_missing_pagination_field_fails():
    fake = _FakeResponse(200, body={"some_other_shape": True})
    r = preflight.check_apollo_plan(_FakeClient(response=fake))
    assert r.status == "fail"
    assert "pagination" in r.detail


def test_apollo_unreachable_fails():
    r = preflight.check_apollo_plan(_FakeClient(exception=FastPathHttpError("network down")))
    assert r.status == "fail"


# ---------------------------------------------------------------------------
# Layer 3 — LeadMagic
# ---------------------------------------------------------------------------

def test_leadmagic_email_status_field_present_passes():
    fake = _FakeResponse(200, body={"email_status": "valid", "credits_remaining": 2400})
    r = preflight.check_leadmagic(_FakeClient(response=fake))
    assert r.status == "pass"
    assert "credits_remaining=2400" in r.detail


def test_leadmagic_returns_status_not_email_status_fails():
    fake = _FakeResponse(200, body={"status": "valid"})
    r = preflight.check_leadmagic(_FakeClient(response=fake))
    assert r.status == "fail"
    assert "status" in r.detail and "email_status" in r.detail


def test_leadmagic_low_credits_warns():
    fake = _FakeResponse(200, body={"email_status": "valid", "credits_remaining": 50})
    r = preflight.check_leadmagic(_FakeClient(response=fake))
    assert r.status == "warn"
    assert "50" in r.detail


def test_leadmagic_402_fails():
    r = preflight.check_leadmagic(_FakeClient(exception=CreditsExhaustedError("402")))
    assert r.status == "fail"
    assert "402" in r.detail


# ---------------------------------------------------------------------------
# Layer 4 — Instantly accounts
# ---------------------------------------------------------------------------

def test_instantly_six_matching_accounts_passes():
    body = {"items": [
        {"email": "wilson@netgainiqgroup.com"},
        {"email": "ben@netgainiqgroup.com"},
        {"email": "outreach@netgainiqadvisory.com"},
        {"email": "wilson@netgainiqadvisory.com"},
        {"email": "team@netgainiqpartners.com"},
        {"email": "hello@netgainiqpartners.com"},
    ]}
    r = preflight.check_instantly_accounts(_FakeClient(response=_FakeResponse(200, body=body)))
    assert r.status == "pass"
    assert "6" in r.detail


def test_instantly_three_matching_accounts_warns():
    body = {"items": [
        {"email": "a@netgainiqgroup.com"},
        {"email": "b@netgainiqadvisory.com"},
        {"email": "c@netgainiqpartners.com"},
        {"email": "d@gmail.com"},
        {"email": "e@otherdomain.com"},
    ]}
    r = preflight.check_instantly_accounts(_FakeClient(response=_FakeResponse(200, body=body)))
    assert r.status == "warn"
    assert "3" in r.detail


def test_instantly_zero_matching_fails():
    body = {"items": [{"email": "a@gmail.com"}, {"email": "b@yahoo.com"}]}
    r = preflight.check_instantly_accounts(_FakeClient(response=_FakeResponse(200, body=body)))
    assert r.status == "fail"


def test_instantly_bare_list_response_works():
    body = [{"email": "a@netgainiqgroup.com"}, {"email": "b@netgainiqadvisory.com"}]
    r = preflight.check_instantly_accounts(
        _FakeClient(response=_FakeResponse(200, body=body)),
        expected_min=2,
    )
    assert r.status == "pass"


def test_instantly_unrecognized_shape_fails():
    body = "this is not a list"
    r = preflight.check_instantly_accounts(_FakeClient(response=_FakeResponse(200, body=body)))
    assert r.status == "fail"


# ---------------------------------------------------------------------------
# Layer 5 — Vault files
# ---------------------------------------------------------------------------

def test_vault_files_all_present_passes():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "tam.md").write_text("x")
        (d / "persona.md").write_text("x")
        (d / "template.md").write_text("x")
        (d / "ex.json").write_text("{}")
        (d / "la.json").write_text("[]")
        cfg = _make_pipeline_config(
            tam=d / "tam.md",
            persona=d / "persona.md",
            template=d / "template.md",
            excl=d / "ex.json",
            lookalikes=d / "la.json",
        )
        r = preflight.check_vault_files(cfg)
        assert r.status == "pass"


def test_vault_files_template_missing_fails():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "tam.md").write_text("x")
        (d / "persona.md").write_text("x")
        cfg = _make_pipeline_config(
            tam=d / "tam.md",
            persona=d / "persona.md",
            template=d / "missing.md",
            excl=d / "ex.json",
            lookalikes=d / "la.json",
        )
        r = preflight.check_vault_files(cfg)
        assert r.status == "fail"
        assert "template" in r.detail


# ---------------------------------------------------------------------------
# Layer 6 — Template quality
# ---------------------------------------------------------------------------

def test_template_quality_good_template_passes():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        p.write_text(_GOOD_TEMPLATE, encoding="utf-8")
        r = preflight.check_template_quality(p)
        assert r.status == "pass", r.detail


def test_template_quality_nested_spintax_fails():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        p.write_text(_TEMPLATE_NESTED_SPINTAX, encoding="utf-8")
        r = preflight.check_template_quality(p)
        assert r.status == "fail"
        assert "nested" in r.detail.lower()


def test_template_quality_empty_pipe_option_fails():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        p.write_text(_TEMPLATE_EMPTY_OPTION, encoding="utf-8")
        r = preflight.check_template_quality(p)
        assert r.status == "fail"
        assert "empty" in r.detail.lower()


def test_template_quality_unknown_variable_fails():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        p.write_text(_TEMPLATE_UNKNOWN_VAR, encoding="utf-8")
        r = preflight.check_template_quality(p)
        assert r.status == "fail"
        assert "totally_made_up_field" in r.detail


def test_template_quality_missing_file_fails():
    r = preflight.check_template_quality(Path("/nope/template.md"))
    assert r.status == "fail"


# ---------------------------------------------------------------------------
# Layer 7 — Template body quality (warn-only)
# ---------------------------------------------------------------------------

def test_template_body_quality_no_body_markers_warns():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        p.write_text("just text without any Body markers\n", encoding="utf-8")
        r = preflight.check_template_body_quality(p)
        assert r.status == "warn"


def test_template_body_quality_runs_against_good_template():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.md"
        p.write_text(_GOOD_TEMPLATE, encoding="utf-8")
        r = preflight.check_template_body_quality(p)
        # warn or pass — never fail (this layer is non-blocking)
        assert r.status in ("warn", "pass")


def test_template_body_quality_missing_file_warns():
    r = preflight.check_template_body_quality(Path("/nope/t.md"))
    assert r.status == "warn"


# ---------------------------------------------------------------------------
# Layer 8 — TAM parse
# ---------------------------------------------------------------------------

def test_tam_parse_good_passes():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        tam = d / "tam.md"
        la = d / "la.json"
        tam.write_text(_TAM_GOOD, encoding="utf-8")
        la.write_text(_LOOKALIKES_3, encoding="utf-8")
        r = preflight.check_tam_parse(tam, la)
        assert r.status == "pass"


def test_tam_parse_missing_keys_fails():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        tam = d / "tam.md"
        la = d / "la.json"
        tam.write_text(_TAM_MISSING_KEYS, encoding="utf-8")
        la.write_text(_LOOKALIKES_3, encoding="utf-8")
        r = preflight.check_tam_parse(tam, la)
        assert r.status == "fail"
        assert "naics_codes" in r.detail


def test_tam_parse_no_json_block_fails():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        tam = d / "tam.md"
        la = d / "la.json"
        tam.write_text(_TAM_NO_JSON, encoding="utf-8")
        la.write_text(_LOOKALIKES_3, encoding="utf-8")
        r = preflight.check_tam_parse(tam, la)
        assert r.status == "fail"


def test_tam_parse_lookalike_not_in_tam_warns():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        tam = d / "tam.md"
        la = d / "la.json"
        tam.write_text(_TAM_GOOD, encoding="utf-8")
        la.write_text(_LOOKALIKES_WITH_MISSING, encoding="utf-8")
        r = preflight.check_tam_parse(tam, la)
        assert r.status == "warn"
        assert "FakeCo" in r.detail


def test_tam_parse_tam_file_missing_fails():
    r = preflight.check_tam_parse(Path("/nope/tam.md"), Path("/nope/la.json"))
    assert r.status == "fail"


# ---------------------------------------------------------------------------
# Layer 9 — Output dir safety
# ---------------------------------------------------------------------------

def test_output_dir_no_existing_files_passes():
    with tempfile.TemporaryDirectory() as tmp:
        r = preflight.check_output_dir(today="2026-05-09", dir_=Path(tmp))
        assert r.status == "pass"


def test_output_dir_existing_today_files_warns():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "2026-05-09_contacts_verified.json").write_text("{}")
        r = preflight.check_output_dir(today="2026-05-09", dir_=d)
        assert r.status == "warn"
        assert "2026-05-09" in r.detail


def test_output_dir_missing_dir_warns():
    r = preflight.check_output_dir(today="2026-05-09", dir_=Path("/nope/never/here"))
    assert r.status == "warn"


# ---------------------------------------------------------------------------
# PreflightReport semantics
# ---------------------------------------------------------------------------

def test_report_has_failures_true_when_any_fail():
    r = preflight.PreflightReport()
    r.add(preflight.CheckResult("a", "pass", "ok"))
    r.add(preflight.CheckResult("b", "fail", "broken"))
    assert r.has_failures() is True


def test_report_has_failures_false_when_all_pass_or_warn():
    r = preflight.PreflightReport()
    r.add(preflight.CheckResult("a", "pass", "ok"))
    r.add(preflight.CheckResult("b", "warn", "noisy"))
    assert r.has_failures() is False
    assert r.has_warnings() is True


def test_report_to_dict_summary_counts():
    r = preflight.PreflightReport()
    r.add(preflight.CheckResult("a", "pass", "ok"))
    r.add(preflight.CheckResult("b", "warn", "x"))
    r.add(preflight.CheckResult("c", "fail", "x"))
    d = r.to_dict()
    assert d["summary"]["passed"] == 1
    assert d["summary"]["warned"] == 1
    assert d["summary"]["failed"] == 1
    assert len(d["checks"]) == 3


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def test_write_report_creates_dated_file():
    with tempfile.TemporaryDirectory() as tmp:
        report = preflight.PreflightReport()
        report.add(preflight.CheckResult("env", "pass", "ok"))
        path = preflight.write_report(report, out_dir=Path(tmp))
        assert path.exists()
        body = json.loads(path.read_text(encoding="utf-8"))
        assert "checks" in body
        assert body["summary"]["passed"] == 1


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_env_all_three_present_passes,
        test_env_missing_one_key_fails,
        test_env_empty_value_fails,
        test_apollo_basic_plan_passes,
        test_apollo_free_plan_fails_with_403,
        test_apollo_bad_key_fails_with_401,
        test_apollo_missing_pagination_field_fails,
        test_apollo_unreachable_fails,
        test_leadmagic_email_status_field_present_passes,
        test_leadmagic_returns_status_not_email_status_fails,
        test_leadmagic_low_credits_warns,
        test_leadmagic_402_fails,
        test_instantly_six_matching_accounts_passes,
        test_instantly_three_matching_accounts_warns,
        test_instantly_zero_matching_fails,
        test_instantly_bare_list_response_works,
        test_instantly_unrecognized_shape_fails,
        test_vault_files_all_present_passes,
        test_vault_files_template_missing_fails,
        test_template_quality_good_template_passes,
        test_template_quality_nested_spintax_fails,
        test_template_quality_empty_pipe_option_fails,
        test_template_quality_unknown_variable_fails,
        test_template_quality_missing_file_fails,
        test_template_body_quality_no_body_markers_warns,
        test_template_body_quality_runs_against_good_template,
        test_template_body_quality_missing_file_warns,
        test_tam_parse_good_passes,
        test_tam_parse_missing_keys_fails,
        test_tam_parse_no_json_block_fails,
        test_tam_parse_lookalike_not_in_tam_warns,
        test_tam_parse_tam_file_missing_fails,
        test_output_dir_no_existing_files_passes,
        test_output_dir_existing_today_files_warns,
        test_output_dir_missing_dir_warns,
        test_report_has_failures_true_when_any_fail,
        test_report_has_failures_false_when_all_pass_or_warn,
        test_report_to_dict_summary_counts,
        test_write_report_creates_dated_file,
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
