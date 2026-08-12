import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from document_chunker.extractor import extract_pdf
from document_chunker.loader import load_pdf
from document_chunker.paragraph_normalizer import build_structured_document
from document_chunker.schemas import ExtractedDocument, ExtractedPage, PDFDocumentInput
from document_chunker.step2_pipeline import normalize_document, validate_structured_document
from document_chunker.structured_models import (
    HeadingBlock,
    ListBlock,
    PageFooterBlock,
    ParagraphBlock,
    StructuredNormalizedDocument,
    TableBlock,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _extract(pdf_name: str) -> ExtractedDocument:
    document_input = PDFDocumentInput(path=DATA_DIR / pdf_name)
    reader = load_pdf(document_input)
    return extract_pdf(document_input, reader)


def _document(texts: list[str], document_id: str = "doc1") -> ExtractedDocument:
    pages = [ExtractedPage(page_number=i, text=text) for i, text in enumerate(texts, start=1)]
    return ExtractedDocument(
        document_id=document_id,
        file_name=f"{document_id}.pdf",
        file_path=f"/tmp/{document_id}.pdf",
        pages=pages,
        full_text="\n\n".join(texts),
    )


MULTI_PAGE_MIXED_DOCUMENT = _document(
    [
        "CHAPTER 01\n"
        "This is an opening paragraph with some\nwrapped content across lines.\n"
        "- First bullet item\n"
        "- Second bullet item that\n  wraps onto another line\n"
        "Week 5: A Real Heading\n"
        "Name  Role  Score\n"
        "Ana  Engineer  98\n"
        "Bob  Analyst  91\n",
        "STEP 2\n"
        "A closing paragraph on the second page\nthat also wraps across lines.\n",
    ]
)


# --- fixture sanity: the mixed document actually exercises every block type ---


def test_fixture_produces_all_four_block_types():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    kinds = {type(b) for b in structured.blocks}
    assert kinds == {HeadingBlock, ParagraphBlock, ListBlock, TableBlock}


# --- Invariant 1: non-empty content ---


def test_invariant_non_empty_content_holds_on_synthetic_document():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    assert all(b.text.strip() for b in structured.blocks)


def test_invariant_non_empty_content_detects_a_synthetic_violation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    structured.blocks[0].text = "   "
    issues = validate_structured_document(structured)
    assert any("empty" in issue for issue in issues)


# --- Invariant 2: monotonic order ---


def test_invariant_monotonic_order_holds_on_synthetic_document():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    for previous, current in zip(structured.blocks, structured.blocks[1:]):
        assert current.start_char >= previous.end_char


def test_invariant_monotonic_order_detects_a_synthetic_violation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    structured.blocks[1].start_char = structured.blocks[0].start_char
    issues = validate_structured_document(structured)
    assert any("start_char" in issue for issue in issues)


# --- Invariant 3: exact span equality ---


def test_invariant_span_equality_holds_on_synthetic_document():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    for block in structured.blocks:
        assert structured.full_text[block.start_char : block.end_char] == block.text


def test_invariant_span_equality_detects_a_synthetic_violation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    structured.blocks[0].end_char -= 1
    issues = validate_structured_document(structured)
    assert any("does not match" in issue for issue in issues)


# --- Invariant 4: lossless content integrity ---


def test_invariant_lossless_content_holds_on_synthetic_document():
    issues = validate_structured_document(
        build_structured_document(MULTI_PAGE_MIXED_DOCUMENT), source=MULTI_PAGE_MIXED_DOCUMENT
    )
    assert issues == []


def test_invariant_lossless_content_holds_on_sample_pdf():
    extracted = _extract("sample.pdf")
    structured = build_structured_document(extracted)
    issues = validate_structured_document(structured, source=extracted)
    assert issues == []


def test_invariant_lossless_content_detects_a_synthetic_violation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    structured.blocks[0].text = "completely different text"
    issues = validate_structured_document(structured, source=MULTI_PAGE_MIXED_DOCUMENT)
    assert any("content lost" in issue for issue in issues)


def test_invariant_lossless_content_ignores_stripped_list_markers():
    # Stripping "- " from a bullet is expected, not a loss - the words themselves must
    # still all be present.
    document = _document(["- Learn functions and scope\n- Work with lists and sets"])
    structured = build_structured_document(document)
    issues = validate_structured_document(structured, source=document)
    assert issues == []


def test_invariant_lossless_content_ignores_table_pipe_rendering():
    # TableBlock.text adds "|" separators that were never in the source - that must not
    # be flagged as "extra" content, and the check only cares about things going missing.
    document = _document(["Name  Role  Score\nAna  Engineer  98\nBob  Analyst  91"])
    structured = build_structured_document(document)
    issues = validate_structured_document(structured, source=document)
    assert issues == []


def test_noise_flagged_footer_is_emitted_separately_not_embedded_in_table_text():
    footer = "baswe.Ai Engineer Accelerator™ | Page 6"
    document = _document(
        [
            "STEP 1\n"
            "Step | Window | Hours\n"
            "1 | Week 1–2 | 5–10 hours total\n"
            f"{footer}\n"
            "Pull 10–15 real job descriptions.",
            "STEP 2\n"
            "Step | Window | Hours\n"
            "2 | Month 1–2 | 6–8 hrs/week\n"
            f"{footer}\n"
            "Build the mathematical foundation.",
            "STEP 3\n"
            "Step | Window | Hours\n"
            "3 | Months 3–4 | 8–10 hrs/week\n"
            f"{footer}\n"
            "Ship a portfolio project.",
        ],
        document_id="noise_table_boundary",
    )

    structured = build_structured_document(document)
    issues = validate_structured_document(structured, source=document)

    assert issues == []
    assert sum(isinstance(block, PageFooterBlock) for block in structured.blocks) == 3

    for block in structured.blocks:
        if not isinstance(block, TableBlock):
            continue
        assert footer not in block.text
        assert all(footer not in cell for row in [block.columns, *block.rows] for cell in row)


# --- Invariant 5: table rectangularity ---


def test_invariant_table_rectangularity_holds_on_synthetic_document():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    for block in structured.blocks:
        if isinstance(block, TableBlock) and block.columns:
            assert all(len(row) == len(block.columns) for row in block.rows)


def test_invariant_table_rectangularity_detects_a_synthetic_violation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    table = next(b for b in structured.blocks if isinstance(b, TableBlock))
    table.rows = [table.rows[0][:-1]]  # drop a cell, making this row too short
    issues = validate_structured_document(structured)
    assert any("cells, expected" in issue for issue in issues)


# --- Invariant 6: list non-emptiness ---


def test_invariant_list_non_emptiness_holds_on_synthetic_document():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    for block in structured.blocks:
        if isinstance(block, ListBlock):
            assert block.items
            assert all(item.strip() for item in block.items)


def test_invariant_list_non_emptiness_detects_a_synthetic_violation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    list_block = next(b for b in structured.blocks if isinstance(b, ListBlock))
    list_block.items = []
    issues = validate_structured_document(structured)
    assert any("zero items" in issue for issue in issues)


# --- Invariant 7: JSON debug inspection ---


def test_invariant_json_serialization_round_trips_without_mutation():
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)
    before = structured.model_copy(deep=True)

    payload = json.loads(structured.to_json())

    assert structured == before  # to_json() must not mutate the document
    assert payload["document_id"] == structured.document_id
    assert len(payload["blocks"]) == len(structured.blocks)


def test_invariant_json_serialization_holds_in_the_validator():
    issues = validate_structured_document(build_structured_document(MULTI_PAGE_MIXED_DOCUMENT))
    assert not any("serialize" in issue or "mutated" in issue for issue in issues)


def test_to_dict_requires_no_disk_io(tmp_path, monkeypatch):
    # Assert no file gets created anywhere as a side effect of inspection.
    monkeypatch.chdir(tmp_path)
    structured = build_structured_document(MULTI_PAGE_MIXED_DOCUMENT)

    structured.to_dict()
    structured.to_json()

    assert list(tmp_path.iterdir()) == []


# --- full pipeline entry point ---


def test_normalize_document_returns_a_validated_structured_document():
    structured = normalize_document(MULTI_PAGE_MIXED_DOCUMENT)
    assert isinstance(structured, StructuredNormalizedDocument)
    assert validate_structured_document(structured, source=MULTI_PAGE_MIXED_DOCUMENT) == []


def test_normalize_document_raises_with_all_violations_when_invalid(monkeypatch):
    import document_chunker.step2_pipeline as pipeline

    def _broken_build(document):
        structured = build_structured_document(document)
        structured.blocks[0].text = "   "
        return structured

    monkeypatch.setattr(pipeline, "build_structured_document", _broken_build)

    with pytest.raises(ValueError, match="empty"):
        pipeline.normalize_document(MULTI_PAGE_MIXED_DOCUMENT)


# --- golden row assertions (BAWSE dataset), re-verified through the full pipeline ---


def test_golden_rows_hold_through_the_full_validated_pipeline():
    extracted = _extract("BAWSE.pdf")
    structured = build_structured_document(extracted)

    top_industries = next(
        b for b in structured.blocks if isinstance(b, TableBlock) and any("Technology" in row[0] for row in b.rows)
    )
    technology_row = next(row for row in top_industries.rows if row[0] == "Technology")
    assert list(technology_row) == [
        "Technology",
        "46%",
        "Foundation models, search, recommendations, developer tools",
    ]
    manufacturing_row = next(row for row in top_industries.rows if "Manufacturing" in row[0])
    assert list(manufacturing_row) == [
        "Manufacturing / Auto",
        "6%",
        "Predictive maintenance, computer vision, supply chain",
    ]

    salary_table = next(
        b for b in structured.blocks if isinstance(b, TableBlock) and any("Junior" in row[0] for row in b.rows)
    )
    mid_level_row = next(row for row in salary_table.rows if "Mid-Level" in row[0])
    assert list(mid_level_row) == [
        "Mid-Level (3–5 yrs)",
        "$193,000",
        "$128K – $265K",
        "Sweet spot — highest volume of openings",
    ]


# --- full suite across real, complex documents ---


@pytest.mark.parametrize(
    "pdf_name",
    ["BAWSE.pdf", "generic.pdf", "invoice.pdf", "receipt.pdf", "report.pdf", "resume.pdf", "sample.pdf", "empty.pdf"],
)
def test_core_span_and_structural_invariants_hold_on_real_documents(pdf_name):
    """Invariants 1, 2, 3, 5, 6, 7 across the real fixture PDFs. Lossless-content
    (invariant 4) is verified separately where needed because it is source-aware."""
    if pdf_name == "empty.pdf":
        with pytest.raises(ValidationError, match="file is empty"):
            _extract(pdf_name)
        return

    extracted = _extract(pdf_name)
    structured = build_structured_document(extracted)

    issues = validate_structured_document(structured)  # no `source` - skips invariant 4
    assert issues == [], f"{pdf_name}: {issues}"


def test_pipe_separated_prose_is_no_longer_misdetected_as_a_table():
    """This used to document a known limitation: two unrelated pipe-separated lines on
    BAWSE.pdf page 1 were glued into a fake 2-row table. The 2-row coherence check now
    rejects that weakest-evidence case so the lines remain ordinary paragraph content."""
    extracted = _extract("BAWSE.pdf")
    structured = build_structured_document(extracted)

    issues = validate_structured_document(structured, source=extracted)
    assert issues == []

    paragraph_texts = [block.text for block in structured.blocks if isinstance(block, ParagraphBlock)]
    table_texts = [block.text for block in structured.blocks if isinstance(block, TableBlock)]

    assert any("Leverage Play" in text and "domain knowledge" in text for text in paragraph_texts)
    assert any("Updated June 2026" in text and "BASWE LLC" in text for text in paragraph_texts)
    assert all("Leverage Play | domain knowledge" not in text for text in table_texts)
    assert all("Updated June 2026 | baswe.Ai Engineer Accelerator™ | BASWE LLC" not in text for text in table_texts)
