import re

from document_chunker.schemas import (
    ExtractDocument,
    ExtractDocumentPage,
    NormalizedDocument,
    NormalizedPage,
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

DEFAULT_NORMALIZATION_STRATEGY = "conservative"


def normalize_text(text: str) -> str:
    """Apply conservative, deterministic whitespace and control-character cleanup."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 1. normalize line endings
    text = _NON_BREAKING_SPACE_RE.sub(" ", text)  # 2. replace non-breaking spaces

    text = text.replace("\v", "\n").replace("\f", "\n")
    text = _CONTROL_CHAR_RE.sub("", text)  # 3. remove null/control characters
    text = _INVISIBLE_CHAR_RE.sub("", text)  # 10. remove invisible control characters

    text = _HORIZONTAL_WHITESPACE_RE.sub(" ", text)  # 4. collapse repeated spaces/tabs
    text = _TRAILING_LINE_WHITESPACE_RE.sub("\n", text)  # 5. remove spaces around line breaks
    text = _LEADING_LINE_WHITESPACE_RE.sub("\n", text)

    text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)  # 6/8. limit and control blank lines

    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", text)  # 9. normalize spaces around punctuation
    text = _SPACE_AFTER_OPEN_BRACKET_RE.sub(r"\1", text)

    return text.strip()  # 7. trim leading/trailing whitespace


def normalize_page(page: ExtractDocumentPage) -> NormalizedPage:
    text = normalize_text(page.text)
    return NormalizedPage(
        page_number=page.page_number,
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
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
