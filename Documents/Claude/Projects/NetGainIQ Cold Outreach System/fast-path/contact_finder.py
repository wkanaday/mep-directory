"""Module 2 — Contact Finder.

Public entry point: `find_contacts(config, env, client_pool) -> list[dict]`.

Two-phase company discovery (named lookalikes → SIC/NAICS broad search),
deduped by primary_domain, exclusion-filtered, then per-company contact
selection with title priority + Ops/Finance pairing. Each contact's email
is sourced from Apollo (when present) or LeadMagic email-finder fallback,
then validated through LeadMagic email-validation. Output is a dated JSON
file in pipeline-data/.

Apollo API field names follow Apollo's v1 convention. Some fields may
need adjustment after the first live smoke run records actual responses
to tests/fixtures/. The exception types (AuthFailure, CreditsExhausted)
propagate up so the orchestrator can halt on terminal API failures.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import requests

import config as cfg
from api_client import FastPathApiClient
from exceptions import (
    AuthFailureError,
    CreditsExhaustedError,
    FastPathError,
    FastPathHttpError,
)

logger = logging.getLogger("fast_path.contact_finder")


# ---------------------------------------------------------------------------
# Tunables — stable against API contract
# ---------------------------------------------------------------------------

ORG_SEARCH_PER_PAGE = 100
PEOPLE_SEARCH_PER_PAGE = 25
MAX_LOOKALIKES_PER_RUN = 25       # Defensive cap on the lookalike loop.
MAX_SIC_NAICS_PAGES = 5           # 5 × 100 = 500 orgs max from broad search.

VALID_CONFIDENCE_FLOOR = 95
RISKY_CONFIDENCE_FLOOR = 80

OPS_TOKENS = ("operations", "manufacturing", "operating")
FIN_TOKENS = ("finance", "financial", "cfo")


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class HitRateSummary:
    organizations_discovered: int = 0
    organizations_after_exclusions: int = 0
    contacts_attempted: int = 0
    emails_from_apollo: int = 0
    emails_from_leadmagic: int = 0
    emails_not_found: int = 0
    valid_count: int = 0
    risky_count: int = 0
    rejected_count: int = 0
    catch_all_count: int = 0
    lookalikes_matched: int = 0
    lookalikes_total: int = 0

    def hit_rate(self) -> float:
        if self.contacts_attempted == 0:
            return 0.0
        return (self.valid_count + self.risky_count + self.catch_all_count) / self.contacts_attempted


# ---------------------------------------------------------------------------
# Phase 1 — Lookalike pass
# ---------------------------------------------------------------------------

def search_lookalikes(
    apollo: FastPathApiClient,
    lookalikes: list[dict],
) -> list[dict]:
    """Resolve each named lookalike to one Apollo organization. Returns a
    list of org dicts tagged with `source="lookalike"`.
    """
    orgs: list[dict] = []
    for entry in lookalikes[:MAX_LOOKALIKES_PER_RUN]:
        name = entry.get("name")
        if not name:
            continue
        try:
            resp = apollo.call(
                "POST",
                "/api/v1/organizations/search",
                json={"q_organization_name": name, "page": 1, "per_page": 5},
            )
        except (AuthFailureError, CreditsExhaustedError):
            raise
        except (requests.HTTPError, FastPathHttpError) as e:
            logger.warning(f"lookalike '{name}' failed: {e}")
            continue
        body = _safe_json(resp)
        org = _select_best_org_match(name, _read_orgs(body))
        if org is None:
            logger.info(f"lookalike '{name}' returned no Apollo match")
            continue
        org["_source_tag"] = "lookalike"
        org["_lookalike_name"] = name
        orgs.append(org)
    return orgs


def _select_best_org_match(query: str, candidates: list[dict]) -> Optional[dict]:
    """Pick the Apollo organization most likely to match the query name.
    Strategy: case-insensitive substring of organization_name, prefer
    shorter names (less likely to be a parent group / subsidiary).
    """
    qlower = query.lower().strip()
    matches = [c for c in candidates if qlower in (c.get("name") or "").lower()]
    if not matches:
        return candidates[0] if candidates else None
    matches.sort(key=lambda c: len(c.get("name") or ""))
    return matches[0]


# ---------------------------------------------------------------------------
# Phase 2 — SIC/NAICS broad search
# ---------------------------------------------------------------------------

def search_by_filter(
    apollo: FastPathApiClient,
    tam_filters: dict,
) -> list[dict]:
    """Run the broad SIC/NAICS organization search. Paginates up to
    MAX_SIC_NAICS_PAGES. Each org tagged with `source="sic_naics"`.
    """
    orgs: list[dict] = []
    base_body = _build_apollo_org_filter_body(tam_filters)
    for page in range(1, MAX_SIC_NAICS_PAGES + 1):
        body = dict(base_body)
        body["page"] = page
        body["per_page"] = ORG_SEARCH_PER_PAGE
        try:
            resp = apollo.call("POST", "/api/v1/organizations/search", json=body)
        except (AuthFailureError, CreditsExhaustedError):
            raise
        except (requests.HTTPError, FastPathHttpError) as e:
            logger.warning(f"sic/naics page {page} failed: {e}")
            break
        page_orgs = _read_orgs(_safe_json(resp))
        if not page_orgs:
            break
        for org in page_orgs:
            org["_source_tag"] = "sic_naics"
        orgs.extend(page_orgs)
        if len(page_orgs) < ORG_SEARCH_PER_PAGE:
            break
    return orgs


def _build_apollo_org_filter_body(tam_filters: dict) -> dict:
    """Map TAM filter parameters into Apollo's expected request shape.

    Apollo accepts these in the organizations/search body:
      - sic_codes, naics_codes (lists of strings)
      - organization_num_employees_ranges (list of "min,max" strings)
      - revenue_range_min, revenue_range_max (USD ints)
      - organization_locations (list of state codes)
    """
    body: dict[str, Any] = {}
    if "sic_codes" in tam_filters:
        body["sic_codes"] = tam_filters["sic_codes"]
    if "naics_codes" in tam_filters:
        body["naics_codes"] = tam_filters["naics_codes"]
    emp = tam_filters.get("employee_count", {})
    if isinstance(emp, dict) and "min" in emp and "max" in emp:
        body["organization_num_employees_ranges"] = [f"{emp['min']},{emp['max']}"]
    rev = tam_filters.get("revenue_range", {})
    if isinstance(rev, dict):
        if "min" in rev:
            body["revenue_range_min"] = rev["min"]
        if "max" in rev:
            body["revenue_range_max"] = rev["max"]
    if "hq_states" in tam_filters:
        body["organization_locations"] = tam_filters["hq_states"]
    return body


# ---------------------------------------------------------------------------
# Phase 3 — Merge + dedupe
# ---------------------------------------------------------------------------

def merge_dedupe(*org_lists: list[dict]) -> list[dict]:
    """Union all org lists, deduped by `primary_domain` (lowercased). When
    the same domain appears in multiple lists, merge the source tags into
    `_source_tag = "lookalike|sic_naics" | "lookalike" | "sic_naics"`.
    """
    by_domain: dict[str, dict] = {}
    for orgs in org_lists:
        for org in orgs:
            domain = (org.get("primary_domain") or "").strip().lower()
            if not domain:
                continue
            if domain in by_domain:
                existing = by_domain[domain]
                existing_tags = set(existing.get("_source_tag", "").split("|"))
                new_tags = set(org.get("_source_tag", "").split("|"))
                merged_tags = sorted(t for t in (existing_tags | new_tags) if t)
                existing["_source_tag"] = "|".join(merged_tags)
            else:
                org["primary_domain"] = domain
                by_domain[domain] = org
    return list(by_domain.values())


# ---------------------------------------------------------------------------
# Phase 4 — Exclusion filter
# ---------------------------------------------------------------------------

def filter_excluded(orgs: list[dict], excluded_domains: set[str]) -> list[dict]:
    return [
        o for o in orgs
        if (o.get("primary_domain") or "").strip().lower() not in excluded_domains
    ]


# ---------------------------------------------------------------------------
# Phase 5 — Lookalike coverage metric
# ---------------------------------------------------------------------------

def lookalike_coverage(
    orgs: list[dict],
    lookalikes: list[dict],
) -> tuple[int, int]:
    """Count how many of the lookalikes appear in the surviving org list,
    matched by domain or name.
    """
    domains = {(o.get("primary_domain") or "").lower() for o in orgs}
    names = {(o.get("name") or "").lower() for o in orgs}
    matched = 0
    for la in lookalikes:
        d = (la.get("domain") or "").lower()
        n = (la.get("name") or "").lower()
        aliases = [a.lower() for a in la.get("aliases", [])]
        if d and d in domains:
            matched += 1
            continue
        if any(an in names for an in [n] + aliases if an):
            matched += 1
    return matched, len(lookalikes)


# ---------------------------------------------------------------------------
# Phase 6 — Per-company contact selection
# ---------------------------------------------------------------------------

def fetch_people(apollo: FastPathApiClient, org: dict) -> list[dict]:
    """Pull people for one organization, filtered by the title priority
    list. Returns list of person dicts.

    Uses /api/v1/mixed_people/api_search (the legacy /api/v1/people/search
    was deprecated for API callers as of 2026-05-07). Note: this endpoint
    returns *previews* — `last_name` is obfuscated and `email` is absent.
    Call `enrich_person()` per selected contact to unlock the full record.
    """
    org_id = org.get("id") or org.get("organization_id")
    if not org_id:
        return []
    try:
        resp = apollo.call(
            "POST",
            "/api/v1/mixed_people/api_search",
            json={
                "organization_ids": [org_id],
                "person_titles": cfg.TITLE_PRIORITY,
                "page": 1,
                "per_page": PEOPLE_SEARCH_PER_PAGE,
            },
        )
    except (AuthFailureError, CreditsExhaustedError):
        raise
    except (requests.HTTPError, FastPathHttpError) as e:
        logger.warning(f"people search failed for org {org_id}: {e}")
        return []
    body = _safe_json(resp)
    return body.get("people") or body.get("contacts") or []


def enrich_person(apollo: FastPathApiClient, person: dict) -> Optional[dict]:
    """Unlock a preview record by calling /api/v1/people/match. Returns
    the full person dict (with `last_name` and `email`) on success, or
    `None` if the person has no id or the match call fails.

    Costs one Apollo people-enrichment credit per call. Call only on
    contacts that survive `select_contacts()` to minimize spend.
    """
    pid = person.get("id")
    if not pid:
        return None
    try:
        resp = apollo.call(
            "POST",
            "/api/v1/people/match",
            json={"id": pid},
        )
    except (AuthFailureError, CreditsExhaustedError):
        raise
    except (requests.HTTPError, FastPathHttpError) as e:
        logger.warning(f"people/match failed for person {pid}: {e}")
        return None
    body = _safe_json(resp)
    unlocked = body.get("person") if isinstance(body.get("person"), dict) else body
    if not isinstance(unlocked, dict) or not unlocked.get("id"):
        return None
    # Preserve the preview's title (the match endpoint can return a
    # different employment record); the search-side title is what
    # passed select_contacts() title-rank, so keep it authoritative.
    if person.get("title") and not unlocked.get("title"):
        unlocked["title"] = person["title"]
    return unlocked


def select_contacts(people: list[dict], *, max_per_company: int = 2) -> list[dict]:
    """Rank by title priority, then prefer one Ops + one Finance when both
    exist. Returns up to `max_per_company` people.
    """
    ranked = sorted(people, key=lambda p: _title_rank(p.get("title", "")))
    if max_per_company == 1 or len(ranked) <= 1:
        return ranked[:max_per_company]

    ops = next((p for p in ranked if _title_family(p.get("title", "")) == "ops"), None)
    fin = next((p for p in ranked if _title_family(p.get("title", "")) == "fin"), None)
    if ops and fin and ops is not fin:
        return [ops, fin][:max_per_company]
    return ranked[:max_per_company]


def _title_rank(title: str) -> int:
    if not title:
        return 999
    title_lower = title.lower()
    for i, target in enumerate(cfg.TITLE_PRIORITY):
        if target.lower() in title_lower or title_lower in target.lower():
            return i
    # Generic fallback: penalize unrecognized titles last.
    return 500


def _title_family(title: str) -> str:
    """Classify title into 'ops' | 'fin' | 'other' for pairing."""
    if not title:
        return "other"
    tl = title.lower()
    if any(tok in tl for tok in OPS_TOKENS):
        return "ops"
    if any(tok in tl for tok in FIN_TOKENS):
        return "fin"
    return "other"


# ---------------------------------------------------------------------------
# Phase 7 + 8 — Email sourcing + validation
# ---------------------------------------------------------------------------

def source_email(
    leadmagic: FastPathApiClient,
    *,
    person: dict,
    org: dict,
) -> tuple[Optional[str], str]:
    """Return (email, source) for a person. Source is "apollo" if Apollo
    already supplied an email, "leadmagic" if we resolve via finder, or
    "" if nothing found.
    """
    apollo_email = (person.get("email") or "").strip()
    if apollo_email and apollo_email.lower() != "email_not_unlocked@domain.com":
        return apollo_email, "apollo"

    domain = (org.get("primary_domain") or "").strip()
    first = (person.get("first_name") or "").strip()
    last = (person.get("last_name") or "").strip()
    if not (domain and first and last):
        return None, ""

    try:
        resp = leadmagic.call(
            "POST",
            "/v1/people/email-finder",
            json={
                "first_name": first,
                "last_name": last,
                "domain": domain,
            },
        )
    except (AuthFailureError, CreditsExhaustedError):
        raise
    except (requests.HTTPError, FastPathHttpError) as e:
        logger.warning(f"leadmagic finder failed for {first} {last} @ {domain}: {e}")
        return None, ""

    body = _safe_json(resp)
    email = (body.get("email") or "").strip()
    if not email or body.get("status") == "not_found":
        return None, ""
    return email, "leadmagic"


def validate_email(
    leadmagic: FastPathApiClient,
    email: str,
) -> tuple[str, Optional[int]]:
    """Run LeadMagic email-validation. Returns (classification, confidence_pct).
    Classification ∈ {"valid", "risky", "rejected", "catch_all"}.
    """
    try:
        resp = leadmagic.call(
            "POST",
            "/v1/people/email-validation",
            json={"email": email},
        )
    except (AuthFailureError, CreditsExhaustedError):
        raise
    except (requests.HTTPError, FastPathHttpError) as e:
        logger.warning(f"leadmagic validation failed for {email}: {e}")
        return "rejected", None

    body = _safe_json(resp)
    status = (body.get("email_status") or "").lower()
    confidence = body.get("email_confidence") or body.get("confidence_score")
    try:
        confidence_int = int(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_int = None

    if status == "catch_all" or status == "catch-all":
        return "catch_all", confidence_int
    if confidence_int is not None:
        if confidence_int >= VALID_CONFIDENCE_FLOOR:
            return "valid", confidence_int
        if confidence_int >= RISKY_CONFIDENCE_FLOOR:
            return "risky", confidence_int
        return "rejected", confidence_int
    # Fallback when no numeric confidence: trust the textual status.
    if status == "valid":
        return "valid", confidence_int
    if status in ("risky", "uncertain", "unknown"):
        return "risky", confidence_int
    return "rejected", confidence_int


# ---------------------------------------------------------------------------
# Phase 9 — Industry term + assemble VerifiedContact
# ---------------------------------------------------------------------------

DEFAULT_INDUSTRY_TERM = "specialty manufacturing"


def industry_term_for(org: dict) -> str:
    raw = org.get("industry")
    if not raw:
        industries = org.get("industries")
        if isinstance(industries, list) and industries:
            raw = industries[0]
    if not raw or not str(raw).strip():
        return DEFAULT_INDUSTRY_TERM
    return str(raw).strip().lower()


def build_verified_contact(
    *,
    org: dict,
    person: dict,
    email: str,
    email_source: str,
    classification: str,
    confidence: Optional[int],
) -> dict:
    return {
        "contact_id": str(uuid.uuid4()),
        "first_name": (person.get("first_name") or "").strip(),
        "last_name": (person.get("last_name") or "").strip(),
        "email": email,
        "email_status": classification,
        "email_confidence": confidence,
        "email_source": email_source,
        "title": (person.get("title") or "").strip(),
        "company_name": (org.get("name") or "").strip(),
        "company_domain": (org.get("primary_domain") or "").strip().lower(),
        "employee_count": org.get("estimated_num_employees") or org.get("employee_count"),
        "revenue_estimate": org.get("estimated_annual_revenue") or org.get("revenue_estimate"),
        "facility_count": org.get("facility_count"),
        "hq_city": org.get("city") or org.get("hq_city"),
        "hq_state": org.get("state") or org.get("hq_state"),
        "industry_term": industry_term_for(org),
        "sic_code": _first_or_none(org.get("sic_codes") or org.get("primary_sic_code")),
        "ownership_type": org.get("ownership_type") or _infer_ownership(org),
        "source": (org.get("_source_tag") or "sic_naics"),
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _first_or_none(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _infer_ownership(org: dict) -> Optional[str]:
    if org.get("publicly_traded_symbol") or org.get("ticker"):
        return "public"
    return None


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def find_contacts(
    config: cfg.PipelineConfig,
    env: dict[str, str],
    client_pool: dict[str, FastPathApiClient],
    *,
    summary: Optional[HitRateSummary] = None,
) -> list[dict]:
    """Run the full discovery pipeline. Returns the list of verified contacts.

    Mutates `summary` in place for the orchestrator/log, when supplied.
    """
    summary = summary if summary is not None else HitRateSummary()
    apollo = client_pool["apollo"]
    leadmagic = client_pool["leadmagic"]

    lookalikes = cfg.load_lookalikes(config.lookalikes_path)
    summary.lookalikes_total = len(lookalikes)
    excluded = cfg.load_exclusions(config.exclusions_path)
    tam_filters = read_tam_filters(config.tam_path)

    lookalike_orgs = search_lookalikes(apollo, lookalikes)
    naics_orgs = search_by_filter(apollo, tam_filters)
    organizations = merge_dedupe(lookalike_orgs, naics_orgs)
    summary.organizations_discovered = len(organizations)

    organizations = filter_excluded(organizations, excluded)
    summary.organizations_after_exclusions = len(organizations)
    summary.lookalikes_matched, summary.lookalikes_total = lookalike_coverage(organizations, lookalikes)

    verified: list[dict] = []
    for org in organizations:
        if len(verified) >= config.max_contacts:
            break
        people = fetch_people(apollo, org)
        selected = select_contacts(people, max_per_company=config.max_per_company)
        for preview in selected:
            if len(verified) >= config.max_contacts:
                break
            summary.contacts_attempted += 1
            # mixed_people/api_search returns previews (obfuscated last_name,
            # no email). Unlock via /people/match before sourcing email.
            person = enrich_person(apollo, preview) or preview
            email, source = source_email(leadmagic, person=person, org=org)
            if not email:
                summary.emails_not_found += 1
                continue
            if source == "apollo":
                summary.emails_from_apollo += 1
            elif source == "leadmagic":
                summary.emails_from_leadmagic += 1
            classification, confidence = validate_email(leadmagic, email)
            if classification == "rejected":
                summary.rejected_count += 1
                continue
            if classification == "valid":
                summary.valid_count += 1
            elif classification == "risky":
                summary.risky_count += 1
            elif classification == "catch_all":
                summary.catch_all_count += 1
            verified.append(build_verified_contact(
                org=org, person=person, email=email,
                email_source=source, classification=classification,
                confidence=confidence,
            ))
    return verified


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

_TAM_JSON_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def read_tam_filters(tam_path: Path) -> dict:
    """Pull the `filters` block out of the TAM markdown's Apollo Validation
    Parameters JSON section.
    """
    text = tam_path.read_text(encoding="utf-8")
    for m in _TAM_JSON_RE.finditer(text):
        try:
            block = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        filters = block.get("filters") if isinstance(block, dict) else None
        if filters:
            return filters
    raise FastPathError(f"No filters block found in TAM file: {tam_path}")


def write_contacts(
    contacts: list[dict],
    summary: HitRateSummary,
    *,
    out_dir: Optional[Path] = None,
    today: Optional[str] = None,
) -> Path:
    target_dir = out_dir or cfg.PIPELINE_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    today = today or date.today().isoformat()
    out_path = target_dir / f"{today}_contacts_verified.json"
    payload = {
        "run_date": today,
        "summary": {
            "organizations_discovered": summary.organizations_discovered,
            "organizations_after_exclusions": summary.organizations_after_exclusions,
            "contacts_attempted": summary.contacts_attempted,
            "valid": summary.valid_count,
            "risky": summary.risky_count,
            "rejected": summary.rejected_count,
            "catch_all": summary.catch_all_count,
            "emails_from_apollo": summary.emails_from_apollo,
            "emails_from_leadmagic": summary.emails_from_leadmagic,
            "emails_not_found": summary.emails_not_found,
            "lookalikes_matched": summary.lookalikes_matched,
            "lookalikes_total": summary.lookalikes_total,
            "hit_rate": round(summary.hit_rate(), 3),
        },
        "contacts": contacts,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _safe_json(resp) -> dict:
    try:
        body = resp.json()
        return body if isinstance(body, dict) else {"_raw": body}
    except Exception:  # noqa: BLE001
        return {}


def _read_orgs(body: dict) -> list[dict]:
    for key in ("organizations", "accounts", "results", "items"):
        val = body.get(key)
        if isinstance(val, list):
            return val
    return []
