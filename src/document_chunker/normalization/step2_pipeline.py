import itertools
import re
from collections import Counter

from src.document_chunker.normalization.list_detector import match_list_item
from src.document_chunker.normalization.paragraph_normalizer import (
    build_structured_document,
)
from src.document_chunker.normalization.structured_models import (
    ListBlock,
    NormalizedBlock,
    StructuredNormalizedDocument,
    TableBlock,
)
from src.document_chunker.schemas import ExtractedDocument

# Phase 6/7 of the Step 2 "Normalize + Preserve Structure" redesign: the main pipeline
# orchestrator. Canonical text assembly and offset assignment (Phase 6) already happen
# inside paragraph_normalizer.build_structured_document - every block's final text is
# decided before full_text is rendered by joining them with "\n\n", and start_char/
# end_char are derived from that same join structure afterward (see that module's
# docstring). This module adds Phase 7's validation suite on top, and the single
# entry point (normalize_document) that runs the pipeline and enforces it, since Step 2
# must be completely stable before Step 3 (chunking) is built on it.

_WORD_RE = re.compile(r"\S+")


def normalize_document(document: ExtractedDocument) -> StructuredNormalizedDocument:
    """Run the full Step 2 pipeline and enforce every Phase 7 invariant before
    returning. Raises ValueError (with every violation found, not just the first) if
    the result isn't valid - callers should never receive a StructuredNormalizedDocument
    that hasn't passed validation."""
    structured = build_structured_document(document)
    issues = validate_structured_document(structured, source=document)
    if issues:
        raise ValueError("Step 2 validation failed:\n" + "\n".join(issues))
    return structured


def validate_structured_document(
    structured: StructuredNormalizedDocument, source: ExtractedDocument | None = None
) -> list[str]:
    """All 7 Phase 7 invariants, checked independently of how the document was built.
    Returns violation messages, most-severe-first-found; an empty list means every
    invariant holds. `source` (the pre-Step2 ExtractedDocument) is optional - when
    given, also runs the lossless-content-integrity check (invariant 4), which needs
    the original text to compare against."""
    issues: list[str] = []
    issues += _check_non_empty_content(structured.blocks)
    issues += _check_monotonic_order(structured.blocks)
    issues += structured.validate_spans()
    if source is not None:
        issues += _check_lossless_content(source, structured)
    issues += _check_table_rectangularity(structured.blocks)
    issues += _check_list_non_emptiness(structured.blocks)
    issues += _check_json_serializable(structured)
    return issues


def _check_non_empty_content(blocks: list[NormalizedBlock]) -> list[str]:
    return [
        f"{b.block_id}: text is empty or whitespace-only"
        for b in blocks
        if not b.text.strip()
    ]


def _check_monotonic_order(blocks: list[NormalizedBlock]) -> list[str]:
    issues = []
    for previous, current in itertools.pairwise(blocks):
        if current.start_char < previous.end_char:
            issues.append(
                f"{current.block_id}: start_char {current.start_char} is before "
                f"{previous.block_id}'s end_char {previous.end_char}"
            )
    return issues


def _check_table_rectangularity(blocks: list[NormalizedBlock]) -> list[str]:
    issues = []
    for block in blocks:
        if not isinstance(block, TableBlock) or not block.columns:
            continue
        expected = len(block.columns)
        for index, row in enumerate(block.rows):
            if len(row) != expected:
                issues.append(
                    f"{block.block_id}: row {index} has {len(row)} cells, expected {expected}"
                )
    return issues


def _check_list_non_emptiness(blocks: list[NormalizedBlock]) -> list[str]:
    issues = []
    for block in blocks:
        if not isinstance(block, ListBlock):
            continue
        if not block.items:
            issues.append(f"{block.block_id}: list has zero items")
            continue
        for index, item in enumerate(block.items):
            if not item.strip():
                issues.append(
                    f"{block.block_id}: item {index} is empty or whitespace-only"
                )
    return issues


def _check_json_serializable(structured: StructuredNormalizedDocument) -> list[str]:
    """StructuredNormalizedDocument must serialize cleanly to JSON, purely in memory -
    no disk I/O, and without mutating the document (checked by comparing it against
    itself before/after)."""
    before = structured.model_copy(deep=True)
    try:
        structured.to_json()
    except Exception as exc:  # noqa: BLE001 - any serialization failure is a violation
        return [f"document failed to serialize to JSON: {exc}"]
    if structured != before:
        return ["serializing to JSON mutated the document"]
    return []


def _content_tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _expected_source_tokens(document: ExtractedDocument) -> Counter:
    """The tokens Step 2 is expected to preserve from the raw extractor text: every
    non-whitespace token, except a recognized list-item marker at the start of a line
    (e.g. "-", "1.", "(a)") - those are structural glyphs the pipeline intentionally
    strips, not content, exactly like list_detector.match_list_item already does when
    building a ListBlock's items."""
    tokens: Counter = Counter()
    for page in document.pages:
        for raw_line in page.text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            item_text = match_list_item(line)
            content = item_text if item_text is not None else line
            tokens.update(_content_tokens(content))
    return tokens


def _actual_structured_tokens(structured: StructuredNormalizedDocument) -> Counter:
    """The tokens actually present across every block - a TableBlock's cells are
    tokenized directly (not its rendered `text`), since rendering adds "|" column
    separators that were never part of the source content."""
    tokens: Counter = Counter()
    for block in structured.blocks:
        if isinstance(block, TableBlock):
            for row in [block.columns, *block.rows]:
                for cell in row:
                    tokens.update(_content_tokens(cell))
        else:
            tokens.update(_content_tokens(block.text))
    return tokens


def _check_lossless_content(
    document: ExtractedDocument, structured: StructuredNormalizedDocument
) -> list[str]:
    expected = _expected_source_tokens(document)
    actual = _actual_structured_tokens(structured)
    missing = expected - actual
    if not missing:
        return []
    sample = ", ".join(
        f"{token!r}x{count}" for token, count in list(missing.items())[:10]
    )
    return [
        f"content lost during normalization: {sum(missing.values())} token(s) missing, e.g. {sample}"
    ]
