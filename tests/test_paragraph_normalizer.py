import re

from document_chunker.paragraph_normalizer import build_structured_document
from document_chunker.schemas import ExtractedDocument, ExtractedPage
from document_chunker.structured_models import ParagraphBlock


def _document(texts: list[str], document_id: str = "doc1") -> ExtractedDocument:
    pages = [ExtractedPage(page_number=i, text=text) for i, text in enumerate(texts, start=1)]
    return ExtractedDocument(
        document_id=document_id,
        file_name=f"{document_id}.pdf",
        file_path=f"/tmp/{document_id}.pdf",
        pages=pages,
        full_text="\n\n".join(texts),
    )


def _non_whitespace_tokens(text: str) -> list[str]:
    return re.findall(r"\S+", text)


# --- visual wrap resolution ---


def test_line_wrap_mid_sentence_is_space_joined():
    document = _document(["line one of a\nparagraph"])

    structured = build_structured_document(document)

    assert len(structured.blocks) == 1
    assert structured.blocks[0].text == "line one of a paragraph"


def test_multiple_wrapped_lines_join_into_one_paragraph():
    document = _document(["The quick brown fox\njumps over the\nlazy dog."])

    structured = build_structured_document(document)

    assert structured.blocks[0].text == "The quick brown fox jumps over the lazy dog."


def test_leading_and_trailing_whitespace_is_stripped():
    document = _document(["   padded paragraph text   \n  still padded  "])

    structured = build_structured_document(document)

    assert structured.blocks[0].text == "padded paragraph text still padded"


def test_internal_multi_spaces_are_collapsed():
    document = _document(["word1    word2\tword3   word4"])

    structured = build_structured_document(document)

    assert structured.blocks[0].text == "word1 word2 word3 word4"


# --- paragraph boundary signals ---


def test_blank_line_starts_a_new_paragraph_block():
    document = _document(["First paragraph.\n\nSecond paragraph."])

    structured = build_structured_document(document)

    assert [b.text for b in structured.blocks] == ["First paragraph.", "Second paragraph."]
    assert all(isinstance(b, ParagraphBlock) for b in structured.blocks)


def test_multiple_consecutive_blank_lines_still_produce_one_boundary():
    document = _document(["First.\n\n\n\nSecond."])

    structured = build_structured_document(document)

    assert [b.text for b in structured.blocks] == ["First.", "Second."]


def test_page_boundary_always_starts_a_new_paragraph_even_without_a_blank_line():
    document = _document(["First page ends mid", "sentence on next page."])

    structured = build_structured_document(document)

    assert [b.text for b in structured.blocks] == ["First page ends mid", "sentence on next page."]
    assert [b.page for b in structured.blocks] == [1, 2]


def test_blank_page_contributes_no_blocks():
    document = _document(["Page one text.", "", "Page three text."])

    structured = build_structured_document(document)

    assert [b.text for b in structured.blocks] == ["Page one text.", "Page three text."]
    assert [b.page for b in structured.blocks] == [1, 3]


# --- full_text assembly and span invariants ---


def test_full_text_joins_blocks_with_double_newline():
    document = _document(["Alpha.\n\nBeta."])

    structured = build_structured_document(document)

    assert structured.full_text == "Alpha.\n\nBeta."


def test_span_invariant_holds_for_every_block():
    document = _document(
        [
            "First page has\na wrapped line.\n\nAnd a second paragraph.",
            "Second page starts\nfresh.",
        ]
    )

    structured = build_structured_document(document)

    assert structured.validate_spans() == []
    structured.assert_spans_valid()  # must not raise


def test_blocks_are_monotonically_ordered():
    document = _document(
        [
            "One.\n\nTwo.\n\nThree.",
            "Four on page two.",
        ]
    )

    structured = build_structured_document(document)

    for previous, current in zip(structured.blocks, structured.blocks[1:]):
        assert current.start_char >= previous.end_char


def test_block_ids_are_unique_and_sequential():
    document = _document(["One.\n\nTwo.\n\nThree."])

    structured = build_structured_document(document)

    assert [b.block_id for b in structured.blocks] == ["block_001", "block_002", "block_003"]


# --- content preservation ---


def test_no_non_whitespace_content_is_dropped_during_line_joining():
    raw_text = (
        "  This   line has  extra   spaces\n"
        "and wraps   onto a second line.\n\n"
        "A completely separate paragraph\nwith its own wrap."
    )
    document = _document([raw_text])

    structured = build_structured_document(document)

    assert _non_whitespace_tokens(structured.full_text) == _non_whitespace_tokens(raw_text)


def test_no_content_dropped_across_multiple_pages_with_blank_page():
    raw_pages = [
        "Page one first\nline wraps here.",
        "",
        "Page three has\ntwo lines\n\nand a second paragraph.",
    ]
    document = _document(raw_pages)

    structured = build_structured_document(document)

    expected_tokens = [tok for page in raw_pages for tok in _non_whitespace_tokens(page)]
    assert _non_whitespace_tokens(structured.full_text) == expected_tokens
