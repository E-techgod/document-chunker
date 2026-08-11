from document_chunker.heading_detector import detect_heading_level
from document_chunker.normalizer import _HORIZONTAL_WHITESPACE_RE, _preprocess_text
from document_chunker.schemas import ExtractedDocument
from document_chunker.structured_models import HeadingBlock, ParagraphBlock, StructuredNormalizedDocument

# Phase 2/3 of the Step 2 "Normalize + Preserve Structure" redesign: paragraph and
# heading reconstruction with baseline span calculation, built on Phase 1's
# structured_models. This is a separate, parallel pipeline from normalizer.py's existing
# normalize_page/normalize_document - it is not wired into chunker.py and does not touch
# the existing NormalizedDocument/NormalizedBlock (schemas.py) that pipeline depends on.
#
# List and table detection are still out of scope: every non-blank, non-heading line
# accumulates into a ParagraphBlock. A vertical-gap (Delta-Y) paragraph-boundary signal
# is part of the Step 2 design but has no implementation here, because the current
# Extractor (kept unchanged per the Phase 1 scoping decision) only provides plain
# per-page text - no spatial/coordinate metadata to compute a gap from.
#
# Heading detection runs line-by-line during the same pass that splits paragraphs,
# rather than only after chunking on blank lines: real single-column PDF extraction
# (verified against this repo's own sample PDFs) rarely inserts a blank line between a
# heading and the body text that follows it, so a heading almost never ends up as its
# own blank-line-bounded chunk. A line matching heading_detector.detect_heading_level
# closes out whatever paragraph was accumulating and starts its own HeadingBlock; a
# blank line closes out the current paragraph without starting a heading.


def _join_wrapped_lines(lines: list[str]) -> str:
    """Resolve visual line wraps across a paragraph's physical lines: join them with a
    single space, collapse internal multi-space/tab runs to one, and trim the ends."""
    joined = " ".join(line.strip() for line in lines if line.strip())
    return _HORIZONTAL_WHITESPACE_RE.sub(" ", joined).strip()


def _split_into_blocks(preprocessed_text: str) -> list[tuple[str, int | None]]:
    """Walk preprocessed page text line by line, producing (text, heading_level) entries
    in document order - heading_level is None for a paragraph. A blank line or a
    detected heading both flush whatever paragraph lines have accumulated so far."""
    entries: list[tuple[str, int | None]] = []
    buffer: list[str] = []

    def flush_paragraph() -> None:
        text = _join_wrapped_lines(buffer)
        if text:
            entries.append((text, None))
        buffer.clear()

    for raw_line in preprocessed_text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue

        level = detect_heading_level(line)
        if level is not None:
            flush_paragraph()
            entries.append((line, level))
            continue

        buffer.append(raw_line)

    flush_paragraph()
    return entries


def build_structured_document(document: ExtractedDocument) -> StructuredNormalizedDocument:
    """Reconstruct HeadingBlocks and ParagraphBlocks from raw per-page extractor text and
    assemble the canonical full_text, interleaved in document order. A page boundary
    always starts a new block - text is never joined across two pages, even mid-sentence,
    since page is a per-block field on NormalizedBlock (Phase 1) that would otherwise be
    ambiguous for a merged block.

    Spans are computed strictly after block text assembly: every block's final text is
    decided first, full_text is rendered by joining them with "\\n\\n", and only then are
    start_char/end_char derived from that same join structure (cumulative length, not a
    text search) - so a repeated block's offsets can never be misattributed to an
    earlier duplicate occurrence.
    """
    entries: list[tuple[int, str, int | None]] = []  # (page_number, text, heading_level)
    for page in document.pages:
        preprocessed = _preprocess_text(page.text)
        for text, level in _split_into_blocks(preprocessed):
            entries.append((page.page_number, text, level))

    full_text = "\n\n".join(text for _, text, _ in entries)

    blocks: list[HeadingBlock | ParagraphBlock] = []
    cursor = 0
    for index, (page_number, text, level) in enumerate(entries):
        start = cursor
        end = start + len(text)
        block_id = f"block_{index + 1:03d}"
        if level is not None:
            blocks.append(HeadingBlock(block_id=block_id, text=text, page=page_number, start_char=start, end_char=end, level=level))
        else:
            blocks.append(ParagraphBlock(block_id=block_id, text=text, page=page_number, start_char=start, end_char=end))
        cursor = end + 2  # skip the "\n\n" delimiter before the next block

    return StructuredNormalizedDocument(document_id=document.document_id, full_text=full_text, blocks=blocks)
