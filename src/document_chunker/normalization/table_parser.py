from src.document_chunker.normalization.list_detector import match_list_item
from src.document_chunker.normalization.normalizer import (
    _classify_line,
    _is_table_candidate,
    _render_table_block,
)
from src.document_chunker.normalization.table_normalizer import TableNormalizer
from src.document_chunker.schemas import NormalizedTable

# Phase 5 of the Step 2 redesign: table region parsing for paragraph_normalizer's
# _split_into_blocks. Row/cell reconstruction (column inference, wrapped-cell merging,
# header detection) is delegated entirely to table_normalizer.TableNormalizer, the same
# position-based algorithm already proven and bug-fixed against this repo's own
# real-world PDF tables for the existing normalizer.py pipeline - see that module's
# docstring for the algorithm itself. This module's job is just the adapter: decide when
# a run of lines is a table region, hand it to TableNormalizer via lightweight
# ClassifiedLine wrappers, then shape the result into Phase 1's TableBlock contract
# (rectangular rows, a rendered "col | col | col" text representation).


def is_table_row_candidate(line: str) -> bool:
    """Whether `line` looks like it could be a table row - reuses normalizer.py's own
    line-level table detection (2+ pipe/whitespace-gap-separated columns, at least one
    of them compact), so a table region is recognized the same way in both pipelines."""
    return _is_table_candidate(line)


def _collect_table_region(
    lines: list[str], start_index: int, noise_line_indices: dict[int, str] | None = None
) -> int:
    """Physical lines belonging to this table region: everything up to the next blank
    line or list-item marker line - the same region-boundary convention
    TableNormalizer.collect_region already uses (stop on blank/list_item), plus any
    line the caller already classified as page-header/page-footer noise."""
    end_index = start_index
    noise_line_indices = noise_line_indices or {}
    while end_index < len(lines):
        stripped = lines[end_index].strip()
        if (
            end_index in noise_line_indices
            or not stripped
            or match_list_item(stripped) is not None
        ):
            break
        end_index += 1
    return end_index


def _rectangularize(
    rows: list[list[str]], num_columns: int, overflow_joiners: list[str] | None = None
) -> list[list[str]]:
    """Pad a short row with empty strings, or fold an overlong one's extra cells into
    its last column, so every row has exactly num_columns cells - Phase 5's explicit
    rectangularity requirement (TableNormalizer's own contract allows ragged rows for
    the older pipeline, since real PDFs are often ragged; this is an intentional,
    additional guarantee only Phase 5's TableBlock makes)."""
    if num_columns <= 0:
        return [list(row) for row in rows]

    rectangular = []
    for index, row in enumerate(rows):
        joiner = " "
        if overflow_joiners is not None and index < len(overflow_joiners):
            joiner = overflow_joiners[index]
        if len(row) < num_columns:
            row = list(row) + [""] * (num_columns - len(row))
        elif len(row) > num_columns:
            row = list(row[: num_columns - 1]) + [joiner.join(row[num_columns - 1 :])]
        else:
            row = list(row)
        rectangular.append(row)
    return rectangular


def parse_table_region(
    lines: list[str], start_index: int, noise_line_indices: dict[int, str] | None = None
) -> tuple[tuple[list[str], list[list[str]], str] | None, int]:
    """Parse a table region starting at `lines[start_index]` (already confirmed to look
    like a table row by the caller via is_table_row_candidate) into (columns, rows,
    text). Returns (None, start_index) if the region doesn't actually hold a valid
    table (mirrors TableNormalizer.build's own None case, e.g. a single unparseable
    line)."""
    end_index = _collect_table_region(
        lines, start_index, noise_line_indices=noise_line_indices
    )
    # _classify_line (not a hardcoded "table_row" type) matters here: TableNormalizer's
    # continuation-vs-new-row logic (_looks_like_table_continuation) explicitly treats a
    # line typed "table_row" as never being a mere continuation fragment, so a
    # single-word wrapped cell like "Consulting" must come through as the same "text"
    # type the older pipeline's own classifier would give it - not "table_row" - or it
    # gets wrongly rejected instead of merged.
    classified = [_classify_line(line) for line in lines[start_index:end_index]]

    block, consumed, row_uses_pipe_delimiter = (
        TableNormalizer().build_with_row_delimiter_flags(classified, 0)
    )
    if block is None or block.table is None:
        return None, start_index

    columns = block.table.header
    overflow_joiners = [
        " | " if uses_pipe else " " for uses_pipe in row_uses_pipe_delimiter
    ]
    rows = _rectangularize(
        block.table.rows, len(columns), overflow_joiners=overflow_joiners
    )
    text = _render_table_block(NormalizedTable(header=columns, rows=rows))

    return (columns, rows, text), start_index + consumed
