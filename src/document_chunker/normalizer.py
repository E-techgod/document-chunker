import re
from dataclasses import dataclass

from document_chunker.schemas import (
    ExtractedDocument,
    ExtractedPage,
    NormalizationStrategy,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedPage,
    NormalizedTable,
)

# NBSP + the Unicode "space separator" block (en/em/thin/hair/ideographic spaces, etc.)
_NON_BREAKING_SPACE_RE = re.compile(
    "[\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000]"
)
# Zero-width space/joiners, left/right-to-left marks, BOM, soft hyphen.
_INVISIBLE_CHAR_RE = re.compile("[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t]+")
_TRAILING_LINE_WHITESPACE_RE = re.compile(r"[ \t]+\n")
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"[ \t]+([.,;:!?)\]}])")
_SPACE_AFTER_OPEN_BRACKET_RE = re.compile(r"([(\[{])[ \t]+")
_LIST_ITEM_RE = re.compile(r"^(?:[●•\-→]|\d+[.)])\s+")
_NUMERIC_ROW_RE = re.compile(r"^[\d$€£¥(),.%+\-/: ]+$")
_SENTENCE_TERMINAL_RE = re.compile(r'[.!?]["\')\]]?$')
_WRAP_CONTINUATION_END_RE = re.compile(
    r"(?:,|[&/\-–—]|(?:\b(?:and|or|but|nor|yet|so|for)\b))$", re.IGNORECASE
)
_PIPE_SPLIT_TABLE_RE = re.compile(r"\s*\|\s*")
_WHITESPACE_SPLIT_TABLE_RE = re.compile(r"\s{2,}")
# A numbered section label followed by more title text, e.g. "Week 4: Git, GitHub & APIs"
# or "Chapter 3: Introduction" — unlike a bare trailing colon, the colon sits mid-line.
_NUMBERED_LABEL_HEADING_RE = re.compile(r"^[A-Z][A-Za-z]*\s+[0-9]+[A-Za-z]*\s*:\s+\S")

DEFAULT_NORMALIZATION_STRATEGY: NormalizationStrategy = "structural"


@dataclass(frozen=True)
class ClassifiedLine:
    text: str
    line_type: str
    indent: int
    raw_text: str


@dataclass(frozen=True)
class BlockEntry:
    block: NormalizedBlock
    preceded_by_blank: bool


def _normalize_inline_text(text: str) -> str:
    text = _HORIZONTAL_WHITESPACE_RE.sub(" ", text.strip())
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_BRACKET_RE.sub(r"\1", text)
    return text


def _measure_indent(text: str) -> int:
    indent = 0
    for char in text:
        if char == " ":
            indent += 1
            continue
        if char == "\t":
            indent += 4
            continue
        break
    return indent


def _preprocess_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INVISIBLE_CHAR_RE.sub("", text)
    text = _NON_BREAKING_SPACE_RE.sub(" ", text)
    text = text.replace("\v", "\n").replace("\f", "\n")
    text = _CONTROL_CHAR_RE.sub("", text)
    text = _TRAILING_LINE_WHITESPACE_RE.sub("\n", text)
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", text)


def _is_title_cased_short_line(text: str) -> bool:
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z'/-]*", text) if word]
    if not words or len(words) > 12 or len(text) > 90:
        return False
    if len(words) < 2:
        return False

    lowercase_allowed = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
    clause_like_words = {
        "am",
        "are",
        "be",
        "been",
        "being",
        "can",
        "could",
        "did",
        "do",
        "does",
        "had",
        "has",
        "have",
        "how",
        "is",
        "it",
        "its",
        "should",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "those",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "would",
        "you",
        "your",
    }
    lowered_words = [word.lower() for word in words]
    if any(word in clause_like_words for word in lowered_words):
        return False

    title_like = 0
    for word in words:
        if word.lower() in lowercase_allowed or word[:1].isupper() and word[1:] == word[1:].lower():
            title_like += 1
    return title_like >= max(2, len(words) - 1)


def _is_heading_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _LIST_ITEM_RE.match(stripped):
        return False
    if len(stripped) <= 90 and stripped.endswith(":"):
        return True
    if (
        len(stripped) <= 90
        and _NUMBERED_LABEL_HEADING_RE.match(stripped)
        and not _SENTENCE_TERMINAL_RE.search(stripped)
    ):
        return True

    words = stripped.split()
    if len(words) > 14:
        return False

    letters = [char for char in stripped if char.isalpha()]
    if letters:
        uppercase_ratio = sum(char.isupper() for char in letters) / len(letters)
        if uppercase_ratio >= 0.8 and (len(words) >= 2 or len(stripped) >= 8):
            return True

    return False


def _is_table_candidate(text: str) -> bool:
    if not text or _LIST_ITEM_RE.match(text):
        return False
    columns = _split_table_columns(text)
    if len(columns) < 2:
        return False
    compact_columns = sum(
        1
        for column in columns
        if len(column.split()) <= 4 or _NUMERIC_ROW_RE.match(column)
    )
    return compact_columns >= 1


def _is_list_item(text: str) -> bool:
    return bool(_LIST_ITEM_RE.match(text))


def _classify_line(text: str) -> ClassifiedLine:
    indent = _measure_indent(text)
    stripped = text.strip()
    if not stripped:
        return ClassifiedLine(text="", line_type="blank", indent=indent, raw_text=text)
    if _is_list_item(stripped):
        return ClassifiedLine(
            text=_normalize_inline_text(stripped),
            line_type="list_item",
            indent=indent,
            raw_text=text,
        )
    if _is_table_candidate(stripped):
        return ClassifiedLine(
            text=stripped, line_type="table_row", indent=indent, raw_text=text
        )
    if _is_heading_like(stripped):
        return ClassifiedLine(
            text=_normalize_inline_text(stripped),
            line_type="heading",
            indent=indent,
            raw_text=text,
        )
    if _is_title_cased_short_line(stripped):
        return ClassifiedLine(
            text=_normalize_inline_text(stripped),
            line_type="heading",
            indent=indent,
            raw_text=text,
        )
    return ClassifiedLine(
        text=_normalize_inline_text(stripped),
        line_type="text",
        indent=indent,
        raw_text=text,
    )


def _should_join_with_next(
    current: ClassifiedLine, following: ClassifiedLine | None
) -> bool:
    if following is None:
        return False
    if current.line_type != "text" or following.line_type != "text":
        return False
    if _has_strong_paragraph_stop(current, following):
        return False
    return _has_paragraph_join_signal(current, following)


def _has_strong_paragraph_stop(
    current: ClassifiedLine, following: ClassifiedLine
) -> bool:
    if _SENTENCE_TERMINAL_RE.search(current.text):
        return True
    if following.text[:1].isdigit():
        return True
    if _is_heading_like(following.text) or _is_title_cased_short_line(following.text):
        return True
    return bool(_looks_like_section_label(following.text))


def _has_paragraph_join_signal(
    current: ClassifiedLine, following: ClassifiedLine
) -> bool:
    if not _starts_like_paragraph_continuation(following):
        return False
    if _WRAP_CONTINUATION_END_RE.search(current.text):
        return True
    if _looks_like_short_lowercase_fragment(current):
        return True
    if _following_starts_lowercase(following):
        return True
    if following.indent > current.indent:
        return True
    if _looks_visually_wrapped(current):
        return True
    return bool(_looks_like_wrapped_fragment(current, following))


def _starts_like_paragraph_continuation(line: ClassifiedLine) -> bool:
    return bool(line.text[:1]) and (
        line.text[:1].isalnum() or line.text[:1] in {"(", '"', "'"}
    )


def _following_starts_lowercase(line: ClassifiedLine) -> bool:
    return bool(line.text[:1]) and line.text[:1].islower()


def _looks_visually_wrapped(line: ClassifiedLine) -> bool:
    return len(line.text) >= 55 or len(line.text.split()) >= 9


def _looks_like_short_lowercase_fragment(line: ClassifiedLine) -> bool:
    words = line.text.split()
    return 1 <= len(words) <= 2 and line.text[:1].islower()


def _looks_like_wrapped_fragment(
    current: ClassifiedLine, following: ClassifiedLine
) -> bool:
    current_words = current.text.split()
    following_words = following.text.split()
    if len(current_words) > 2 or len(following_words) > 3:
        return False
    if _looks_like_section_label(current.text) or _looks_like_section_label(
        following.text
    ):
        return False
    return any(char.islower() for char in following.text[1:]) or current.text.isupper()


def _looks_like_section_label(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped.endswith(":"):
        return False
    if stripped[:1].isdigit():
        return False
    words = stripped.split()
    if not 2 <= len(words) <= 6:
        return False
    if stripped[-1:] in {",", ";", "-", "–", "—", "&", "/"}:
        return False
    return all(word[:1].isupper() for word in words if word[:1].isalnum())


def _split_table_columns(
    text: str,
    expected_columns: int | None = None,
    allow_token_fallback: bool = True,
) -> list[str]:
    if "|" in text:
        columns = [
            segment for segment in _PIPE_SPLIT_TABLE_RE.split(text) if segment.strip()
        ]
    else:
        columns = [
            segment
            for segment in _WHITESPACE_SPLIT_TABLE_RE.split(text)
            if segment.strip()
        ]

    normalized_columns = [_normalize_inline_text(segment) for segment in columns]
    if expected_columns is None or len(normalized_columns) == expected_columns:
        return normalized_columns

    if not allow_token_fallback:
        return normalized_columns

    fallback_columns = [
        _normalize_inline_text(segment) for segment in text.split() if segment.strip()
    ]
    if len(fallback_columns) == expected_columns:
        return fallback_columns

    return normalized_columns


def _row_contains_numeric_cell(row: list[str]) -> bool:
    return any(any(char.isdigit() for char in cell) for cell in row)


def _append_wrapped_table_text(row: list[str], continuation: str) -> None:
    normalized_continuation = _normalize_inline_text(continuation)
    for index in range(len(row) - 1, -1, -1):
        if _WRAP_CONTINUATION_END_RE.search(row[index]):
            row[index] = f"{row[index]} {normalized_continuation}".strip()
            return
    for index in range(len(row) - 1, -1, -1):
        if not _NUMERIC_ROW_RE.match(row[index]):
            row[index] = f"{row[index]} {normalized_continuation}".strip()
            return
    row[-1] = f"{row[-1]} {normalized_continuation}".strip()


def _looks_like_header_row(first_row: list[str], body_rows: list[list[str]]) -> bool:
    if len(first_row) < 2 or not body_rows:
        return False
    if _row_contains_numeric_cell(first_row):
        return False
    if not all(len(cell.split()) <= 6 for cell in first_row):
        return False

    comparable_body_rows = [
        row for row in body_rows if abs(len(row) - len(first_row)) <= 1
    ]
    if not comparable_body_rows:
        return False

    return any(_row_contains_numeric_cell(row) for row in comparable_body_rows)


def _parse_table_row(
    line: ClassifiedLine, expected_columns: int | None = None
) -> list[str]:
    row = _split_table_columns(
        line.text,
        expected_columns=expected_columns,
        allow_token_fallback=False,
    )
    if len(row) >= 2:
        return row

    if line.line_type == "text":
        return row

    fallback_row = _split_table_columns(
        line.text,
        expected_columns=expected_columns,
        allow_token_fallback=True,
    )
    if len(fallback_row) >= 2:
        return fallback_row

    return row


def _looks_like_table_continuation(
    lines: list[ClassifiedLine],
    continuation_index: int,
    candidate_end_index: int,
    expected_columns: int,
    previous_row: list[str],
) -> bool:
    continuation = lines[continuation_index]
    # A wrapped fragment can get misclassified as a heading (e.g. a short,
    # title-cased continuation like "Career Prep") by the line-level
    # classifier, which has no notion that it's sitting inside a table. Blank
    # and list-item lines never appear here anyway since candidate_end_index
    # stops scanning before them; only rule out an actual table_row, whose
    # multiple columns would already have satisfied len(row) >= 2 upstream.
    if continuation.line_type in {"blank", "list_item", "table_row"}:
        return False
    if _SENTENCE_TERMINAL_RE.search(continuation.text):
        return False

    next_index = continuation_index + 1
    if next_index < candidate_end_index:
        next_line = lines[next_index]
        if next_line.line_type != "blank":
            next_row = _parse_table_row(next_line, expected_columns=expected_columns)
            if len(next_row) >= 2:
                return True

    # Either the last line in the candidate range, or the line after it isn't
    # tabular either: only treat this as a wrapped cell when the previous row
    # visibly trails off (ends in a comma/ampersand/dash/conjunction) rather
    # than assuming every trailing fragment belongs to it.
    return any(_WRAP_CONTINUATION_END_RE.search(cell) for cell in previous_row)


def _build_table(
    lines: list[ClassifiedLine], start_index: int
) -> tuple[NormalizedBlock | None, int]:
    """Row/cell reconstruction for a table region is delegated to TableNormalizer (see
    table_normalizer.py) - a physical line is not necessarily a table row, so that module
    owns detecting the header/column count, merging wrapped cell lines back into the
    logical row they continue, and emitting complete rows in order. Imported locally to
    avoid a circular import (table_normalizer.py reuses this module's line-parsing
    helpers)."""
    from document_chunker.table_normalizer import TableNormalizer

    return TableNormalizer().build(lines, start_index)


def _build_paragraph(
    lines: list[ClassifiedLine], start_index: int
) -> tuple[NormalizedBlock, int]:
    parts = [lines[start_index].text]
    index = start_index

    while index + 1 < len(lines):
        current = lines[index]
        following = lines[index + 1]
        if following.line_type == "blank":
            break
        if not _should_join_with_next(current, following):
            break

        parts.append(following.text)
        index += 1

    paragraph = " ".join(parts)
    paragraph = _HORIZONTAL_WHITESPACE_RE.sub(" ", paragraph).strip()
    return NormalizedBlock(block_type="paragraph", text=paragraph), index + 1


def _render_table_block(table: NormalizedTable) -> str:
    rows = []
    if table.header:
        rows.append(" | ".join(table.header))
    rows.extend(" | ".join(row) for row in table.rows)
    return "\n".join(rows)


def _render_blocks(
    block_entries: list[BlockEntry],
) -> tuple[str, list[NormalizedBlock]]:
    rendered = ""
    previous_type: str | None = None
    positioned_blocks: list[NormalizedBlock] = []
    for entry in block_entries:
        block = entry.block
        separator = ""
        if rendered:
            if entry.preceded_by_blank:
                separator = "\n\n"
            else:
                separator = "\n" if previous_type == "heading" else "\n\n"

        segment = ""
        if block.block_type in {"heading", "paragraph"} and block.text:
            segment = block.text
        elif block.block_type == "list" and block.items:
            segment = "\n".join(block.items)
        elif block.block_type == "table" and block.table:
            segment = _render_table_block(block.table)

        if segment:
            rendered += separator
            start = len(rendered)
            rendered += segment
            end = len(rendered)
        else:
            start = end = len(rendered)

        positioned_blocks.append(
            block.model_copy(update={"start_char": start, "end_char": end})
        )
        previous_type = block.block_type

    stripped = rendered.strip()
    leading_trim = len(rendered) - len(rendered.lstrip())
    final_blocks = [
        block.model_copy(
            update={
                "start_char": min(
                    max(block.start_char - leading_trim, 0), len(stripped)
                ),
                "end_char": min(max(block.end_char - leading_trim, 0), len(stripped)),
            }
        )
        for block in positioned_blocks
    ]
    return stripped, final_blocks


def _build_list(
    lines: list[ClassifiedLine], start_index: int
) -> tuple[NormalizedBlock, int]:
    items: list[str] = []
    index = start_index

    while index < len(lines) and lines[index].line_type == "list_item":
        item = lines[index]
        item_parts = [item.text]
        continuation_index = index + 1

        while continuation_index < len(lines):
            continuation = lines[continuation_index]
            if not _is_list_continuation(item, continuation):
                break
            item_parts.append(continuation.text)
            continuation_index += 1

        items.append(" ".join(item_parts).strip())
        index = continuation_index

    return NormalizedBlock(block_type="list", items=items), index


def _is_list_continuation(item: ClassifiedLine, continuation: ClassifiedLine) -> bool:
    if continuation.line_type in {"blank", "list_item", "heading", "table_row"}:
        return False
    if continuation.line_type != "text":
        return False
    return continuation.indent > item.indent


def _build_block_entries(text: str) -> list[BlockEntry]:
    lines = [_classify_line(line) for line in _preprocess_text(text).split("\n")]
    block_entries: list[BlockEntry] = []
    index = 0
    preceded_by_blank = False

    while index < len(lines):
        current = lines[index]
        if current.line_type == "blank":
            preceded_by_blank = True
            index += 1
            continue
        if current.line_type == "heading":
            block_entries.append(
                BlockEntry(
                    block=NormalizedBlock(block_type="heading", text=current.text),
                    preceded_by_blank=preceded_by_blank,
                )
            )
            preceded_by_blank = False
            index += 1
            continue
        if current.line_type == "list_item":
            list_block, next_index = _build_list(lines, index)
            block_entries.append(
                BlockEntry(
                    block=list_block,
                    preceded_by_blank=preceded_by_blank,
                )
            )
            preceded_by_blank = False
            index = next_index
            continue
        if current.line_type == "table_row":
            table_block, next_index = _build_table(lines, index)
            if table_block is not None:
                block_entries.append(
                    BlockEntry(block=table_block, preceded_by_blank=preceded_by_blank)
                )
                preceded_by_blank = False
                index = next_index
                continue
        paragraph_block, next_index = _build_paragraph(lines, index)
        block_entries.append(
            BlockEntry(block=paragraph_block, preceded_by_blank=preceded_by_blank)
        )
        preceded_by_blank = False
        index = next_index

    return block_entries


def _build_blocks(text: str) -> list[NormalizedBlock]:
    return [entry.block for entry in _build_block_entries(text)]


def repair_line_wraps(text: str) -> str:
    """Repair soft line wraps using page-local structural classification rules."""
    text, _ = _render_blocks(_build_block_entries(text))
    return text


def normalize_text(text: str) -> str:
    """Apply structural normalization for text-based single-column PDF text."""
    return repair_line_wraps(text).strip()


def normalize_page(page: ExtractedPage) -> NormalizedPage:
    block_entries = _build_block_entries(page.text)
    text, blocks = _render_blocks(block_entries)
    return NormalizedPage(
        page_number=page.page_number,
        text=text,
        blocks=blocks,
    )


def normalize_document(
    document: ExtractedDocument,
    strategy: NormalizationStrategy = DEFAULT_NORMALIZATION_STRATEGY,
) -> NormalizedDocument:
    """Normalize an ExtractedDocument page by page, preserving page boundaries, then recombine."""
    pages = [normalize_page(page) for page in document.pages]
    # Joining across a blank page produces "\n\n" + "" + "\n\n" (4 newlines);
    # collapse those back down so the combined text keeps rule 6/8's limit too.
    full_text = _EXCESS_BLANK_LINES_RE.sub(
        "\n\n", "\n\n".join(page.text for page in pages)
    )

    return NormalizedDocument(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        document_type=document.document_type,
        pages=pages,
        full_text=full_text,
        normalized_strategy=strategy,
    )
