import re

from document_chunker.normalizer import _HORIZONTAL_WHITESPACE_RE, _preprocess_text
from document_chunker.schemas import ExtractedDocument
from document_chunker.structured_models import ParagraphBlock, StructuredNormalizedDocument

# Phase 2 of the Step 2 "Normalize + Preserve Structure" redesign: paragraph
# reconstruction and baseline span calculation, built on Phase 1's structured_models.
# This is a separate, parallel pipeline from normalizer.py's existing
# normalize_page/normalize_document - it is not wired into chunker.py and does not touch
# the existing NormalizedDocument/NormalizedBlock (schemas.py) that pipeline depends on.
#
# Heading, list, and table detection are out of scope here: every non-blank run of text
# becomes a ParagraphBlock. A vertical-gap (Delta-Y) paragraph-boundary signal is part of
# the Step 2 design but has no implementation here, because the current Extractor (kept
# unchanged per the Phase 1 scoping decision) only provides plain per-page text - no
# spatial/coordinate metadata to compute a gap from. Blank-line runs and page boundaries
# are the two signals actually available and implemented.

_PARAGRAPH_BREAK_RE = re.compile(r"\n{2,}")


def _split_into_paragraph_chunks(preprocessed_text: str) -> list[str]:
    """Split already-preprocessed page text on any run of 2+ consecutive newlines (blank
    lines) - one of the two paragraph-boundary signals available without coordinate data."""
    return [chunk for chunk in _PARAGRAPH_BREAK_RE.split(preprocessed_text) if chunk.strip()]


def _join_wrapped_lines(chunk: str) -> str:
    """Resolve visual line wraps within one paragraph chunk: join its physical lines with
    a single space, collapse internal multi-space/tab runs to one, and trim the ends."""
    lines = [line.strip() for line in chunk.split("\n") if line.strip()]
    joined = " ".join(lines)
    return _HORIZONTAL_WHITESPACE_RE.sub(" ", joined).strip()


def build_structured_document(document: ExtractedDocument) -> StructuredNormalizedDocument:
    """Reconstruct ParagraphBlocks from raw per-page extractor text and assemble the
    canonical full_text. A page boundary always starts a new paragraph - text is never
    joined across two pages, even mid-sentence, since page is a per-block field on
    NormalizedBlock (Phase 1) that would otherwise be ambiguous for a merged paragraph.

    Spans are computed strictly after paragraph text assembly: every paragraph's final
    text is decided first, full_text is rendered by joining them with "\\n\\n", and only
    then are start_char/end_char derived from that same join structure (cumulative
    length, not a text search) - so a repeated paragraph's offsets can never be
    misattributed to an earlier duplicate occurrence.
    """
    paragraphs: list[tuple[int, str]] = []
    for page in document.pages:
        preprocessed = _preprocess_text(page.text)
        for chunk in _split_into_paragraph_chunks(preprocessed):
            text = _join_wrapped_lines(chunk)
            if text:
                paragraphs.append((page.page_number, text))

    full_text = "\n\n".join(text for _, text in paragraphs)

    blocks: list[ParagraphBlock] = []
    cursor = 0
    for index, (page_number, text) in enumerate(paragraphs):
        start = cursor
        end = start + len(text)
        blocks.append(
            ParagraphBlock(
                block_id=f"block_{index + 1:03d}",
                text=text,
                page=page_number,
                start_char=start,
                end_char=end,
            )
        )
        cursor = end + 2  # skip the "\n\n" delimiter before the next block

    return StructuredNormalizedDocument(document_id=document.document_id, full_text=full_text, blocks=blocks)
