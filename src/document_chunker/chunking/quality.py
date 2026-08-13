import itertools
from bisect import bisect_right

from src.document_chunker.chunking.chunker import document_structural_units
from src.document_chunker.chunking.evaluator import validate_chunks
from src.document_chunker.schemas import (
    ChunkingConfig,
    ChunkingResult,
    ChunkQualityReport,
    DocumentChunk,
    NormalizedDocument,
)

# A chunk under this share of max_chunk_size is too small to carry standalone meaning.
TINY_CHUNK_RATIO = 0.10

_PROSE_BLOCK_TYPES = {"heading", "paragraph"}


def _avg_utilization(chunks: list[DocumentChunk], max_chunk_size: int) -> float:
    if not chunks:
        return 0.0
    return sum(chunk.char_count / max_chunk_size for chunk in chunks) / len(chunks)


def _tiny_chunk_count(chunks: list[DocumentChunk], max_chunk_size: int) -> int:
    threshold = max_chunk_size * TINY_CHUNK_RATIO
    return sum(1 for chunk in chunks if chunk.char_count < threshold)


def _interior_boundaries(chunks: list[DocumentChunk], text_length: int) -> list[int]:
    """Chunk start/end offsets that fall strictly inside the document, excluding its very
    first and last position - those aren't splits, they're the document's own edges."""
    boundaries = {chunk.start_char for chunk in chunks} | {
        chunk.end_char for chunk in chunks
    }
    boundaries.discard(0)
    boundaries.discard(text_length)
    return sorted(boundaries)


def _splits_a_word(full_text: str, boundary: int) -> bool:
    return not full_text[boundary - 1].isspace() and not full_text[boundary].isspace()


def _classify_splits(
    document: NormalizedDocument, chunks: list[DocumentChunk]
) -> tuple[int, int, int]:
    """Count chunk boundaries that cut through the interior of an atomic structural unit:
    a word (inside a heading/paragraph), a list item (bullet), or a table row. Works for
    any chunking strategy - it checks boundaries against the document's own structure, not
    against the pieces a particular strategy chose to respect."""
    units = document_structural_units(document)
    starts = [start for start, _, _ in units]
    full_text = document.full_text

    word_splits = bullet_splits = table_row_splits = 0
    for boundary in _interior_boundaries(chunks, len(full_text)):
        index = bisect_right(starts, boundary) - 1
        if index < 0:
            continue
        start, end, block_type = units[index]
        if not (start < boundary < end):
            continue  # boundary sits on a unit edge, or in inter-element whitespace

        if block_type == "list":
            bullet_splits += 1
        elif block_type == "table":
            table_row_splits += 1
        elif block_type in _PROSE_BLOCK_TYPES and _splits_a_word(full_text, boundary):
            word_splits += 1

    return word_splits, bullet_splits, table_row_splits


def _overlap_overhead(chunks: list[DocumentChunk]) -> float:
    """Share of all emitted characters that are redundant duplicates from character-based
    overlap between consecutive chunks."""
    total_chars = sum(chunk.char_count for chunk in chunks)
    if total_chars == 0:
        return 0.0
    redundant = sum(
        max(0, earlier.end_char - later.start_char)
        for earlier, later in itertools.pairwise(chunks)
    )
    return redundant / total_chars


def _context_prefix_overhead(chunks: list[DocumentChunk]) -> float:
    """Share of delivered (contextualized) text that is injected context rather than the
    chunk's own content."""
    total = sum(len(chunk.contextualized_text) for chunk in chunks)
    if total == 0:
        return 0.0
    prefix_chars = sum(
        len(chunk.context_prefix) + 1 for chunk in chunks if chunk.context_prefix
    )
    return prefix_chars / total


def _context_coverage(
    document: NormalizedDocument, chunks: list[DocumentChunk]
) -> float:
    """Of the chunks that need context to stand alone (their leading unit doesn't open on a
    heading, and isn't the document's own opening unit - there's no governing heading yet
    and no previous chunk to fall back on, so _resolve_context_prefix() has nothing to
    attach even in a fully working pipeline), the share that actually received a non-empty
    context_prefix."""
    units = document_structural_units(document)
    unit_type_by_start = {start: block_type for start, _, block_type in units}
    document_start = units[0][0] if units else None

    needing = satisfied = 0
    for chunk in chunks:
        if chunk.start_char == document_start:
            continue  # opens the document itself - no prior heading exists to draw from
        if unit_type_by_start.get(chunk.start_char) == "heading":
            continue  # opens fresh on its own heading, doesn't need a prefix
        needing += 1
        if chunk.context_prefix:
            satisfied += 1

    return satisfied / needing if needing else 1.0


def evaluate_chunk_quality(
    document: NormalizedDocument, result: ChunkingResult, config: ChunkingConfig
) -> ChunkQualityReport:
    """Score a ChunkingResult's quality on the metrics that distinguish chunking strategies
    in practice - chunk-size utilization, tiny/fragment chunks, structural splits, and
    context overhead/coverage - so V1, V2.1, and V2.2 outputs can be compared on the same
    document. Complements validate_chunks(), which only checks pass/fail invariants."""
    chunks = result.chunks
    chunk_count = len(chunks)
    is_valid = validate_chunks(document, result, config).is_valid
    word_splits, bullet_splits, table_row_splits = _classify_splits(document, chunks)
    tiny_chunk_count = _tiny_chunk_count(chunks, config.max_chunk_size)

    is_structural = config.chunking_strategy == "structural"
    if config.chunking_strategy == "characters" and config.overlap_size > 0:
        context_overhead = _overlap_overhead(chunks)
        overhead_source = "overlap"
    elif is_structural and config.propagate_context:
        context_overhead = _context_prefix_overhead(chunks)
        overhead_source = "context_prefix"
    else:
        context_overhead = 0.0
        overhead_source = "none"

    context_coverage = (
        _context_coverage(document, chunks)
        if is_structural and config.propagate_context
        else None
    )

    return ChunkQualityReport(
        document_id=document.document_id,
        chunking_strategy=config.chunking_strategy,
        propagate_context=config.propagate_context,
        is_valid=is_valid,
        chunk_count=chunk_count,
        avg_utilization=_avg_utilization(chunks, config.max_chunk_size),
        tiny_chunk_count=tiny_chunk_count,
        tiny_chunk_ratio=(tiny_chunk_count / chunk_count) if chunk_count else 0.0,
        word_splits=word_splits,
        bullet_splits=bullet_splits,
        table_row_splits=table_row_splits,
        context_overhead=context_overhead,
        overhead_source=overhead_source,
        context_coverage=context_coverage,
    )


_METRICS = (
    "Valid",
    "Chunks",
    "Avg utilization",
    "Tiny chunks",
    "Word splits",
    "Bullet splits",
    "Table-row splits",
    "Context overhead",
    "Context coverage",
)


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _cell(report: ChunkQualityReport, metric: str) -> str:
    if metric == "Valid":
        return "✓" if report.is_valid else "✗"
    if metric == "Chunks":
        return str(report.chunk_count)
    if metric == "Avg utilization":
        return _pct(report.avg_utilization)
    if metric == "Tiny chunks":
        return _pct(report.tiny_chunk_ratio)
    if metric == "Word splits":
        return str(report.word_splits)
    if metric == "Bullet splits":
        return str(report.bullet_splits)
    if metric == "Table-row splits":
        return str(report.table_row_splits)
    if metric == "Context overhead":
        suffix = "*" if report.overhead_source == "overlap" else ""
        return f"{_pct(report.context_overhead)}{suffix}"
    if metric == "Context coverage":
        return (
            "N/A" if report.context_coverage is None else _pct(report.context_coverage)
        )
    raise ValueError(f"unknown metric: {metric}")


def format_quality_comparison(reports: dict[str, ChunkQualityReport]) -> str:
    """Render a `Metric | <label> | <label> | ...` comparison table, one column per report,
    in the order given (e.g. {"V1": ..., "V2.1": ..., "V2.2": ...})."""
    if not reports:
        return ""

    labels = list(reports)
    label_col = max(len(metric) for metric in _METRICS) + 2
    col_width = max(max(len(label) for label in labels), 6) + 4

    header = "Metric".ljust(label_col) + "".join(
        label.center(col_width) for label in labels
    )
    lines = [header, "-" * len(header)]
    for metric in _METRICS:
        row = metric.ljust(label_col) + "".join(
            _cell(reports[label], metric).center(col_width) for label in labels
        )
        lines.append(row)

    if any(report.overhead_source == "overlap" for report in reports.values()):
        lines.append(
            "* overlap redundancy from character-based chunking, not injected context"
        )

    return "\n".join(lines)
