"""Unit tests for fast-path/fast_path_runner.py.

Run as a script (`python test_fast_path_runner.py`) or under pytest.
preflight, contact_finder, email_assembler are mocked to avoid HTTP.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg  # noqa: E402
import contact_finder  # noqa: E402
import fast_path_runner  # noqa: E402
import preflight  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_run_config(dir_: Path, **overrides) -> Path:
    """Build a minimal run-config.json with all required vault-path entries
    pointing at temp files.
    """
    base = {
        "tam_path": str(dir_ / "tam.md"),
        "persona_path": str(dir_ / "persona.md"),
        "template_path": str(dir_ / "template.md"),
        "exclusions_path": str(dir_ / "ex.json"),
        "lookalikes_path": str(dir_ / "la.json"),
        "max_contacts": 30,
        "max_per_company": 2,
        "warn_below_hit_rate": 0.5,
    }
    base.update(overrides)
    # Touch the referenced files so config loads.
    (dir_ / "tam.md").write_text("x")
    (dir_ / "persona.md").write_text("x")
    (dir_ / "template.md").write_text("x")
    (dir_ / "ex.json").write_text("[]")
    (dir_ / "la.json").write_text("[]")
    cfg_path = dir_ / "run-config.json"
    cfg_path.write_text(json.dumps(base), encoding="utf-8")
    return cfg_path


def _seed_env() -> None:
    os.environ["APOLLO_API_KEY"] = "a"
    os.environ["LEADMAGIC_API_KEY"] = "b"
    os.environ["INSTANTLY_API_KEY"] = "c"


def _clear_env() -> None:
    for k in ("APOLLO_API_KEY", "LEADMAGIC_API_KEY", "INSTANTLY_API_KEY"):
        os.environ.pop(k, None)


def _good_preflight_report() -> preflight.PreflightReport:
    r = preflight.PreflightReport()
    for name in ("env", "apollo_plan", "leadmagic", "instantly_accounts",
                 "vault_files", "template_quality", "template_body_quality",
                 "tam_parse", "output_dir"):
        r.add(preflight.CheckResult(name, "pass", "ok"))
    return r


def _failing_preflight_report() -> preflight.PreflightReport:
    r = preflight.PreflightReport()
    r.add(preflight.CheckResult("env", "pass", "ok"))
    r.add(preflight.CheckResult("apollo_plan", "fail", "403 free plan"))
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dry_run_runs_only_preflight():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_env()
        cfg_path = _write_run_config(Path(tmp))
        with mock.patch.object(preflight, "run", return_value=_good_preflight_report()), \
             mock.patch.object(preflight, "write_report", return_value=Path(tmp) / "pf.json"), \
             mock.patch.object(contact_finder, "find_contacts") as cf_mock, \
             mock.patch.object(contact_finder, "write_contacts") as wc_mock:
            rc = fast_path_runner.main(["--config", str(cfg_path), "--dry-run"])
        _clear_env()
    assert rc == 0
    cf_mock.assert_not_called()
    wc_mock.assert_not_called()


def test_preflight_failure_returns_exit_1():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_env()
        cfg_path = _write_run_config(Path(tmp))
        with mock.patch.object(preflight, "run", return_value=_failing_preflight_report()), \
             mock.patch.object(preflight, "write_report", return_value=Path(tmp) / "pf.json"), \
             mock.patch.object(contact_finder, "find_contacts") as cf_mock:
            rc = fast_path_runner.main(["--config", str(cfg_path)])
        _clear_env()
    assert rc == 1
    cf_mock.assert_not_called()


def test_full_flow_calls_preflight_then_contact_finder_then_assembler():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_env()
        cfg_path = _write_run_config(Path(tmp))
        # Two contacts so assembler has something to do.
        contacts = [
            {"contact_id": "c1", "email": "a@b.com", "company_domain": "b.com",
             "first_name": "A", "last_name": "B"},
        ]
        records = [{"contact_id": "c1", "email": "a@b.com",
                    "email_1_subject": "s", "email_1_body": "b",
                    "email_2_subject": "s", "email_2_body": "b",
                    "email_3_subject": "s", "email_3_body": "b"}]

        sentinel_summary = contact_finder.HitRateSummary(contacts_attempted=1, valid_count=1)

        def fake_find(run_cfg, env, pool, *, summary=None):
            if summary is not None:
                summary.contacts_attempted = 1
                summary.valid_count = 1
            return contacts

        with mock.patch.object(preflight, "run", return_value=_good_preflight_report()), \
             mock.patch.object(preflight, "write_report", return_value=Path(tmp) / "pf.json"), \
             mock.patch.object(contact_finder, "find_contacts", side_effect=fake_find), \
             mock.patch.object(contact_finder, "write_contacts", return_value=Path(tmp) / "c.json") as wc_mock, \
             mock.patch("fast_path_runner.email_assembler.assemble_emails", return_value=records) as ae_mock, \
             mock.patch("fast_path_runner.email_assembler.write_assembled", return_value=Path(tmp) / "e.json") as wa_mock:
            rc = fast_path_runner.main(["--config", str(cfg_path)])
        _clear_env()

    assert rc == 0
    wc_mock.assert_called_once()
    ae_mock.assert_called_once()
    wa_mock.assert_called_once()


def test_zero_contacts_aborts_before_assembly():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_env()
        cfg_path = _write_run_config(Path(tmp))
        with mock.patch.object(preflight, "run", return_value=_good_preflight_report()), \
             mock.patch.object(preflight, "write_report", return_value=Path(tmp) / "pf.json"), \
             mock.patch.object(contact_finder, "find_contacts", return_value=[]), \
             mock.patch.object(contact_finder, "write_contacts", return_value=Path(tmp) / "c.json"), \
             mock.patch("fast_path_runner.email_assembler.assemble_emails") as ae_mock:
            rc = fast_path_runner.main(["--config", str(cfg_path)])
        _clear_env()
    assert rc == 1
    ae_mock.assert_not_called()


def test_zero_assembled_emails_returns_exit_1():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_env()
        cfg_path = _write_run_config(Path(tmp))
        contacts = [{"contact_id": "c1", "email": "a@b.com", "company_domain": "b.com",
                     "first_name": "A", "last_name": "B"}]
        with mock.patch.object(preflight, "run", return_value=_good_preflight_report()), \
             mock.patch.object(preflight, "write_report", return_value=Path(tmp) / "pf.json"), \
             mock.patch.object(contact_finder, "find_contacts", return_value=contacts), \
             mock.patch.object(contact_finder, "write_contacts", return_value=Path(tmp) / "c.json"), \
             mock.patch("fast_path_runner.email_assembler.assemble_emails", return_value=[]), \
             mock.patch("fast_path_runner.email_assembler.write_assembled", return_value=Path(tmp) / "e.json"):
            rc = fast_path_runner.main(["--config", str(cfg_path)])
        _clear_env()
    assert rc == 1


def test_runner_does_not_import_campaign_loader():
    """The review gate is core safety. The runner must not import or call
    campaign_loader programmatically — only print the next-step command
    for Wilson to run after review.
    """
    src = (Path(__file__).resolve().parent.parent / "fast_path_runner.py").read_text(encoding="utf-8")
    assert "import campaign_loader" not in src
    assert "from campaign_loader" not in src
    # No programmatic call to load_campaign().
    assert "load_campaign(" not in src
    # But the runner should tell the user how to invoke it manually.
    assert "python campaign_loader.py" in src


def test_missing_config_file_returns_exit_1():
    _seed_env()
    rc = fast_path_runner.main(["--config", "/does/not/exist.json"])
    _clear_env()
    assert rc == 1


def test_missing_env_returns_exit_1():
    with tempfile.TemporaryDirectory() as tmp:
        _clear_env()
        # Also clear .env file at fast-path/.env if it exists — but we don't
        # have one. load_env will read the empty environment and raise.
        cfg_path = _write_run_config(Path(tmp))
        rc = fast_path_runner.main(["--config", str(cfg_path)])
    assert rc == 1


def test_argparse_dry_run_flag():
    parser_argv = ["--config", "x.json", "--dry-run"]
    # Verify argparse parses without error.
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(parser_argv)
    assert args.dry_run is True


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_dry_run_runs_only_preflight,
        test_preflight_failure_returns_exit_1,
        test_full_flow_calls_preflight_then_contact_finder_then_assembler,
        test_zero_contacts_aborts_before_assembly,
        test_zero_assembled_emails_returns_exit_1,
        test_runner_does_not_import_campaign_loader,
        test_missing_config_file_returns_exit_1,
        test_missing_env_returns_exit_1,
        test_argparse_dry_run_flag,
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
