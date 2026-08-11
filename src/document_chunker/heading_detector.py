import re

# Phase 3 of the Step 2 redesign: structural heading detection for paragraph_normalizer's
# build_structured_document, which calls detect_heading_level per physical line (the
# layout signal - a heading is one short standalone line - falls naturally out of that
# line-by-line pass, so it isn't judged here). Font/bold metadata isn't available (the
# Extractor stays plain-text-only, per the Phase 1 scoping decision), so the only content
# signal used is an explicit structural numbering prefix (CHAPTER 01, STEP 3, Week 5:,
# Month 2 -, Section 4.1).
#
# Deliberately NOT a signal: all-caps / uppercase ratio on its own. A narrative callout
# like "CRITICAL INSIGHT: GENERALISTS ARE LOSING GROUND" is capitalized for emphasis, not
# because it's a section header, and must not be misread as one.

_MAX_HEADING_LENGTH = 90

_HEADING_PATTERN_RE = re.compile(
    r"^[A-Z][A-Za-z]*\s+\d+(?:\.\d+)*[A-Za-z]?(?:\s*[:—–-]\s*.*)?$"
)
_NUMBERING_RE = re.compile(r"\d+(?:\.\d+)*")
_LIST_ITEM_PREFIX_RE = re.compile(r"^(?:[●•\-→]|\d+[.)])\s+")


def detect_heading_level(text: str) -> int | None:
    """The heading level (1 for a bare number like "CHAPTER 01", 2+ for each further
    dot-separated numbering segment - "Section 4.1" -> 2) if `text` matches an explicit
    structural heading prefix, else None. `text` is expected to be a single physical
    line (paragraph_normalizer calls this once per line); a multi-line string will never
    match, since the pattern is anchored to the whole string."""
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LENGTH:
        return None
    if _LIST_ITEM_PREFIX_RE.match(stripped):
        return None
    if not _HEADING_PATTERN_RE.match(stripped):
        return None

    numbering = _NUMBERING_RE.search(stripped)
    if not numbering:
        return 1
    return len(numbering.group().split("."))
