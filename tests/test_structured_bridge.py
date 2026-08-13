from pathlib import Path

import pytest

from src.document_chunker.chunking.chunker import chunk_document
from src.document_chunker.chunking.chunking_strategies import get_chunking_strategy
from src.document_chunker.chunking.evaluator import validate_chunks
from src.document_chunker.io.extractor import extract_pdf
from src.document_chunker.io.loader import load_pdf
from src.document_chunker.normalization.paragraph_normalizer import (
    build_structured_document,
)
from src.document_chunker.normalization.structured_bridge import to_normalized_document
from src.document_chunker.normalization.structured_models import (
    HeadingBlock,
    ListBlock,
    PageFooterBlock,
    PageHeaderBlock,
    ParagraphBlock,
    StructuredNormalizedDocument,
    TableBlock,
)
from src.document_chunker.schemas import (
    ChunkingConfig,
    ExtractedDocument,
    ExtractedPage,
    PDFDocumentInput,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _document(texts: list[str], document_id: str = "doc1") -> ExtractedDocument:
    pages = [
        ExtractedPage(page_number=i, text=text) for i, text in enumerate(texts, start=1)
    ]
    return ExtractedDocument(
        document_id=document_id,
        file_name=f"{document_id}.pdf",
        file_path=f"/tmp/{document_id}.pdf",
        pages=pages,
        full_text="\n\n".join(texts),
    )


def _extract(pdf_name: str) -> ExtractedDocument:
    document_input = PDFDocumentInput(path=DATA_DIR / pdf_name)
    reader = load_pdf(document_input)
    return extract_pdf(document_input, reader)


def _noisy_document() -> ExtractedDocument:
    ordinals = ["one", "two", "three"]
    texts = [
        f"Company Confidential\n"
        f"Unique subtitle {ordinal}\n"
        f"This is body content unique to page {ordinal} with real prose that should stay intact.\n"
        f"Page {n}"
        for n, ordinal in enumerate(ordinals, start=1)
    ]
    return _document(texts)


# --- noise exclusion ---


def test_noise_blocks_are_excluded_from_bridged_document():
    document = _noisy_document()
    structured = build_structured_document(document)

    normalized = to_normalized_document(document, structured)

    assert "Company Confidential" not in normalized.full_text
    assert "Page 1" not in normalized.full_text
    for page in normalized.pages:
        assert all(block.block_type != "page_header" for block in page.blocks)
        for block in page.blocks:
            assert block.block_type in {"heading", "paragraph", "list", "table"}


def test_content_text_is_preserved_in_bridged_document():
    document = _noisy_document()
    structured = build_structured_document(document)

    normalized = to_normalized_document(document, structured)

    assert "This is body content unique to page one" in normalized.full_text
    assert "This is body content unique to page two" in normalized.full_text
    assert "This is body content unique to page three" in normalized.full_text


def test_page_with_only_noise_becomes_empty_page():
    document = _document(["Company Confidential\nPage 1"] * 3)
    structured = build_structured_document(document)

    normalized = to_normalized_document(document, structured)

    for page in normalized.pages:
        assert page.text == ""
        assert page.blocks == []


def test_bridge_space_joins_mid_sentence_page_break_after_noise_filtering():
    document = _document(
        ["You will be a competitive candidate in 12", "months.\n\nSTEP 1"]
    )
    structured = build_structured_document(document)

    normalized = to_normalized_document(document, structured)

    assert (
        normalized.full_text
        == "You will be a competitive candidate in 12 months.\n\nSTEP 1"
    )


def test_bridge_keeps_double_newline_for_intentional_page_break():
    document = _document(
        ["This paragraph is complete.", "Another paragraph starts here."]
    )
    structured = build_structured_document(document)

    normalized = to_normalized_document(document, structured)

    assert (
        normalized.full_text
        == "This paragraph is complete.\n\nAnother paragraph starts here."
    )


# --- block-type mapping ---


def _sample_structured_document() -> (
    tuple[ExtractedDocument, StructuredNormalizedDocument]
):
    document = _document(["placeholder"])
    full_text = "Overview\nSome prose.\nfirst\nsecond\nName | Score\nAna | 98\nRunning Title\nPage 1"
    structured = StructuredNormalizedDocument(
        document_id=document.document_id,
        full_text=full_text,
        blocks=[
            HeadingBlock(
                block_id="block_001",
                text="Overview",
                page=1,
                start_char=0,
                end_char=8,
                level=1,
            ),
            ParagraphBlock(
                block_id="block_002",
                text="Some prose.",
                page=1,
                start_char=9,
                end_char=20,
            ),
            ListBlock(
                block_id="block_003",
                text="first\nsecond",
                page=1,
                start_char=21,
                end_char=33,
                items=["first", "second"],
            ),
            TableBlock(
                block_id="block_004",
                text="Name | Score\nAna | 98",
                page=1,
                start_char=34,
                end_char=56,
                columns=["Name", "Score"],
                rows=[["Ana", "98"]],
            ),
            PageHeaderBlock(
                block_id="block_005",
                text="Running Title",
                page=1,
                start_char=57,
                end_char=70,
            ),
            PageFooterBlock(
                block_id="block_006", text="Page 1", page=1, start_char=71, end_char=77
            ),
        ],
    )
    return document, structured


def test_each_content_block_type_maps_to_correct_schema_block():
    document, structured = _sample_structured_document()

    normalized = to_normalized_document(document, structured)

    blocks = normalized.pages[0].blocks
    assert [b.block_type for b in blocks] == ["heading", "paragraph", "list", "table"]
    assert blocks[0].text == "Overview"
    assert blocks[1].text == "Some prose."
    assert blocks[2].items == ["first", "second"]
    assert blocks[3].table.header == ["Name", "Score"]
    assert blocks[3].table.rows == [["Ana", "98"]]


# --- end-to-end regression: bridged document still chunks/validates cleanly ---


def test_chunk_document_and_validate_chunks_succeed_on_bridged_document():
    document = _noisy_document()
    structured = build_structured_document(document)
    normalized = to_normalized_document(document, structured)
    config = ChunkingConfig(
        max_chunk_size=1000,
        overlap_size=0,
        chunking_strategy="structural",
        propagate_context=True,
    )

    result = chunk_document(normalized, config=config)
    report = validate_chunks(normalized, result, config)

    assert report.is_valid, report.issues


@pytest.mark.parametrize("pdf_name", ["sample.pdf", "BAWSE.pdf"])
def test_full_bridge_pipeline_validates_cleanly_on_real_documents(pdf_name):
    # Uses build_structured_document directly (not step2_pipeline.normalize_document's
    # raising wrapper): BAWSE.pdf has one known, pre-existing Step 2 limitation unrelated
    # to noise detection or this bridge (see
    # test_known_limitation_pipe_separated_labels_can_misdetect_as_a_table in
    # test_normalizer_validation.py) - what this test regresses on is the bridge +
    # chunking/validation layer, already covered independently for Step 2 itself.
    extracted = _extract(pdf_name)
    structured = build_structured_document(extracted)
    normalized = to_normalized_document(extracted, structured)
    _, config = get_chunking_strategy("v2.2")

    result = chunk_document(normalized, config=config)
    report = validate_chunks(normalized, result, config)

    assert report.is_valid, report.issues
