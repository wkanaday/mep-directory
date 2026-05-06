"""Unit tests for fast-path/config.py.

Run as a script (`python test_config.py`) or under pytest.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from config import (  # noqa: E402
    PipelineConfig,
    load_env,
    load_exclusions,
    load_lookalikes,
    load_run_config,
)
from exceptions import FastPathError  # noqa: E402


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------

def _write_env(dir_: Path, **kwargs: str) -> Path:
    body = "\n".join(f"{k}={v}" for k, v in kwargs.items()) + "\n"
    p = dir_ / ".env.test"
    p.write_text(body, encoding="utf-8")
    return p


def _clear_env() -> None:
    for k in ("APOLLO_API_KEY", "LEADMAGIC_API_KEY", "INSTANTLY_API_KEY"):
        os.environ.pop(k, None)


def test_load_env_all_three_keys_passes():
    with tempfile.TemporaryDirectory() as tmp:
        _clear_env()
        env_path = _write_env(
            Path(tmp),
            APOLLO_API_KEY="apollo-xxx",
            LEADMAGIC_API_KEY="lm-yyy",
            INSTANTLY_API_KEY="inst-zzz",
        )
        out = load_env(env_path=env_path)
        assert out["APOLLO_API_KEY"] == "apollo-xxx"
        assert out["LEADMAGIC_API_KEY"] == "lm-yyy"
        assert out["INSTANTLY_API_KEY"] == "inst-zzz"
        _clear_env()


def test_load_env_missing_key_raises():
    with tempfile.TemporaryDirectory() as tmp:
        _clear_env()
        env_path = _write_env(
            Path(tmp),
            APOLLO_API_KEY="apollo-xxx",
            LEADMAGIC_API_KEY="lm-yyy",
            # INSTANTLY_API_KEY missing
        )
        try:
            load_env(env_path=env_path)
        except FastPathError as e:
            assert "INSTANTLY_API_KEY" in str(e)
        else:
            raise AssertionError("expected FastPathError for missing key")
        _clear_env()


def test_load_env_empty_value_raises():
    with tempfile.TemporaryDirectory() as tmp:
        _clear_env()
        env_path = _write_env(
            Path(tmp),
            APOLLO_API_KEY="apollo-xxx",
            LEADMAGIC_API_KEY="",  # empty
            INSTANTLY_API_KEY="inst-zzz",
        )
        try:
            load_env(env_path=env_path)
        except FastPathError as e:
            assert "LEADMAGIC_API_KEY" in str(e)
        else:
            raise AssertionError("expected FastPathError for empty key")
        _clear_env()


# ---------------------------------------------------------------------------
# Run config
# ---------------------------------------------------------------------------

_RUN_CONFIG_SAMPLE = {
    "tam_path": "C:/Users/wkana/AI/Obsidian Vault/NetGainIQ/TAM/sample-tam.md",
    "persona_path": "C:/Users/wkana/AI/Obsidian Vault/NetGainIQ/Personas/sample-persona.md",
    "template_path": "C:/Users/wkana/AI/Obsidian Vault/NetGainIQ/Templates/sample-template.md",
    "exclusions_path": "pipeline-data/exclusions.json",
    "lookalikes_path": "pipeline-data/manufacturing-broad-lookalikes.json",
    "max_contacts": 30,
    "max_per_company": 2,
    "warn_below_hit_rate": 0.5,
}


def test_load_run_config_parses_all_fields():
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "run-config.json"
        cfg_path.write_text(json.dumps(_RUN_CONFIG_SAMPLE), encoding="utf-8")
        cfg = load_run_config(cfg_path)
        assert isinstance(cfg, PipelineConfig)
        assert cfg.max_contacts == 30
        assert cfg.max_per_company == 2
        assert cfg.warn_below_hit_rate == 0.5


def test_load_run_config_resolves_relative_to_fast_path_dir():
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "run-config.json"
        cfg_path.write_text(json.dumps(_RUN_CONFIG_SAMPLE), encoding="utf-8")
        cfg = load_run_config(cfg_path)
        assert cfg.exclusions_path.is_absolute()
        assert cfg.exclusions_path.name == "exclusions.json"
        assert "fast-path" in str(cfg.exclusions_path).replace("\\", "/")


def test_load_run_config_keeps_absolute_paths():
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "run-config.json"
        cfg_path.write_text(json.dumps(_RUN_CONFIG_SAMPLE), encoding="utf-8")
        cfg = load_run_config(cfg_path)
        assert "Obsidian Vault" in str(cfg.tam_path)


def test_load_run_config_missing_file_raises():
    try:
        load_run_config(Path("/this/path/does/not/exist/run-config.json"))
    except FastPathError as e:
        assert "not found" in str(e).lower()
    else:
        raise AssertionError("expected FastPathError for missing config file")


# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------

def test_load_exclusions_dict_shape():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "exclusions.json"
        p.write_text(json.dumps({"domains": ["Foo.com", "BAR.COM", "baz.com"]}), encoding="utf-8")
        out = load_exclusions(path=p)
        assert out == {"foo.com", "bar.com", "baz.com"}


def test_load_exclusions_bare_list_shape():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "exclusions.json"
        p.write_text(json.dumps(["one.com", "two.com"]), encoding="utf-8")
        out = load_exclusions(path=p)
        assert out == {"one.com", "two.com"}


def test_load_exclusions_strips_blanks():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "exclusions.json"
        p.write_text(json.dumps({"domains": ["a.com", "  ", "", "b.com"]}), encoding="utf-8")
        out = load_exclusions(path=p)
        assert out == {"a.com", "b.com"}


def test_load_exclusions_missing_file_raises():
    try:
        load_exclusions(path=Path("/nope/exclusions.json"))
    except FastPathError as e:
        assert "not found" in str(e).lower()
    else:
        raise AssertionError("expected FastPathError")


# ---------------------------------------------------------------------------
# Lookalikes
# ---------------------------------------------------------------------------

def test_load_lookalikes_list_shape():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "lookalikes.json"
        body = [
            {"name": "Lincoln Electric", "domain": "lincolnelectric.com"},
            {"name": "Timken", "domain": "timken.com"},
        ]
        p.write_text(json.dumps(body), encoding="utf-8")
        out = load_lookalikes(path=p)
        assert len(out) == 2
        assert out[0]["name"] == "Lincoln Electric"


def test_load_lookalikes_companies_wrapper_shape():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "lookalikes.json"
        body = {"companies": [{"name": "Materion", "domain": "materion.com"}]}
        p.write_text(json.dumps(body), encoding="utf-8")
        out = load_lookalikes(path=p)
        assert len(out) == 1
        assert out[0]["name"] == "Materion"


def test_load_lookalikes_missing_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "lookalikes.json"
        p.write_text(json.dumps([{"domain": "anonymous.com"}]), encoding="utf-8")
        try:
            load_lookalikes(path=p)
        except FastPathError as e:
            assert "name" in str(e).lower()
        else:
            raise AssertionError("expected FastPathError for missing name")


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

def test_paths_resolve_to_absolute():
    assert config.FAST_PATH_DIR.is_absolute()
    assert config.PROJECT_ROOT.is_absolute()
    assert config.PIPELINE_DATA_DIR.is_absolute()
    assert config.BANNED_PHRASES_PATH.is_absolute()


def test_email_max_words_is_65_for_all_three():
    # All three Fast Path emails share the 65-word limit per Wilson's
    # 2026-05-06 correction. Lock this in so a future refactor doesn't
    # silently regress to type-driven 65/45/45.
    assert config.EMAIL_BODY_MAX_WORDS == 65


def test_sending_domains_are_three_netgainiq_domains():
    assert len(config.SENDING_DOMAINS) == 3
    for d in config.SENDING_DOMAINS:
        assert d.startswith("netgainiq")


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_load_env_all_three_keys_passes,
        test_load_env_missing_key_raises,
        test_load_env_empty_value_raises,
        test_load_run_config_parses_all_fields,
        test_load_run_config_resolves_relative_to_fast_path_dir,
        test_load_run_config_keeps_absolute_paths,
        test_load_run_config_missing_file_raises,
        test_load_exclusions_dict_shape,
        test_load_exclusions_bare_list_shape,
        test_load_exclusions_strips_blanks,
        test_load_exclusions_missing_file_raises,
        test_load_lookalikes_list_shape,
        test_load_lookalikes_companies_wrapper_shape,
        test_load_lookalikes_missing_name_raises,
        test_paths_resolve_to_absolute,
        test_email_max_words_is_65_for_all_three,
        test_sending_domains_are_three_netgainiq_domains,
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
