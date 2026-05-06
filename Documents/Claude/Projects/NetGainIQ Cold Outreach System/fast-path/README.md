# Fast Path — Tier B Sending Pipeline

Five Python modules that turn TAM parameters and an evergreen email template into a paused, loaded Instantly campaign. Built for NetGainIQ's first Tier B Manufacturing send (target: Friday 2026-05-09).

No LLM calls in the pipeline. Every step is deterministic Python — testable, zero token cost.

## Architecture

```
preflight  ->  contact_finder  ->  email_assembler  ->  [Wilson reviews]  ->  campaign_loader
   ^              ^                   ^                                            ^
   1              2                   3                                            4
   |______________|___________________|                                            |
              fast_path_runner (one CLI command)                       separate manual command
```

The review gate is core safety — never collapse it. The runner stops after assembly so Wilson can read every email before anything touches Instantly.

## First-time setup

```bash
cd fast-path
pip install -r requirements.txt
cp .env.example .env
# Fill in APOLLO_API_KEY, LEADMAGIC_API_KEY, INSTANTLY_API_KEY in .env
```

Verify dependencies and config:
```bash
python -m pytest tests/ -q   # all 172 tests should pass
```

## Daily operation

### Step 1: dry-run the preflight

```bash
python fast_path_runner.py --config pipeline-data/run-config.json --dry-run
```

Validates `.env` keys, all three API endpoints + plan tiers, vault file existence, template parse + body quality, TAM JSON, and `pipeline-data/` safety. Reports `[OK]/[WARN]/[FAIL]` per layer. Writes `pipeline-data/{date}_preflight_report.json`.

If anything fails, fix it before proceeding. Common failures:

| Failure | Fix |
|---|---|
| `env` — missing/empty key | Edit `.env`, refill the missing key |
| `apollo_plan` — 401 | Apollo key is wrong; double-check the dashboard |
| `apollo_plan` — 403 free plan | Upgrade Apollo to Basic+ |
| `leadmagic` — 402 credits | Refill LeadMagic credits |
| `leadmagic` — `status` not `email_status` | LeadMagic API contract changed; update `preflight.check_leadmagic` |
| `instantly_accounts` — 0 matches | Inboxes haven't been added to Instantly yet, or domain typo |
| `vault_files` — template missing | Wilson's evergreen template hasn't landed in the vault |
| `template_quality` — nested spintax | Fix the `{a|{b|c}}` pattern in the template |
| `template_quality` — unknown variable slot | Variable not in `KNOWN_VARIABLE_SLOTS`; either rename or add to the set |

### Step 2: live run (preflight + contact discovery + email assembly)

```bash
python fast_path_runner.py --config pipeline-data/run-config.json
```

Output files written to `pipeline-data/`:
- `{date}_preflight_report.json` — preflight results
- `{date}_contacts_verified.json` — verified contact list + summary
- `{date}_emails_assembled.json` — three assembled emails per contact
- `{date}_fast_path_runner.log` — full run log
- `{date}_contact_finder.log`, `{date}_email_assembler.log` — per-module logs

The runner stops here. Open `{date}_emails_assembled.json` and read every record before proceeding.

### Step 3: review the assembled emails

For every record, check:
- Subject and body for each of the three emails (`email_1_subject`, `email_1_body`, …)
- `data_tier` is `"rich"` for contacts with `facility_count`, `"lite"` otherwise
- `template_angle` is the angle assigned by per-domain rotation
- `word_counts` — every email under 65 words
- No `{...}` markers anywhere

Edits at this stage: open the JSON in an editor, fix the bodies in place, re-save. The campaign loader reads the JSON as-is.

### Step 4: load the campaign (paused)

```bash
python campaign_loader.py --records pipeline-data/{date}_emails_assembled.json
# Optional: --campaign-name "B-MFG-Manufacturing-C2-Special"
```

Creates a paused Instantly campaign, attaches all sending accounts on the three NetGainIQ domains, uploads each record as a lead with `subject_1/body_1` through `subject_3/body_3` custom variables matching the sequence step refs.

Default name: `B-MFG-Manufacturing-C1-Evergreen`.

Output: `pipeline-data/{date}_campaign_loaded.json` (campaign id, accounts, lead count, errors).

### Step 5: activate in the Instantly UI

1. Open the Instantly UI.
2. Find the campaign by name or id.
3. Click into one or two leads — verify the custom variables (subject_1, body_1, …) populated correctly.
4. Verify the sequence steps reference `{{subject_1}}/{{body_1}}` etc.
5. Verify the schedule is Tue-Fri 7:00am-9:00am (no Monday).
6. Activate.

Day 1 sends start the next Tue-Fri 7-9am window in each prospect's local timezone.

## Configuration files

### `pipeline-data/run-config.json`
The per-campaign config. Edit to point at a different vault file or change the campaign volume:
```json
{
  "tam_path": "C:/Users/wkana/AI/Obsidian Vault/.../tam.md",
  "persona_path": "C:/Users/wkana/AI/Obsidian Vault/.../persona.md",
  "template_path": "C:/Users/wkana/AI/Obsidian Vault/.../templates.md",
  "exclusions_path": "pipeline-data/exclusions.json",
  "lookalikes_path": "pipeline-data/manufacturing-broad-lookalikes.json",
  "max_contacts": 30,
  "max_per_company": 2,
  "warn_below_hit_rate": 0.5
}
```

### `pipeline-data/exclusions.json`
Domain exclusion list. Add lowercased domains to expand. Initial entries are 8 distributors/OEMs from the TAM exclusion list plus Kennametal (anchor client).

### `pipeline-data/manufacturing-broad-lookalikes.json`
Named cohort anchors. The contact finder searches for each by name first, before the broad SIC/NAICS pass — it both gives a hit-rate floor (we expect to find these companies) and surfaces a confidence metric (count of how many were found).

### `.env`
API credentials. Never commit. `.gitignore` already excludes it.

## Daily limits + ramp

- Week 1 (May 9-16): 20-30/day. Manual review the first 2-3 days.
- Week 2 (May 19-23): 50/day — only if bounces <3%, no spam complaints.
- Week 3 (May 26+): 100/day — steady state.

Red flags that pause the ramp: bounce rate >3%, any spam complaint, open rate <20%, Instantly deliverability warnings.

To reduce volume, lower `max_contacts` in `run-config.json`. To raise it, also update Instantly's per-campaign daily_limit in the UI (the runner sets 30; the UI override is fine).

## Architecture notes

- `config.py` — paths, API base URLs, rate-limit config per service, sending domains, campaign defaults, title priority list. `EMAIL_BODY_MAX_WORDS = 65` for all three emails (E1, E2, E3 share the limit per Wilson's 2026-05-06 spec).
- `api_client.py` — `FastPathApiClient` class. One instance per service. Inter-call delay before every request (0.5s Apollo/LeadMagic, 1s Instantly). Backoff `[30,60,120]` for Apollo/LeadMagic, `[60,120,300]` for Instantly. 429/5xx retry. 402 → `CreditsExhaustedError`. 401 → `AuthFailureError`.
- `preflight.py` — 9 layers, each a small standalone function. Returns a `PreflightReport` dataclass.
- `contact_finder.py` — Two-phase discovery (named lookalikes → SIC/NAICS broad search), dedupe by primary_domain, exclusion filter, title-priority + Ops/Finance pairing, Apollo email or LeadMagic finder fallback, LeadMagic validation.
- `email_assembler.py` — Pure data transform. Per-domain rotation distributes angles + spintax variants across multiple contacts at the same company. Reuses `cold-email-template-writer/scripts/check_scoring.py` for word-count + banned-phrase + opener + CTA validation.
- `campaign_loader.py` — Instantly v2 API. Discovers accounts, creates paused campaign, uploads leads with custom variables.
- `fast_path_runner.py` — Thin orchestrator. Does NOT invoke `campaign_loader` (review gate).

## When something breaks at runtime

- **`CreditsExhaustedError` mid-run** — the run halts and writes whatever was processed so far. Refill credits, then re-run. The dated output JSON gets overwritten on the second run; if you want to preserve it, rename it first.
- **Apollo `401`** — bad API key. Check `.env`, regenerate if needed.
- **Instantly campaign created but lead upload fails partway** — open `{date}_campaign_loaded.json` and check `errors`. Per-lead failures are recorded but don't halt the run. Re-upload the failed leads via the Instantly UI or rerun campaign_loader after editing the records JSON to include only the failed ones.
- **Hit rate below 50%** — preflight + summary will warn. Investigate why: TAM filter too narrow? Exclusion list too aggressive? Apollo data stale on take-private companies?
- **`Subject:` lines not matching the template format** — the assembler looks for `**Subject lines:**` and `**Body:**` markers. The format must match `industrial-tooling-metalworking-email-templates.md` precedent.

## Tests

```bash
python -m pytest tests/ -q
```

172 tests, ~0.5s run time. Each test file also runs standalone:
```bash
python tests/test_config.py
python tests/test_preflight.py
# ... etc
```

Test idiom matches `scanner-engine/tests/test_rss.py` (HTTP-bound modules) and `cold-email-template-writer/tests/test_check_scoring.py` (pure logic). No `pytest-mock` dependency.

## Plan reference

Full implementation plan: `~/.claude/plans/prd-fast-path-typed-castle.md`.
PRD: `../PRD-FAST-PATH-PIPELINE.md`.
Decision record: `Obsidian Vault > Decisions/2026-05-06-fast-path-to-first-send.md`.
