from dataclasses import dataclass, field
from typing import Literal

from document_chunker.heading_detector import detect_heading_level
from document_chunker.list_detector import is_continuation_line, match_list_item
from document_chunker.normalizer import _HORIZONTAL_WHITESPACE_RE, _measure_indent, _preprocess_text
from document_chunker.schemas import ExtractedDocument
from document_chunker.structured_models import (
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    StructuredNormalizedDocument,
)

# Phase 2/3/4 of the Step 2 "Normalize + Preserve Structure" redesign: paragraph,
# heading, and list reconstruction with baseline span calculation, built on Phase 1's
# structured_models. This is a separate, parallel pipeline from normalizer.py's existing
# normalize_page/normalize_document - it is not wired into chunker.py and does not touch
# the existing NormalizedDocument/NormalizedBlock (schemas.py) that pipeline depends on.
#
# Table detection is still out of scope: every non-blank, non-heading, non-list-item
# line accumulates into a ParagraphBlock. A vertical-gap (Delta-Y) paragraph-boundary
# signal is part of the Step 2 design but has no implementation here, because the
# current Extractor (kept unchanged per the Phase 1 scoping decision) only provides
# plain per-page text - no spatial/coordinate metadata to compute a gap from.
#
# Heading and list detection both run line-by-line during the same single pass that
# splits paragraphs, rather than only after chunking on blank lines: real single-column
# PDF extraction (verified against this repo's own sample PDFs) rarely inserts a blank
# line between a heading/list and the body text around it, so they almost never end up
# as their own blank-line-bounded chunk on their own. A detected heading or list-item
# marker closes out whatever paragraph was accumulating; a blank line, a heading, or a
# non-continuation line all close out a list in progress (see list_detector for the
# continuation-vs-new-paragraph distinction).

_BlockKind = Literal["heading", "paragraph", "list"]


@dataclass(frozen=True)
class _BlockEntry:
    kind: _BlockKind
    text: str
    level: int | None = None
    items: list[str] = field(default_factory=list)


def _join_wrapped_lines(lines: list[str]) -> str:
    """Resolve visual line wraps across a block's physical lines: join them with a
    single space, collapse internal multi-space/tab runs to one, and trim the ends."""
    joined = " ".join(line.strip() for line in lines if line.strip())
    return _HORIZONTAL_WHITESPACE_RE.sub(" ", joined).strip()


def _split_into_blocks(preprocessed_text: str) -> list[_BlockEntry]:
    """Walk preprocessed page text line by line, producing _BlockEntry objects in
    document order."""
    entries: list[_BlockEntry] = []
    paragraph_lines: list[str] = []
    item_lines: list[str] = []
    completed_items: list[str] = []
    item_marker_indent: int | None = None

    def flush_paragraph() -> None:
        text = _join_wrapped_lines(paragraph_lines)
        if text:
            entries.append(_BlockEntry(kind="paragraph", text=text))
        paragraph_lines.clear()

    def flush_current_item() -> None:
        nonlocal item_marker_indent
        text = _join_wrapped_lines(item_lines)
        if text:
            completed_items.append(text)
        item_lines.clear()
        item_marker_indent = None

    def flush_list() -> None:
        flush_current_item()
        if completed_items:
            entries.append(_BlockEntry(kind="list", text="\n".join(completed_items), items=list(completed_items)))
        completed_items.clear()

    for raw_line in preprocessed_text.split("\n"):
        line = raw_line.strip()

        if not line:
            flush_paragraph()
            flush_list()
            continue

        item_text = match_list_item(line)
        if item_text is not None:
            flush_paragraph()
            flush_current_item()
            item_lines.append(item_text)
            item_marker_indent = _measure_indent(raw_line)
            continue

        level = detect_heading_level(line)
        if level is not None:
            flush_paragraph()
            flush_list()
            entries.append(_BlockEntry(kind="heading", text=line, level=level))
            continue

        if item_lines and is_continuation_line(raw_line, item_marker_indent):
            item_lines.append(line)
            continue

        flush_list()
        paragraph_lines.append(raw_line)

    flush_paragraph()
    flush_list()
    return entries


def build_structured_document(document: ExtractedDocument) -> StructuredNormalizedDocument:
    """Reconstruct HeadingBlocks, ParagraphBlocks, and ListBlocks from raw per-page
    extractor text and assemble the canonical full_text, interleaved in document order.
    A page boundary always starts a new block - text is never joined across two pages,
    even mid-sentence or mid-list, since page is a per-block field on NormalizedBlock
    (Phase 1) that would otherwise be ambiguous for a merged block.

    Spans are computed strictly after block text assembly: every block's final text is
    decided first, full_text is rendered by joining them with "\\n\\n", and only then are
    start_char/end_char derived from that same join structure (cumulative length, not a
    text search) - so a repeated block's offsets can never be misattributed to an
    earlier duplicate occurrence.
    """
    entries: list[tuple[int, _BlockEntry]] = []
    for page in document.pages:
        preprocessed = _preprocess_text(page.text)
        for entry in _split_into_blocks(preprocessed):
            entries.append((page.page_number, entry))

    full_text = "\n\n".join(entry.text for _, entry in entries)

    blocks: list[HeadingBlock | ParagraphBlock | ListBlock] = []
    cursor = 0
    for index, (page_number, entry) in enumerate(entries):
        start = cursor
        end = start + len(entry.text)
        block_id = f"block_{index + 1:03d}"
        if entry.kind == "heading":
            blocks.append(
                HeadingBlock(
                    block_id=block_id, text=entry.text, page=page_number, start_char=start, end_char=end, level=entry.level
                )
            )
        elif entry.kind == "list":
            blocks.append(
                ListBlock(
                    block_id=block_id, text=entry.text, page=page_number, start_char=start, end_char=end, items=entry.items
                )
            )
        else:
            blocks.append(ParagraphBlock(block_id=block_id, text=entry.text, page=page_number, start_char=start, end_char=end))
        cursor = end + 2  # skip the "\n\n" delimiter before the next block

    return StructuredNormalizedDocument(document_id=document.document_id, full_text=full_text, blocks=blocks)
