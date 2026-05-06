# Fast Path — Verification Status

**Last updated:** 2026-05-06 (initial scaffolding complete)

## Pre-launch verification gate

Each step from the plan's verification section maps to one entry below. Live items requiring API keys or the manufacturing-broad evergreen template are deferred until those preconditions are satisfied.

| # | Step | Status | Notes |
|---|---|---|---|
| 1 | Existing `test_check_scoring` still green after refactor | PASS | 10/10 tests pass with new `max_words` param defaulting to None. Verified 2026-05-06. |
| 2 | Preflight regression with bad inputs | PASS | Covered by 39 unit tests in `test_preflight.py`. Each layer's failure path is exercised: missing env keys, Apollo 401/403/missing-pagination, LeadMagic missing `email_status` field, missing vault files, nested spintax, unknown variable slot, empty pipe options. |
| 3 | Preflight live | DEFERRED | Requires `.env` filled with real API keys + Wilson's evergreen template in vault. |
| 4 | Contact finder live (lookalikes only) | DEFERRED | Requires `.env`. First live run records actual Apollo/LeadMagic responses to `tests/fixtures/`. |
| 5 | Email assembler live | DEFERRED | Requires the manufacturing-evergreen template. Smoke against existing sub-segment template confirms parser handles real format (`**Body:**` markers, `**Subject lines:**` lists, all 32 candidate bodies pass scoring at max_words=65). |
| 6 | Banned-phrase regression | PASS | Covered by `test_banned_phrase_leverage_rejects_contact` in `test_email_assembler.py`. Inject "leverage" into a body, confirm assembler rejects the contact. |
| 7 | Idempotency check | PASS (unit) | Covered by `test_output_dir_existing_today_files_warns` in `test_preflight.py`. Live re-run idempotency to be smoked when API keys land. |
| 8 | Campaign loader against TEST campaign | DEFERRED | Requires `.env`. Plan: create `TEST-DELETE-ME` campaign with 1 fake lead, inspect custom variables in Instantly UI, delete. |
| 9 | End-to-end on 5 real contacts (paused) | DEFERRED | Requires `.env` + evergreen template. Final pre-send gate. |

## Test counts

- 172 tests in `fast-path/tests/`
- 10 tests in `cold-email-template-writer/tests/test_check_scoring.py` (still green after refactor)
- **Total: 182 tests passing as of 2026-05-06.**

## Known gaps until preconditions land

1. **`{date}_emails_assembled.json` cannot be produced** until the manufacturing-evergreen template exists in the vault. The runner halts at the `vault_files` preflight layer.
2. **Apollo and LeadMagic field names assumed plausible** but not yet recorded against real API responses. The first live run is expected to surface 1-2 field-name corrections; the contact_finder is structured to make these easy to patch.
3. **No fixture files in `tests/fixtures/`** — to be captured during the first live smoke run per the plan ("capture real Apollo/LeadMagic responses to fixtures").

## Next session quick start

Once Wilson lands the manufacturing-evergreen template + verifies the three API keys:
1. `cd fast-path && python fast_path_runner.py --config pipeline-data/run-config.json --dry-run`
2. Address any preflight failures.
3. `python fast_path_runner.py --config pipeline-data/run-config.json` (live).
4. Review `pipeline-data/{date}_emails_assembled.json`.
5. `python campaign_loader.py --records pipeline-data/{date}_emails_assembled.json --campaign-name TEST-DELETE-ME` against 1 fake lead first.
6. Delete the test campaign in Instantly.
7. Re-run with the real `B-MFG-Manufacturing-C1-Evergreen` name.
8. Activate in Instantly UI after final read-through.
