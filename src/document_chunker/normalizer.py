import re
from dataclasses import dataclass

from document_chunker.schemas import (
    ExtractedPage,
    ExtractedDocument,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedPage,
    NormalizedTable,
    NormalizationStrategy,
)

# NBSP + the Unicode "space separator" block (en/em/thin/hair/ideographic spaces, etc.)
_NON_BREAKING_SPACE_RE = re.compile("[\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000]")
# Zero-width space/joiners, left/right-to-left marks, BOM, soft hyphen.
_INVISIBLE_CHAR_RE = re.compile("[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t]+")
_TRAILING_LINE_WHITESPACE_RE = re.compile(r"[ \t]+\n")
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"[ \t]+([.,;:!?)\]}])")
_SPACE_AFTER_OPEN_BRACKET_RE = re.compile(r"([(\[{])[ \t]+")
_BULLET_RE = re.compile(r"^(?:[●•\-→]|\d+[.)])\s+")
_NUMERIC_ROW_RE = re.compile(r"^[\d$€£¥(),.%+\-/: ]+$")
_SENTENCE_TERMINAL_RE = re.compile(r'[.!?]["\')\]]?$')
_PIPE_SPLIT_TABLE_RE = re.compile(r"\s*\|\s*")
_WHITESPACE_SPLIT_TABLE_RE = re.compile(r"\s{2,}")

DEFAULT_NORMALIZATION_STRATEGY: NormalizationStrategy = "structural"

@dataclass(frozen=True)
class ClassifiedLine:
    text: str
    line_type: str


@dataclass(frozen=True)
class BlockEntry:
    block: NormalizedBlock
    preceded_by_blank: bool


def _normalize_inline_text(text: str) -> str:
    text = _HORIZONTAL_WHITESPACE_RE.sub(" ", text.strip())
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_BRACKET_RE.sub(r"\1", text)
    return text


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

    lowercase_allowed = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
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
        if word.lower() in lowercase_allowed:
            title_like += 1
        elif word[:1].isupper() and word[1:] == word[1:].lower():
            title_like += 1
    return title_like >= max(2, len(words) - 1)


def _is_heading_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _BULLET_RE.match(stripped):
        return False
    if len(stripped) <= 90 and stripped.endswith(":"):
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
    if not text or _BULLET_RE.match(text):
        return False
    columns = _split_table_columns(text)
    if len(columns) < 2:
        return False
    compact_columns = sum(1 for column in columns if len(column.split()) <= 4 or _NUMERIC_ROW_RE.match(column))
    return compact_columns >= 2


def _classify_line(text: str) -> ClassifiedLine:
    stripped = text.strip()
    if not stripped:
        return ClassifiedLine(text="", line_type="blank")
    if _BULLET_RE.match(stripped):
        return ClassifiedLine(text=_normalize_inline_text(stripped), line_type="list_item")
    if _is_table_candidate(stripped):
        return ClassifiedLine(text=stripped, line_type="table_row")
    if _is_heading_like(stripped):
        return ClassifiedLine(text=_normalize_inline_text(stripped), line_type="heading")
    if _is_title_cased_short_line(stripped):
        return ClassifiedLine(text=_normalize_inline_text(stripped), line_type="heading")
    return ClassifiedLine(text=_normalize_inline_text(stripped), line_type="text")


def _should_join_with_next(current: ClassifiedLine, following: ClassifiedLine | None) -> bool:
    if following is None:
        return False
    paragraphish_types = {"text", "table_row"}
    if current.line_type not in paragraphish_types or following.line_type not in paragraphish_types:
        return False
    if _SENTENCE_TERMINAL_RE.search(current.text):
        return False
    if following.text[:1].isdigit():
        return False
    return following.text[:1].isalnum() or following.text[:1] in {"(", '"', "'"}


def _split_table_columns(
    text: str,
    expected_columns: int | None = None,
    allow_token_fallback: bool = True,
) -> list[str]:
    if "|" in text:
        columns = [segment for segment in _PIPE_SPLIT_TABLE_RE.split(text) if segment.strip()]
    else:
        columns = [segment for segment in _WHITESPACE_SPLIT_TABLE_RE.split(text) if segment.strip()]

    normalized_columns = [_normalize_inline_text(segment) for segment in columns]
    if expected_columns is None or len(normalized_columns) == expected_columns:
        return normalized_columns

    if not allow_token_fallback:
        return normalized_columns

    fallback_columns = [_normalize_inline_text(segment) for segment in text.split() if segment.strip()]
    if len(fallback_columns) == expected_columns:
        return fallback_columns

    return normalized_columns


def _row_contains_numeric_cell(row: list[str]) -> bool:
    return any(any(char.isdigit() for char in cell) for cell in row)


def _append_wrapped_table_text(row: list[str], continuation: str) -> None:
    normalized_continuation = _normalize_inline_text(continuation)
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
    if not all(len(cell.split()) <= 4 for cell in first_row):
        return False

    comparable_body_rows = [row for row in body_rows if abs(len(row) - len(first_row)) <= 1]
    if not comparable_body_rows:
        return False

    return any(_row_contains_numeric_cell(row) for row in comparable_body_rows)


def _build_table(lines: list[ClassifiedLine], start_index: int) -> tuple[NormalizedBlock | None, int]:
    candidate_end_index = start_index
    while candidate_end_index < len(lines):
        line_type = lines[candidate_end_index].line_type
        if line_type in {"blank", "list_item"}:
            break
        candidate_end_index += 1

    if candidate_end_index - start_index < 2:
        return None, start_index

    header = _split_table_columns(lines[start_index].text)
    if len(header) < 2:
        return None, start_index

    rows = [header]
    for row_index in range(start_index + 1, candidate_end_index):
        row = _split_table_columns(
            lines[row_index].text,
            expected_columns=len(header),
            allow_token_fallback=False,
        )
        if len(row) >= 2:
            rows.append(row)
            continue

        if lines[row_index].line_type != "text":
            row = _split_table_columns(lines[row_index].text, expected_columns=len(header))
            if len(row) >= 2:
                rows.append(row)
                continue

        if len(row) == 1 and len(rows) >= 2:
            _append_wrapped_table_text(rows[-1], row[0])
            continue
        return None, start_index

    if len(rows) < 2:
        return None, start_index

    if _looks_like_header_row(rows[0], rows[1:]):
        table_header = rows[0]
        body = rows[1:]
    else:
        table_header = []
        body = rows

    table = NormalizedTable(header=table_header, rows=body)
    return NormalizedBlock(block_type="table", table=table), candidate_end_index


def _build_paragraph(lines: list[ClassifiedLine], start_index: int) -> tuple[NormalizedBlock, int]:
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


def _render_blocks(block_entries: list[BlockEntry]) -> str:
    rendered = ""
    previous_type: str | None = None
    for entry in block_entries:
        block = entry.block
        separator = ""
        if rendered:
            if entry.preceded_by_blank:
                separator = "\n\n"
            else:
                separator = "\n" if previous_type == "heading" else "\n\n"

        if block.block_type in {"heading", "paragraph"} and block.text:
            rendered += separator + block.text
        elif block.block_type == "list" and block.items:
            rendered += separator + "\n".join(block.items)
        elif block.block_type == "table" and block.table:
            rendered += separator + _render_table_block(block.table)
        previous_type = block.block_type
    return rendered.strip()


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
            items: list[str] = []
            while index < len(lines) and lines[index].line_type == "list_item":
                items.append(lines[index].text)
                index += 1
            block_entries.append(
                BlockEntry(
                    block=NormalizedBlock(block_type="list", items=items),
                    preceded_by_blank=preceded_by_blank,
                )
            )
            preceded_by_blank = False
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
    return _render_blocks(_build_block_entries(text))


def normalize_text(text: str) -> str:
    """Apply structural normalization for text-based single-column PDF text."""
    return repair_line_wraps(text).strip()


def normalize_page(page: ExtractedPage) -> NormalizedPage:
    block_entries = _build_block_entries(page.text)
    blocks = [entry.block for entry in block_entries]
    text = _render_blocks(block_entries)
    return NormalizedPage(
        page_number=page.page_number,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
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
    full_text = _EXCESS_BLANK_LINES_RE.sub("\n\n", "\n\n".join(page.text for page in pages))

    return NormalizedDocument(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        document_type=document.document_type,
        page_count=len(pages),
        pages=pages,
        full_text=full_text,
        word_count=len(full_text.split()),
        char_count=len(full_text),
        normalized_strategy=strategy,
    )
