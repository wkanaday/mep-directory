"""Unit tests for fast-path/email_assembler.py.

Run as a script (`python test_email_assembler.py`) or under pytest. No
HTTP, no time waits — pure data transform.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import email_assembler  # noqa: E402
from email_assembler import (  # noqa: E402
    ParsedTemplate,
    TemplateAngle,
    TemplateEmail,
    _has_top_level_pipe,
    _split_top_level_pipes,
    assemble_emails,
    assemble_for_contact,
    parse_template,
    resolve_spintax_and_variables,
    write_assembled,
)


# ---------------------------------------------------------------------------
# Fixture template
# ---------------------------------------------------------------------------

SAMPLE_TEMPLATE = """\
---
title: "Sample Manufacturing Evergreen"
---

**Sender:** Wilson Kanaday

## Angle 1: Invoice Errors

### Email 1 — Data-Rich Version

**Subject lines:**
1. invoice errors
2. contract drift
3. surviving plants

**Body:**

Hi {first_name},

{company_name}'s {facility_count} sites turn over {industry_term} contracts that {drift quietly past their renewal dates|stay on auto-renew past renewal}. Peers see 20-40% in waste savings within 45 days.

We audit invoices at no cost — you pay only on results.

{Worth a quick look?|Want to see the gap?}

{sender_name}
NetGainIQ

PS: 31% savings on a similar consolidation for one peer.

**Spintax variations:** 4

### Email 1 — Data-Lite Fallback

**Subject lines:**
1. invoice errors
2. contract drift

**Body:**

Hi {first_name},

{company_name} runs {industry_term} operations where waste contracts {silently drift past renewal|tend to stay on auto-renew}. Peers find 20-40% in waste savings within 45 days.

We audit invoices at no cost — you pay only on results.

Worth 15 minutes?

{sender_name}
NetGainIQ

**Spintax variations:** 2

### Email 2 — Follow-Up Data-Rich

**Subject lines:**
1. surviving-plant variance
2. re: contract drift

**Body:**

Hi {first_name},

Surviving plants at {company_name} are where {industry_term} EBITDA hides at {facility_count}-site scale. The post-consolidation variance typically clears 20-35%. {Want to see the variance?|Worth seeing the variance?}

{sender_name}
NetGainIQ

**Spintax variations:** 2

### Email 2 — Follow-Up Data-Lite Fallback

**Subject lines:**
1. surviving sites
2. re: drift

**Body:**

Hi {first_name},

For {industry_term} operations, surviving-site variance after a footprint move {typically hides|usually hides} 20-35% in waste overpricing. {Want to see the gap?|Worth seeing?}

{sender_name}
NetGainIQ

**Spintax variations:** 2

### Email 3 — Final Data-Rich

**Subject lines:**
1. last note
2. closing the loop

**Body:**

Hi {first_name},

Last note — at {facility_count}-site {industry_term} scale, the consolidation savings window closes inside 60 days. {Worth a 15-min look?|Want to see if it fits?}

{sender_name}
NetGainIQ

**Spintax variations:** 2

### Email 3 — Final Data-Lite Fallback

**Subject lines:**
1. last note

**Body:**

Hi {first_name},

Last note — for {industry_term} operations the contract drift gap closes within 45 days. {Worth a 15-min look?|Want to see if it fits?}

{sender_name}
NetGainIQ

**Spintax variations:** 2

## Angle 2: New Ops Leadership

### Email 1 — Data-Rich Version

**Subject lines:**
1. new ops chair
2. first 90 days

**Body:**

Hi {first_name},

The new ops leader at {company_name} has 90 days to surface quick wins across {facility_count} sites. {industry_term} waste contracts are the {fastest reachable line|fastest line to fix}.

We audit invoices at no cost.

Worth a quick look?

{sender_name}
NetGainIQ

**Spintax variations:** 2

### Email 1 — Data-Lite Fallback

**Subject lines:**
1. new leadership
2. first 90 days

**Body:**

Hi {first_name},

New ops leadership at {company_name} typically opens a 90-day window for {industry_term} cost wins. {Waste contracts are the fastest line to surface savings|Waste is the fastest line for quick wins}.

Worth 15 minutes?

{sender_name}
NetGainIQ

**Spintax variations:** 2

### Email 2 — Follow-Up Data-Rich

**Subject lines:**
1. re: 90 days

**Body:**

Hi {first_name},

The window narrows at {facility_count}-site {industry_term} scale — typically 20-30% remains addressable in the first 90 days. Worth a quick check?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 2 — Follow-Up Data-Lite Fallback

**Subject lines:**
1. re: ops

**Body:**

Hi {first_name},

For {industry_term} operations the 90-day window narrows fast — peers find 20-30% addressable in that window. Worth a quick check?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 3 — Final Data-Rich

**Subject lines:**
1. last note

**Body:**

Hi {first_name},

Closing the loop — {company_name} at {facility_count} sites surfaces {industry_term} savings inside the first 90 days or not at all. Worth a 15-min look?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 3 — Final Data-Lite Fallback

**Subject lines:**
1. last note

**Body:**

Hi {first_name},

Closing the loop — {industry_term} operations typically surface contract-drift savings within the first 90 days. Worth a quick check?

{sender_name}
NetGainIQ

**Spintax variations:** 1
"""


# ---------------------------------------------------------------------------
# Flat-format fixture (mimics the production manufacturing-evergreen template)
# ---------------------------------------------------------------------------

FLAT_TEMPLATE = """\
---
title: "Test Flat Template"
date: 2026-05-07
sender_name: "Wilson Kanaday"
---

# Test Flat Template

**Sender:** Wilson Kanaday

---

## Email 1: Cost recovery question

**Subject lines:**
1. cost line
2. expense recovery
3. invoice review

**Body:**

Hi {first_name},

What if there were a single cost line at {company_name} that you could trim 20-40% on with no out-of-pocket spend?

For most {industry_term} operators, waste services is that line. We do the review at no charge. If we don't find savings, you pay nothing.

Worth a 15-minute call?

{sender_name}
Partner, NetGainIQ

PS: Most operators we talk to have never had anyone look at this.

**Word count:** 51 words (body only)

---

## Email 2: A peer review

**Subject lines:**
1. cost line
2. expense recovery
3. invoice review

**Body:**

Hi {first_name},

What would you think if a quick review of {company_name}'s waste invoices surfaced 20-40% in overspending?

That's the typical range for {industry_term} operators. The review is free. If we don't find anything, you pay nothing.

Worth a quick look?

{sender_name}
Partner, NetGainIQ

PS: Most operators we talk to have never had anyone look at this.

**Word count:** 45 words (body only)

---

## Email 3: Closing the loop

**Subject lines:**
1. cost line
2. expense recovery
3. invoice review

**Body:**

Hi {first_name},

What does {company_name} have to lose by letting us review your waste invoices when the review is free and you only pay if we find savings?

Most {industry_term} operators are overpaying 20-40% and don't realize it.

Worth 15 minutes?

{sender_name}
Partner, NetGainIQ

PS: Most operators we talk to have never had anyone look at this.

**Word count:** 41 words (body only)

---

## Scoring Report

| Criterion | Email 1 | Email 2 | Email 3 |
|-----------|---------|---------|---------|
| C1 word count | PASS | PASS | PASS |

---

## Design Decisions

- Same subject pool across all three emails.
- No spintax. One version per email.
- No facility_count variable.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_template(text: str = SAMPLE_TEMPLATE) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        prefix="template_", suffix=".md", delete=False, mode="w", encoding="utf-8",
    )
    tmp.write(text)
    tmp.close()
    return Path(tmp.name)


def _contact(**overrides) -> dict:
    base = {
        "contact_id": "test-id",
        "first_name": "John", "last_name": "Smith",
        "email": "j.smith@timken.com",
        "company_name": "Timken", "company_domain": "timken.com",
        "industry_term": "bearings",
        "facility_count": 12,
        "hq_city": "North Canton", "hq_state": "OH",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Spintax / variable resolver
# ---------------------------------------------------------------------------

def test_spintax_resolves_to_first_option_at_variant_zero():
    out = resolve_spintax_and_variables(
        "Hi {a|b|c}!",
        variant_index=0,
        variables={},
    )
    assert out == "Hi a!"


def test_spintax_resolves_with_modulo_wrap():
    out = resolve_spintax_and_variables(
        "Hi {a|b|c}!",
        variant_index=4,
        variables={},
    )
    assert out == "Hi b!"  # 4 % 3 = 1


def test_variable_substitutes_when_provided():
    out = resolve_spintax_and_variables(
        "Hi {first_name}!",
        variant_index=0,
        variables={"first_name": "Wilson"},
    )
    assert out == "Hi Wilson!"


def test_variable_unresolved_marker_remains():
    out = resolve_spintax_and_variables(
        "Hi {nope}!",
        variant_index=0,
        variables={"first_name": "Wilson"},
    )
    assert "{nope}" in out


def test_spintax_with_inner_variable_resolves_chosen_option():
    out = resolve_spintax_and_variables(
        "{Hello {first_name}|Hey {first_name}}",
        variant_index=1,
        variables={"first_name": "Wilson"},
    )
    assert out == "Hey Wilson"


def test_top_level_pipe_detector():
    assert _has_top_level_pipe("a|b") is True
    assert _has_top_level_pipe("a {b|c} d") is False  # pipe nested
    assert _has_top_level_pipe("plain text") is False


def test_top_level_pipe_split_ignores_pipes_inside_inner_braces():
    options = _split_top_level_pipes("Hi {first_name}|Hey {first_name}")
    assert options == ["Hi {first_name}", "Hey {first_name}"]


# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------

def test_parse_template_extracts_two_angles():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    assert len(template.angles) == 2
    assert template.angles[0].name.startswith("Angle 1")
    assert template.angles[1].name.startswith("Angle 2")


def test_parse_template_each_angle_has_six_emails():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    for angle in template.angles:
        # E1/E2/E3 × {rich, lite} = 6 sections
        assert len(angle.emails) == 6, f"{angle.name} has {len(angle.emails)}"
        numbers = sorted(e.number for e in angle.emails)
        assert numbers == [1, 1, 2, 2, 3, 3]
        tiers = sorted(e.tier for e in angle.emails)
        assert tiers == ["lite", "lite", "lite", "rich", "rich", "rich"]


def test_parse_template_subject_lines_extracted():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    rich_e1 = template.angles[0].email_for(1, "rich")
    assert rich_e1 is not None
    assert "invoice errors" in rich_e1.subject_lines


def test_parse_template_body_has_no_metadata_lines():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    rich_e1 = template.angles[0].email_for(1, "rich")
    assert "Spintax variations" not in rich_e1.body


def test_parse_template_sender_name_from_frontmatter():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    assert template.sender_name == "Wilson Kanaday"


# ---------------------------------------------------------------------------
# Per-contact assembly
# ---------------------------------------------------------------------------

def test_assemble_for_contact_returns_three_emails():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    rec = assemble_for_contact(_contact(), template, counter=0)
    assert rec is not None
    assert rec["email_1_body"]
    assert rec["email_2_body"]
    assert rec["email_3_body"]


def test_data_rich_routes_when_facility_count_present():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    rec = assemble_for_contact(_contact(facility_count=12), template, counter=0)
    assert rec is not None
    assert rec["data_tier"] == "rich"
    assert "12 sites" in rec["email_1_body"]


def test_data_lite_routes_when_facility_count_null():
    p = _write_template()
    template = parse_template(p)
    p.unlink()
    rec = assemble_for_contact(_contact(facility_count=None), template, counter=0)
    assert rec is not None
    assert rec["data_tier"] == "lite"


def test_two_contacts_at_same_domain_get_different_angles():
    p = _write_template()
    contacts = [
        _contact(contact_id="c1", first_name="A"),
        _contact(contact_id="c2", first_name="B"),
    ]
    out = assemble_emails(contacts, p)
    p.unlink()
    assert len(out) == 2
    assert out[0]["template_angle"] != out[1]["template_angle"]


def test_two_contacts_at_same_domain_get_different_spintax_variants():
    p = _write_template()
    contacts = [
        _contact(contact_id="c1", first_name="A"),
        _contact(contact_id="c2", first_name="B"),
    ]
    out = assemble_emails(contacts, p)
    p.unlink()
    assert out[0]["spintax_variant"] != out[1]["spintax_variant"]


def test_three_contacts_at_same_domain_rotate_through_angles():
    p = _write_template()
    contacts = [_contact(contact_id=f"c{i}", first_name=f"P{i}") for i in range(3)]
    out = assemble_emails(contacts, p)
    p.unlink()
    # Only 2 angles in the template — third contact wraps to first angle
    assert out[0]["template_angle"] == out[2]["template_angle"]
    assert out[0]["template_angle"] != out[1]["template_angle"]


# ---------------------------------------------------------------------------
# Validation rejection paths
# ---------------------------------------------------------------------------

def test_unresolved_variable_in_template_rejects_contact():
    bad_template = SAMPLE_TEMPLATE.replace(
        "{company_name}'s {facility_count} sites",
        "{company_name}'s {totally_made_up_field} sites",
        1,
    )
    p = _write_template(bad_template)
    template = parse_template(p)
    rec = assemble_for_contact(_contact(), template, counter=0)
    p.unlink()
    assert rec is None


def test_banned_phrase_leverage_rejects_contact():
    bad_template = SAMPLE_TEMPLATE.replace(
        "We audit invoices at no cost",
        "We leverage cross-site analytics",
        1,
    )
    p = _write_template(bad_template)
    template = parse_template(p)
    rec = assemble_for_contact(_contact(), template, counter=0)
    p.unlink()
    assert rec is None


def test_over_65_word_body_rejects_contact():
    long_body = (
        "Hi {first_name},\n\n"
        + "We are a leading provider of innovative cutting-edge solutions designed to streamline operational efficiency and unlock value across the enterprise stack. "
        + "Our approach combines deep domain expertise with proprietary methodologies refined over decades of working with industry leaders. "
        + "We have successfully partnered with hundreds of organizations across multiple verticals to drive measurable outcomes. "
        + "{company_name} would benefit from a thoughtful, customized engagement focused on the specific opportunities most relevant to your unique situation. "
        + "Worth a 15-minute call to discuss?\n\n"
        + "{sender_name}\nNetGainIQ\n"
    )
    bad_template = SAMPLE_TEMPLATE.split("### Email 1 — Data-Rich Version")[0] + (
        "### Email 1 — Data-Rich Version\n\n"
        "**Subject lines:**\n1. test\n\n**Body:**\n\n" + long_body + "\n**Spintax variations:** 1\n"
        + SAMPLE_TEMPLATE.split("### Email 1 — Data-Rich Version", 1)[1].split("### Email 1 — Data-Rich Version", 1)[0].split("### Email 1 — Data-Lite Fallback", 1)[1].partition("### Email 2")[0]
        + "\n## Angle 2\n"  # truncate angle 2 — single-angle template
    )
    # Simpler approach: hand-craft a one-angle template with a too-long body.
    long_template = """\
---
title: "Long body test"
---

**Sender:** Wilson Kanaday

## Angle 1: Test

### Email 1 — Data-Rich Version

**Subject lines:**
1. test

**Body:**

""" + long_body + """\

**Spintax variations:** 1

### Email 1 — Data-Lite Fallback

**Subject lines:**
1. test

**Body:**

Hi {first_name},

Short body for {company_name} in {industry_term}. Worth 15 min?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 2 — Follow-Up Data-Rich

**Subject lines:**
1. test

**Body:**

Hi {first_name},

Follow up on {company_name} {industry_term} contracts. Worth 15 min?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 2 — Follow-Up Data-Lite Fallback

**Subject lines:**
1. test

**Body:**

Hi {first_name},

Follow up on {company_name} {industry_term} contracts. Worth 15 min?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 3 — Final Data-Rich

**Subject lines:**
1. test

**Body:**

Hi {first_name},

Last note on {company_name} {industry_term} contracts at {facility_count} sites. Worth a 15-minute call?

{sender_name}
NetGainIQ

**Spintax variations:** 1

### Email 3 — Final Data-Lite Fallback

**Subject lines:**
1. test

**Body:**

Hi {first_name},

Last note on {company_name} {industry_term} contracts. Worth a 15-minute call?

{sender_name}
NetGainIQ

**Spintax variations:** 1
"""
    p = _write_template(long_template)
    template = parse_template(p)
    rec = assemble_for_contact(_contact(), template, counter=0)
    p.unlink()
    assert rec is None  # E1 body over 65 words → rejected


# ---------------------------------------------------------------------------
# Output completeness
# ---------------------------------------------------------------------------

def test_no_unresolved_markers_in_assembled_output():
    p = _write_template()
    contacts = [_contact()]
    out = assemble_emails(contacts, p)
    p.unlink()
    rec = out[0]
    for key in ("email_1_body", "email_2_body", "email_3_body",
                "email_1_subject", "email_2_subject", "email_3_subject"):
        # No unresolved {name} markers in output
        assert "{" not in rec[key], f"{key} contains unresolved markers: {rec[key]}"


def test_word_counts_recorded_for_each_email():
    p = _write_template()
    contacts = [_contact()]
    out = assemble_emails(contacts, p)
    p.unlink()
    rec = out[0]
    assert isinstance(rec["word_counts"], list)
    assert len(rec["word_counts"]) == 3
    assert all(isinstance(w, int) for w in rec["word_counts"])


def test_contact_with_all_three_emails_returns_record():
    p = _write_template()
    contacts = [_contact()]
    out = assemble_emails(contacts, p)
    p.unlink()
    assert len(out) == 1
    assert all(out[0][f"email_{i}_body"] for i in (1, 2, 3))
    assert all(out[0][f"email_{i}_subject"] for i in (1, 2, 3))


# ---------------------------------------------------------------------------
# Flat-format template (production manufacturing-evergreen shape)
# ---------------------------------------------------------------------------

def _flat_contact() -> dict:
    """Contact with no facility_count — matches the flat-template variable set."""
    return {
        "contact_id": "flat-1",
        "first_name": "John", "last_name": "Smith",
        "email": "j.smith@timken.com",
        "company_name": "Timken", "company_domain": "timken.com",
        "industry_term": "bearings",
        "facility_count": None,
        "hq_city": "North Canton", "hq_state": "OH",
    }


def test_parse_flat_template_extracts_one_angle():
    p = _write_template(FLAT_TEMPLATE)
    template = parse_template(p)
    p.unlink()
    assert len(template.angles) == 1
    assert template.angles[0].name == "default"


def test_parse_flat_template_has_three_emails():
    p = _write_template(FLAT_TEMPLATE)
    template = parse_template(p)
    p.unlink()
    angle = template.angles[0]
    assert len(angle.emails) == 3
    assert sorted(e.number for e in angle.emails) == [1, 2, 3]
    assert all(e.tier == "universal" for e in angle.emails)


def test_flat_template_subject_lines_extracted():
    p = _write_template(FLAT_TEMPLATE)
    template = parse_template(p)
    p.unlink()
    e1 = template.angles[0].email_for(1, "rich")  # universal fallback
    assert e1 is not None
    assert "cost line" in e1.subject_lines
    assert "expense recovery" in e1.subject_lines
    assert "invoice review" in e1.subject_lines


def test_flat_template_body_extracted_without_metadata():
    p = _write_template(FLAT_TEMPLATE)
    template = parse_template(p)
    p.unlink()
    for n in (1, 2, 3):
        email = template.angles[0].email_for(n, "rich")
        assert email is not None
        # Body should NOT include `**Word count:**`, scoring-report content, or
        # design-decisions content. The body extractor terminates at the next
        # `**Foo:**` line, and the section walker stops at the next H2 header.
        assert "Word count" not in email.body
        assert "Scoring Report" not in email.body
        assert "Design Decisions" not in email.body


def test_assemble_for_contact_with_flat_template():
    p = _write_template(FLAT_TEMPLATE)
    template = parse_template(p)
    rec = assemble_for_contact(_flat_contact(), template, counter=0)
    p.unlink()
    assert rec is not None, "expected a record back from the flat-template assembly"
    assert rec["template_angle"] == "default"
    # All three emails should have non-empty subject + body, no leftover markers.
    for n in (1, 2, 3):
        subj = rec[f"email_{n}_subject"]
        body = rec[f"email_{n}_body"]
        assert subj, f"email_{n}_subject is empty"
        assert body, f"email_{n}_body is empty"
        assert "{" not in subj, f"email_{n}_subject has unresolved marker: {subj}"
        assert "{" not in body, f"email_{n}_body has unresolved marker: {body}"


def test_flat_template_contacts_same_domain_get_same_angle():
    """With one synthetic angle, all contacts at the same domain map to the
    "default" angle. This is correct: rotation needs >=2 angles to vary.
    """
    p = _write_template(FLAT_TEMPLATE)
    contacts = [
        _flat_contact() | {"contact_id": "c1", "first_name": "A"},
        _flat_contact() | {"contact_id": "c2", "first_name": "B"},
    ]
    out = assemble_emails(contacts, p)
    p.unlink()
    assert len(out) == 2
    assert out[0]["template_angle"] == out[1]["template_angle"] == "default"


def test_flat_template_contacts_same_domain_get_different_subjects():
    """Variant counter still rotates subject-line selection within an email's
    subject_lines list, even when the template has only one angle.
    """
    p = _write_template(FLAT_TEMPLATE)
    contacts = [
        _flat_contact() | {"contact_id": "c1", "first_name": "A"},
        _flat_contact() | {"contact_id": "c2", "first_name": "B"},
    ]
    out = assemble_emails(contacts, p)
    p.unlink()
    assert out[0]["email_1_subject"] != out[1]["email_1_subject"]


_PRODUCTION_TEMPLATE_PATH = Path(
    r"C:\Users\wkana\AI\Obsidian Vault\NetGainIQ\Templates\manufacturing-evergreen-email-templates.md"
)


def test_parse_actual_production_template_smoke():
    """Smoke test against the real manufacturing-evergreen template. Skips
    cleanly if the file isn't present (e.g., on a fresh checkout).
    """
    if not _PRODUCTION_TEMPLATE_PATH.exists():
        print(f"      (skipped — {_PRODUCTION_TEMPLATE_PATH} not found)")
        return
    template = parse_template(_PRODUCTION_TEMPLATE_PATH)
    assert len(template.angles) == 1, (
        f"expected 1 synthetic angle, got {len(template.angles)}"
    )
    angle = template.angles[0]
    assert len(angle.emails) == 3, (
        f"expected 3 emails in the flat template, got {len(angle.emails)}"
    )
    assert sorted(e.number for e in angle.emails) == [1, 2, 3]


def test_assemble_against_actual_production_template_smoke():
    """End-to-end assembly against the real production template."""
    if not _PRODUCTION_TEMPLATE_PATH.exists():
        print(f"      (skipped — {_PRODUCTION_TEMPLATE_PATH} not found)")
        return
    contacts = [_flat_contact()]
    out = assemble_emails(contacts, _PRODUCTION_TEMPLATE_PATH)
    assert len(out) == 1, "expected exactly one assembled record from one contact"
    rec = out[0]
    for n in (1, 2, 3):
        body = rec[f"email_{n}_body"]
        assert body, f"email_{n}_body is empty"
        assert "{first_name}" not in body, "first_name was not substituted"
        assert "{company_name}" not in body, "company_name was not substituted"
        assert "{industry_term}" not in body, "industry_term was not substituted"


# ---------------------------------------------------------------------------
# write_assembled
# ---------------------------------------------------------------------------

def test_write_assembled_creates_dated_json():
    with tempfile.TemporaryDirectory() as tmp:
        records = [{
            "contact_id": "x", "email": "a@b.com",
            "email_1_subject": "s", "email_1_body": "b",
            "email_2_subject": "s", "email_2_body": "b",
            "email_3_subject": "s", "email_3_body": "b",
        }]
        path = write_assembled(records, out_dir=Path(tmp), today="2026-05-09")
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["count"] == 1
        assert body["records"][0]["contact_id"] == "x"


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

def run_all_tests() -> bool:
    tests = [
        test_spintax_resolves_to_first_option_at_variant_zero,
        test_spintax_resolves_with_modulo_wrap,
        test_variable_substitutes_when_provided,
        test_variable_unresolved_marker_remains,
        test_spintax_with_inner_variable_resolves_chosen_option,
        test_top_level_pipe_detector,
        test_top_level_pipe_split_ignores_pipes_inside_inner_braces,
        test_parse_template_extracts_two_angles,
        test_parse_template_each_angle_has_six_emails,
        test_parse_template_subject_lines_extracted,
        test_parse_template_body_has_no_metadata_lines,
        test_parse_template_sender_name_from_frontmatter,
        test_assemble_for_contact_returns_three_emails,
        test_data_rich_routes_when_facility_count_present,
        test_data_lite_routes_when_facility_count_null,
        test_two_contacts_at_same_domain_get_different_angles,
        test_two_contacts_at_same_domain_get_different_spintax_variants,
        test_three_contacts_at_same_domain_rotate_through_angles,
        test_unresolved_variable_in_template_rejects_contact,
        test_banned_phrase_leverage_rejects_contact,
        test_over_65_word_body_rejects_contact,
        test_no_unresolved_markers_in_assembled_output,
        test_word_counts_recorded_for_each_email,
        test_contact_with_all_three_emails_returns_record,
        # Flat-format template (production manufacturing-evergreen shape)
        test_parse_flat_template_extracts_one_angle,
        test_parse_flat_template_has_three_emails,
        test_flat_template_subject_lines_extracted,
        test_flat_template_body_extracted_without_metadata,
        test_assemble_for_contact_with_flat_template,
        test_flat_template_contacts_same_domain_get_same_angle,
        test_flat_template_contacts_same_domain_get_different_subjects,
        test_parse_actual_production_template_smoke,
        test_assemble_against_actual_production_template_smoke,
        test_write_assembled_creates_dated_json,
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
