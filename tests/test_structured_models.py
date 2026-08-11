import json

import pytest
from pydantic import ValidationError

from document_chunker.structured_models import (
    HeadingBlock,
    ListBlock,
    PageFooterBlock,
    PageHeaderBlock,
    ParagraphBlock,
    StructuredNormalizedDocument,
    TableBlock,
)


# --- block instantiation ---


def test_heading_block_defaults_type_and_accepts_level():
    block = HeadingBlock(block_id="block_001", text="Overview", page=1, start_char=0, end_char=8, level=2)

    assert block.type == "heading"
    assert block.level == 2


def test_heading_block_level_is_optional():
    block = HeadingBlock(block_id="block_001", text="Overview", page=1, start_char=0, end_char=8)

    assert block.level is None


def test_paragraph_block_defaults_type():
    block = ParagraphBlock(block_id="block_002", text="Some prose.", page=1, start_char=9, end_char=20)

    assert block.type == "paragraph"


def test_list_block_holds_items():
    block = ListBlock(
        block_id="block_003",
        text="first\nsecond",
        page=1,
        start_char=0,
        end_char=12,
        items=["first", "second"],
    )

    assert block.type == "list"
    assert block.items == ["first", "second"]


def test_table_block_holds_columns_and_rows():
    block = TableBlock(
        block_id="block_004",
        text="Name | Score\nAna | 98",
        page=1,
        start_char=0,
        end_char=22,
        title="Scores",
        columns=["Name", "Score"],
        rows=[["Ana", "98"]],
    )

    assert block.type == "table"
    assert block.title == "Scores"
    assert block.columns == ["Name", "Score"]
    assert block.rows == [["Ana", "98"]]


def test_table_block_is_rectangular_true_when_rows_match_columns():
    block = TableBlock(
        block_id="block_004",
        text="",
        page=1,
        start_char=0,
        end_char=0,
        columns=["Name", "Score"],
        rows=[["Ana", "98"], ["Bob", "91"]],
    )

    assert block.is_rectangular is True


def test_table_block_is_rectangular_false_for_ragged_rows():
    # Real-world tables are often ragged (see TableNormalizer) - this must not raise.
    block = TableBlock(
        block_id="block_004",
        text="",
        page=1,
        start_char=0,
        end_char=0,
        columns=["Name", "Role", "Score"],
        rows=[["Ana", "Engineer", "98"], ["Bob", "Analyst"]],
    )

    assert block.is_rectangular is False
    assert block.rows == [["Ana", "Engineer", "98"], ["Bob", "Analyst"]]


def test_block_requires_page_at_least_one():
    with pytest.raises(ValidationError):
        HeadingBlock(block_id="block_001", text="Overview", page=0, start_char=0, end_char=8)


# --- noise blocks (page headers/footers) ---


def test_content_block_types_default_is_noise_false():
    heading = HeadingBlock(block_id="block_001", text="Overview", page=1, start_char=0, end_char=8)
    paragraph = ParagraphBlock(block_id="block_002", text="Some prose.", page=1, start_char=9, end_char=20)

    assert heading.is_noise is False
    assert paragraph.is_noise is False


def test_page_header_block_defaults_type_and_is_noise():
    block = PageHeaderBlock(block_id="block_001", text="Running Title", page=1, start_char=0, end_char=13)

    assert block.type == "page_header"
    assert block.is_noise is True


def test_page_footer_block_defaults_type_and_is_noise():
    block = PageFooterBlock(block_id="block_001", text="Page 3", page=1, start_char=0, end_char=6)

    assert block.type == "page_footer"
    assert block.is_noise is True


def test_is_noise_can_be_overridden_explicitly():
    block = ParagraphBlock(block_id="block_001", text="Confidential", page=1, start_char=0, end_char=12, is_noise=True)

    assert block.is_noise is True


# --- container model / polymorphism ---


def _sample_document() -> StructuredNormalizedDocument:
    full_text = "Overview\nSome prose.\nfirst\nsecond\nName | Score\nAna | 98"
    return StructuredNormalizedDocument(
        document_id="doc1",
        full_text=full_text,
        blocks=[
            HeadingBlock(block_id="block_001", text="Overview", page=1, start_char=0, end_char=8, level=1),
            ParagraphBlock(block_id="block_002", text="Some prose.", page=1, start_char=9, end_char=20),
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
        ],
    )


def _sample_document_with_noise() -> StructuredNormalizedDocument:
    full_text = "Running Title\nOverview\nSome prose.\nPage 1"
    return StructuredNormalizedDocument(
        document_id="doc1",
        full_text=full_text,
        blocks=[
            PageHeaderBlock(block_id="block_001", text="Running Title", page=1, start_char=0, end_char=13),
            HeadingBlock(block_id="block_002", text="Overview", page=1, start_char=14, end_char=22, level=1),
            ParagraphBlock(block_id="block_003", text="Some prose.", page=1, start_char=23, end_char=34),
            PageFooterBlock(block_id="block_004", text="Page 1", page=1, start_char=35, end_char=41),
        ],
    )


def test_content_blocks_excludes_noise_blocks():
    document = _sample_document_with_noise()

    assert [b.block_id for b in document.content_blocks] == ["block_002", "block_003"]


def test_content_blocks_is_all_blocks_when_no_noise_present():
    document = _sample_document()

    assert document.content_blocks == document.blocks


def test_document_holds_polymorphic_block_list_in_order():
    document = _sample_document()

    assert [type(b).__name__ for b in document.blocks] == [
        "HeadingBlock",
        "ParagraphBlock",
        "ListBlock",
        "TableBlock",
    ]


def test_document_rejects_duplicate_block_ids():
    with pytest.raises(ValidationError, match="duplicate block_id"):
        StructuredNormalizedDocument(
            document_id="doc1",
            full_text="AB",
            blocks=[
                ParagraphBlock(block_id="block_001", text="A", page=1, start_char=0, end_char=1),
                ParagraphBlock(block_id="block_001", text="B", page=1, start_char=1, end_char=2),
            ],
        )


# --- serialization ---


def test_to_dict_round_trips_through_model_validate():
    document = _sample_document()

    restored = StructuredNormalizedDocument.model_validate(document.to_dict())

    assert restored == document


def test_to_json_produces_valid_json_with_discriminated_block_types():
    document = _sample_document()

    payload = json.loads(document.to_json())

    assert payload["document_id"] == "doc1"
    assert [b["type"] for b in payload["blocks"]] == ["heading", "paragraph", "list", "table"]


def test_document_model_validate_reconstructs_correct_block_subclasses_from_dict():
    document = _sample_document()
    payload = document.to_dict()

    restored = StructuredNormalizedDocument.model_validate(payload)

    assert isinstance(restored.blocks[0], HeadingBlock)
    assert isinstance(restored.blocks[1], ParagraphBlock)
    assert isinstance(restored.blocks[2], ListBlock)
    assert isinstance(restored.blocks[3], TableBlock)
    assert restored.blocks[0].level == 1
    assert restored.blocks[2].items == ["first", "second"]
    assert restored.blocks[3].rows == [["Ana", "98"]]


def test_noise_blocks_round_trip_through_to_dict_and_model_validate():
    document = _sample_document_with_noise()

    restored = StructuredNormalizedDocument.model_validate(document.to_dict())

    assert restored == document
    assert isinstance(restored.blocks[0], PageHeaderBlock)
    assert isinstance(restored.blocks[3], PageFooterBlock)
    assert restored.blocks[0].is_noise is True
    assert restored.blocks[3].is_noise is True


# --- span invariant validator ---


def test_validate_spans_returns_no_issues_for_correct_offsets():
    document = _sample_document()

    assert document.validate_spans() == []
    document.assert_spans_valid()  # must not raise


def test_validate_spans_reports_mismatched_block():
    document = StructuredNormalizedDocument(
        document_id="doc1",
        full_text="Overview\nSome prose.",
        blocks=[
            HeadingBlock(block_id="block_001", text="Overview", page=1, start_char=0, end_char=8),
            # Wrong offsets: full_text[9:13] is "Some", not "Some prose."
            ParagraphBlock(block_id="block_002", text="Some prose.", page=1, start_char=9, end_char=13),
        ],
    )

    issues = document.validate_spans()

    assert len(issues) == 1
    assert "block_002" in issues[0]


def test_assert_spans_valid_raises_when_a_span_is_wrong():
    document = StructuredNormalizedDocument(
        document_id="doc1",
        full_text="Overview",
        blocks=[
            HeadingBlock(block_id="block_001", text="wrong text", page=1, start_char=0, end_char=8),
        ],
    )

    with pytest.raises(AssertionError, match="block_001"):
        document.assert_spans_valid()
