from document_chunker.normalizer import (
    DEFAULT_NORMALIZATION_STRATEGY,
    normalize_document,
    normalize_page,
    normalize_text,
)
from document_chunker.schemas import ExtractDocumentPage


# --- normalize_text: one test per rule ---


def test_normalizes_line_endings():
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_replaces_non_breaking_spaces():
    assert normalize_text("a\xa0b c　d") == "a b c d"


def test_removes_null_and_control_characters():
    assert normalize_text("a\x00b\x1fc\x7fd") == "abcd"


def test_vertical_tab_and_form_feed_become_newlines():
    assert normalize_text("a\vb\fc") == "a\nb\nc"


def test_collapses_repeated_spaces_and_tabs():
    assert normalize_text("a    b\t\tc") == "a b c"


def test_removes_spaces_around_line_breaks():
    assert normalize_text("a   \n   b") == "a\nb"


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


# --- normalize_page ---


def test_normalize_page_recalculates_counts():
    page = ExtractDocumentPage(page_number=1, text="  a    b  ", word_count=99, char_count=99)
    normalized = normalize_page(page)
    assert normalized.text == "a b"
    assert normalized.word_count == 2
    assert normalized.char_count == 3


def test_normalize_page_preserves_page_number():
    page = ExtractDocumentPage(page_number=7, text="text", word_count=1, char_count=4)
    normalized = normalize_page(page)
    assert normalized.page_number == 7


def test_normalize_page_blank_page_stays_empty():
    page = ExtractDocumentPage(page_number=2, text="", word_count=0, char_count=0)
    normalized = normalize_page(page)
    assert normalized.text == ""
    assert normalized.word_count == 0
    assert normalized.char_count == 0


def test_normalize_page_control_char_only_page_becomes_empty():
    page = ExtractDocumentPage(page_number=1, text="\x00\x1f  \n  ", word_count=1, char_count=6)
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

    assert normalized.pages[0].text == "a\nb"
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
    assert normalized.normalized_strategy == "conservative"


def test_normalize_document_custom_strategy_override(make_extract_document):
    document = make_extract_document(["some text"])
    normalized = normalize_document(document, strategy="aggressive")

    assert normalized.normalized_strategy == "aggressive"
