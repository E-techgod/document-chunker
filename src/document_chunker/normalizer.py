import re
from collections import Counter
from dataclasses import dataclass

from document_chunker.schemas import (
    ExtractDocument,
    ExtractDocumentPage,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedPage,
    NormalizedTable,
)

# NBSP + the Unicode "space separator" block (en/em/thin/hair/ideographic spaces, etc.)
_NON_BREAKING_SPACE_RE = re.compile("[\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000]")
# Zero-width space/joiners, left/right-to-left marks, BOM, soft hyphen.
_INVISIBLE_CHAR_RE = re.compile("[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t]+")
_TRAILING_LINE_WHITESPACE_RE = re.compile(r"[ \t]+\n")
_LEADING_LINE_WHITESPACE_RE = re.compile(r"\n[ \t]+")
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"[ \t]+([.,;:!?)\]}])")
_SPACE_AFTER_OPEN_BRACKET_RE = re.compile(r"([(\[{])[ \t]+")
_BULLET_RE = re.compile(r"^(?:[●•\-→]|\d+[.)])\s+")
_NUMERIC_ROW_RE = re.compile(r"^[\d$€£¥(),.%+\-/: ]+$")
_SENTENCE_TERMINAL_RE = re.compile(r'[.!?]["\')\]]?$')
_SPLIT_TABLE_RE = re.compile(r"\s{2,}|\s+\|\s+")

DEFAULT_NORMALIZATION_STRATEGY = "aggressive"


@dataclass(frozen=True)
class ClassifiedLine:
    text: str
    line_type: str


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
    text = _LEADING_LINE_WHITESPACE_RE.sub("\n", text)
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", text)


def _is_title_cased_short_line(text: str) -> bool:
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z'/-]*", text) if word]
    if not words or len(words) > 12 or len(text) > 90:
        return False

    lowercase_allowed = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
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
    columns = [segment.strip() for segment in _SPLIT_TABLE_RE.split(text) if segment.strip()]
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
    if current.line_type != "text" or following.line_type != "text":
        return False
    if _SENTENCE_TERMINAL_RE.search(current.text):
        return False
    if following.text[:1].isdigit():
        return False
    return following.text[:1].isalnum() or following.text[:1] in {"(", '"', "'"}


def _split_table_columns(text: str) -> list[str]:
    return [_normalize_inline_text(segment) for segment in _SPLIT_TABLE_RE.split(text) if segment.strip()]


def _build_table(lines: list[ClassifiedLine], start_index: int) -> tuple[NormalizedBlock | None, int]:
    rows: list[list[str]] = []
    index = start_index
    while index < len(lines) and lines[index].line_type == "table_row":
        row = _split_table_columns(lines[index].text)
        if len(row) < 2:
            break
        rows.append(row)
        index += 1

    if len(rows) < 2:
        return None, start_index

    column_count = Counter(len(row) for row in rows).most_common(1)[0][0]
    normalized_rows = [row for row in rows if len(row) == column_count]
    if len(normalized_rows) < 2:
        return None, start_index

    header = normalized_rows[0]
    body = normalized_rows[1:]
    table = NormalizedTable(header=header, rows=body)
    return NormalizedBlock(block_type="table", table=table), index


def _build_paragraph(lines: list[ClassifiedLine], start_index: int) -> tuple[NormalizedBlock, int]:
    parts = [lines[start_index].text]
    index = start_index

    while index + 1 < len(lines):
        current = lines[index]
        following = lines[index + 1]
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


def _render_blocks(blocks: list[NormalizedBlock]) -> str:
    rendered = ""
    previous_type: str | None = None
    for block in blocks:
        separator = ""
        if rendered:
            separator = "\n" if previous_type == "heading" else "\n\n"

        if block.block_type in {"heading", "paragraph"} and block.text:
            rendered += separator + block.text
        elif block.block_type == "list" and block.items:
            rendered += separator + "\n".join(block.items)
        elif block.block_type == "table" and block.table:
            rendered += separator + _render_table_block(block.table)
        previous_type = block.block_type
    return rendered.strip()


def _build_blocks(text: str) -> list[NormalizedBlock]:
    lines = [_classify_line(line) for line in _preprocess_text(text).split("\n")]
    blocks: list[NormalizedBlock] = []
    index = 0

    while index < len(lines):
        current = lines[index]
        if current.line_type == "blank":
            index += 1
            continue
        if current.line_type == "heading":
            blocks.append(NormalizedBlock(block_type="heading", text=current.text))
            index += 1
            continue
        if current.line_type == "list_item":
            items: list[str] = []
            while index < len(lines) and lines[index].line_type == "list_item":
                items.append(lines[index].text)
                index += 1
            blocks.append(NormalizedBlock(block_type="list", items=items))
            continue
        if current.line_type == "table_row":
            table_block, next_index = _build_table(lines, index)
            if table_block is not None:
                blocks.append(table_block)
                index = next_index
                continue
        paragraph_block, next_index = _build_paragraph(lines, index)
        blocks.append(paragraph_block)
        index = next_index

    return blocks


def repair_line_wraps(text: str) -> str:
    """Repair soft line wraps using page-local structural classification rules."""
    blocks = _build_blocks(text)
    return _render_blocks(blocks)


def normalize_text(text: str) -> str:
    """Apply structural normalization for text-based single-column PDF text."""
    return repair_line_wraps(text).strip()


def normalize_page(page: ExtractDocumentPage) -> NormalizedPage:
    blocks = _build_blocks(page.text)
    text = _render_blocks(blocks)
    return NormalizedPage(
        page_number=page.page_number,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        blocks=blocks,
    )


def normalize_document(
    document: ExtractDocument, strategy: str = DEFAULT_NORMALIZATION_STRATEGY
) -> NormalizedDocument:
    """Normalize an ExtractDocument page by page, preserving page boundaries, then recombine."""
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
        word_count=sum(page.word_count for page in pages),
        char_count=len(full_text),
        normalized_strategy=strategy,
    )
