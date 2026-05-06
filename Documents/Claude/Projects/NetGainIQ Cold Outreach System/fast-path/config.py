"""Fast Path configuration: paths, constants, and config loaders.

Layered design:
  - Constants (this module): values that don't change per campaign — API
    base URLs, send window, daily ramp limits, title priority, paths.
  - .env at fast-path/.env: API credentials. Loaded via load_env().
  - --config JSON (e.g. pipeline-data/run-config.json): values that DO
    change per campaign — vault paths, exclusion/lookalike paths, hit-rate
    threshold. Loaded via load_run_config().
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from exceptions import FastPathError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FAST_PATH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FAST_PATH_DIR.parent
PIPELINE_DATA_DIR = FAST_PATH_DIR / "pipeline-data"
BANNED_PHRASES_PATH = PROJECT_ROOT / "cold-email-template-writer" / "references" / "banned-phrases.md"
ENV_PATH = FAST_PATH_DIR / ".env"


# ---------------------------------------------------------------------------
# API base URLs
# ---------------------------------------------------------------------------

APOLLO_BASE_URL = "https://api.apollo.io"
LEADMAGIC_BASE_URL = "https://api.leadmagic.io"
INSTANTLY_BASE_URL = "https://api.instantly.ai"


# ---------------------------------------------------------------------------
# Rate-limit + retry config (per service) — consumed by api_client.py
# ---------------------------------------------------------------------------

APOLLO_RATE = {"delay_s": 0.5, "backoff_schedule": [30, 60, 120]}
LEADMAGIC_RATE = {"delay_s": 0.5, "backoff_schedule": [30, 60, 120]}
INSTANTLY_RATE = {"delay_s": 1.0, "backoff_schedule": [60, 120, 300]}


# ---------------------------------------------------------------------------
# Sending domains (NetGainIQ)
# ---------------------------------------------------------------------------

SENDING_DOMAINS = (
    "netgainiqgroup.com",
    "netgainiqadvisory.com",
    "netgainiqpartners.com",
)


# ---------------------------------------------------------------------------
# Campaign defaults (Tue-Fri 7-9am, 30/day, stop on reply, open tracking on)
# ---------------------------------------------------------------------------

DEFAULT_CAMPAIGN_NAME = "B-MFG-Manufacturing-C1-Evergreen"

CAMPAIGN_SCHEDULE = {
    "days": ["tuesday", "wednesday", "thursday", "friday"],
    "start_hour": 7,
    "end_hour": 9,
    "timezone_mode": "prospect",
}

DAILY_SEND_LIMIT = 30
STOP_ON_REPLY = True
OPEN_TRACKING = True
LINK_TRACKING = False

EMAIL_DAY_OFFSETS = [0, 3, 7]  # E1 day 0, E2 day 3, E3 day 7
EMAIL_BODY_MAX_WORDS = 65       # All three emails — see plan, Wilson 2026-05-06
EMAIL_VALIDATION_MIN_VALID_PCT = 95
EMAIL_VALIDATION_MIN_RISKY_PCT = 80


# ---------------------------------------------------------------------------
# Health thresholds (used by post-send monitoring; preflight-relevant)
# ---------------------------------------------------------------------------

BOUNCE_RATE_PAUSE_THRESHOLD = 0.03    # 3% bounces — escalate
OPEN_RATE_FLOOR = 0.20                # below 20% open rate — investigate


# ---------------------------------------------------------------------------
# Title priority for contact selection (per PRD user story 11)
# ---------------------------------------------------------------------------

TITLE_PRIORITY = [
    "COO",
    "Chief Operating Officer",
    "SVP Operations",
    "EVP Operations",
    "VP Operations",
    "CFO",
    "Chief Financial Officer",
    "SVP Manufacturing",
    "VP Manufacturing",
    "VP Finance",
    "Chief Manufacturing Officer",
    "Segment President",
    "VP & President",
]

OPERATIONS_TITLE_TOKENS = ("operations", "manufacturing", "operating")
FINANCE_TITLE_TOKENS = ("finance", "financial", "cfo")


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------

_REQUIRED_ENV_KEYS = ("APOLLO_API_KEY", "LEADMAGIC_API_KEY", "INSTANTLY_API_KEY")


def load_env(env_path: Path | None = None) -> dict[str, str]:
    """Load API credentials from .env. Raise on any missing/empty key.

    Returns a dict with three keys: APOLLO_API_KEY, LEADMAGIC_API_KEY,
    INSTANTLY_API_KEY.
    """
    target = env_path or ENV_PATH
    load_dotenv(dotenv_path=target, override=False)
    missing = []
    out = {}
    for key in _REQUIRED_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if not val:
            missing.append(key)
        else:
            out[key] = val
    if missing:
        raise FastPathError(
            f"Missing or empty .env keys: {', '.join(missing)}. "
            f"Expected at {target}. Copy .env.example and fill in real values."
        )
    return out


# ---------------------------------------------------------------------------
# Run config (per-campaign --config JSON)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineConfig:
    tam_path: Path
    persona_path: Path
    template_path: Path
    exclusions_path: Path
    lookalikes_path: Path
    max_contacts: int
    max_per_company: int
    warn_below_hit_rate: float

    @classmethod
    def from_dict(cls, data: dict, *, base_dir: Path | None = None) -> "PipelineConfig":
        """Resolve config from a dict. Relative paths resolve against base_dir
        (defaults to fast-path/), absolute paths pass through unchanged.
        """
        base = base_dir or FAST_PATH_DIR

        def _resolve(p: str) -> Path:
            path = Path(p)
            return path if path.is_absolute() else (base / path).resolve()

        return cls(
            tam_path=_resolve(data["tam_path"]),
            persona_path=_resolve(data["persona_path"]),
            template_path=_resolve(data["template_path"]),
            exclusions_path=_resolve(data["exclusions_path"]),
            lookalikes_path=_resolve(data["lookalikes_path"]),
            max_contacts=int(data.get("max_contacts", 30)),
            max_per_company=int(data.get("max_per_company", 2)),
            warn_below_hit_rate=float(data.get("warn_below_hit_rate", 0.5)),
        )


def load_run_config(path: Path) -> PipelineConfig:
    """Read a --config JSON file and return a frozen PipelineConfig."""
    if not path.exists():
        raise FastPathError(f"Run config not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return PipelineConfig.from_dict(data, base_dir=FAST_PATH_DIR)


# ---------------------------------------------------------------------------
# Reference data loaders
# ---------------------------------------------------------------------------

def load_exclusions(path: Path | None = None) -> set[str]:
    """Load the excluded-domain set. JSON shape: {"domains": ["..."]}.
    Domains are lowercased on load.
    """
    target = path or (PIPELINE_DATA_DIR / "exclusions.json")
    if not target.exists():
        raise FastPathError(f"Exclusions file not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    domains = data.get("domains") if isinstance(data, dict) else data
    if not isinstance(domains, list):
        raise FastPathError(f"Exclusions JSON must contain a list of domains: {target}")
    return {str(d).strip().lower() for d in domains if str(d).strip()}


def load_lookalikes(path: Path | None = None) -> list[dict]:
    """Load the named-lookalike companies list. JSON shape: list of objects
    with at minimum a `name` key and ideally `aliases`, `domain`,
    `revenue_estimate`.
    """
    target = path or (PIPELINE_DATA_DIR / "manufacturing-broad-lookalikes.json")
    if not target.exists():
        raise FastPathError(f"Lookalikes file not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "companies" in data:
        data = data["companies"]
    if not isinstance(data, list):
        raise FastPathError(f"Lookalikes JSON must be a list: {target}")
    for item in data:
        if not isinstance(item, dict) or "name" not in item:
            raise FastPathError(f"Lookalike entry missing required `name` field in {target}")
    return data
