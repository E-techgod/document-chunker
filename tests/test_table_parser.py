from pathlib import Path

from document_chunker.extractor import extract_pdf
from document_chunker.loader import load_pdf
from document_chunker.paragraph_normalizer import build_structured_document
from document_chunker.schemas import PDFDocumentInput
from document_chunker.structured_models import TableBlock
from document_chunker.table_parser import is_table_row_candidate, parse_table_region

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _extract(pdf_name: str):
    document_input = PDFDocumentInput(path=DATA_DIR / pdf_name)
    reader = load_pdf(document_input)
    return extract_pdf(document_input, reader)


# --- is_table_row_candidate ---


def test_pipe_separated_line_is_a_table_row_candidate():
    assert is_table_row_candidate("Name | Role | Score") is True


def test_wide_gap_separated_line_is_a_table_row_candidate():
    assert is_table_row_candidate("Name    Role    Score") is True


def test_plain_sentence_is_not_a_table_row_candidate():
    assert is_table_row_candidate("This is a normal sentence with no columns.") is False


# --- parse_table_region: basic reconstruction ---


def test_simple_table_reconstructs_columns_and_rows():
    lines = ["Name  Role  Score", "Ana  Engineer  98", "Bob  Analyst  91"]

    result, consumed = parse_table_region(lines, 0)

    assert result is not None
    columns, rows, text = result
    assert columns == ["Name", "Role", "Score"]
    assert rows == [["Ana", "Engineer", "98"], ["Bob", "Analyst", "91"]]
    assert consumed == 3


def test_table_text_renders_as_pipe_separated_markdown_like_string():
    lines = ["Name  Role  Score", "Ana  Engineer  98"]

    result, _ = parse_table_region(lines, 0)

    _, _, text = result
    assert text == "Name | Role | Score\nAna | Engineer | 98"


def test_non_table_region_returns_none():
    lines = ["Just a normal sentence."]

    result, consumed = parse_table_region(lines, 0)

    assert result is None
    assert consumed == 0


# --- row rectangularity (Phase 5 requirement) ---


def test_short_row_is_padded_with_empty_strings():
    lines = ["Name  Role  Score", "Ana  Engineer  98", "Bob  Analyst"]

    result, _ = parse_table_region(lines, 0)

    columns, rows, _ = result
    assert all(len(row) == len(columns) for row in rows)
    assert rows[1] == ["Bob", "Analyst", ""]


def test_overlong_row_folds_extra_cells_into_the_last_column_without_losing_data():
    # A numeric cell in a comparable body row is what makes "Name  Role" register as a
    # real header (see normalizer._looks_like_header_row) - otherwise the table comes
    # back headerless and there's no target column count to rectangularize against.
    lines = ["Name  Role", "Ana  Engineer  Remote", "Bob  Analyst  55"]

    result, _ = parse_table_region(lines, 0)

    columns, rows, _ = result
    assert columns == ["Name", "Role"]
    assert all(len(row) == len(columns) for row in rows)
    assert rows[0] == ["Ana", "Engineer Remote"]


# --- Golden Row Assertions against real BAWSE.pdf tables ---


def test_golden_rows_top_industries_table():
    extracted = _extract("BAWSE.pdf")
    structured = build_structured_document(extracted)
    table = next(
        b for b in structured.blocks if isinstance(b, TableBlock) and any("Technology" in row[0] for row in b.rows)
    )

    technology_row = next(row for row in table.rows if row[0] == "Technology")
    assert list(technology_row) == [
        "Technology",
        "46%",
        "Foundation models, search, recommendations, developer tools",
    ]
    manufacturing_row = next(row for row in table.rows if "Manufacturing" in row[0])
    assert list(manufacturing_row) == [
        "Manufacturing / Auto",
        "6%",
        "Predictive maintenance, computer vision, supply chain",
    ]


def test_golden_row_salary_snapshot_table():
    extracted = _extract("BAWSE.pdf")
    structured = build_structured_document(extracted)
    table = next(
        b for b in structured.blocks if isinstance(b, TableBlock) and any("Junior" in row[0] for row in b.rows)
    )

    mid_level_row = next(row for row in table.rows if "Mid-Level" in row[0])
    assert list(mid_level_row) == [
        "Mid-Level (3–5 yrs)",
        "$193,000",
        "$128K – $265K",
        "Sweet spot — highest volume of openings",
    ]


def test_all_rows_rectangular_in_real_tables():
    for pdf_name in ["sample.pdf", "BAWSE.pdf"]:
        extracted = _extract(pdf_name)
        structured = build_structured_document(extracted)
        for block in structured.blocks:
            if isinstance(block, TableBlock) and block.columns:
                assert all(len(row) == len(block.columns) for row in block.rows), pdf_name


# --- span integrity and document ordering ---


def test_span_invariant_holds_for_table_blocks_in_real_documents():
    for pdf_name in ["sample.pdf", "BAWSE.pdf"]:
        extracted = _extract(pdf_name)
        structured = build_structured_document(extracted)
        assert structured.validate_spans() == [], pdf_name
        structured.assert_spans_valid()


def test_table_block_sits_between_surrounding_heading_and_paragraph():
    from document_chunker.schemas import ExtractedDocument, ExtractedPage

    text = "STEP 1\nName  Role  Score\nAna  Engineer  98\n\nClosing paragraph text."
    document = ExtractedDocument(
        document_id="doc1",
        file_name="doc1.pdf",
        file_path="/tmp/doc1.pdf",
        pages=[ExtractedPage(page_number=1, text=text)],
        full_text=text,
    )

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == ["HeadingBlock", "TableBlock", "ParagraphBlock"]
    for previous, current in zip(structured.blocks, structured.blocks[1:]):
        assert current.start_char >= previous.end_char
