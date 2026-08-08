from collections.abc import Iterator

from document_chunker.counting import count_words
from document_chunker.schemas import (
    ChunkingConfig,
    ChunkingResult,
    DocumentChunk,
    NormalizedDocument,
)

DEFAULT_CHUNKING_STRATEGY = "characters"


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


def chunk_document(document: NormalizedDocument, config: ChunkingConfig | None = None) -> ChunkingResult:
    """Chunk a NormalizedDocument's full_text into fixed-size, overlapping character chunks."""
    config = config or ChunkingConfig()
    if config.chunking_strategy != DEFAULT_CHUNKING_STRATEGY:
        raise ValueError(f"Unsupported chunking_strategy: {config.chunking_strategy}")

    page_spans = _compute_page_spans(document)
    chunks = []
    for start, end in _iter_char_spans(document.full_text, config.max_chunk_size, config.overlap_size):
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
