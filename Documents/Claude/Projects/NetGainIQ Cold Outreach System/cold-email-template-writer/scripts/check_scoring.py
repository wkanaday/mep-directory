"""Module 1: Scoring Criteria Checker.

Public interface:
    check(email_body: str, *, email_type: str = "e1") -> dict[str, bool]
    check_with_detail(email_body: str, *, email_type: str = "e1") -> dict

CLI:
    python check_scoring.py <file_path> [--type e1|e2] [--json]

The 5 binary criteria match references/scoring-criteria.md:
    C1: word count <= 65 (e1) or <= 45 (e2)
    C2: first sentence references a specific situation, not a generic claim
    C3: first two sentences contain a specific number
    C4: zero banned phrases (case-insensitive substring match)
    C5: last body sentence is a concrete question (ends in ?, not a throwaway)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PERSONALIZATION_SLOTS = frozenset({
    "{company_name}", "{industry_term}", "{waste_type}",
    "{facility_count}", "{state_count}", "{revenue_range}",
    "{ownership_type}", "{hq_city}",
})

NUMERIC_SLOTS = frozenset({
    "{facility_count}", "{state_count}", "{revenue_range}",
})

_GENERIC_OPENER_PATTERNS = [
    re.compile(r"^\s*I\s", re.IGNORECASE),
    re.compile(r"^\s*We\s", re.IGNORECASE),
    re.compile(r"^\s*Our\s", re.IGNORECASE),
    re.compile(r"^\s*In\s+today'?s\b", re.IGNORECASE),
    re.compile(r"^\s*Many\s+companies\b", re.IGNORECASE),
    re.compile(r"^\s*Companies\s+(with|that)\b", re.IGNORECASE),
    re.compile(r"^\s*Most\s+(companies|manufacturers|hospitals|firms|operators)\b", re.IGNORECASE),
]

_THROWAWAY_CTA_PATTERNS = [
    re.compile(r"\blet me know\b", re.IGNORECASE),
    re.compile(r"\bfeel free\b", re.IGNORECASE),
    re.compile(r"\bwould you (be )?(open|interested|like)\b", re.IGNORECASE),
    re.compile(r"\bat your convenience\b", re.IGNORECASE),
    re.compile(r"\bI'?d love to\b", re.IGNORECASE),
]

_FUZZY_NUMBER_RE = re.compile(r"\b(six|seven|eight|nine|ten)\s+figures?\b", re.IGNORECASE)

# Matches a double-quoted phrase using straight (") or curly (“”) quotes.
# Press Quote Mirror emails open with a quoted statement and are accepted as
# concrete specifics under C3 even when no digit is present.
_QUOTE_RE = re.compile(r'"[^"]+"|“[^”]+”')


def _load_banned_phrases() -> frozenset[str]:
    """Load banned phrases from references/banned-phrases.md.

    Each banned phrase is a line of the form `- "phrase"`. Returns a
    frozenset of lowercased phrase strings. Falls back to a minimal
    hardcoded list if the references file is missing.
    """
    refs_path = Path(__file__).resolve().parent.parent / "references" / "banned-phrases.md"
    if not refs_path.exists():
        return frozenset({
            "i'd love to", "just wanted to", "reaching out because",
            "hope this finds you well", "i noticed that", "i came across",
            "touching base", "wanted to connect", "leverage", "synergy",
            "streamline", "unlock",
        })
    phrases = set()
    line_re = re.compile(r'^\s*-\s*"([^"]+)"')
    for line in refs_path.read_text(encoding="utf-8").splitlines():
        m = line_re.match(line)
        if m:
            phrases.add(m.group(1).lower())
    return frozenset(phrases)


_BANNED_PHRASES: frozenset[str] = _load_banned_phrases()


def _extract_body(text: str) -> str:
    """Strip greeting, signature, and PS line from a full email block.

    Idempotent: if no greeting/signature/PS markers match, the input
    is returned trimmed. This lets callers pass either a full email
    block or an already-extracted body.
    """
    body = text.strip()
    body = re.sub(r"^\s*Hi\s+[^,\n]+,\s*\n+", "", body, count=1, flags=re.IGNORECASE)
    body = re.sub(r"\n+\s*PS:.*$", "", body, count=1, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(
        r"\n+\s*\S[^\n]*\n+\s*NetGainIQ\s*$",
        "",
        body,
        count=1,
    )
    return body.strip()


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on .!? followed by whitespace.

    Heuristic — does not handle abbreviations like 'Inc.' but acceptable
    for the criteria. Newlines are flattened to single spaces first so
    paragraph breaks do not interfere.
    """
    flat = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    return [s.strip() for s in sentences if s.strip()]


def _check_c1(body: str, threshold: int) -> tuple[bool, str]:
    words = re.findall(r"\S+", body)
    n = len(words)
    if n <= threshold:
        return True, f"{n} words (limit {threshold})"
    return False, f"{n} words exceeds {threshold}"


def _check_c2(body: str) -> tuple[bool, str]:
    sentences = _split_sentences(body)
    if not sentences:
        return False, "no sentences found"
    first = sentences[0]
    for slot in PERSONALIZATION_SLOTS:
        if slot in first.lower():
            return True, f"personalized via {slot}"
    for pat in _GENERIC_OPENER_PATTERNS:
        if pat.search(first):
            return False, f"generic opener matched: {pat.pattern!r}"
    return True, "no generic-opener pattern matched"


def _check_c3(body: str) -> tuple[bool, str]:
    sentences = _split_sentences(body)
    head = " ".join(sentences[:2])
    head_lower = head.lower()
    for slot in NUMERIC_SLOTS:
        if slot in head_lower:
            return True, f"numeric slot {slot} in first 2 sentences"
    if _FUZZY_NUMBER_RE.search(head):
        return True, "spelled-out figure (six/seven/eight figures)"
    if re.search(r"\d", head):
        return True, "digit present in first 2 sentences"
    if _QUOTE_RE.search(head):
        return True, "quoted statement (Press Quote Mirror exception)"
    return False, "no number, numeric slot, or quoted statement in first 2 sentences"


def _check_c4(body: str) -> tuple[bool, str]:
    haystack = body.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in haystack:
            return False, f"banned phrase matched: {phrase!r}"
    return True, "zero banned phrases"


def _check_c5(body: str) -> tuple[bool, str]:
    sentences = _split_sentences(body)
    if not sentences:
        return False, "no sentences found"
    last = sentences[-1].rstrip()
    if not last.endswith("?"):
        return False, f"last sentence does not end in ?: {last!r}"
    for pat in _THROWAWAY_CTA_PATTERNS:
        if pat.search(last):
            return False, f"throwaway pattern matched: {pat.pattern!r}"
    return True, f"concrete question: {last!r}"


def check(email_body: str, *, email_type: str = "e1", max_words: int | None = None) -> dict[str, bool]:
    """Apply 5 binary scoring criteria. Returns boolean dict.

    `max_words`, when provided, overrides the email_type-derived word-count
    threshold. Defaults preserve historical behavior (e1 → 65, e2 → 45).
    """
    detail = check_with_detail(email_body, email_type=email_type, max_words=max_words)
    return {k: v["passed"] for k, v in detail.items()}


def check_with_detail(email_body: str, *, email_type: str = "e1", max_words: int | None = None) -> dict:
    """Apply 5 criteria with human-readable failure reasons.

    Returns a dict with keys c1_word_count, c2_specific_opening,
    c3_number_present, c4_no_banned_phrases, c5_concrete_cta — each
    mapping to {passed: bool, detail: str}.

    `max_words`, when provided, overrides the email_type-derived word-count
    threshold. Defaults preserve historical behavior (e1 → 65, e2 → 45).
    """
    if email_type not in ("e1", "e2"):
        raise ValueError(f"email_type must be 'e1' or 'e2', got {email_type!r}")
    threshold = max_words if max_words is not None else (65 if email_type == "e1" else 45)
    body = _extract_body(email_body)

    c1_pass, c1_detail = _check_c1(body, threshold)
    c2_pass, c2_detail = _check_c2(body)
    c3_pass, c3_detail = _check_c3(body)
    c4_pass, c4_detail = _check_c4(body)
    c5_pass, c5_detail = _check_c5(body)

    return {
        "c1_word_count": {"passed": c1_pass, "detail": c1_detail},
        "c2_specific_opening": {"passed": c2_pass, "detail": c2_detail},
        "c3_number_present": {"passed": c3_pass, "detail": c3_detail},
        "c4_no_banned_phrases": {"passed": c4_pass, "detail": c4_detail},
        "c5_concrete_cta": {"passed": c5_pass, "detail": c5_detail},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply 5 binary scoring criteria to an email body.",
    )
    parser.add_argument("file_path", type=Path,
                        help="Path to a file containing an email body or full email block.")
    parser.add_argument("--type", choices=["e1", "e2"], default="e1",
                        help="Email type: e1 (max 65 words) or e2 (max 45). Default e1.")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON to stdout instead of human report.")
    args = parser.parse_args()

    text = args.file_path.read_text(encoding="utf-8")
    detail = check_with_detail(text, email_type=args.type)
    all_pass = all(v["passed"] for v in detail.values())

    if args.json:
        out = {"ok": all_pass, "checks": detail}
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
    else:
        lines = [f"Scoring report ({args.file_path.name}, type={args.type})",
                 f"  Overall: {'PASS' if all_pass else 'FAIL'}"]
        for k, v in detail.items():
            mark = "PASS" if v["passed"] else "FAIL"
            lines.append(f"  {k}: {mark}  ({v['detail']})")
        sys.stdout.write("\n".join(lines) + "\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
