"""Module 5 — Fast Path Runner (orchestrator).

Thin wrapper. Chains preflight → contact_finder → email_assembler.

DOES NOT invoke campaign_loader — that runs as a separate manual command
after Wilson reviews the assembled emails JSON. That review gate is the
core safety property of the pipeline; do not collapse it.

Usage:
    python fast_path_runner.py --config pipeline-data/run-config.json
    python fast_path_runner.py --config pipeline-data/run-config.json --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import config as cfg
import contact_finder
import email_assembler
import preflight
from api_client import FastPathApiClient
from exceptions import (
    AuthFailureError,
    CreditsExhaustedError,
    FastPathError,
    PreflightFailure,
)


def _build_client_pool(env: dict[str, str]) -> dict[str, FastPathApiClient]:
    """Construct one FastPathApiClient per service with the right rate-
    limit, backoff, and auth header layout.
    """
    leadmagic_credit_extractor = lambda r: _safe_credits(r)  # noqa: E731

    return {
        "apollo": FastPathApiClient(
            base_url=cfg.APOLLO_BASE_URL,
            headers={"x-api-key": env["APOLLO_API_KEY"], "Content-Type": "application/json"},
            delay_s=cfg.APOLLO_RATE["delay_s"],
            backoff_schedule=cfg.APOLLO_RATE["backoff_schedule"],
            name="apollo",
        ),
        "leadmagic": FastPathApiClient(
            base_url=cfg.LEADMAGIC_BASE_URL,
            headers={"X-API-Key": env["LEADMAGIC_API_KEY"], "Content-Type": "application/json"},
            delay_s=cfg.LEADMAGIC_RATE["delay_s"],
            backoff_schedule=cfg.LEADMAGIC_RATE["backoff_schedule"],
            credit_extractor=leadmagic_credit_extractor,
            name="leadmagic",
        ),
        "instantly": FastPathApiClient(
            base_url=cfg.INSTANTLY_BASE_URL,
            headers={
                "Authorization": f"Bearer {env['INSTANTLY_API_KEY']}",
                "Content-Type": "application/json",
            },
            delay_s=cfg.INSTANTLY_RATE["delay_s"],
            backoff_schedule=cfg.INSTANTLY_RATE["backoff_schedule"],
            name="instantly",
        ),
    }


def _safe_credits(resp) -> int | None:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("credits_remaining")
    except Exception:  # noqa: BLE001
        return None
    return None


def _setup_logging(verbose: bool = False) -> None:
    """Module-level loggers + a file handler under pipeline-data/."""
    cfg.PIPELINE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    log_path = cfg.PIPELINE_DATA_DIR / f"{today}_fast_path_runner.log"

    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt))
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))

    root = logging.getLogger("fast_path")
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)


def _print_status(label: str, status: str, detail: str = "") -> None:
    """Match machine-0-runner.py's [OK]/[SKIP]/[FAIL] print style."""
    tag = {"pass": "[OK]", "warn": "[WARN]", "fail": "[FAIL]"}.get(status, "[--]")
    line = f"{tag:6} {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fast Path orchestrator: preflight -> contact_finder -> email_assembler.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=cfg.PIPELINE_DATA_DIR / "run-config.json",
        help="Path to run-config.json (default: pipeline-data/run-config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preflight only - no contact discovery, no email assembly.",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args(argv)

    _setup_logging(verbose=args.verbose)

    try:
        run_config = cfg.load_run_config(args.config)
    except FastPathError as e:
        print(f"[FAIL] config load: {e}")
        return 1

    try:
        env = cfg.load_env()
    except FastPathError as e:
        print(f"[FAIL] env load: {e}")
        return 1

    client_pool = _build_client_pool(env)

    print(f"\n=== Fast Path run {date.today().isoformat()} ===\n")
    print(f"Config: {args.config}")
    print(f"Mode:   {'DRY-RUN (preflight only)' if args.dry_run else 'LIVE'}\n")

    # --- Preflight ---
    print("Step 1/3 — preflight")
    report = preflight.run(run_config, env, client_pool)
    preflight_path = preflight.write_report(report)
    for check in report.checks:
        _print_status(check.name, check.status, check.detail)
    print(f"\nPreflight report: {preflight_path}")
    if report.has_failures():
        print("\n[FAIL] preflight detected failures. Pipeline halted.")
        return 1

    if args.dry_run:
        print("\n[OK] dry-run complete — preflight passed.")
        return 0

    # --- Contact finder ---
    print("\nStep 2/3 — contact_finder")
    summary = contact_finder.HitRateSummary()
    try:
        contacts = contact_finder.find_contacts(
            run_config, env, client_pool, summary=summary,
        )
    except CreditsExhaustedError as e:
        print(f"[FAIL] credits exhausted: {e}")
        return 1
    except AuthFailureError as e:
        print(f"[FAIL] auth failure: {e}")
        return 1

    contacts_path = contact_finder.write_contacts(contacts, summary)
    print(
        f"orgs discovered: {summary.organizations_discovered}, "
        f"after exclusions: {summary.organizations_after_exclusions}, "
        f"contacts attempted: {summary.contacts_attempted}, "
        f"valid: {summary.valid_count}, risky: {summary.risky_count}, "
        f"catch-all: {summary.catch_all_count}, rejected: {summary.rejected_count}"
    )
    print(f"hit rate: {summary.hit_rate():.1%} "
          f"(lookalikes matched: {summary.lookalikes_matched}/{summary.lookalikes_total})")
    print(f"Contacts: {contacts_path}")
    if summary.hit_rate() < run_config.warn_below_hit_rate:
        print(f"[WARN] hit rate below threshold ({run_config.warn_below_hit_rate:.1%})")

    if not contacts:
        print("\n[FAIL] no verified contacts discovered. Pipeline halted before assembly.")
        return 1

    # --- Email assembler ---
    print("\nStep 3/3 — email_assembler")
    records = email_assembler.assemble_emails(
        contacts,
        run_config.template_path,
        run_config.persona_path,
    )
    assembled_path = email_assembler.write_assembled(records)
    print(f"assembled: {len(records)}/{len(contacts)} contacts")
    print(f"Emails: {assembled_path}")

    if not records:
        print("\n[FAIL] zero emails assembled — review template + contact data.")
        return 1

    print(
        f"\n[OK] Pipeline complete.\n"
        f"REVIEW: {assembled_path}\n"
        f"Then run: python campaign_loader.py --records {assembled_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
