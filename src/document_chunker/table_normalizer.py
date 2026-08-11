import re

from document_chunker.normalizer import (
    ClassifiedLine,
    _append_wrapped_table_text,
    _looks_like_header_row,
    _looks_like_table_continuation,
    _normalize_inline_text,
    _parse_table_row,
)
from document_chunker.schemas import NormalizedBlock, NormalizedTable

_COLUMN_GAP_RE = re.compile(r"\s{2,}")


def _segment_positions(raw_text: str) -> list[tuple[int, str]]:
    """(start_offset, text) for each column-like segment in `raw_text` - the line's
    original, un-stripped text, so offsets are absolute character positions comparable
    across every physical line of the same table. Split on '|' if present, otherwise on
    2+-space gaps (the same convention normalize_page's line-level table detection uses)."""
    segments: list[tuple[int, str]] = []
    cursor = 0

    if "|" in raw_text:
        for part in raw_text.split("|"):
            leading = len(part) - len(part.lstrip())
            stripped = part.strip()
            if stripped:
                segments.append((cursor + leading, _normalize_inline_text(stripped)))
            cursor += len(part) + 1
        return segments

    for gap in _COLUMN_GAP_RE.finditer(raw_text):
        if gap.start() > cursor:
            candidate = raw_text[cursor : gap.start()]
            leading = len(candidate) - len(candidate.lstrip())
            stripped = candidate.strip()
            if stripped:
                segments.append((cursor + leading, _normalize_inline_text(stripped)))
        cursor = gap.end()
    if cursor < len(raw_text):
        candidate = raw_text[cursor:]
        leading = len(candidate) - len(candidate.lstrip())
        stripped = candidate.strip()
        if stripped:
            segments.append((cursor + leading, _normalize_inline_text(stripped)))
    return segments


def _nearest_column(offset: int, column_starts: list[int]) -> int:
    return min(range(len(column_starts)), key=lambda i: abs(column_starts[i] - offset))


class TableNormalizer:
    """Reconstructs logical table rows from physical text lines.

    A physical line is not necessarily a table row: layout-mode PDF extraction wraps an
    over-width cell onto its own line, indented to align with the column it belongs to
    rather than the row's first column. That character-offset alignment (established from
    the header row) is the primary signal used here to tell a genuine new row (a segment
    lands at column 0's position) apart from a wrapped continuation (it doesn't) - falling
    back to the existing content-shape heuristics (_parse_table_row's token-count fallback,
    _looks_like_table_continuation's lookahead/trailing-signal check) only when position
    data is inconclusive, e.g. a short trailing fragment that happens to sit at column 0's
    offset. Known limitation: a wrapped column-0 value whose continuation line also carries
    a later column's wrapped text (so it still looks like >=2 populated cells) is read as a
    new row rather than a continuation - there is no reliable signal to distinguish the two
    from a single line alone.
    """

    def detect_header(self, lines: list[ClassifiedLine], start_index: int) -> list[str]:
        """The first candidate line's parsed cell values, and (via _looks_like_header_row,
        applied later in build()) whether they're the header or the first data row."""
        return _parse_table_row(lines[start_index])

    def collect_region(self, lines: list[ClassifiedLine], start_index: int) -> int:
        """Physical lines belonging to this table: everything up to the next blank or
        list-item line, exactly like normalize_page's other block boundaries."""
        end_index = start_index
        while end_index < len(lines) and lines[end_index].line_type not in {"blank", "list_item"}:
            end_index += 1
        return end_index

    def infer_column_starts(self, header_line: ClassifiedLine) -> list[int]:
        """Column count and start offsets, inferred from the header (or first data row,
        for a headerless table) - the reference grid every later line is matched against."""
        segments = _segment_positions(header_line.raw_text)
        if segments:
            return [offset for offset, _ in segments]
        return [header_line.indent]

    def reconstruct_rows(
        self,
        lines: list[ClassifiedLine],
        start_index: int,
        end_index: int,
        header_values: list[str],
        column_starts: list[int],
    ) -> tuple[list[list[str]], int]:
        """Walk the table's physical lines, merging wrapped cell lines into the row
        currently open and emitting a complete logical row each time a line shows evidence
        of a new first-column value (a segment positioned at column 0)."""
        expected_columns = len(header_values)
        rows: list[list[str]] = [header_values]
        row_index = start_index + 1

        while row_index < end_index:
            line = lines[row_index]

            if _nearest_column(line.indent, column_starts) == 0:
                row = _parse_table_row(line, expected_columns=expected_columns)
                if len(row) >= 2:
                    rows.append(row)
                    row_index += 1
                    continue

                if len(rows) >= 2 and _looks_like_table_continuation(
                    lines, row_index, end_index, expected_columns, rows[-1]
                ):
                    # Position is ambiguous here (this line's own offset landed at
                    # column 0), so fall back to the content-based target-cell
                    # heuristic rather than trusting an offset that may just be a
                    # short trailing fragment sitting where column 0 happens to start.
                    self._merge_by_content(rows[-1], line)
                    row_index += 1
                    continue
                break

            # Positionally not at column 0: this line cannot be a new row's first cell,
            # so it can only be a wrapped continuation of the row already in progress -
            # its segments' offsets reliably indicate which column(s) they continue.
            if len(rows) < 2:
                break
            self._merge_by_position(rows[-1], line, column_starts)
            row_index += 1

        return rows, row_index

    def _merge_by_position(self, row: list[str], line: ClassifiedLine, column_starts: list[int]) -> None:
        """Append each of `line`'s segments into the cell of `row` whose column start is
        nearest its own offset - handles both a single wrapped fragment and multiple
        columns' wrapped text sharing one physical line."""
        segments = _segment_positions(line.raw_text)
        if not segments:
            segments = [(line.indent, _normalize_inline_text(line.text))]
        for offset, text in segments:
            index = min(_nearest_column(offset, column_starts), len(row) - 1)
            row[index] = f"{row[index]} {text}".strip()

    def _merge_by_content(self, row: list[str], line: ClassifiedLine) -> None:
        """Append `line`'s content using the existing content-shape heuristic (scan for a
        trailing wrap-continuation signal, else the last non-numeric cell)."""
        segments = _segment_positions(line.raw_text)
        continuation_text = segments[0][1] if segments else _normalize_inline_text(line.text)
        _append_wrapped_table_text(row, continuation_text)

    def build(self, lines: list[ClassifiedLine], start_index: int) -> tuple[NormalizedBlock | None, int]:
        header_values = self.detect_header(lines, start_index)
        if len(header_values) < 2:
            return None, start_index

        end_index = self.collect_region(lines, start_index)
        column_starts = self.infer_column_starts(lines[start_index])
        rows, consumed_index = self.reconstruct_rows(lines, start_index, end_index, header_values, column_starts)

        if len(rows) < 2:
            return None, start_index

        if _looks_like_header_row(rows[0], rows[1:]):
            header, body = rows[0], rows[1:]
        else:
            header, body = [], rows

        table = NormalizedTable(header=header, rows=body)
        return NormalizedBlock(block_type="table", table=table), consumed_index
