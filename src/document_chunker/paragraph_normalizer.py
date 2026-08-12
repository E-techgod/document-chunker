import re
from dataclasses import dataclass, field
from typing import Literal

from document_chunker.heading_detector import detect_heading_level
from document_chunker.list_detector import is_continuation_line, match_list_item
from document_chunker.noise_detector import detect_noise_lines
from document_chunker.normalizer import (
    _HORIZONTAL_WHITESPACE_RE,
    _measure_indent,
    _preprocess_text,
)
from document_chunker.schemas import ExtractedDocument
from document_chunker.structured_models import (
    HeadingBlock,
    ListBlock,
    PageFooterBlock,
    PageHeaderBlock,
    ParagraphBlock,
    StructuredNormalizedDocument,
    TableBlock,
)
from document_chunker.table_parser import is_table_row_candidate, parse_table_region

# Phase 2/3/4/5 of the Step 2 "Normalize + Preserve Structure" redesign: paragraph,
# heading, list, and table reconstruction with baseline span calculation, built on
# Phase 1's structured_models. This is a separate, parallel pipeline from normalizer.py's
# existing normalize_page/normalize_document - it is not wired into chunker.py and does
# not touch the existing NormalizedDocument/NormalizedBlock (schemas.py) that pipeline
# depends on.
#
# A vertical-gap (Delta-Y) paragraph-boundary signal is part of the Step 2 design but has
# no implementation here, because the current Extractor (kept unchanged per the Phase 1
# scoping decision) only provides plain per-page text - no spatial/coordinate metadata to
# compute a gap from.
#
# Heading, list, and table detection all run line-by-line during the same single pass
# that splits paragraphs, rather than only after chunking on blank lines: real
# single-column PDF extraction (verified against this repo's own sample PDFs) rarely
# inserts a blank line between a heading/list/table and the body text around it, so they
# almost never end up as their own blank-line-bounded chunk on their own. A detected
# heading, list-item marker, or table-row candidate closes out whatever paragraph was
# accumulating; a blank line, a heading, a table, or a non-continuation line all close
# out a list in progress (see list_detector for the continuation-vs-new-paragraph
# distinction). Table row/cell reconstruction itself is delegated to table_parser.py,
# which reuses table_normalizer.TableNormalizer - the same position-based algorithm
# already proven against this repo's own real-world PDF tables for the older pipeline.

_BlockKind = Literal[
    "heading", "paragraph", "list", "table", "page_header", "page_footer"
]
_MID_SENTENCE_CONTINUATION_RE = re.compile(r"[.!?:][\"')\]]*$")


@dataclass(frozen=True)
class _BlockEntry:
    kind: _BlockKind
    text: str
    level: int | None = None
    items: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


def _join_wrapped_lines(lines: list[str]) -> str:
    """Resolve visual line wraps across a block's physical lines: join them with a
    single space, collapse internal multi-space/tab runs to one, and trim the ends."""
    joined = " ".join(line.strip() for line in lines if line.strip())
    return _HORIZONTAL_WHITESPACE_RE.sub(" ", joined).strip()


def _starts_with_lowercase(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and stripped[0].islower()


def _should_space_join_page_boundary(
    current_page: int,
    current_entry: _BlockEntry,
    next_page: int,
    next_entry: _BlockEntry,
) -> bool:
    if current_entry.kind != "paragraph" or next_entry.kind != "paragraph":
        return False
    if next_page != current_page + 1:
        return False
    if _MID_SENTENCE_CONTINUATION_RE.search(current_entry.text.rstrip()):
        return False
    return _starts_with_lowercase(next_entry.text)


def _split_into_blocks(
    preprocessed_text: str, noise_line_indices: dict[int, str] | None = None
) -> list[_BlockEntry]:
    """Walk preprocessed page text line by line, producing _BlockEntry objects in
    document order. `noise_line_indices` (from noise_detector.detect_noise_lines) maps
    a line index to "page_header"/"page_footer" - those lines are pulled out as their
    own block instead of being swept into a paragraph, checked before any other line
    classification so a noise line is never misread as a table row or continuation."""
    entries: list[_BlockEntry] = []
    paragraph_lines: list[str] = []
    item_lines: list[str] = []
    completed_items: list[str] = []
    item_marker_indent: int | None = None
    noise_line_indices = noise_line_indices or {}

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
            entries.append(
                _BlockEntry(
                    kind="list",
                    text="\n".join(completed_items),
                    items=list(completed_items),
                )
            )
        completed_items.clear()

    lines = preprocessed_text.split("\n")
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()

        if not line:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        noise_kind = noise_line_indices.get(index)
        if noise_kind is not None:
            flush_paragraph()
            flush_list()
            entries.append(_BlockEntry(kind=noise_kind, text=line))
            index += 1
            continue

        item_text = match_list_item(line)
        if item_text is not None:
            flush_paragraph()
            flush_current_item()
            item_lines.append(item_text)
            item_marker_indent = _measure_indent(raw_line)
            index += 1
            continue

        level = detect_heading_level(line)
        if level is not None:
            flush_paragraph()
            flush_list()
            entries.append(_BlockEntry(kind="heading", text=line, level=level))
            index += 1
            continue

        if is_table_row_candidate(line):
            table, next_index = parse_table_region(
                lines, index, noise_line_indices=noise_line_indices
            )
            if table is not None:
                flush_paragraph()
                flush_list()
                columns, rows, text = table
                entries.append(
                    _BlockEntry(kind="table", text=text, columns=columns, rows=rows)
                )
                index = next_index
                continue

        if item_lines and is_continuation_line(raw_line, item_marker_indent):
            item_lines.append(line)
            index += 1
            continue

        flush_list()
        paragraph_lines.append(raw_line)
        index += 1

    flush_paragraph()
    flush_list()
    return entries


def build_structured_document(
    document: ExtractedDocument,
) -> StructuredNormalizedDocument:
    """Reconstruct HeadingBlocks, ParagraphBlocks, ListBlocks, and TableBlocks from raw
    per-page extractor text and assemble the canonical full_text, interleaved in
    document order. A page boundary always starts a new block - text is never joined
    across two pages, even mid-sentence, mid-list, or mid-table, since page is a
    per-block field on NormalizedBlock (Phase 1) that would otherwise be ambiguous for a
    merged block.

    Spans are computed strictly after block text assembly: every block's final text is
    decided first, full_text is rendered by joining them with its actual per-boundary
    delimiter, and only then are start_char/end_char derived from that same join
    structure (cumulative length, not a text search) - so a repeated block's offsets
    can never be misattributed to an earlier duplicate occurrence.
    """
    preprocessed_pages = [_preprocess_text(page.text) for page in document.pages]
    page_line_lists = [text.split("\n") for text in preprocessed_pages]
    noise_by_page = detect_noise_lines(page_line_lists)

    entries: list[tuple[int, _BlockEntry]] = []
    for page, preprocessed, noise_line_indices in zip(
        document.pages, preprocessed_pages, noise_by_page
    ):
        for entry in _split_into_blocks(
            preprocessed, noise_line_indices=noise_line_indices
        ):
            entries.append((page.page_number, entry))

    delimiters: list[str] = []
    for index, (page_number, entry) in enumerate(entries[:-1]):
        next_page_number, next_entry = entries[index + 1]
        if _should_space_join_page_boundary(
            page_number, entry, next_page_number, next_entry
        ):
            delimiters.append(" ")
        else:
            delimiters.append("\n\n")

    full_text = "".join(
        entry.text + (delimiters[index] if index < len(delimiters) else "")
        for index, (_, entry) in enumerate(entries)
    )

    blocks: list[
        HeadingBlock
        | ParagraphBlock
        | ListBlock
        | TableBlock
        | PageHeaderBlock
        | PageFooterBlock
    ] = []
    cursor = 0
    for index, (page_number, entry) in enumerate(entries):
        start = cursor
        end = start + len(entry.text)
        block_id = f"block_{index + 1:03d}"
        if entry.kind == "heading":
            blocks.append(
                HeadingBlock(
                    block_id=block_id,
                    text=entry.text,
                    page=page_number,
                    start_char=start,
                    end_char=end,
                    level=entry.level,
                )
            )
        elif entry.kind == "list":
            blocks.append(
                ListBlock(
                    block_id=block_id,
                    text=entry.text,
                    page=page_number,
                    start_char=start,
                    end_char=end,
                    items=entry.items,
                )
            )
        elif entry.kind == "table":
            blocks.append(
                TableBlock(
                    block_id=block_id,
                    text=entry.text,
                    page=page_number,
                    start_char=start,
                    end_char=end,
                    columns=entry.columns,
                    rows=entry.rows,
                )
            )
        elif entry.kind == "page_header":
            blocks.append(
                PageHeaderBlock(
                    block_id=block_id,
                    text=entry.text,
                    page=page_number,
                    start_char=start,
                    end_char=end,
                )
            )
        elif entry.kind == "page_footer":
            blocks.append(
                PageFooterBlock(
                    block_id=block_id,
                    text=entry.text,
                    page=page_number,
                    start_char=start,
                    end_char=end,
                )
            )
        else:
            blocks.append(
                ParagraphBlock(
                    block_id=block_id,
                    text=entry.text,
                    page=page_number,
                    start_char=start,
                    end_char=end,
                )
            )
        if index < len(delimiters):
            cursor = end + len(delimiters[index])
        else:
            cursor = end

    return StructuredNormalizedDocument(
        document_id=document.document_id, full_text=full_text, blocks=blocks
    )
