from document_chunker.schemas import (
    ChunkingConfig,
    ChunkingResult,
    ChunkValidationIssue,
    ChunkValidationReport,
    DocumentChunk,
    NormalizedDocument,
)

ORDER = "order_preservation"
MAX_SIZE = "max_size"
OVERLAP = "overlap"
COVERAGE = "coverage"
TRACEABILITY = "traceability"
OFFSETS = "offsets"


def _check_order(chunks: list[DocumentChunk]) -> list[ChunkValidationIssue]:
    return [
        ChunkValidationIssue(
            invariant=ORDER,
            chunk_index=chunk.chunk_index,
            message=f"chunk at list position {position} has chunk_index {chunk.chunk_index}, expected {position}",
        )
        for position, chunk in enumerate(chunks)
        if chunk.chunk_index != position
    ]


def _check_max_size(chunks: list[DocumentChunk], config: ChunkingConfig) -> list[ChunkValidationIssue]:
    # The structural strategy treats max_chunk_size as a soft target: a single
    # unsplittable sentence/element is kept whole even if it overflows the limit.
    if config.chunking_strategy == "structural":
        return []
    return [
        ChunkValidationIssue(
            invariant=MAX_SIZE,
            chunk_index=chunk.chunk_index,
            message=f"chunk text length {len(chunk.text)} exceeds max_chunk_size {config.max_chunk_size}",
        )
        for chunk in chunks
        if len(chunk.text) > config.max_chunk_size
    ]


def _check_overlap(chunks: list[DocumentChunk], config: ChunkingConfig) -> list[ChunkValidationIssue]:
    issues = []
    for current, following in zip(chunks, chunks[1:]):
        is_full_sized = (current.end_char - current.start_char) == config.max_chunk_size
        # A skipped whitespace-only span leaves an actual gap between current.end_char
        # and following.start_char in the output; only compare overlap between chunks
        # that are genuinely back-to-back (touching or overlapping), not across a gap.
        has_gap = following.start_char > current.end_char
        if not is_full_sized or has_gap:
            continue

        expected_start = current.end_char - config.overlap_size
        if following.start_char != expected_start:
            issues.append(
                ChunkValidationIssue(
                    invariant=OVERLAP,
                    chunk_index=following.chunk_index,
                    message=(
                        f"chunk {following.chunk_index} starts at {following.start_char}, "
                        f"expected {expected_start} ({config.overlap_size}-char overlap with "
                        f"chunk {current.chunk_index})"
                    ),
                )
            )
    return issues


def _check_coverage(full_text: str, chunks: list[DocumentChunk]) -> list[ChunkValidationIssue]:
    issues = []
    spans = sorted((chunk.start_char, chunk.end_char) for chunk in chunks)
    cursor = 0
    for start, end in spans:
        if start > cursor:
            gap_text = full_text[cursor:start]
            if gap_text.strip():
                issues.append(
                    ChunkValidationIssue(
                        invariant=COVERAGE,
                        chunk_index=None,
                        message=f"full_text[{cursor}:{start}] is not covered by any chunk: {gap_text!r}",
                    )
                )
        cursor = max(cursor, end)

    if cursor < len(full_text):
        gap_text = full_text[cursor:]
        if gap_text.strip():
            issues.append(
                ChunkValidationIssue(
                    invariant=COVERAGE,
                    chunk_index=None,
                    message=f"full_text[{cursor}:{len(full_text)}] is not covered by any chunk: {gap_text!r}",
                )
            )
    return issues


def _check_traceability(full_text: str, chunks: list[DocumentChunk]) -> list[ChunkValidationIssue]:
    issues = []
    for chunk in chunks:
        if full_text[chunk.start_char : chunk.end_char] != chunk.text:
            issues.append(
                ChunkValidationIssue(
                    invariant=TRACEABILITY,
                    chunk_index=chunk.chunk_index,
                    message=f"full_text[{chunk.start_char}:{chunk.end_char}] does not match chunk.text",
                )
            )
    return issues


def _check_offsets(full_text: str, chunks: list[DocumentChunk]) -> list[ChunkValidationIssue]:
    issues = []
    text_length = len(full_text)
    previous_start: int | None = None

    for chunk in chunks:
        if not (0 <= chunk.start_char < chunk.end_char <= text_length):
            issues.append(
                ChunkValidationIssue(
                    invariant=OFFSETS,
                    chunk_index=chunk.chunk_index,
                    message=(
                        f"start_char={chunk.start_char}, end_char={chunk.end_char} "
                        f"out of bounds for text of length {text_length}"
                    ),
                )
            )
        elif chunk.end_char - chunk.start_char != len(chunk.text):
            issues.append(
                ChunkValidationIssue(
                    invariant=OFFSETS,
                    chunk_index=chunk.chunk_index,
                    message=(
                        f"end_char - start_char ({chunk.end_char - chunk.start_char}) "
                        f"!= len(chunk.text) ({len(chunk.text)})"
                    ),
                )
            )

        if previous_start is not None and chunk.start_char < previous_start:
            issues.append(
                ChunkValidationIssue(
                    invariant=OFFSETS,
                    chunk_index=chunk.chunk_index,
                    message=f"start_char {chunk.start_char} is out of order (previous chunk started at {previous_start})",
                )
            )
        previous_start = chunk.start_char

    return issues


def validate_chunks(
    document: NormalizedDocument,
    result: ChunkingResult,
    config: ChunkingConfig,
) -> ChunkValidationReport:
    """Check a ChunkingResult against the chunking invariants, collecting every violation found."""
    issues = [
        *_check_order(result.chunks),
        *_check_max_size(result.chunks, config),
        *_check_overlap(result.chunks, config),
        *_check_coverage(document.full_text, result.chunks),
        *_check_traceability(document.full_text, result.chunks),
        *_check_offsets(document.full_text, result.chunks),
    ]
    return ChunkValidationReport(document_id=document.document_id, issues=issues)
