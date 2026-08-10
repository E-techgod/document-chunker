import re
from collections.abc import Iterator
from dataclasses import dataclass, replace

from document_chunker.counting import count_words
from document_chunker.schemas import (
    ChunkingConfig,
    ChunkingResult,
    DocumentChunk,
    NormalizedDocument,
    NormalizedPage,
)

DEFAULT_CHUNKING_STRATEGY = "characters"
STRUCTURAL_STRATEGY = "structural"

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class _Unit:
    """One atomic structural unit, with the context needed to make it self-contained
    when it opens a chunk on its own (v2.2 structural context propagation)."""

    start: int
    end: int
    block_type: str
    heading_text: str | None = None
    table_header_text: str | None = None
    is_table_header_row: bool = False


def _compute_page_spans(document: NormalizedDocument) -> list[tuple[int, int, int]]:
    """Locate each page's (page_number, start_char, end_char) span within full_text."""
    spans = []
    cursor = 0
    for page in document.pages:
        if not page.text:
            spans.append((page.page_number, cursor, cursor))
            continue
        start = document.full_text.find(page.text, cursor)
        if start == -1:
            spans.append((page.page_number, cursor, cursor))
            continue
        end = start + len(page.text)
        spans.append((page.page_number, start, end))
        cursor = end
    return spans


def _page_numbers_for_span(spans: list[tuple[int, int, int]], start_char: int, end_char: int) -> list[int]:
    return [
        page_number
        for page_number, page_start, page_end in spans
        if page_start < end_char and page_end > start_char
    ]


def _iter_char_spans(text: str, max_chunk_size: int, overlap_size: int) -> Iterator[tuple[int, int]]:
    step = max_chunk_size - overlap_size
    if step <= 0:
        raise ValueError("overlap_size must be smaller than max_chunk_size")

    text_length = len(text)
    start = 0
    while start < text_length:
        end = min(start + max_chunk_size, text_length)
        yield start, end
        if end == text_length:
            break
        start += step


def _iter_page_units(page: NormalizedPage) -> Iterator[_Unit]:
    """Yield page-local structural units, one per atomic structural unit on the page."""
    for block in page.blocks:
        if block.block_type in {"heading", "paragraph"}:
            if block.end_char > block.start_char:
                yield _Unit(block.start_char, block.end_char, block.block_type)
        elif block.block_type == "list":
            cursor = block.start_char
            for item in block.items:
                yield _Unit(cursor, cursor + len(item), block.block_type)
                cursor += len(item) + 1
        elif block.block_type == "table" and block.table:
            header_text = " | ".join(block.table.header) if block.table.header else None
            rows = ([" | ".join(block.table.header)] if block.table.header else []) + [
                " | ".join(row) for row in block.table.rows
            ]
            cursor = block.start_char
            for index, row_text in enumerate(rows):
                yield _Unit(
                    cursor,
                    cursor + len(row_text),
                    block.block_type,
                    table_header_text=header_text,
                    is_table_header_row=(index == 0 and header_text is not None),
                )
                cursor += len(row_text) + 1


def _iter_page_structural_elements(page: NormalizedPage) -> Iterator[tuple[int, int]]:
    """Yield page-local (start, end) spans, one per atomic structural unit on the page."""
    for unit in _iter_page_units(page):
        yield unit.start, unit.end


def _split_into_sentences(start: int, end: int, text: str) -> Iterator[tuple[int, int]]:
    """Split text[start:end] into contiguous, gap-free sentence spans (absolute offsets)."""
    segment = text[start:end]
    cursor = start
    for match in _SENTENCE_BOUNDARY_RE.finditer(segment):
        boundary = start + match.end()
        yield cursor, boundary
        cursor = boundary
    yield cursor, end


def _flatten_elements(
    elements: Iterator[tuple[int, int]], max_chunk_size: int, text: str
) -> Iterator[tuple[int, int]]:
    for start, end in elements:
        if end - start > max_chunk_size:
            yield from _split_into_sentences(start, end, text)
        else:
            yield start, end


def _pack_elements(pieces: Iterator[tuple[int, int]], max_chunk_size: int) -> Iterator[tuple[int, int]]:
    current_start: int | None = None
    current_end: int | None = None

    for start, end in pieces:
        if current_start is None:
            current_start, current_end = start, end
        elif end - current_start <= max_chunk_size:
            current_end = end
        else:
            yield current_start, current_end
            current_start, current_end = start, end

    if current_start is not None:
        yield current_start, current_end


def structural_elements(document: NormalizedDocument) -> list[tuple[int, int]]:
    """Document-order (start, end) spans, in full_text, for every atomic structural unit
    (heading, paragraph, list item, table row) — before any size-based splitting."""
    page_spans = _compute_page_spans(document)
    return [
        (page_start + local_start, page_start + local_end)
        for page, (_, page_start, _) in zip(document.pages, page_spans)
        for local_start, local_end in _iter_page_structural_elements(page)
    ]


def structural_pieces(document: NormalizedDocument, max_chunk_size: int) -> list[tuple[int, int]]:
    """structural_elements(), with any element longer than max_chunk_size further split at
    sentence boundaries. These are the exact units chunk_document packs into chunks."""
    return list(_flatten_elements(iter(structural_elements(document)), max_chunk_size, document.full_text))


def _iter_structural_spans(document: NormalizedDocument, max_chunk_size: int) -> Iterator[tuple[int, int]]:
    yield from _pack_elements(iter(structural_pieces(document, max_chunk_size)), max_chunk_size)


def _document_units(document: NormalizedDocument) -> list[_Unit]:
    """structural_elements(), enriched with each unit's governing heading text (the nearest
    preceding heading, tracked in a single document-order pass so it correctly spans pages)."""
    page_spans = _compute_page_spans(document)
    units = [
        replace(unit, start=page_start + unit.start, end=page_start + unit.end)
        for page, (_, page_start, _) in zip(document.pages, page_spans)
        for unit in _iter_page_units(page)
    ]

    current_heading: str | None = None
    annotated: list[_Unit] = []
    for unit in units:
        if unit.block_type == "heading":
            annotated.append(unit)
            current_heading = document.full_text[unit.start : unit.end]
        else:
            annotated.append(replace(unit, heading_text=current_heading))
    return annotated


def _flatten_units(units: Iterator[_Unit], max_chunk_size: int, text: str) -> Iterator[_Unit]:
    for unit in units:
        if unit.end - unit.start > max_chunk_size:
            for start, end in _split_into_sentences(unit.start, unit.end, text):
                yield replace(unit, start=start, end=end)
        else:
            yield unit


def _resolve_context_prefix(unit: _Unit, previous_unit: _Unit | None, full_text: str) -> str:
    """The context needed for `unit` to make sense as the first thing in a chunk: nothing if
    it's a heading (it opens fresh); otherwise its governing heading, plus its table's header
    row if it continues a table, falling back to the previous chunk's last unit only when no
    heading exists anywhere yet."""
    if unit.block_type == "heading":
        return ""

    parts = [unit.heading_text] if unit.heading_text else []
    if unit.block_type == "table" and unit.table_header_text and not unit.is_table_header_row:
        parts.append(unit.table_header_text)
    if not parts and previous_unit is not None:
        parts.append(full_text[previous_unit.start : previous_unit.end])
    return "\n".join(parts)


def _pack_units_with_context(
    units: list[_Unit], max_chunk_size: int, full_text: str
) -> Iterator[tuple[int, int, str]]:
    index = 0
    previous_unit: _Unit | None = None

    while index < len(units):
        leading = units[index]
        context_prefix = _resolve_context_prefix(leading, previous_unit, full_text)
        reserved = len(context_prefix) + 1 if context_prefix else 0
        budget = max(max_chunk_size - reserved, leading.end - leading.start)

        current_start, current_end = leading.start, leading.end
        index += 1
        while index < len(units) and units[index].end - current_start <= budget:
            current_end = units[index].end
            index += 1

        yield current_start, current_end, context_prefix
        previous_unit = units[index - 1]


def _iter_structural_spans_with_context(
    document: NormalizedDocument, max_chunk_size: int
) -> Iterator[tuple[int, int, str]]:
    units = list(_flatten_units(iter(_document_units(document)), max_chunk_size, document.full_text))
    yield from _pack_units_with_context(units, max_chunk_size, document.full_text)


def chunk_document(document: NormalizedDocument, config: ChunkingConfig | None = None) -> ChunkingResult:
    """Chunk a NormalizedDocument's full_text using the configured chunking_strategy."""
    config = config or ChunkingConfig()
    if config.chunking_strategy == DEFAULT_CHUNKING_STRATEGY:
        spans = ((start, end, "") for start, end in _iter_char_spans(document.full_text, config.max_chunk_size, config.overlap_size))
    elif config.chunking_strategy == STRUCTURAL_STRATEGY:
        if config.propagate_context:
            spans = _iter_structural_spans_with_context(document, config.max_chunk_size)
        else:
            spans = ((start, end, "") for start, end in _iter_structural_spans(document, config.max_chunk_size))
    else:
        raise ValueError(f"Unsupported chunking_strategy: {config.chunking_strategy}")

    page_spans = _compute_page_spans(document)
    chunks = []
    for start, end, context_prefix in spans:
        chunk_text = document.full_text[start:end]
        if not chunk_text.strip():
            continue

        index = len(chunks)
        chunks.append(
            DocumentChunk(
                document_id=document.document_id,
                chunk_id=f"{document.document_id}_chunk_{index}",
                chunk_index=index,
                start_char=start,
                end_char=end,
                text=chunk_text,
                page_numbers=_page_numbers_for_span(page_spans, start, end),
                word_count=count_words(chunk_text),
                char_count=len(chunk_text),
                context_prefix=context_prefix,
            )
        )

    return ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        document_type=document.document_type,
        chunks=chunks,
        chunking_strategy=config.chunking_strategy,
    )
