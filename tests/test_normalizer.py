from document_chunker.counting import count_words
from document_chunker.normalizer import (
    DEFAULT_NORMALIZATION_STRATEGY,
    normalize_document,
    normalize_page,
    normalize_text,
    repair_line_wraps
)
from document_chunker.schemas import ExtractedPage, NormalizedDocument, NormalizedPage


# --- normalize_text: one test per rule ---
def test_repairs_wrapped_sentence() -> None:
    text = "Engineers —\nnot\nresearchers,\nnot\nML\nPhDs."
    assert repair_line_wraps(text) == (
        "Engineers — not researchers, not ML PhDs."
    )


def test_preserves_paragraph_break() -> None:
    text = "First paragraph.\n\nSecond paragraph."
    assert repair_line_wraps(text) == text


def test_preserves_bullet_boundary() -> None:
    text = "The philosophy:\n● Engineering first"
    assert repair_line_wraps(text) == text


def test_preserves_numbered_item() -> None:
    text = "Steps:\n1. Load the PDF"
    assert repair_line_wraps(text) == text


def test_attaches_indented_continuation_lines_to_list_items() -> None:
    text = (
        "Key Actions:\n"
        "● Keep blank lines\n"
        "  when preserving paragraph breaks.\n"
        "1. Preserve list items\n"
        "   across wrapped PDF lines.\n"
    )
    expected = (
        "Key Actions:\n"
        "● Keep blank lines when preserving paragraph breaks.\n"
        "1. Preserve list items across wrapped PDF lines."
    )
    assert repair_line_wraps(text) == expected


def test_attaches_indented_continuation_lines_to_numbered_list_items() -> None:
    text = (
        "1. Watching tutorials without building...\n"
        "    on GitHub, you didn't do that week.\n"
    )
    expected = "1. Watching tutorials without building... on GitHub, you didn't do that week."
    assert repair_line_wraps(text) == expected


def test_stops_list_continuations_at_structural_boundaries() -> None:
    text = (
        "● First item\n"
        "  continuation text\n"
        "Next Section:\n"
        "Paragraph line\n"
    )
    expected = "● First item continuation text\n\nNext Section:\nParagraph line"
    assert repair_line_wraps(text) == expected


def test_normalization_is_idempotent() -> None:
    text = "Engineers —\nnot\nresearchers."
    normalized = normalize_text(text)

    assert normalize_text(normalized) == normalized

def test_normalizes_line_endings():
    assert normalize_text("a\r\nb\rc") == "a b c"


def test_replaces_non_breaking_spaces():
    assert normalize_text("a\xa0b c　d") == "a b c d"


def test_removes_null_and_control_characters():
    assert normalize_text("a\x00b\x1fc\x7fd") == "abcd"


def test_vertical_tab_and_form_feed_become_newlines():
    assert normalize_text("a\vb\fc") == "a b c"


def test_collapses_repeated_spaces_and_tabs():
    assert normalize_text("a    b\t\tc") == "a b c"


def test_removes_spaces_around_line_breaks():
    assert normalize_text("a   \n   b") == "a b"


def test_limits_excessive_blank_lines():
    assert normalize_text("a\n\n\n\n\nb") == "a\n\nb"


def test_trims_leading_and_trailing_whitespace():
    assert normalize_text("   a b   ") == "a b"
    assert normalize_text("\n\na b\n\n") == "a b"


def test_normalizes_spaces_around_isolated_punctuation():
    assert normalize_text("word , word ; word : word ! word ? word .") == (
        "word, word; word: word! word? word."
    )


def test_normalizes_space_around_brackets():
    assert normalize_text("( word ) and [ word ] and { word }") == (
        "(word) and [word] and {word}"
    )


def test_removes_invisible_control_characters():
    assert normalize_text("a​b‌c﻿d­e") == "abcde"


def test_normalize_text_empty_string_returns_empty():
    assert normalize_text("") == ""


def test_normalize_text_whitespace_only_returns_empty():
    assert normalize_text("   \n\t\n   ") == ""


def test_normalize_text_full_pipeline_combined():
    messy = (
        "  Hello World  \r\n"
        "This\x00 is​ a    test  \r\n"
        "\n\n\n\n"
        "Value , here ; and ( spaced )  \r\n"
        "   \n"
        "End.  "
    )
    expected = "Hello World\nThis is a test\n\nValue, here; and (spaced)\n\nEnd."
    assert normalize_text(messy) == expected


def test_repairs_hard_wrapped_lines_within_a_paragraph():
    wrapped = (
        "Who this is for: Students with no prior coding experience who want to become job-ready AI\n"
        "Engineers — \n"
        "not\n"
        "researchers,\n"
        "not\n"
        "ML\n"
        "PhDs.\n"
        "The people building real LLM-powered\n"
        "products that companies actually pay for."
    )
    expected = (
        "Who this is for: Students with no prior coding experience who want to become job-ready AI "
        "Engineers — not researchers, not ML PhDs.\n\nThe people building real LLM-powered "
        "products that companies actually pay for."
    )
    assert normalize_text(wrapped) == expected


def test_preserves_blank_line_paragraph_breaks_while_repairing_wraps():
    text = "First paragraph wraps\nacross two lines.\n\nSecond paragraph also\nwraps here."
    expected = "First paragraph wraps across two lines.\n\nSecond paragraph also wraps here."
    assert normalize_text(text) == expected


def test_preserves_blank_line_between_heading_and_paragraph() -> None:
    text = "Few-Shot Example\n\nParagraph line\ncontinues here."
    expected = "Few-Shot Example\n\nParagraph line continues here."
    assert normalize_text(text) == expected


def test_does_not_promote_title_cased_clause_to_heading() -> None:
    text = "Who This Is For\ncontinues on the next line."
    expected = "Who This Is For continues on the next line."
    assert normalize_text(text) == expected


def test_does_not_join_short_standalone_line_with_title_cased_following_line() -> None:
    text = "Overview\nImplementation Notes"
    expected = "Overview\n\nImplementation Notes"
    assert normalize_text(text) == expected


def test_joins_when_following_line_is_indented_continuation() -> None:
    text = "This paragraph introduces the main idea\n    with supporting detail from the next wrapped line."
    expected = "This paragraph introduces the main idea with supporting detail from the next wrapped line."
    assert normalize_text(text) == expected


def test_joins_when_current_line_ends_with_conjunction() -> None:
    text = "The workflow handles extraction and\nvalidation before indexing."
    expected = "The workflow handles extraction and validation before indexing."
    assert normalize_text(text) == expected


# --- normalize_page ---


def test_normalize_page_recalculates_counts():
    page = ExtractedPage(page_number=1, text="  a    b  ")
    normalized = normalize_page(page)
    assert normalized.text == "a b"
    assert normalized.word_count == 2
    assert normalized.char_count == 3
    assert normalized.blocks[0].block_type == "paragraph"


def test_normalize_page_block_offsets_locate_block_text_within_page_text():
    page = ExtractedPage(page_number=1, text="TITLE:\n\nSome paragraph text here.")
    normalized = normalize_page(page)

    assert [b.block_type for b in normalized.blocks] == ["heading", "paragraph"]
    for block in normalized.blocks:
        assert normalized.text[block.start_char : block.end_char] == block.text


def test_normalize_page_block_offsets_span_list_items_in_order():
    page = ExtractedPage(page_number=1, text="- first item\n- second item")
    normalized = normalize_page(page)

    list_block = normalized.blocks[0]
    assert list_block.block_type == "list"
    assert normalized.text[list_block.start_char : list_block.end_char] == "\n".join(list_block.items)


def test_normalize_page_preserves_page_number():
    page = ExtractedPage(page_number=7, text="text")
    normalized = normalize_page(page)
    assert normalized.page_number == 7


def test_normalize_page_blank_page_stays_empty():
    page = ExtractedPage(page_number=2, text="")
    normalized = normalize_page(page)
    assert normalized.text == ""
    assert normalized.word_count == 0
    assert normalized.char_count == 0


def test_normalize_page_control_char_only_page_becomes_empty():
    page = ExtractedPage(page_number=1, text="\x00\x1f  \n  ")
    normalized = normalize_page(page)
    assert normalized.text == ""
    assert normalized.word_count == 0
    assert normalized.char_count == 0


# --- normalize_document ---


def test_normalize_document_preserves_page_boundaries(make_extract_document):
    document = make_extract_document(["  page one  ", "  page two  ", "  page three  "])
    normalized = normalize_document(document)

    assert normalized.page_count == 3
    assert [p.page_number for p in normalized.pages] == [1, 2, 3]
    assert [p.text for p in normalized.pages] == ["page one", "page two", "page three"]


def test_normalize_document_normalizes_each_page_independently(make_extract_document):
    document = make_extract_document(["a\r\nb", "c\x00d"])
    normalized = normalize_document(document)

    assert normalized.pages[0].text == "a b"
    assert normalized.pages[1].text == "cd"


def test_normalize_document_combines_pages_into_full_text(make_extract_document):
    document = make_extract_document(["page one", "page two"])
    normalized = normalize_document(document)

    assert normalized.full_text == "page one\n\npage two"


def test_normalize_document_collapses_blank_line_run_from_blank_page_join(make_extract_document):
    document = make_extract_document(["page one", "", "page three"])
    normalized = normalize_document(document)

    # "\n\n" + "" + "\n\n" would otherwise leave 4 consecutive newlines in full_text.
    assert normalized.full_text == "page one\n\npage three"
    assert normalized.page_count == 3
    assert normalized.pages[1].text == ""


def test_normalize_document_recalculates_word_and_char_counts(make_extract_document):
    document = make_extract_document(["hello   world", "foo   bar   baz"])
    normalized = normalize_document(document)

    assert normalized.pages[0].word_count == 2
    assert normalized.pages[1].word_count == 3
    assert normalized.word_count == 5
    assert normalized.char_count == len(normalized.full_text)


def test_normalize_document_preserves_input_metadata(make_extract_document):
    document = make_extract_document(
        ["some text"],
        document_id="doc-42",
        file_name="report.pdf",
        file_path="/data/report.pdf",
        document_type="report",
    )
    normalized = normalize_document(document)

    assert normalized.document_id == "doc-42"
    assert normalized.file_name == "report.pdf"
    assert str(normalized.file_path) == "/data/report.pdf"
    assert normalized.document_type == "report"


def test_normalize_document_default_strategy_is_conservative(make_extract_document):
    document = make_extract_document(["some text"])
    normalized = normalize_document(document)

    assert normalized.normalized_strategy == DEFAULT_NORMALIZATION_STRATEGY
    assert normalized.normalized_strategy == "structural"


def test_normalize_document_custom_strategy_override(make_extract_document):
    document = make_extract_document(["some text"])
    normalized = normalize_document(document, strategy="aggressive")

    assert normalized.normalized_strategy == "aggressive"


def test_preserves_heading_paragraph_list_and_soft_wrap_boundaries() -> None:
    text = (
        "Executive Summary\n"
        "This document explains\n"
        "the pipeline behavior.\n"
        "\n"
        "Key Actions:\n"
        "● Keep blank lines\n"
        "1. Preserve list items\n"
    )
    expected = (
        "Executive Summary\n"
        "This document explains the pipeline behavior.\n\n"
        "Key Actions:\n"
        "● Keep blank lines\n1. Preserve list items"
    )
    assert normalize_text(text) == expected


def test_preserves_page_local_processing_for_wrapped_lines(make_extract_document) -> None:
    document = make_extract_document(
        [
            "Page One Heading\nWrapped line\ncontinues here",
            "Page Two Heading\nAnother line\ncontinues there",
        ]
    )

    normalized = normalize_document(document)

    assert normalized.pages[0].text == "Page One Heading\nWrapped line continues here"
    assert normalized.pages[1].text == "Page Two Heading\nAnother line continues there"
    assert normalized.full_text == (
        "Page One Heading\nWrapped line continues here\n\n"
        "Page Two Heading\nAnother line continues there"
    )


def test_builds_structural_table_representation() -> None:
    page = ExtractedPage(
        page_number=1,
        text="Name  Role  Score\nAna  Engineer  98\nBob  Analyst  91",
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == ["Name", "Role", "Score"]
    assert normalized.blocks[0].table.rows == [
        ["Ana", "Engineer", "98"],
        ["Bob", "Analyst", "91"],
    ]
    assert normalized.text == "Name | Role | Score\nAna | Engineer | 98\nBob | Analyst | 91"


def test_builds_headerless_structural_table_representation() -> None:
    page = ExtractedPage(
        page_number=1,
        text="Ana  Engineer  98\nBob  Analyst  91",
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == []
    assert normalized.blocks[0].table.rows == [
        ["Ana", "Engineer", "98"],
        ["Bob", "Analyst", "91"],
    ]
    assert normalized.text == "Ana | Engineer | 98\nBob | Analyst | 91"


def test_builds_table_when_rows_are_indented() -> None:
    page = ExtractedPage(
        page_number=1,
        text="  Name  Role  Score\n    Ana  Engineer  98\n  Bob  Analyst  91",
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == ["Name", "Role", "Score"]
    assert normalized.blocks[0].table.rows == [
        ["Ana", "Engineer", "98"],
        ["Bob", "Analyst", "91"],
    ]


def test_builds_table_when_a_row_uses_single_space_column_gaps() -> None:
    page = ExtractedPage(
        page_number=1,
        text="Name  Role  Score\nAna Engineer 98\nBob  Analyst  91",
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == ["Name", "Role", "Score"]
    assert normalized.blocks[0].table.rows == [
        ["Ana", "Engineer", "98"],
        ["Bob", "Analyst", "91"],
    ]


def test_preserves_table_with_variable_column_counts() -> None:
    page = ExtractedPage(
        page_number=1,
        text="Name  Role\nAna  Engineer  Remote\nBob  Analyst",
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == []
    assert normalized.blocks[0].table.rows == [
        ["Name", "Role"],
        ["Ana", "Engineer", "Remote"],
        ["Bob", "Analyst"],
    ]


def test_appends_wrapped_table_line_to_previous_row() -> None:
    page = ExtractedPage(
        page_number=1,
        text=(
            "Item  Description  Amount\n"
            "Widget  Starter package  25\n"
            "with setup assistance\n"
            "Gadget  Renewal  30"
        ),
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == ["Item", "Description", "Amount"]
    assert normalized.blocks[0].table.rows == [
        ["Widget", "Starter package with setup assistance", "25"],
        ["Gadget", "Renewal", "30"],
    ]


def test_stops_table_before_following_paragraph_line() -> None:
    page = ExtractedPage(
        page_number=1,
        text=(
            "Item  Description  Amount\n"
            "Widget  Starter package  25\n"
            "Gadget  Renewal  30\n"
            "The renewal note belongs in a paragraph."
        ),
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.rows == [
        ["Widget", "Starter package", "25"],
        ["Gadget", "Renewal", "30"],
    ]
    assert normalized.blocks[1].block_type == "paragraph"
    assert normalized.blocks[1].text == "The renewal note belongs in a paragraph."


def test_falls_back_to_text_when_table_rows_cannot_be_parsed_consistently() -> None:
    page = ExtractedPage(
        page_number=1,
        text="Name  Role  Score\nAna Senior Engineer 98 % growth\nBob  Analyst  91",
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type != "table"


def test_keeps_rows_independent_when_most_cells_are_long_prose() -> None:
    page = ExtractedPage(
        page_number=1,
        text=(
            "Month                        Focus                              Build by end of month\n"
            "1         Python, Git & Engineering Basics                 A CLI app pushed to GitHub\n"
            "2         Data, Text & Embeddings Foundations              A semantic search prototype\n"
            "3         Generative AI & Prompt Engineering               An LLM-powered data extractor\n"
            "4         RAG, Vector Stores & Frameworks                  A \"Chat with your docs\" app\n"
            "5         Machine Learning Foundations                     A re-ranker that boosts your RAG\n"
            "6         Agentic Systems, Production &                    A deployed AI product on GitHub\n"
            "          Capstone"
        ),
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.header == ["Month", "Focus", "Build by end of month"]
    assert normalized.blocks[0].table.rows == [
        ["1", "Python, Git & Engineering Basics", "A CLI app pushed to GitHub"],
        ["2", "Data, Text & Embeddings Foundations", "A semantic search prototype"],
        ["3", "Generative AI & Prompt Engineering", "An LLM-powered data extractor"],
        ["4", "RAG, Vector Stores & Frameworks", "A \"Chat with your docs\" app"],
        ["5", "Machine Learning Foundations", "A re-ranker that boosts your RAG"],
        ["6", "Agentic Systems, Production & Capstone", "A deployed AI product on GitHub"],
    ]

def test_appends_wrapped_final_row_when_followed_by_unrelated_text() -> None:
    page = ExtractedPage(
        page_number=1,
        text=(
            "Month                        Focus                              Build by end of month\n"
            "6         Agentic Systems, Production &                    A deployed AI product on GitHub\n"
            "          Capstone\n"
            "Questions? Reach out to your program coordinator."
        ),
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.rows == [
        ["6", "Agentic Systems, Production & Capstone", "A deployed AI product on GitHub"],
    ]
    assert normalized.blocks[1].block_type == "paragraph"
    assert normalized.blocks[1].text == "Questions? Reach out to your program coordinator."


def test_appends_multi_word_wrapped_row_misclassified_as_heading() -> None:
    page = ExtractedPage(
        page_number=1,
        text=(
            "Month                        Focus                              Build by end of month\n"
            "7         Interviewing &                                  A polished portfolio site\n"
            "          Career Prep"
        ),
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.rows == [
        ["7", "Interviewing & Career Prep", "A polished portfolio site"],
    ]
    assert len(normalized.blocks) == 1


def test_does_not_merge_genuine_heading_after_complete_table_row() -> None:
    page = ExtractedPage(
        page_number=1,
        text=(
            "Month                        Focus                              Build by end of month\n"
            "6         Agentic Systems, Production & Capstone         A deployed AI product on GitHub\n"
            "Career Services"
        ),
    )

    normalized = normalize_page(page)

    assert normalized.blocks[0].block_type == "table"
    assert normalized.blocks[0].table is not None
    assert normalized.blocks[0].table.rows == [
        ["6", "Agentic Systems, Production & Capstone", "A deployed AI product on GitHub"],
    ]
    assert normalized.blocks[1].block_type == "heading"
    assert normalized.blocks[1].text == "Career Services"


def test_normalized_document_metrics_integrity(normalized_doc: NormalizedDocument):
    """Verify that computed document and page metrics strictly match content lengths."""
    
    # Check Document level
    assert normalized_doc.page_count == len(normalized_doc.pages)
    assert normalized_doc.char_count == len(normalized_doc.full_text)
    assert normalized_doc.word_count == sum(page.word_count for page in normalized_doc.pages)
    assert normalized_doc.word_count == count_words(normalized_doc.full_text)

    # Check Page level
    for page in normalized_doc.pages:
        assert page.char_count == len(page.text)
        assert page.word_count == count_words(page.text)


def test_json_serialization_includes_computed_fields(normalized_doc: NormalizedDocument):
    """Verify @computed_field fields appear when serialized to JSON/dict."""
    doc_dict = normalized_doc.model_dump()

    # Pydantic automatically serializes @computed_field properties into dicts/JSON
    assert "page_count" in doc_dict
    assert "word_count" in doc_dict
    assert "char_count" in doc_dict
    
    assert doc_dict["page_count"] == len(normalized_doc.pages)
