import math
import re
from collections import Counter

# Document-noise detection for paragraph_normalizer.build_structured_document: running
# page headers/footers, page numbers, and repeated branding/copyright lines.
#
# The Extractor stays plain-text-only (no bounding boxes or Y-coordinates - see the same
# Phase 1 scoping decision noted in heading_detector.py/paragraph_normalizer.py), so
# "position" here is a proxy: the first/last few non-blank lines of each page's text
# stand in for the top/bottom of the physical page. Combined with cross-page repetition,
# this catches the same running headers/footers a coordinate-based approach would, without
# requiring the extractor to capture layout metadata.

_PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?$", re.IGNORECASE
)
_DASHED_PAGE_NUMBER_RE = re.compile(r"^[-–—]\s*\d{1,4}\s*[-–—]$")
_ROMAN_NUMERAL_RE = re.compile(r"^[ivxlcdm]{1,6}$", re.IGNORECASE)
_DIGIT_RUN_RE = re.compile(r"\d+")

DEFAULT_ZONE_SIZE = 2
DEFAULT_MIN_REPEAT_COUNT = 3
DEFAULT_MIN_REPEAT_RATIO = 0.4


def _is_page_number_line(text: str) -> bool:
    if not text:
        return False
    return bool(
        _PAGE_NUMBER_RE.match(text)
        or _DASHED_PAGE_NUMBER_RE.match(text)
        or _ROMAN_NUMERAL_RE.match(text)
    )


def _normalize_for_repetition(text: str) -> str:
    """Collapse digit runs so 'Page 3' and 'Page 47' - or a copyright line with a
    changing year - count as the same recurring line."""
    return _DIGIT_RUN_RE.sub("#", text.strip().lower())


def _zone_lines(lines: list[str], zone_size: int) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(index, stripped text) pairs for the first/last `zone_size` non-blank lines."""
    non_blank = [(index, line.strip()) for index, line in enumerate(lines) if line.strip()]
    return non_blank[:zone_size], non_blank[-zone_size:]


def detect_noise_lines(
    page_lines: list[list[str]],
    zone_size: int = DEFAULT_ZONE_SIZE,
    min_repeat_count: int = DEFAULT_MIN_REPEAT_COUNT,
    min_repeat_ratio: float = DEFAULT_MIN_REPEAT_RATIO,
) -> list[dict[int, str]]:
    """For each page's line list (already preprocessed and split on "\\n" - the same
    lines paragraph_normalizer._split_into_blocks will walk), return a dict mapping
    line index -> "page_header" | "page_footer" for lines that look like running
    noise: an explicit page-number pattern, or text that recurs in the same top/bottom
    zone across many pages (repeated branding, copyright, running titles).

    With fewer than `min_repeat_count` pages, repetition has no statistical meaning, so
    only the page-number-pattern rule can fire - this is intentional, not a gap.
    """
    header_counts: Counter[str] = Counter()
    footer_counts: Counter[str] = Counter()
    per_page_zones: list[tuple[list[tuple[int, str]], list[tuple[int, str]]]] = []

    for lines in page_lines:
        header_zone, footer_zone = _zone_lines(lines, zone_size)
        per_page_zones.append((header_zone, footer_zone))
        for _, text in header_zone:
            header_counts[_normalize_for_repetition(text)] += 1
        for _, text in footer_zone:
            footer_counts[_normalize_for_repetition(text)] += 1

    page_count = len(page_lines)
    threshold = max(min_repeat_count, math.ceil(page_count * min_repeat_ratio))

    results: list[dict[int, str]] = []
    for header_zone, footer_zone in per_page_zones:
        noise: dict[int, str] = {}
        for index, text in header_zone:
            normalized = _normalize_for_repetition(text)
            if _is_page_number_line(text) or header_counts[normalized] >= threshold:
                noise[index] = "page_header"
        for index, text in footer_zone:
            normalized = _normalize_for_repetition(text)
            if _is_page_number_line(text) or footer_counts[normalized] >= threshold:
                noise[index] = "page_footer"
        results.append(noise)

    return results
