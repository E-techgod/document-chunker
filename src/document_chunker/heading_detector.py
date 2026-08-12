import re

# Phase 3 of the Step 2 redesign: structural heading detection for paragraph_normalizer's
# build_structured_document, which calls detect_heading_level per physical line (the
# layout signal - a heading is one short standalone line - falls naturally out of that
# line-by-line pass, so it isn't judged here). Font/bold metadata isn't available (the
# Extractor stays plain-text-only, per the Phase 1 scoping decision), so the content
# signal used is an explicit structural numbering prefix (CHAPTER 01, STEP 3, Week 5:,
# Month 2 -, Section 4.1), plus two narrow fallbacks for short standalone section titles:
# all-caps ("YOUR STRUCTURAL ADVANTAGE") and every-word-capitalized title case ("Key
# Market Facts"). The all-caps fallback allows a longer run only when it contains a digit
# (a year, a version, a metric) - a real content signal a plain emphatic callout won't
# have - so the tight word cap still holds for pure-alphabetic phrases.
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
_ALL_CAPS_HEADING_RE = re.compile(r"^[A-Z0-9/&()'’.,\-–—\s]+$")
_INLINE_PUNCTUATION_RE = re.compile(r"[:.;!?]")
_DIGIT_RE = re.compile(r"\d")
_MIN_ALL_CAPS_WORDS = 2
_MAX_ALL_CAPS_WORDS = 4
# A longer all-caps run is allowed only when it carries a digit (a year, a version, a
# metric) - that's a genuine content signal a plain emphatic callout ("AI AGENT IDEAS BY
# DOMAIN") won't have, so the tight 4-word cap still holds for pure-alphabetic phrases.
_MAX_ALL_CAPS_WORDS_WITH_DIGIT = 8

_TITLE_CASE_WORD_RE = re.compile(r"^[A-Z][a-z']*$")
_MULTI_SPACE_RE = re.compile(r"  ")
_MIN_TITLE_CASE_WORDS = 2
_MAX_TITLE_CASE_WORDS = 5


def _is_short_all_caps_heading(stripped: str) -> bool:
    if _INLINE_PUNCTUATION_RE.search(stripped):
        return False
    if not _ALL_CAPS_HEADING_RE.fullmatch(stripped):
        return False

    words = stripped.split()
    max_words = _MAX_ALL_CAPS_WORDS_WITH_DIGIT if _DIGIT_RE.search(stripped) else _MAX_ALL_CAPS_WORDS
    if not (_MIN_ALL_CAPS_WORDS <= len(words) <= max_words):
        return False

    # Require at least one alphabetic token so digit-only separators do not qualify.
    return any(any(char.isalpha() for char in word) for word in words)


def _is_short_title_case_heading(stripped: str) -> bool:
    """A short line where every word is capitalized ("Key Market Facts"). Requiring
    every word (not just the first) to start with a capital, and be otherwise lowercase,
    excludes ordinary sentences (only their first word is capitalized) and ALL-CAPS text
    (handled separately above) without needing a second regex pass over punctuation. Runs
    of 2+ spaces are a column-layout signal (a table header row like "Name  Role  Score"
    is also all-title-case) - checked on the raw string, since .split() would otherwise
    collapse that signal away, so those are left for table detection instead."""
    if _INLINE_PUNCTUATION_RE.search(stripped):
        return False
    if _MULTI_SPACE_RE.search(stripped):
        return False

    words = stripped.split()
    if not (_MIN_TITLE_CASE_WORDS <= len(words) <= _MAX_TITLE_CASE_WORDS):
        return False

    return all(_TITLE_CASE_WORD_RE.match(word) for word in words)


def detect_heading_level(text: str) -> int | None:
    """The heading level (1 for a bare number like "CHAPTER 01", 2+ for each further
    dot-separated numbering segment - "Section 4.1" -> 2) if `text` matches an explicit
    structural heading prefix, or 2 for a short standalone all-caps section title, else
    None. `text` is expected to be a single physical line (paragraph_normalizer calls
    this once per line); a multi-line string will never match, since the patterns are
    anchored to the whole string."""
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LENGTH:
        return None
    if _LIST_ITEM_PREFIX_RE.match(stripped):
        return None
    if _HEADING_PATTERN_RE.match(stripped):
        numbering = _NUMBERING_RE.search(stripped)
        if not numbering:
            return 1
        return len(numbering.group().split("."))
    if _is_short_all_caps_heading(stripped):
        return 2
    if _is_short_title_case_heading(stripped):
        return 2

    return None
