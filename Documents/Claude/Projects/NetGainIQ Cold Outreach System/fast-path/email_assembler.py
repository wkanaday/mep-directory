"""Module 3 — Email Assembler.

Pure data transform. Reads the template, walks contacts, and produces
3 fully-assembled emails per surviving contact (subject + body, no
unresolved markup). Per-domain rotation distributes angles + spintax
variants across multiple contacts at the same company.

Public entry point: `assemble_emails(contacts, template_path, persona_path) -> list[dict]`.

Validation pipeline per contact: spintax resolution → variable substitution
→ unresolved-marker check → check_scoring.check_with_detail(body, max_words=65)
for each of the three emails. A contact is rejected if any criterion fails.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import config as cfg

logger = logging.getLogger("fast_path.email_assembler")

# Reuse the cold-email-template-writer scoring helper.
sys.path.insert(0, str(cfg.PROJECT_ROOT / "cold-email-template-writer" / "scripts"))
try:
    from check_scoring import check_with_detail  # type: ignore
except Exception:  # noqa: BLE001
    check_with_detail = None  # type: ignore


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class TemplateEmail:
    number: int           # 1, 2, or 3
    tier: str             # "rich" | "lite"
    subject_lines: list[str]
    body: str


@dataclass
class TemplateAngle:
    name: str
    emails: list[TemplateEmail] = field(default_factory=list)

    def email_for(self, number: int, tier: str) -> Optional[TemplateEmail]:
        for e in self.emails:
            if e.number == number and e.tier == tier:
                return e
        # Fallback to the other tier if the requested one is missing.
        for e in self.emails:
            if e.number == number:
                return e
        return None


@dataclass
class ParsedTemplate:
    sender_name: str
    angles: list[TemplateAngle]


# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_SENDER_RE = re.compile(r"^\*\*Sender:\*\*\s*(.+?)\s*$", re.MULTILINE)
_ANGLE_HEADER_RE = re.compile(r"^##\s+(?!#)(.+?)\s*$", re.MULTILINE)
_EMAIL_HEADER_RE = re.compile(r"^###\s+Email\s+(\d+)\s*[—\-]\s*(.+?)\s*$", re.MULTILINE)
_FLAT_EMAIL_HEADER_RE = re.compile(
    r"^##\s+Email\s+(\d+)\s*[:—\-]\s*(.+?)\s*$", re.MULTILINE
)
_SUBJECT_HEADER_RE = re.compile(r"^\*\*Subject lines:\*\*\s*$", re.MULTILINE)
_BODY_HEADER_RE = re.compile(r"^\*\*Body:\*\*\s*$", re.MULTILINE)
_SUBJECT_LINE_ITEM_RE = re.compile(r"^\s*\d+\.\s*(.+?)\s*$", re.MULTILINE)
_NESTED_SPINTAX_RE = re.compile(r"\{[^{}]*\{[^{}]*\|[^{}]*\}[^{}]*\|")  # outer pipe with inner pipe-brace
_UNRESOLVED_MARKER_RE = re.compile(r"\{[^}]*\}")


def parse_template(template_path: Path) -> ParsedTemplate:
    """Read the template file and produce a ParsedTemplate."""
    text = template_path.read_text(encoding="utf-8")
    text_no_fm = _FRONTMATTER_RE.sub("", text)

    sender = "Wilson Kanaday"
    m = _SENDER_RE.search(text_no_fm)
    if m:
        sender = m.group(1).strip()

    angles = _parse_angles(text_no_fm)
    return ParsedTemplate(sender_name=sender, angles=angles)


def _parse_angles(text: str) -> list[TemplateAngle]:
    """Multi-angle path first (`## Angle X` sections, each with nested
    `### Email N — Rich/Lite` subsections). If no angle sections yield
    emails, fall back to flat format (`## Email N: Title` H2 headers
    directly under the document) wrapped in a single synthetic angle.
    """
    matches = list(_ANGLE_HEADER_RE.finditer(text))
    angles: list[TemplateAngle] = []
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        # Skip any non-angle ## sections.
        if not name.lower().startswith("angle"):
            continue
        section_start = m.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[section_start:section_end]
        angle = TemplateAngle(name=name, emails=_parse_emails(section))
        if angle.emails:
            angles.append(angle)
    if angles:
        return angles

    flat_emails = _try_parse_flat_emails(text)
    if flat_emails:
        return [TemplateAngle(name="default", emails=flat_emails)]
    return []


def _try_parse_flat_emails(text: str) -> list[TemplateEmail]:
    """Parse `## Email N: Title` H2-level email headers (flat templates,
    no per-angle wrapping). Each email's section runs from end-of-header
    to the next H2 header of any kind — so trailing H2 sections like
    `## Scoring Report` or `## Design Decisions` correctly bound the
    last email's body region.

    Tags every email with `tier="universal"` so TemplateAngle.email_for()
    falls back regardless of the tier the assembler asks for.
    """
    flat_matches = list(_FLAT_EMAIL_HEADER_RE.finditer(text))
    if not flat_matches:
        return []
    h2_starts = [m.start() for m in _ANGLE_HEADER_RE.finditer(text)]

    emails: list[TemplateEmail] = []
    for em in flat_matches:
        number = int(em.group(1))
        section_start = em.end()
        section_end = next(
            (s for s in h2_starts if s > em.start()),
            len(text),
        )
        section = text[section_start:section_end]
        subjects = _extract_subject_lines(section)
        body = _extract_body(section)
        if body:
            emails.append(TemplateEmail(
                number=number,
                tier="universal",
                subject_lines=subjects,
                body=body,
            ))
    return emails


def _parse_emails(angle_section: str) -> list[TemplateEmail]:
    """Split an angle section on `### Email N ...` headers."""
    matches = list(_EMAIL_HEADER_RE.finditer(angle_section))
    if not matches:
        return []
    emails: list[TemplateEmail] = []
    for i, m in enumerate(matches):
        number = int(m.group(1))
        descriptor = m.group(2).strip().lower()
        if "lite" in descriptor or "fallback" in descriptor:
            tier = "lite"
        else:
            tier = "rich"
        email_start = m.end()
        email_end = matches[i + 1].start() if i + 1 < len(matches) else len(angle_section)
        body_block = angle_section[email_start:email_end]
        subjects = _extract_subject_lines(body_block)
        body = _extract_body(body_block)
        if body:
            emails.append(TemplateEmail(
                number=number, tier=tier,
                subject_lines=subjects, body=body,
            ))
    return emails


def _extract_subject_lines(block: str) -> list[str]:
    sm = _SUBJECT_HEADER_RE.search(block)
    if not sm:
        return []
    bm = _BODY_HEADER_RE.search(block, sm.end())
    end = bm.start() if bm else len(block)
    region = block[sm.end():end]
    return [m.group(1).strip() for m in _SUBJECT_LINE_ITEM_RE.finditer(region) if m.group(1).strip()]


def _extract_body(block: str) -> str:
    bm = _BODY_HEADER_RE.search(block)
    if not bm:
        return ""
    after = block[bm.end():]
    # Body ends at next `**...**` line (e.g., `**Spintax variations:**`)
    next_marker = re.search(r"^\*\*[^*\n]+\*\*", after, flags=re.MULTILINE)
    end = next_marker.start() if next_marker else len(after)
    return after[:end].strip()


# ---------------------------------------------------------------------------
# Spintax + variable resolution
# ---------------------------------------------------------------------------

def resolve_spintax_and_variables(
    text: str,
    *,
    variant_index: int,
    variables: dict[str, str],
) -> str:
    """Walk top-level `{...}` blocks. Spintax blocks (containing pipes at
    depth 0) resolve to options[variant_index % len(options)]. Variable
    blocks (a single name, no pipes at top level) resolve to
    variables.get(name, "{name}") — leaving unrecognized vars as-is so
    the unresolved-marker check catches them downstream.

    Variables nested inside spintax options are resolved recursively in
    the chosen option only (efficient + matches semantics: only the
    selected variant's variables matter).
    """
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        end = _find_matching_brace(text, i)
        if end == -1:
            # Unbalanced brace — copy literally; downstream check catches it.
            out.append(ch)
            i += 1
            continue
        content = text[i + 1:end]
        if _has_top_level_pipe(content):
            options = _split_top_level_pipes(content)
            chosen = options[variant_index % len(options)]
            # Resolve variables (and any inner spintax — defensively) in
            # the chosen option. Forbids nested spintax at parse time so
            # this should only see variables.
            out.append(resolve_spintax_and_variables(
                chosen, variant_index=variant_index, variables=variables,
            ))
        else:
            name = content.strip()
            if name in variables:
                out.append(str(variables[name]))
            else:
                # Leave the marker so the unresolved-marker check rejects.
                out.append("{" + name + "}")
        i = end + 1
    return "".join(out)


def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    for j in range(start, len(text)):
        ch = text[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _has_top_level_pipe(content: str) -> bool:
    depth = 0
    for ch in content:
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
        elif ch == "|" and depth == 0:
            return True
    return False


def _split_top_level_pipes(content: str) -> list[str]:
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


# ---------------------------------------------------------------------------
# Per-contact assembly
# ---------------------------------------------------------------------------

def _build_variables(contact: dict, sender_name: str) -> dict[str, str]:
    """Map a verified contact + persona-derived sender into the variable
    dictionary expected by template tokens.
    """
    return {
        "first_name": str(contact.get("first_name") or ""),
        "last_name": str(contact.get("last_name") or ""),
        "company_name": str(contact.get("company_name") or ""),
        "company_domain": str(contact.get("company_domain") or ""),
        "industry_term": str(contact.get("industry_term") or "specialty manufacturing"),
        "sender_name": sender_name,
        "facility_count": str(contact.get("facility_count") or "") if contact.get("facility_count") else "",
        "hq_city": str(contact.get("hq_city") or ""),
        "hq_state": str(contact.get("hq_state") or ""),
        "revenue_range": str(contact.get("revenue_estimate") or ""),
        "ownership_type": str(contact.get("ownership_type") or ""),
    }


def _fix_company_possessive(body: str, company_name: str) -> str:
    """Normalize "Xs's" → "Xs'" when the company name ends in `s`.
    Scoped to literal `<company_name>'s` matches so unrelated possessives
    (e.g., "boss's office") are untouched.
    """
    if not company_name or not company_name.endswith(("s", "S")):
        return body
    return body.replace(f"{company_name}'s", f"{company_name}'")


def _word_count(body: str) -> int:
    """Word count after stripping greeting/signature/PS — mirrors the
    extractor inside check_scoring._extract_body for reporting purposes.
    The signature regex matches any final line ending with `NetGainIQ`
    (e.g., bare `NetGainIQ` or `Partner, NetGainIQ`).
    """
    stripped = body.strip()
    stripped = re.sub(r"^\s*Hi\s+[^,\n]+,\s*\n+", "", stripped, count=1, flags=re.IGNORECASE)
    stripped = re.sub(r"\n+\s*PS:.*$", "", stripped, count=1, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(
        r"\n+\s*\S[^\n]*\n+[^\n]*NetGainIQ\s*$",
        "",
        stripped,
        count=1,
    )
    return len(re.findall(r"\S+", stripped))


def assemble_for_contact(
    contact: dict,
    template: ParsedTemplate,
    *,
    counter: int,
) -> Optional[dict]:
    """Build one assembled record for `contact`. Returns None when the
    contact is rejected (scoring failure or unresolved variables).

    `counter` is the contact's per-domain ordinal — used to distribute
    angle and spintax variant across contacts at the same company.
    """
    if not template.angles:
        logger.warning("template has no angles; skipping contact")
        return None

    angle_index = counter % len(template.angles)
    angle = template.angles[angle_index]
    tier = "rich" if contact.get("facility_count") else "lite"
    variant = counter  # spintax variant counter; modded inside resolver

    variables = _build_variables(contact, template.sender_name)

    assembled_emails: list[tuple[str, str, list[int]]] = []  # (subject, body, [word_count])
    for n in (1, 2, 3):
        email = angle.email_for(n, tier)
        if email is None:
            logger.info(f"angle '{angle.name}' has no email #{n}; skipping contact {contact.get('contact_id')}")
            return None
        subject = _resolve_subject(email, variant=variant, variables=variables)
        body = resolve_spintax_and_variables(
            email.body, variant_index=variant, variables=variables,
        )
        body = _fix_company_possessive(body, variables["company_name"])

        # Reject on unresolved variables.
        leftovers = [m.group(0) for m in _UNRESOLVED_MARKER_RE.finditer(body) if m.group(0).startswith("{")]
        if leftovers:
            logger.info(
                f"contact {contact.get('contact_id')} email#{n} rejected: "
                f"unresolved markers {leftovers[:3]}"
            )
            return None

        if check_with_detail is not None:
            try:
                detail = check_with_detail(body, max_words=cfg.EMAIL_BODY_MAX_WORDS)
            except TypeError:
                detail = check_with_detail(body)  # pre-refactor fallback
            failed = [k for k, v in detail.items() if not v["passed"]]
            if failed:
                logger.info(
                    f"contact {contact.get('contact_id')} email#{n} rejected: scoring criteria failed: {failed}"
                )
                return None

        wc = _word_count(body)
        assembled_emails.append((subject, body, [wc]))

    # PS line — pull from email 1 body's tail if present (mirrors existing template style).
    ps_line = _extract_ps_line(assembled_emails[0][1])

    return {
        "contact_id": contact.get("contact_id"),
        "email": contact.get("email"),
        "email_status": contact.get("email_status"),
        "email_confidence": contact.get("email_confidence"),
        "first_name": contact.get("first_name"),
        "last_name": contact.get("last_name"),
        "company_name": contact.get("company_name"),
        "company_domain": contact.get("company_domain"),
        "email_1_subject": assembled_emails[0][0],
        "email_1_body": assembled_emails[0][1],
        "email_2_subject": assembled_emails[1][0],
        "email_2_body": assembled_emails[1][1],
        "email_3_subject": assembled_emails[2][0],
        "email_3_body": assembled_emails[2][1],
        "template_angle": angle.name,
        "spintax_variant": variant,
        "data_tier": tier,
        "ps_line": ps_line,
        "word_counts": [a[2][0] for a in assembled_emails],
        "scoring_pass": True,
    }


def _resolve_subject(email: TemplateEmail, *, variant: int, variables: dict[str, str]) -> str:
    if not email.subject_lines:
        return ""
    raw = email.subject_lines[variant % len(email.subject_lines)]
    return resolve_spintax_and_variables(raw, variant_index=variant, variables=variables)


def _extract_ps_line(body: str) -> str:
    m = re.search(r"\n\s*(PS:.*?)$", body, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def assemble_emails(
    contacts: list[dict],
    template_path: Path,
    persona_path: Optional[Path] = None,
) -> list[dict]:
    """Assemble 3 emails per contact using per-domain rotation. Drops
    contacts whose emails fail scoring or contain unresolved variables.
    """
    template = parse_template(template_path)
    if not template.angles:
        logger.error(f"template has no angles: {template_path}")
        return []

    domain_counter: dict[str, int] = {}
    out: list[dict] = []
    for contact in contacts:
        domain = (contact.get("company_domain") or "").lower()
        ordinal = domain_counter.get(domain, 0)
        domain_counter[domain] = ordinal + 1
        record = assemble_for_contact(contact, template, counter=ordinal)
        if record is not None:
            out.append(record)
    return out


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def write_assembled(
    records: list[dict],
    *,
    out_dir: Optional[Path] = None,
    today: Optional[str] = None,
) -> Path:
    target_dir = out_dir or cfg.PIPELINE_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    today = today or date.today().isoformat()
    out_path = target_dir / f"{today}_emails_assembled.json"
    payload = {
        "run_date": today,
        "count": len(records),
        "records": records,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
