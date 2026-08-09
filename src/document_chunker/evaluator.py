from document_chunker.chunker import STRUCTURAL_STRATEGY, structural_elements, structural_pieces
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
NON_WHITESPACE_COVERAGE = "non_whitespace_coverage"
TRACEABILITY = "traceability"
OFFSETS = "offsets"
STRUCTURAL_INTEGRITY = "structural_integrity"
ELEMENT_ORDER = "element_order"
ATOMIC_ELEMENT_COVERAGE = "atomic_element_coverage"


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


def _check_max_size(
    chunks: list[DocumentChunk], config: ChunkingConfig, pieces: list[tuple[int, int]]
) -> list[ChunkValidationIssue]:
    if config.chunking_strategy != STRUCTURAL_STRATEGY:
        return [
            ChunkValidationIssue(
                invariant=MAX_SIZE,
                chunk_index=chunk.chunk_index,
                message=f"chunk text length {len(chunk.text)} exceeds max_chunk_size {config.max_chunk_size}",
            )
            for chunk in chunks
            if len(chunk.text) > config.max_chunk_size
        ]

    # Structural chunks may only exceed max_chunk_size when they are exactly one
    # atomic element/sentence that was itself too big to split further — never
    # when several elements were packed together.
    oversized_pieces = {(start, end) for start, end in pieces if end - start > config.max_chunk_size}
    issues = []
    for chunk in chunks:
        size = chunk.end_char - chunk.start_char
        if size <= config.max_chunk_size:
            continue
        if (chunk.start_char, chunk.end_char) in oversized_pieces:
            continue
        issues.append(
            ChunkValidationIssue(
                invariant=MAX_SIZE,
                chunk_index=chunk.chunk_index,
                message=(
                    f"chunk text length {size} exceeds max_chunk_size {config.max_chunk_size} "
                    "and is not a single oversized structural element"
                ),
            )
        )
    return issues


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


def _check_non_whitespace_coverage(full_text: str, chunks: list[DocumentChunk]) -> list[ChunkValidationIssue]:
    """Any source region not covered by a chunk must contain only whitespace."""
    issues = []
    spans = sorted((chunk.start_char, chunk.end_char) for chunk in chunks)
    cursor = 0
    for start, end in spans:
        if start > cursor:
            gap_text = full_text[cursor:start]
            if gap_text.strip():
                issues.append(
                    ChunkValidationIssue(
                        invariant=NON_WHITESPACE_COVERAGE,
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
                    invariant=NON_WHITESPACE_COVERAGE,
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


def _check_element_order(elements: list[tuple[int, int]]) -> list[ChunkValidationIssue]:
    """Structural elements must remain in source order (non-overlapping, strictly forward)."""
    issues = []
    for previous, current in zip(elements, elements[1:]):
        if current[0] < previous[1]:
            issues.append(
                ChunkValidationIssue(
                    invariant=ELEMENT_ORDER,
                    chunk_index=None,
                    message=(
                        f"structural element {current} starts before the previous element "
                        f"{previous} ends"
                    ),
                )
            )
    return issues


def _check_atomic_element_coverage(
    elements: list[tuple[int, int]], chunks: list[DocumentChunk], max_chunk_size: int
) -> list[ChunkValidationIssue]:
    """Every structural element that fits within max_chunk_size must appear in exactly one
    chunk. An oversized element is exempt here: it's intentionally spread across the chunks
    holding its sentence-split pieces (checked instead by structural integrity)."""
    issues = []
    for start, end in elements:
        if end <= start or end - start > max_chunk_size:
            continue
        containing = [chunk for chunk in chunks if chunk.start_char <= start and end <= chunk.end_char]
        if len(containing) != 1:
            issues.append(
                ChunkValidationIssue(
                    invariant=ATOMIC_ELEMENT_COVERAGE,
                    chunk_index=None,
                    message=(
                        f"structural element [{start}:{end}] is fully contained in "
                        f"{len(containing)} chunks, expected exactly 1"
                    ),
                )
            )
    return issues


def _check_structural_integrity(
    pieces: list[tuple[int, int]], chunks: list[DocumentChunk]
) -> list[ChunkValidationIssue]:
    """No word, sentence, bullet, or table row is split unless fallback logic requires it:
    every chunk boundary must land on a structural element/sentence-piece boundary."""
    boundaries = {start for start, _ in pieces} | {end for _, end in pieces}

    issues = []
    for chunk in chunks:
        if chunk.start_char not in boundaries:
            issues.append(
                ChunkValidationIssue(
                    invariant=STRUCTURAL_INTEGRITY,
                    chunk_index=chunk.chunk_index,
                    message=f"chunk start_char {chunk.start_char} splits a structural element",
                )
            )
        if chunk.end_char not in boundaries:
            issues.append(
                ChunkValidationIssue(
                    invariant=STRUCTURAL_INTEGRITY,
                    chunk_index=chunk.chunk_index,
                    message=f"chunk end_char {chunk.end_char} splits a structural element",
                )
            )
    return issues


def validate_chunks(
    document: NormalizedDocument,
    result: ChunkingResult,
    config: ChunkingConfig,
) -> ChunkValidationReport:
    """Check a ChunkingResult against the chunking invariants, collecting every violation found."""
    is_structural = config.chunking_strategy == STRUCTURAL_STRATEGY
    elements = structural_elements(document) if is_structural else []
    pieces = structural_pieces(document, config.max_chunk_size) if is_structural else []

    issues = [
        *_check_order(result.chunks),
        *_check_max_size(result.chunks, config, pieces),
        *_check_overlap(result.chunks, config),
        *_check_non_whitespace_coverage(document.full_text, result.chunks),
        *_check_traceability(document.full_text, result.chunks),
        *_check_offsets(document.full_text, result.chunks),
    ]
    if is_structural:
        issues += [
            *_check_element_order(elements),
            *_check_atomic_element_coverage(elements, result.chunks, config.max_chunk_size),
            *_check_structural_integrity(pieces, result.chunks),
        ]
    return ChunkValidationReport(document_id=document.document_id, issues=issues)
