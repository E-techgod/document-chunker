import re

from document_chunker.paragraph_normalizer import build_structured_document
from document_chunker.schemas import ExtractedDocument, ExtractedPage
from document_chunker.step2_pipeline import validate_structured_document
from document_chunker.structured_models import (
    HeadingBlock,
    ListBlock,
    PageFooterBlock,
    PageHeaderBlock,
    ParagraphBlock,
)


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

    assert [b.text for b in structured.blocks] == [
        "First paragraph.",
        "Second paragraph.",
    ]
    assert all(isinstance(b, ParagraphBlock) for b in structured.blocks)


def test_multiple_consecutive_blank_lines_still_produce_one_boundary():
    document = _document(["First.\n\n\n\nSecond."])

    structured = build_structured_document(document)

    assert [b.text for b in structured.blocks] == ["First.", "Second."]


def test_page_boundary_always_starts_a_new_paragraph_even_without_a_blank_line():
    document = _document(["First page ends mid", "sentence on next page."])

    structured = build_structured_document(document)

    assert [b.text for b in structured.blocks] == [
        "First page ends mid",
        "sentence on next page.",
    ]
    assert [b.page for b in structured.blocks] == [1, 2]


def test_mid_sentence_page_break_between_paragraph_blocks_renders_with_space_and_keeps_spans():
    document = _document(
        ["You will be a competitive candidate in 12", "months.\n\nSTEP 1"]
    )

    structured = build_structured_document(document)

    assert (
        structured.full_text
        == "You will be a competitive candidate in 12 months.\n\nSTEP 1"
    )
    assert [b.page for b in structured.blocks] == [1, 2, 2]
    assert [type(b).__name__ for b in structured.blocks] == [
        "ParagraphBlock",
        "ParagraphBlock",
        "HeadingBlock",
    ]
    for block in structured.blocks:
        assert structured.full_text[block.start_char : block.end_char] == block.text
    assert validate_structured_document(structured, source=document) == []


def test_page_boundary_keeps_double_newline_for_intentional_paragraph_break():
    document = _document(
        ["This paragraph is complete.", "Another paragraph starts here."]
    )

    structured = build_structured_document(document)

    assert (
        structured.full_text
        == "This paragraph is complete.\n\nAnother paragraph starts here."
    )
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

    assert [b.block_id for b in structured.blocks] == [
        "block_001",
        "block_002",
        "block_003",
    ]


# --- heading detection and interleaving (Phase 3) ---


def test_heading_and_paragraphs_interleave_in_document_order():
    document = _document(
        [
            "CHAPTER 01\n\nThis is the opening paragraph of the chapter.\n\nWeek 5: Git & APIs\n\nMore prose here."
        ]
    )

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == [
        "HeadingBlock",
        "ParagraphBlock",
        "HeadingBlock",
        "ParagraphBlock",
    ]
    assert [b.text for b in structured.blocks] == [
        "CHAPTER 01",
        "This is the opening paragraph of the chapter.",
        "Week 5: Git & APIs",
        "More prose here.",
    ]
    assert structured.blocks[0].level == 1
    assert structured.blocks[2].level == 1


def test_heading_false_positive_stays_a_paragraph_block():
    document = _document(
        [
            "CRITICAL INSIGHT: GENERALISTS ARE LOSING GROUND\n\nOver 75% of AI job listings seek domain experts."
        ]
    )

    structured = build_structured_document(document)

    assert isinstance(structured.blocks[0], ParagraphBlock)
    assert (
        structured.blocks[0].text == "CRITICAL INSIGHT: GENERALISTS ARE LOSING GROUND"
    )


def test_wrapped_multi_line_chunk_with_numbered_prefix_stays_a_paragraph_not_a_heading():
    # Layout signal: a heading candidate must be a single standalone line. A numbered
    # prefix that wraps across two physical lines is ordinary paragraph content.
    document = _document(["Week 2 was really hard for\nmost students in the cohort."])

    structured = build_structured_document(document)

    assert isinstance(structured.blocks[0], ParagraphBlock)
    assert (
        structured.blocks[0].text
        == "Week 2 was really hard for most students in the cohort."
    )


def test_span_invariant_holds_across_interleaved_heading_and_paragraph_blocks():
    document = _document(
        [
            "CHAPTER 01\n\nOpening paragraph text.\n\nSTEP 3\n\nAnother paragraph here.",
            "Section 4.1\n\nFinal paragraph on page two.",
        ]
    )

    structured = build_structured_document(document)

    assert any(isinstance(b, HeadingBlock) for b in structured.blocks)
    assert structured.validate_spans() == []
    structured.assert_spans_valid()


def test_monotonic_span_ordering_across_interleaved_heading_and_paragraph_blocks():
    document = _document(
        [
            "CHAPTER 01\n\nOpening paragraph text.\n\nSTEP 3\n\nAnother paragraph here.",
            "Section 4.1\n\nFinal paragraph on page two.",
        ]
    )

    structured = build_structured_document(document)

    for previous, current in zip(structured.blocks, structured.blocks[1:]):
        assert current.start_char >= previous.end_char


# --- list detection and grouping (Phase 4) ---


def test_consecutive_bullet_items_group_into_one_list_block():
    document = _document(
        [
            "● Learn functions, arguments, return values, scope\n"
            "● Work with lists, dictionaries, tuples, and sets\n"
            "● Start writing cleaner, reusable code"
        ]
    )

    structured = build_structured_document(document)

    assert len(structured.blocks) == 1
    block = structured.blocks[0]
    assert isinstance(block, ListBlock)
    assert block.items == [
        "Learn functions, arguments, return values, scope",
        "Work with lists, dictionaries, tuples, and sets",
        "Start writing cleaner, reusable code",
    ]


def test_list_block_text_renders_items_joined_by_newline():
    document = _document(["- First item\n- Second item\n- Third item"])

    structured = build_structured_document(document)

    assert structured.blocks[0].text == "First item\nSecond item\nThird item"


def test_multi_line_wrapped_bullet_merges_into_one_item():
    document = _document(
        [
            "    ● Master Git basics: commit, branch, merge, push\n"
            "    ● Call public REST APIs using\n"
            "      requests and other tools\n"
            "    ● Push your first project to GitHub"
        ]
    )

    structured = build_structured_document(document)

    block = structured.blocks[0]
    assert isinstance(block, ListBlock)
    assert block.items == [
        "Master Git basics: commit, branch, merge, push",
        "Call public REST APIs using requests and other tools",
        "Push your first project to GitHub",
    ]


def test_list_terminates_on_blank_line_before_a_paragraph():
    document = _document(["- First item\n- Second item\n\nA normal paragraph follows."])

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == [
        "ListBlock",
        "ParagraphBlock",
    ]
    assert structured.blocks[0].items == ["First item", "Second item"]
    assert structured.blocks[1].text == "A normal paragraph follows."


def test_list_terminates_on_a_new_heading():
    document = _document(
        ["- First item\n- Second item\nSTEP 3\n- Third item\n- Fourth item"]
    )

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == [
        "ListBlock",
        "HeadingBlock",
        "ListBlock",
    ]
    assert structured.blocks[0].items == ["First item", "Second item"]
    assert structured.blocks[2].items == ["Third item", "Fourth item"]


def test_list_terminates_on_a_non_continuation_paragraph_line_without_a_blank_line():
    # A plain line with no marker and no deeper indent than the last item's marker ends
    # the list and starts a paragraph, even without a blank line in between.
    document = _document(
        ["    - First item\n    - Second item\nA paragraph starts right here."]
    )

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == [
        "ListBlock",
        "ParagraphBlock",
    ]
    assert structured.blocks[1].text == "A paragraph starts right here."


def test_preceding_heading_stays_a_separate_block_from_the_list():
    document = _document(
        ["Week 4: Git, GitHub & APIs\n- Master Git basics\n- Push your first project"]
    )

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == [
        "HeadingBlock",
        "ListBlock",
    ]
    assert structured.blocks[0].text == "Week 4: Git, GitHub & APIs"
    assert structured.blocks[1].items == [
        "Master Git basics",
        "Push your first project",
    ]


def test_span_invariant_holds_for_list_blocks():
    document = _document(
        [
            "Week 4: Git, GitHub & APIs\n- Master Git basics\n- Push your first project\n\nClosing paragraph."
        ]
    )

    structured = build_structured_document(document)

    assert any(isinstance(b, ListBlock) for b in structured.blocks)
    assert structured.validate_spans() == []
    structured.assert_spans_valid()


def test_monotonic_span_ordering_across_heading_list_and_paragraph_blocks():
    document = _document(
        [
            "Week 4: Git, GitHub & APIs\n- Master Git basics\n- Push your first project\n\nClosing paragraph.",
            "STEP 3\n- Fresh item on page two",
        ]
    )

    structured = build_structured_document(document)

    for previous, current in zip(structured.blocks, structured.blocks[1:]):
        assert current.start_char >= previous.end_char


def test_separate_list_blocks_on_different_pages_do_not_merge():
    document = _document(["- Page one item", "- Page two item"])

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.blocks] == ["ListBlock", "ListBlock"]
    assert [b.page for b in structured.blocks] == [1, 2]


# --- content preservation ---


def test_no_non_whitespace_content_is_dropped_during_line_joining():
    raw_text = (
        "  This   line has  extra   spaces\n"
        "and wraps onto a second line.\n\n"
        "A completely separate paragraph\nwith its own wrap."
    )
    document = _document([raw_text])

    structured = build_structured_document(document)

    assert _non_whitespace_tokens(structured.full_text) == _non_whitespace_tokens(
        raw_text
    )


def test_no_content_dropped_across_multiple_pages_with_blank_page():
    raw_pages = [
        "Page one first\nline wraps here.",
        "",
        "Page three has\ntwo lines\n\nand a second paragraph.",
    ]
    document = _document(raw_pages)

    structured = build_structured_document(document)

    expected_tokens = [
        tok for page in raw_pages for tok in _non_whitespace_tokens(page)
    ]
    assert _non_whitespace_tokens(structured.full_text) == expected_tokens


# --- noise detection (running headers/footers) ---


def _paged_document_with_repeated_header_and_footer() -> ExtractedDocument:
    # Body/subtitle lines vary by word (not digit) so digit-collapsing normalization in
    # noise_detector doesn't accidentally treat them as a recurring header/footer line -
    # only "Company Confidential" (verbatim-repeated) and "Page N" (page-number pattern)
    # are meant to be flagged as noise here.
    ordinals = ["one", "two", "three"]
    texts = [
        f"Company Confidential\n"
        f"Unique subtitle {ordinal}\n"
        f"This is body content unique to page {ordinal} with real prose that should stay intact.\n"
        f"Page {n}"
        for n, ordinal in enumerate(ordinals, start=1)
    ]
    return _document(texts)


def test_repeated_header_line_becomes_page_header_block():
    document = _paged_document_with_repeated_header_and_footer()

    structured = build_structured_document(document)

    header_blocks = [b for b in structured.blocks if isinstance(b, PageHeaderBlock)]
    assert len(header_blocks) == 3
    assert all(b.text == "Company Confidential" for b in header_blocks)
    assert all(b.is_noise for b in header_blocks)


def test_page_number_footer_line_becomes_page_footer_block():
    document = _paged_document_with_repeated_header_and_footer()

    structured = build_structured_document(document)

    footer_blocks = [b for b in structured.blocks if isinstance(b, PageFooterBlock)]
    assert [b.text for b in footer_blocks] == ["Page 1", "Page 2", "Page 3"]
    assert all(b.is_noise for b in footer_blocks)


def test_content_blocks_excludes_noise_but_keeps_body_paragraphs():
    document = _paged_document_with_repeated_header_and_footer()

    structured = build_structured_document(document)

    assert [type(b).__name__ for b in structured.content_blocks] == [
        "ParagraphBlock"
    ] * 3
    assert [b.text for b in structured.content_blocks] == [
        "Unique subtitle one This is body content unique to page one with real prose that should stay intact.",
        "Unique subtitle two This is body content unique to page two with real prose that should stay intact.",
        "Unique subtitle three This is body content unique to page three with real prose that should stay intact.",
    ]


def test_noise_blocks_are_still_counted_as_preserved_content():
    document = _paged_document_with_repeated_header_and_footer()

    structured = build_structured_document(document)
    issues = validate_structured_document(structured, source=document)

    assert issues == []
