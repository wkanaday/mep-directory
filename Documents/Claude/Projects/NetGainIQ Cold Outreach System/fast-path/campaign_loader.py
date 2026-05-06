"""Module 4 — Campaign Loader.

Creates a paused Instantly campaign loaded with the assembled emails.
Sender accounts auto-discovered + filtered to NetGainIQ's three domains.
The campaign is created paused; Wilson activates manually after a final
review in the Instantly UI.

Public entry point:
    load_campaign(records, config, *, campaign_name=None) -> CampaignResult

Run as a separate manual step *after* fast_path_runner.py's review gate.

Endpoint shapes follow Instantly API v2. Some response field names may
need adjustment after the first live smoke run records actual responses
to tests/fixtures/.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import requests

import config as cfg
from api_client import FastPathApiClient
from exceptions import (
    AuthFailureError,
    CreditsExhaustedError,
    FastPathError,
    FastPathHttpError,
)

logger = logging.getLogger("fast_path.campaign_loader")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CampaignResult:
    campaign_id: str
    name: str
    status: str
    accounts_attached: list[str] = field(default_factory=list)
    leads_uploaded: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "name": self.name,
            "status": self.status,
            "accounts_attached": self.accounts_attached,
            "leads_uploaded": self.leads_uploaded,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Account discovery
# ---------------------------------------------------------------------------

def discover_sending_accounts(
    instantly: FastPathApiClient,
    *,
    sending_domains: tuple[str, ...] = cfg.SENDING_DOMAINS,
) -> list[str]:
    """Return email addresses on any of the configured sending domains."""
    try:
        resp = instantly.call("GET", "/api/v2/accounts")
    except (AuthFailureError, CreditsExhaustedError):
        raise
    except (requests.HTTPError, FastPathHttpError) as e:
        raise FastPathError(f"Instantly accounts unreachable: {e}") from e

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = None
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        items = body.get("items", body.get("data", []))
    else:
        items = None
    if not isinstance(items, list):
        raise FastPathError(
            f"Instantly /accounts returned unexpected shape: {type(body).__name__}"
        )

    matched: list[str] = []
    for acct in items:
        email = (acct.get("email") if isinstance(acct, dict) else "") or ""
        email = email.strip().lower()
        if email and any(email.endswith("@" + d) or email.endswith("." + d) for d in sending_domains):
            matched.append(email)
    return matched


# ---------------------------------------------------------------------------
# Campaign config builder
# ---------------------------------------------------------------------------

def build_campaign_payload(
    *,
    name: str,
    accounts: list[str],
) -> dict:
    """Build the POST /api/v2/campaigns request body. Three sequence steps
    referencing custom variables {{subject_N}}/{{body_N}}.
    """
    return {
        "name": name,
        "status": "paused",
        "campaign_schedule": {
            "schedules": [{
                "name": "default",
                "timing": {
                    "from": f"{cfg.CAMPAIGN_SCHEDULE['start_hour']:02d}:00",
                    "to": f"{cfg.CAMPAIGN_SCHEDULE['end_hour']:02d}:00",
                },
                "days": cfg.CAMPAIGN_SCHEDULE["days"],
                "timezone": "Etc/GMT",
                "timezone_mode": cfg.CAMPAIGN_SCHEDULE["timezone_mode"],
            }],
        },
        "daily_limit": cfg.DAILY_SEND_LIMIT,
        "stop_on_reply": cfg.STOP_ON_REPLY,
        "open_tracking": cfg.OPEN_TRACKING,
        "link_tracking": cfg.LINK_TRACKING,
        "email_list": accounts,
        "sequences": [{
            "steps": [
                {
                    "type": "email",
                    "delay": cfg.EMAIL_DAY_OFFSETS[0],
                    "variants": [{
                        "subject": "{{subject_1}}",
                        "body": "{{body_1}}",
                    }],
                },
                {
                    "type": "email",
                    "delay": cfg.EMAIL_DAY_OFFSETS[1],
                    "variants": [{
                        "subject": "{{subject_2}}",
                        "body": "{{body_2}}",
                    }],
                },
                {
                    "type": "email",
                    "delay": cfg.EMAIL_DAY_OFFSETS[2],
                    "variants": [{
                        "subject": "{{subject_3}}",
                        "body": "{{body_3}}",
                    }],
                },
            ],
        }],
    }


# ---------------------------------------------------------------------------
# Campaign creation
# ---------------------------------------------------------------------------

def create_campaign(
    instantly: FastPathApiClient,
    *,
    name: str,
    accounts: list[str],
) -> str:
    """Create a paused campaign and return its id."""
    payload = build_campaign_payload(name=name, accounts=accounts)
    resp = instantly.call("POST", "/api/v2/campaigns", json=payload)
    body = _safe_json(resp)
    cid = body.get("id") or body.get("campaign_id") or body.get("data", {}).get("id")
    if not cid:
        raise FastPathError(
            f"Instantly campaign create returned no id. Body keys: {sorted(body.keys()) if isinstance(body, dict) else type(body).__name__}"
        )
    return str(cid)


# ---------------------------------------------------------------------------
# Lead upload
# ---------------------------------------------------------------------------

def build_lead_payload(record: dict, *, campaign_id: str) -> dict:
    """Map an assembled-email record into an Instantly lead with custom
    variables referenced by the sequence steps.
    """
    return {
        "campaign": campaign_id,
        "email": record.get("email"),
        "first_name": record.get("first_name"),
        "last_name": record.get("last_name"),
        "company_name": record.get("company_name"),
        "custom_variables": {
            "subject_1": record.get("email_1_subject", ""),
            "body_1": record.get("email_1_body", ""),
            "subject_2": record.get("email_2_subject", ""),
            "body_2": record.get("email_2_body", ""),
            "subject_3": record.get("email_3_subject", ""),
            "body_3": record.get("email_3_body", ""),
        },
    }


def upload_leads(
    instantly: FastPathApiClient,
    records: list[dict],
    *,
    campaign_id: str,
) -> tuple[int, list[str]]:
    """Upload each record as an Instantly lead. Returns (success_count, errors)."""
    success = 0
    errors: list[str] = []
    for record in records:
        payload = build_lead_payload(record, campaign_id=campaign_id)
        try:
            instantly.call("POST", "/api/v2/leads", json=payload)
            success += 1
        except (AuthFailureError, CreditsExhaustedError):
            raise
        except (requests.HTTPError, FastPathHttpError) as e:
            email = record.get("email", "?")
            logger.warning(f"lead upload failed for {email}: {e}")
            errors.append(f"{email}: {e}")
    return success, errors


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def load_campaign(
    records: list[dict],
    instantly: FastPathApiClient,
    *,
    campaign_name: Optional[str] = None,
) -> CampaignResult:
    """End-to-end campaign load. Discovers accounts, creates the paused
    campaign, attaches accounts (via email_list in payload), uploads each
    record as a lead.
    """
    name = campaign_name or cfg.DEFAULT_CAMPAIGN_NAME
    accounts = discover_sending_accounts(instantly)
    if not accounts:
        raise FastPathError(
            "no Instantly sending accounts matched the three NetGainIQ domains"
        )

    campaign_id = create_campaign(instantly, name=name, accounts=accounts)
    leads_uploaded, errors = upload_leads(instantly, records, campaign_id=campaign_id)

    return CampaignResult(
        campaign_id=campaign_id,
        name=name,
        status="paused",
        accounts_attached=accounts,
        leads_uploaded=leads_uploaded,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def write_result(
    result: CampaignResult,
    *,
    out_dir: Optional[Path] = None,
    today: Optional[str] = None,
) -> Path:
    target_dir = out_dir or cfg.PIPELINE_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    today = today or date.today().isoformat()
    out_path = target_dir / f"{today}_campaign_loaded.json"
    out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return out_path


def _safe_json(resp) -> dict:
    try:
        body = resp.json()
        return body if isinstance(body, dict) else {"_raw": body}
    except Exception:  # noqa: BLE001
        return {}
