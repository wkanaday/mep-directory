"""Module 1 — Preflight validator.

Runs nine independent validation layers against environment, APIs, vault
files, and template quality before the rest of the pipeline executes.

Each layer returns a CheckResult with status `pass | warn | fail` and a
human-readable detail string. The orchestrator stops if any layer fails;
warnings are surfaced but non-blocking.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import requests

import config as cfg
from api_client import FastPathApiClient
from exceptions import (
    AuthFailureError,
    CreditsExhaustedError,
    FastPathError,
    FastPathHttpError,
    PreflightFailure,
)

logger = logging.getLogger("fast_path.preflight")

# Make check_scoring importable from cold-email-template-writer/scripts/.
sys.path.insert(
    0,
    str(cfg.PROJECT_ROOT / "cold-email-template-writer" / "scripts"),
)
try:
    from check_scoring import check_with_detail as _scoring_check  # type: ignore
except Exception:  # noqa: BLE001 — log+disable if the helper isn't available
    _scoring_check = None  # type: ignore


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

CheckStatus = Literal["pass", "warn", "fail"]

KNOWN_VARIABLE_SLOTS = frozenset({
    "first_name",
    "last_name",
    "company_name",
    "company_domain",
    "industry_term",
    "sender_name",
    "facility_count",
    "hq_city",
    "hq_state",
    "revenue_range",
    "ownership_type",
})


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class PreflightReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)

    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "run_date": date.today().isoformat(),
            "summary": {
                "passed": sum(1 for c in self.checks if c.status == "pass"),
                "warned": sum(1 for c in self.checks if c.status == "warn"),
                "failed": sum(1 for c in self.checks if c.status == "fail"),
            },
            "checks": [c.to_dict() for c in self.checks],
        }


# ---------------------------------------------------------------------------
# Layer 1 — Environment
# ---------------------------------------------------------------------------

def check_env(env: dict[str, str]) -> CheckResult:
    missing = [k for k in ("APOLLO_API_KEY", "LEADMAGIC_API_KEY", "INSTANTLY_API_KEY")
               if not env.get(k, "").strip()]
    if missing:
        return CheckResult(
            "env",
            "fail",
            f"missing/empty .env keys: {', '.join(missing)}",
        )
    return CheckResult("env", "pass", "all three API keys present")


# ---------------------------------------------------------------------------
# Layer 2 — Apollo auth + plan tier
# ---------------------------------------------------------------------------

def check_apollo_plan(client: FastPathApiClient) -> CheckResult:
    """POST /api/v1/mixed_people/api_search with a small filter — zero
    credit cost. The legacy /api/v1/people/search was deprecated for API
    callers (returns 422 with a deprecation message redirecting here).

    The new endpoint returns 200 with `total_entries` at top level (not
    nested under `pagination`). Basic plan succeeds; free plan returns
    403; bad key returns 401.
    """
    try:
        resp = client.call(
            "POST",
            "/api/v1/mixed_people/api_search",
            json={"q_organization_domains_list": ["apollo.io"], "per_page": 1},
        )
    except AuthFailureError:
        return CheckResult("apollo_plan", "fail", "401 — Apollo API key rejected")
    except CreditsExhaustedError:
        return CheckResult("apollo_plan", "fail", "402 — Apollo credits exhausted")
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "??") if hasattr(e, "response") else "??"
        if code == 403:
            return CheckResult(
                "apollo_plan",
                "fail",
                "403 — Apollo on free plan; People Search requires Basic+",
            )
        return CheckResult("apollo_plan", "fail", f"unexpected {code} response from Apollo")
    except FastPathHttpError as e:
        return CheckResult("apollo_plan", "fail", f"Apollo unreachable: {e}")

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return CheckResult("apollo_plan", "fail", "Apollo returned non-JSON response")

    # Accept either top-level `total_entries` (new mixed_people/api_search)
    # or nested `pagination.total_entries` (legacy shape, in case Apollo
    # mixes responses or rolls back).
    total = body.get("total_entries")
    if total is None and isinstance(body.get("pagination"), dict):
        total = body["pagination"].get("total_entries")
    if total is not None:
        return CheckResult(
            "apollo_plan",
            "pass",
            f"Basic plan active (total_entries={total})",
        )
    return CheckResult(
        "apollo_plan",
        "fail",
        "Apollo response missing total_entries (and pagination.total_entries)",
    )


# ---------------------------------------------------------------------------
# Layer 3 — LeadMagic endpoint validation
# ---------------------------------------------------------------------------

def check_leadmagic(client: FastPathApiClient) -> CheckResult:
    """Verify the email-validation endpoint responds with the expected
    `email_status` field name (NOT `status` — known gotcha).

    Uses the API owner's own email (Wilson's) for validation. 1 credit.
    Skips the email-finder probe by default — finder costs are negative-only
    (free on not_found), so confirming the validation endpoint shape is
    sufficient for preflight.
    """
    try:
        resp = client.call(
            "POST",
            "/v1/people/email-validation",
            json={"email": "wkanaday@gmail.com"},
        )
    except AuthFailureError:
        return CheckResult("leadmagic", "fail", "401 — LeadMagic API key rejected")
    except CreditsExhaustedError:
        return CheckResult("leadmagic", "fail", "402 — LeadMagic credits exhausted")
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "??") if hasattr(e, "response") else "??"
        return CheckResult("leadmagic", "fail", f"LeadMagic returned {code}")
    except FastPathHttpError as e:
        return CheckResult("leadmagic", "fail", f"LeadMagic unreachable: {e}")

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return CheckResult("leadmagic", "fail", "LeadMagic returned non-JSON response")

    if "status" in body and "email_status" not in body:
        return CheckResult(
            "leadmagic",
            "fail",
            "LeadMagic returned `status` instead of `email_status` — API contract changed",
        )
    if "email_status" not in body:
        return CheckResult(
            "leadmagic",
            "fail",
            f"LeadMagic response missing `email_status` field. Got keys: {sorted(body.keys())}",
        )

    credits = body.get("credits_remaining")
    if credits is not None and credits < 100:
        return CheckResult(
            "leadmagic",
            "warn",
            f"LeadMagic email_status field present, but credits_remaining={credits} < 100",
        )
    return CheckResult(
        "leadmagic",
        "pass",
        f"email_status field present"
        + (f"; credits_remaining={credits}" if credits is not None else ""),
    )


# ---------------------------------------------------------------------------
# Layer 4 — Instantly account discovery
# ---------------------------------------------------------------------------

def check_instantly_accounts(
    client: FastPathApiClient,
    *,
    expected_min: int = 6,
) -> CheckResult:
    """GET /api/v2/accounts — filter for the three NetGainIQ sending domains.
    Warn (not fail) when count is below expected_min so an in-progress
    warm-up doesn't block the pipeline.
    """
    try:
        resp = client.call("GET", "/api/v2/accounts")
    except AuthFailureError:
        return CheckResult("instantly_accounts", "fail", "401 — Instantly API key rejected")
    except FastPathHttpError as e:
        return CheckResult("instantly_accounts", "fail", f"Instantly unreachable: {e}")
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "??") if hasattr(e, "response") else "??"
        return CheckResult("instantly_accounts", "fail", f"Instantly returned {code}")

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return CheckResult("instantly_accounts", "fail", "Instantly returned non-JSON response")

    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        items = body.get("items", body.get("data", []))
    else:
        items = None
    if not isinstance(items, list):
        return CheckResult(
            "instantly_accounts",
            "fail",
            f"Instantly response shape unrecognized; expected list, got {type(body).__name__}",
        )

    matched = []
    for acct in items:
        email = (acct.get("email") or "").strip().lower()
        if any(email.endswith(f"@{d}") or email.endswith(f".{d}") for d in cfg.SENDING_DOMAINS):
            matched.append(email)

    if len(matched) == 0:
        return CheckResult(
            "instantly_accounts",
            "fail",
            "no sending accounts matched the three NetGainIQ domains",
        )
    if len(matched) < expected_min:
        return CheckResult(
            "instantly_accounts",
            "warn",
            f"only {len(matched)} accounts on the three domains (expected ≥ {expected_min})",
        )
    return CheckResult(
        "instantly_accounts",
        "pass",
        f"{len(matched)} sending accounts on the three NetGainIQ domains",
    )


# ---------------------------------------------------------------------------
# Layer 5 — Vault files exist
# ---------------------------------------------------------------------------

def check_vault_files(config: cfg.PipelineConfig) -> CheckResult:
    missing = []
    for label, path in (
        ("tam", config.tam_path),
        ("persona", config.persona_path),
        ("template", config.template_path),
    ):
        if not path.exists():
            missing.append(f"{label}: {path}")
    if missing:
        return CheckResult(
            "vault_files",
            "fail",
            "missing input files — " + " | ".join(missing),
        )
    return CheckResult("vault_files", "pass", "tam, persona, template all present")


# ---------------------------------------------------------------------------
# Layer 6 — Template parse + quality
# ---------------------------------------------------------------------------

def check_template_quality(template_path: Path) -> CheckResult:
    if not template_path.exists():
        return CheckResult("template_quality", "fail", f"template not readable at {template_path}")
    text = template_path.read_text(encoding="utf-8")

    # Strip YAML frontmatter so its `variable_slots:` list isn't mistaken for usage.
    body = _strip_frontmatter(text)

    # Walk top-level brace blocks. Variables (e.g. {company_name}) are
    # allowed inside a spintax block's options. What is forbidden is a
    # spintax block containing another spintax block (`{a|b {c|d}}`) —
    # nested resolution is out of scope and silently mis-resolves.
    top_blocks = _scan_top_level_blocks(body)
    for start, end, content in top_blocks:
        if "|" in content:
            inner = _scan_top_level_blocks(content)
            for ist, iend, icontent in inner:
                if "|" in icontent:
                    return CheckResult(
                        "template_quality",
                        "fail",
                        f"nested spintax detected near offset {start}: "
                        f"outer {{{content[:40]}...}} contains inner {{{icontent[:40]}...}}",
                    )

    unknown_vars: list[str] = []
    empty_options: list[str] = []
    seen_vars: set[str] = set()
    for start, end, content in top_blocks:
        if "|" in content:
            # Split top-level pipes — pipes inside nested braces (i.e.
            # variables in options) are already constrained above.
            options = _split_top_level_pipes(content)
            if any(opt.strip() == "" for opt in options):
                empty_options.append(content)
            # Collect any variable names referenced inside the spintax
            # options so they get the same known-slot validation.
            for opt in options:
                for m in re.finditer(r"\{([^{}|]+)\}", opt):
                    name = m.group(1).strip()
                    if not name:
                        empty_options.append(name)
                        continue
                    seen_vars.add(name)
                    if name not in KNOWN_VARIABLE_SLOTS:
                        unknown_vars.append(name)
        else:
            name = content.strip()
            if not name:
                empty_options.append(content)
                continue
            seen_vars.add(name)
            if name not in KNOWN_VARIABLE_SLOTS:
                unknown_vars.append(name)

    problems = []
    if empty_options:
        problems.append(f"empty spintax option(s) or variable(s) near: {empty_options[:3]}")
    if unknown_vars:
        problems.append(f"unknown variable slot(s): {sorted(set(unknown_vars))[:8]}")

    if problems:
        return CheckResult("template_quality", "fail", "; ".join(problems))
    return CheckResult(
        "template_quality",
        "pass",
        f"{len(seen_vars)} known variables, all spintax options non-empty",
    )


def _scan_top_level_blocks(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, content) for every top-level `{...}` block.
    Tracks brace depth so nested braces are returned only as the outer
    block — not split into pieces.
    """
    blocks: list[tuple[int, int, str]] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    blocks.append((start, i, text[start + 1:i]))
                    start = -1
    return blocks


def _split_top_level_pipes(content: str) -> list[str]:
    """Split a spintax-block content on pipes that are NOT inside an inner
    `{...}` (variable). Mirrors the brace-aware splitting the assembler
    will need at substitution time.
    """
    options: list[str] = []
    depth = 0
    last = 0
    for i, ch in enumerate(content):
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
        elif ch == "|" and depth == 0:
            options.append(content[last:i])
            last = i + 1
    options.append(content[last:])
    return options


def _strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (between two `---` lines)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    nl = text.find("\n", end + 4)
    if nl == -1:
        return ""
    return text[nl + 1:]


# ---------------------------------------------------------------------------
# Layer 7 — Template body quality (warn-only)
# ---------------------------------------------------------------------------

_SPINTAX_RE = re.compile(r"\{([^{}|]+\|[^{}]+)\}")
# Body sections in the template are introduced by `**Body:**` (markdown bold).
# This matches the format established by industrial-tooling-metalworking-email-templates.md
# and assumed for the new manufacturing-evergreen template.
_BODY_MARKER_RE = re.compile(r"^\*\*Body:\*\*\s*$", re.MULTILINE)


def check_template_body_quality(template_path: Path) -> CheckResult:
    """Resolve spintax to its first option, leave variables as-is, and run
    check_scoring against each candidate email body. Warns on any failure
    — variables aren't substituted yet, so this is best-effort guidance,
    not a hard gate.
    """
    if _scoring_check is None:
        return CheckResult(
            "template_body_quality",
            "warn",
            "check_scoring helper unavailable; skipped body quality validation",
        )
    if not template_path.exists():
        return CheckResult(
            "template_body_quality",
            "warn",
            f"template not readable at {template_path}",
        )
    text = template_path.read_text(encoding="utf-8")
    body = _strip_frontmatter(text)
    resolved = _SPINTAX_RE.sub(lambda m: m.group(1).split("|", 1)[0], body)

    candidates = _split_email_bodies(resolved)
    if not candidates:
        return CheckResult(
            "template_body_quality",
            "warn",
            "no email body candidates found in template (no `**Body:**` markers)",
        )

    failures = []
    for i, candidate in enumerate(candidates, start=1):
        try:
            detail = _scoring_check(candidate, max_words=cfg.EMAIL_BODY_MAX_WORDS)
        except TypeError:
            # Pre-refactor check_scoring signature — gracefully skip.
            return CheckResult(
                "template_body_quality",
                "warn",
                "check_scoring not yet refactored to accept max_words; skipped",
            )
        broken = [k for k, v in detail.items() if not v["passed"]]
        if broken:
            failures.append(f"body#{i}: {broken}")

    if failures:
        return CheckResult(
            "template_body_quality",
            "warn",
            f"{len(failures)}/{len(candidates)} candidate bodies failed scoring "
            f"(variables unresolved): {failures[:3]}",
        )
    return CheckResult(
        "template_body_quality",
        "pass",
        f"all {len(candidates)} candidate bodies passed scoring",
    )


def _split_email_bodies(text: str) -> list[str]:
    """Find each email body block introduced by a `**Body:**` line. Each
    block runs until the next `**` heading (e.g., `**Spintax variations:**`,
    `**Word count:**`, `**Subject lines:**`) or the next markdown section.
    """
    body_positions = [m.end() for m in _BODY_MARKER_RE.finditer(text)]
    if not body_positions:
        return []

    bodies: list[str] = []
    for start in body_positions:
        # End of body: next `**Foo:**` line, or next `### `/`## `, or EOF.
        end_candidates = []
        for terminator_re in (
            re.compile(r"^\*\*[^*\n]+\*\*", re.MULTILINE),
            re.compile(r"^#{1,3} ", re.MULTILINE),
        ):
            m = terminator_re.search(text, start + 1)
            if m:
                end_candidates.append(m.start())
        end = min(end_candidates) if end_candidates else len(text)
        body = text[start:end].strip()
        if body:
            bodies.append(body)
    return bodies


# ---------------------------------------------------------------------------
# Layer 8 — TAM parse + lookalike cross-reference
# ---------------------------------------------------------------------------

_TAM_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def check_tam_parse(tam_path: Path, lookalikes_path: Path) -> CheckResult:
    if not tam_path.exists():
        return CheckResult("tam_parse", "fail", f"TAM file missing: {tam_path}")
    text = tam_path.read_text(encoding="utf-8")

    # Find the Apollo Validation Parameters JSON block.
    parsed: dict[str, Any] = {}
    for m in _TAM_JSON_BLOCK_RE.finditer(text):
        block = m.group(1)
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if "filters" in parsed:
            break
    else:
        return CheckResult("tam_parse", "fail", "no Apollo validation JSON block found in TAM")

    filters = parsed.get("filters", {}) if isinstance(parsed, dict) else {}
    missing_keys = []
    for key in ("sic_codes", "naics_codes", "employee_count", "revenue_range"):
        if key not in filters:
            missing_keys.append(key)
    if missing_keys:
        return CheckResult(
            "tam_parse",
            "fail",
            f"TAM Apollo block missing keys: {missing_keys}",
        )

    # Cross-reference lookalikes.
    if not lookalikes_path.exists():
        return CheckResult(
            "tam_parse",
            "fail",
            f"lookalikes file missing: {lookalikes_path}",
        )
    lookalikes_data = json.loads(lookalikes_path.read_text(encoding="utf-8"))
    companies = lookalikes_data.get("companies", lookalikes_data) if isinstance(lookalikes_data, dict) else lookalikes_data
    not_in_tam = [c["name"] for c in companies if c["name"] not in text]
    if not_in_tam:
        return CheckResult(
            "tam_parse",
            "warn",
            f"{len(not_in_tam)} lookalike(s) not found in TAM doc by name: {not_in_tam[:5]}",
        )

    return CheckResult(
        "tam_parse",
        "pass",
        f"SIC ({len(filters['sic_codes'])}) + NAICS ({len(filters['naics_codes'])}) "
        f"present; {len(companies)} lookalikes cross-referenced",
    )


# ---------------------------------------------------------------------------
# Layer 9 — Output dir safety
# ---------------------------------------------------------------------------

def check_output_dir(today: Optional[str] = None, dir_: Optional[Path] = None) -> CheckResult:
    today = today or date.today().isoformat()
    target = dir_ or cfg.PIPELINE_DATA_DIR
    if not target.exists():
        return CheckResult("output_dir", "warn", f"pipeline-data dir missing; will be created at {target}")

    existing = [p.name for p in target.iterdir() if p.name.startswith(today)]
    if existing:
        return CheckResult(
            "output_dir",
            "warn",
            f"{len(existing)} file(s) already exist with prefix {today}: {existing[:3]}",
        )
    return CheckResult("output_dir", "pass", f"no prior outputs for {today}")


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------

def run(
    config: cfg.PipelineConfig,
    env: dict[str, str],
    client_pool: dict[str, FastPathApiClient],
) -> PreflightReport:
    """Run all 9 layers. Returns a PreflightReport.

    The orchestrator inspects report.has_failures() to decide go/no-go.
    Tests can call individual check_* functions for fine-grained coverage.
    """
    report = PreflightReport()
    report.add(check_env(env))
    report.add(check_apollo_plan(client_pool["apollo"]))
    report.add(check_leadmagic(client_pool["leadmagic"]))
    report.add(check_instantly_accounts(client_pool["instantly"]))
    report.add(check_vault_files(config))
    report.add(check_template_quality(config.template_path))
    report.add(check_template_body_quality(config.template_path))
    report.add(check_tam_parse(config.tam_path, config.lookalikes_path))
    report.add(check_output_dir())
    return report


def write_report(report: PreflightReport, *, out_dir: Optional[Path] = None) -> Path:
    target_dir = out_dir or cfg.PIPELINE_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out_path = target_dir / f"{today}_preflight_report.json"
    out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return out_path
