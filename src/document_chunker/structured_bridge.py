from document_chunker.normalizer import _EXCESS_BLANK_LINES_RE, BlockEntry, _render_blocks
from document_chunker.schemas import ExtractedDocument
from document_chunker.schemas import NormalizedBlock as SchemaBlock
from document_chunker.schemas import NormalizedDocument, NormalizedPage, NormalizedTable
from document_chunker.structured_models import (
    AnyBlock,
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    StructuredNormalizedDocument,
    TableBlock,
)

# Bridges Step 2 (paragraph_normalizer.build_structured_document, noise-aware) into the
# NormalizedDocument shape chunker.py/evaluator.py already consume unchanged - those two
# modules were built against schemas.py's older, unrelated block shape and have no
# concept of is_noise. `structured_models.NormalizedBlock` and `schemas.NormalizedBlock`
# are two different classes with the same name (see structured_models.py's own docstring
# warning) - this module only ever imports the schemas one, aliased, to keep that
# unambiguous.

NORMALIZED_STRATEGY = "step2-structural-noise-filtered"


def _to_schema_block(block: AnyBlock) -> SchemaBlock:
    if isinstance(block, HeadingBlock):
        return SchemaBlock(block_type="heading", text=block.text)
    if isinstance(block, ParagraphBlock):
        return SchemaBlock(block_type="paragraph", text=block.text)
    if isinstance(block, ListBlock):
        return SchemaBlock(block_type="list", items=block.items)
    if isinstance(block, TableBlock):
        return SchemaBlock(block_type="table", table=NormalizedTable(header=block.columns, rows=block.rows))
    raise ValueError(f"unexpected block type in content_blocks: {block.type!r}")


def to_normalized_document(
    document: ExtractedDocument, structured: StructuredNormalizedDocument
) -> NormalizedDocument:
    """Convert Step 2's noise-filtered content_blocks into a NormalizedDocument the
    existing chunker/evaluator pipeline can consume unchanged. Page-local text and
    start_char/end_char are computed by normalizer._render_blocks - the same span logic
    normalize_page already uses, fed Step-2-sourced blocks instead of freshly
    line-classified ones. A page whose blocks were all noise (or a genuinely blank page)
    yields text="", blocks=[], matching normalize_page's existing blank-page handling.
    """
    blocks_by_page: dict[int, list[AnyBlock]] = {}
    for block in structured.content_blocks:
        blocks_by_page.setdefault(block.page, []).append(block)

    pages: list[NormalizedPage] = []
    for page in document.pages:
        page_blocks = blocks_by_page.get(page.page_number, [])
        entries = [
            BlockEntry(block=_to_schema_block(block), preceded_by_blank=False) for block in page_blocks
        ]
        text, positioned_blocks = _render_blocks(entries)
        pages.append(NormalizedPage(page_number=page.page_number, text=text, blocks=positioned_blocks))

    full_text = _EXCESS_BLANK_LINES_RE.sub("\n\n", "\n\n".join(page.text for page in pages))

    return NormalizedDocument(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        document_type=document.document_type,
        pages=pages,
        full_text=full_text,
        normalized_strategy=NORMALIZED_STRATEGY,
    )
