"""Unit tests for fast-path/contact_finder.py.

Run as a script (`python test_contact_finder.py`) or under pytest.
HTTP is mocked via _FakeResponse + a queue-driven _SeqClient that yields
canned responses in call order.
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

import contact_finder  # noqa: E402
from contact_finder import (  # noqa: E402
    HitRateSummary,
    build_verified_contact,
    enrich_person,
    fetch_people,
    filter_excluded,
    industry_term_for,
    lookalike_coverage,
    merge_dedupe,
    read_tam_filters,
    search_by_filter,
    search_lookalikes,
    select_contacts,
    source_email,
    validate_email,
    write_contacts,
)
from exceptions import (  # noqa: E402
    AuthFailureError,
    CreditsExhaustedError,
    FastPathHttpError,
)


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
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self  # type: ignore[attr-defined]
            raise err


class _SeqClient:
    """API client that returns queued responses in order. Each call records
    its (method, path) tuple in self.calls.
    """

    def __init__(self, queue: list[Any]):
        self._queue = list(queue)
        self.calls: list[tuple[str, str]] = []

    def call(self, method, path, **kwargs):  # noqa: ARG002
        self.calls.append((method, path))
        if not self._queue:
            raise FastPathHttpError(f"_SeqClient ran out of queued responses for {method} {path}")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ---------------------------------------------------------------------------
# Phase 1 — Lookalike pass
# ---------------------------------------------------------------------------

def test_lookalike_pass_picks_best_substring_match():
    apollo = _SeqClient([
        _FakeResponse(200, body={"organizations": [
            {"id": "1", "name": "Lincoln Electric Holdings", "primary_domain": "lincolnelectric.com"},
            {"id": "2", "name": "Lincoln National Corp", "primary_domain": "lincolnfinancial.com"},
        ]}),
    ])
    out = search_lookalikes(apollo, [{"name": "Lincoln Electric", "domain": "lincolnelectric.com"}])
    assert len(out) == 1
    assert out[0]["primary_domain"] == "lincolnelectric.com"
    assert out[0]["_source_tag"] == "lookalike"


def test_lookalike_pass_skips_unmatched_company():
    apollo = _SeqClient([_FakeResponse(200, body={"organizations": []})])
    out = search_lookalikes(apollo, [{"name": "DoesNotExistInc"}])
    assert out == []


def test_lookalike_pass_calls_one_search_per_company():
    apollo = _SeqClient([
        _FakeResponse(200, body={"organizations": [{"id": "1", "name": "Timken", "primary_domain": "timken.com"}]}),
        _FakeResponse(200, body={"organizations": [{"id": "2", "name": "Materion", "primary_domain": "materion.com"}]}),
    ])
    search_lookalikes(apollo, [{"name": "Timken"}, {"name": "Materion"}])
    assert len(apollo.calls) == 2
    assert all(c[1] == "/api/v1/organizations/search" for c in apollo.calls)


def test_lookalike_pass_propagates_credits_exhausted():
    apollo = _SeqClient([CreditsExhaustedError("402")])
    try:
        search_lookalikes(apollo, [{"name": "Timken"}])
    except CreditsExhaustedError:
        return
    raise AssertionError("expected CreditsExhaustedError to propagate")


# ---------------------------------------------------------------------------
# Phase 2 — SIC/NAICS pass
# ---------------------------------------------------------------------------

_TAM_FILTERS = {
    "sic_codes": ["3541"],
    "naics_codes": ["333515"],
    "employee_count": {"min": 2000, "max": 20000},
    "revenue_range": {"min": 500000000, "max": 5000000000},
    "hq_states": ["OH", "PA"],
}


def test_sic_naics_pass_paginates_until_empty():
    page1 = [{"id": str(i), "name": f"Co{i}", "primary_domain": f"co{i}.com"} for i in range(100)]
    page2 = [{"id": "200", "name": "LastCo", "primary_domain": "lastco.com"}]
    apollo = _SeqClient([
        _FakeResponse(200, body={"organizations": page1}),
        _FakeResponse(200, body={"organizations": page2}),  # < per_page → stop
    ])
    out = search_by_filter(apollo, _TAM_FILTERS)
    assert len(out) == 101
    assert all(o["_source_tag"] == "sic_naics" for o in out)


def test_sic_naics_pass_stops_at_max_pages():
    page = [{"id": str(i), "name": f"Co{i}", "primary_domain": f"co{i}.com"} for i in range(100)]
    apollo = _SeqClient([_FakeResponse(200, body={"organizations": page})] * 10)
    out = search_by_filter(apollo, _TAM_FILTERS)
    # MAX_SIC_NAICS_PAGES = 5
    assert len(apollo.calls) == 5


def test_filter_body_maps_tam_into_apollo_shape():
    body = contact_finder._build_apollo_org_filter_body(_TAM_FILTERS)
    assert body["sic_codes"] == ["3541"]
    assert body["naics_codes"] == ["333515"]
    assert body["organization_num_employees_ranges"] == ["2000,20000"]
    assert body["revenue_range_min"] == 500000000
    assert body["revenue_range_max"] == 5000000000
    assert body["organization_locations"] == ["OH", "PA"]


# ---------------------------------------------------------------------------
# Phase 3 — Merge + dedupe
# ---------------------------------------------------------------------------

def test_merge_dedupe_unions_by_domain():
    a = [{"id": "1", "primary_domain": "TIMKEN.com", "_source_tag": "lookalike"}]
    b = [{"id": "2", "primary_domain": "timken.com", "_source_tag": "sic_naics"}]
    out = merge_dedupe(a, b)
    assert len(out) == 1
    tags = set(out[0]["_source_tag"].split("|"))
    assert tags == {"lookalike", "sic_naics"}


def test_merge_dedupe_lowercases_domain():
    a = [{"id": "1", "primary_domain": "Foo.COM", "_source_tag": "lookalike"}]
    out = merge_dedupe(a)
    assert out[0]["primary_domain"] == "foo.com"


def test_merge_dedupe_drops_orgs_without_domain():
    a = [{"id": "1", "primary_domain": "", "_source_tag": "lookalike"}]
    b = [{"id": "2", "_source_tag": "sic_naics"}]
    out = merge_dedupe(a, b)
    assert out == []


# ---------------------------------------------------------------------------
# Phase 4 — Exclusion filter
# ---------------------------------------------------------------------------

def test_exclusion_filter_drops_listed_domains():
    orgs = [
        {"primary_domain": "timken.com"},
        {"primary_domain": "grainger.com"},
        {"primary_domain": "kennametal.com"},
        {"primary_domain": "materion.com"},
    ]
    out = filter_excluded(orgs, {"grainger.com", "kennametal.com"})
    domains = [o["primary_domain"] for o in out]
    assert domains == ["timken.com", "materion.com"]


def test_exclusion_filter_case_insensitive():
    orgs = [{"primary_domain": "GRAINGER.COM"}, {"primary_domain": "timken.com"}]
    out = filter_excluded(orgs, {"grainger.com"})
    assert [o["primary_domain"] for o in out] == ["timken.com"]


# ---------------------------------------------------------------------------
# Phase 5 — Lookalike coverage
# ---------------------------------------------------------------------------

def test_lookalike_coverage_counts_domain_matches():
    orgs = [
        {"name": "Timken", "primary_domain": "timken.com"},
        {"name": "Materion Corp", "primary_domain": "materion.com"},
        {"name": "Random Inc", "primary_domain": "random.com"},
    ]
    lookalikes = [
        {"name": "Timken", "domain": "timken.com"},
        {"name": "Materion", "aliases": ["Materion Corporation"], "domain": "materion.com"},
        {"name": "Lincoln Electric", "domain": "lincolnelectric.com"},
    ]
    matched, total = lookalike_coverage(orgs, lookalikes)
    assert matched == 2
    assert total == 3


def test_lookalike_coverage_uses_aliases_when_domain_missing():
    orgs = [{"name": "Materion Corporation", "primary_domain": "different.com"}]
    lookalikes = [{"name": "Materion", "aliases": ["Materion Corporation"], "domain": "materion.com"}]
    matched, total = lookalike_coverage(orgs, lookalikes)
    assert matched == 1


# ---------------------------------------------------------------------------
# Phase 6 — Title priority + pairing
# ---------------------------------------------------------------------------

def test_title_priority_returns_coo_before_vp_ops():
    people = [
        {"first_name": "Vp", "last_name": "Ops", "title": "VP Operations"},
        {"first_name": "C", "last_name": "Oo", "title": "COO"},
    ]
    out = select_contacts(people, max_per_company=1)
    assert out[0]["title"] == "COO"


def test_ops_finance_pairing_when_both_available():
    people = [
        {"first_name": "F1", "last_name": "L1", "title": "VP Operations"},
        {"first_name": "F2", "last_name": "L2", "title": "VP Manufacturing"},
        {"first_name": "F3", "last_name": "L3", "title": "CFO"},
    ]
    out = select_contacts(people, max_per_company=2)
    families = sorted(contact_finder._title_family(p["title"]) for p in out)
    assert families == ["fin", "ops"]


def test_max_per_company_one_returns_top_ranked_only():
    people = [
        {"title": "CFO"},
        {"title": "COO"},
    ]
    out = select_contacts(people, max_per_company=1)
    assert out[0]["title"] == "COO"


def test_no_finance_present_returns_top_two_by_priority():
    people = [
        {"title": "VP Manufacturing"},
        {"title": "COO"},
        {"title": "VP Operations"},
    ]
    out = select_contacts(people, max_per_company=2)
    titles = [p["title"] for p in out]
    assert titles == ["COO", "VP Operations"]


def test_fetch_people_returns_empty_when_org_has_no_id():
    apollo = _SeqClient([])
    out = fetch_people(apollo, {"name": "Some Co"})
    assert out == []
    assert apollo.calls == []


def test_fetch_people_passes_org_id_in_search_filter():
    apollo = _SeqClient([_FakeResponse(200, body={"people": [{"first_name": "John"}]})])
    out = fetch_people(apollo, {"id": "ABC123", "name": "Co"})
    assert len(out) == 1
    # Apollo deprecated /api/v1/people/search on 2026-05-07; we use the
    # replacement endpoint /api/v1/mixed_people/api_search.
    assert apollo.calls[0] == ("POST", "/api/v1/mixed_people/api_search")


# ---------------------------------------------------------------------------
# Phase 6.5 — Apollo people/match enrichment (unlocks preview records)
# ---------------------------------------------------------------------------

def test_enrich_person_unlocks_full_record():
    apollo = _SeqClient([_FakeResponse(200, body={
        "first_name": "Andrew",
        "last_name": "Winter",
        "email": "awinter@lincolnelectric.com",
        "title": "VP Operations",
        "id": "abc123",
    })])
    preview = {"id": "abc123", "first_name": "Andrew", "last_name_obfuscated": "Wi***r", "title": "VP Operations"}
    out = enrich_person(apollo, preview)
    assert out is not None
    assert out["last_name"] == "Winter"
    assert out["email"] == "awinter@lincolnelectric.com"
    assert apollo.calls[0] == ("POST", "/api/v1/people/match")


def test_enrich_person_returns_none_when_no_id():
    apollo = _SeqClient([])  # should never be called
    out = enrich_person(apollo, {"first_name": "Andrew"})
    assert out is None
    assert apollo.calls == []


def test_enrich_person_handles_match_failure_gracefully():
    apollo = _SeqClient([FastPathHttpError("404")])
    out = enrich_person(apollo, {"id": "abc123", "first_name": "Andrew"})
    assert out is None


def test_enrich_person_propagates_credits_exhausted():
    apollo = _SeqClient([CreditsExhaustedError("402")])
    try:
        enrich_person(apollo, {"id": "abc123"})
    except CreditsExhaustedError:
        return
    raise AssertionError("expected CreditsExhaustedError to propagate")


def test_enrich_person_unwraps_person_wrapper_when_present():
    apollo = _SeqClient([_FakeResponse(200, body={"person": {
        "id": "abc123", "first_name": "Jane", "last_name": "Doe", "email": "jd@x.com",
    }})])
    out = enrich_person(apollo, {"id": "abc123"})
    assert out is not None
    assert out["last_name"] == "Doe"
    assert out["email"] == "jd@x.com"


def test_enrich_person_preserves_preview_title_when_match_omits_it():
    apollo = _SeqClient([_FakeResponse(200, body={
        "id": "abc123", "first_name": "Andrew", "last_name": "Winter", "email": "a@b.com",
    })])
    preview = {"id": "abc123", "title": "VP Operations"}
    out = enrich_person(apollo, preview)
    assert out["title"] == "VP Operations"


# ---------------------------------------------------------------------------
# Phase 7 — Email sourcing
# ---------------------------------------------------------------------------

def test_apollo_email_present_skips_leadmagic():
    leadmagic = _SeqClient([])  # should never be called
    person = {"first_name": "John", "last_name": "Smith", "email": "john@apollo.com"}
    org = {"primary_domain": "apollo.com"}
    email, source = source_email(leadmagic, person=person, org=org)
    assert email == "john@apollo.com"
    assert source == "apollo"
    assert leadmagic.calls == []


def test_apollo_email_locked_falls_back_to_leadmagic():
    leadmagic = _SeqClient([
        _FakeResponse(200, body={"email": "john@timken.com", "status": "valid"}),
    ])
    person = {"first_name": "John", "last_name": "Smith", "email": "email_not_unlocked@domain.com"}
    org = {"primary_domain": "timken.com"}
    email, source = source_email(leadmagic, person=person, org=org)
    assert email == "john@timken.com"
    assert source == "leadmagic"


def test_apollo_email_absent_calls_leadmagic_finder():
    leadmagic = _SeqClient([
        _FakeResponse(200, body={"email": "jane@materion.com", "status": "valid"}),
    ])
    person = {"first_name": "Jane", "last_name": "Doe"}
    org = {"primary_domain": "materion.com"}
    email, source = source_email(leadmagic, person=person, org=org)
    assert source == "leadmagic"
    assert email == "jane@materion.com"


def test_leadmagic_not_found_returns_empty():
    leadmagic = _SeqClient([
        _FakeResponse(200, body={"email": "", "status": "not_found"}),
    ])
    person = {"first_name": "Phantom", "last_name": "User"}
    org = {"primary_domain": "ghosts.com"}
    email, source = source_email(leadmagic, person=person, org=org)
    assert email is None
    assert source == ""


def test_source_email_propagates_credits_exhausted():
    leadmagic = _SeqClient([CreditsExhaustedError("402")])
    person = {"first_name": "Jane", "last_name": "Doe"}
    org = {"primary_domain": "x.com"}
    try:
        source_email(leadmagic, person=person, org=org)
    except CreditsExhaustedError:
        return
    raise AssertionError("expected CreditsExhaustedError to propagate")


# ---------------------------------------------------------------------------
# Phase 8 — Validation classification
# ---------------------------------------------------------------------------

def test_validation_95_percent_returns_valid():
    leadmagic = _SeqClient([_FakeResponse(200, body={"email_status": "valid", "email_confidence": 97})])
    cls, conf = validate_email(leadmagic, "x@y.com")
    assert cls == "valid"
    assert conf == 97


def test_validation_85_percent_returns_risky():
    leadmagic = _SeqClient([_FakeResponse(200, body={"email_status": "valid", "email_confidence": 85})])
    cls, conf = validate_email(leadmagic, "x@y.com")
    assert cls == "risky"


def test_validation_60_percent_returns_rejected():
    leadmagic = _SeqClient([_FakeResponse(200, body={"email_status": "valid", "email_confidence": 60})])
    cls, conf = validate_email(leadmagic, "x@y.com")
    assert cls == "rejected"


def test_validation_catch_all_classified_as_catch_all():
    leadmagic = _SeqClient([_FakeResponse(200, body={"email_status": "catch_all"})])
    cls, _ = validate_email(leadmagic, "x@y.com")
    assert cls == "catch_all"


def test_validation_textual_status_when_no_confidence():
    leadmagic = _SeqClient([_FakeResponse(200, body={"email_status": "risky"})])
    cls, _ = validate_email(leadmagic, "x@y.com")
    assert cls == "risky"


def test_validation_402_propagates():
    leadmagic = _SeqClient([CreditsExhaustedError("402")])
    try:
        validate_email(leadmagic, "x@y.com")
    except CreditsExhaustedError:
        return
    raise AssertionError("expected CreditsExhaustedError")


# ---------------------------------------------------------------------------
# Phase 9 — Industry term + contact assembly
# ---------------------------------------------------------------------------

def test_industry_term_uses_industry_field_when_present():
    assert industry_term_for({"industry": "Bearings"}) == "bearings"


def test_industry_term_falls_back_to_industries_list():
    assert industry_term_for({"industries": ["specialty alloys"]}) == "specialty alloys"


def test_industry_term_default_when_absent():
    from contact_finder import DEFAULT_INDUSTRY_TERM
    assert industry_term_for({}) == DEFAULT_INDUSTRY_TERM
    assert industry_term_for({"industry": ""}) == DEFAULT_INDUSTRY_TERM
    assert industry_term_for({"industries": []}) == DEFAULT_INDUSTRY_TERM


def test_build_verified_contact_full_shape():
    org = {
        "id": "ORG1", "name": "Timken", "primary_domain": "timken.com",
        "estimated_num_employees": 8100, "estimated_annual_revenue": "$4.6B",
        "city": "North Canton", "state": "OH",
        "industry": "bearings", "sic_codes": ["3562"], "publicly_traded_symbol": "TKR",
        "_source_tag": "lookalike",
    }
    person = {"first_name": "John", "last_name": "Smith", "title": "VP Operations"}
    c = build_verified_contact(
        org=org, person=person, email="j.smith@timken.com",
        email_source="apollo", classification="valid", confidence=97,
    )
    assert c["first_name"] == "John"
    assert c["company_name"] == "Timken"
    assert c["company_domain"] == "timken.com"
    assert c["email_status"] == "valid"
    assert c["email_confidence"] == 97
    assert c["email_source"] == "apollo"
    assert c["industry_term"] == "bearings"
    assert c["sic_code"] == "3562"
    assert c["ownership_type"] == "public"
    assert c["source"] == "lookalike"
    assert c["hq_state"] == "OH"
    # contact_id is a uuid string
    assert isinstance(c["contact_id"], str)
    assert len(c["contact_id"]) >= 32


# ---------------------------------------------------------------------------
# read_tam_filters
# ---------------------------------------------------------------------------

def test_read_tam_filters_extracts_json_block():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "tam.md"
        p.write_text("""# TAM
```json
{
  "filters": {
    "sic_codes": ["3541"],
    "employee_count": {"min": 2000, "max": 20000}
  }
}
```
""", encoding="utf-8")
        out = read_tam_filters(p)
        assert out["sic_codes"] == ["3541"]
        assert out["employee_count"]["min"] == 2000


def test_read_tam_filters_raises_when_no_json_block():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "tam.md"
        p.write_text("# TAM\nNo JSON here.\n", encoding="utf-8")
        try:
            read_tam_filters(p)
        except Exception as e:
            assert "filters" in str(e).lower() or "tam" in str(e).lower()
        else:
            raise AssertionError("expected error")


# ---------------------------------------------------------------------------
# write_contacts
# ---------------------------------------------------------------------------

def test_write_contacts_writes_dated_json_with_summary():
    with tempfile.TemporaryDirectory() as tmp:
        contacts = [{
            "contact_id": "c1", "email": "a@b.com", "company_domain": "b.com",
            "email_status": "valid", "first_name": "A", "last_name": "B",
        }]
        s = HitRateSummary(
            organizations_discovered=10, organizations_after_exclusions=8,
            contacts_attempted=2, valid_count=1, risky_count=0,
            rejected_count=0, catch_all_count=1,
            emails_from_apollo=1, emails_from_leadmagic=0, emails_not_found=0,
            lookalikes_matched=2, lookalikes_total=10,
        )
        path = write_contacts(contacts, s, out_dir=Path(tmp), today="2026-05-09")
        assert path.exists()
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["summary"]["valid"] == 1
        assert body["summary"]["catch_all"] == 1
        assert body["summary"]["hit_rate"] == round(2 / 2, 3)
        assert len(body["contacts"]) == 1


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_lookalike_pass_picks_best_substring_match,
        test_lookalike_pass_skips_unmatched_company,
        test_lookalike_pass_calls_one_search_per_company,
        test_lookalike_pass_propagates_credits_exhausted,
        test_sic_naics_pass_paginates_until_empty,
        test_sic_naics_pass_stops_at_max_pages,
        test_filter_body_maps_tam_into_apollo_shape,
        test_merge_dedupe_unions_by_domain,
        test_merge_dedupe_lowercases_domain,
        test_merge_dedupe_drops_orgs_without_domain,
        test_exclusion_filter_drops_listed_domains,
        test_exclusion_filter_case_insensitive,
        test_lookalike_coverage_counts_domain_matches,
        test_lookalike_coverage_uses_aliases_when_domain_missing,
        test_title_priority_returns_coo_before_vp_ops,
        test_ops_finance_pairing_when_both_available,
        test_max_per_company_one_returns_top_ranked_only,
        test_no_finance_present_returns_top_two_by_priority,
        test_fetch_people_returns_empty_when_org_has_no_id,
        test_fetch_people_passes_org_id_in_search_filter,
        test_enrich_person_unlocks_full_record,
        test_enrich_person_returns_none_when_no_id,
        test_enrich_person_handles_match_failure_gracefully,
        test_enrich_person_propagates_credits_exhausted,
        test_enrich_person_unwraps_person_wrapper_when_present,
        test_enrich_person_preserves_preview_title_when_match_omits_it,
        test_apollo_email_present_skips_leadmagic,
        test_apollo_email_locked_falls_back_to_leadmagic,
        test_apollo_email_absent_calls_leadmagic_finder,
        test_leadmagic_not_found_returns_empty,
        test_source_email_propagates_credits_exhausted,
        test_validation_95_percent_returns_valid,
        test_validation_85_percent_returns_risky,
        test_validation_60_percent_returns_rejected,
        test_validation_catch_all_classified_as_catch_all,
        test_validation_textual_status_when_no_confidence,
        test_validation_402_propagates,
        test_industry_term_uses_industry_field_when_present,
        test_industry_term_falls_back_to_industries_list,
        test_industry_term_default_when_absent,
        test_build_verified_contact_full_shape,
        test_read_tam_filters_extracts_json_block,
        test_read_tam_filters_raises_when_no_json_block,
        test_write_contacts_writes_dated_json_with_summary,
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
