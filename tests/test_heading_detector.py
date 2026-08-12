from document_chunker.heading_detector import detect_heading_level


# --- correct classification of structural headings ---


def test_bare_chapter_number_is_a_level_1_heading():
    assert detect_heading_level("CHAPTER 01") == 1


def test_bare_step_number_is_a_level_1_heading():
    assert detect_heading_level("STEP 3") == 1


def test_week_with_colon_and_title_is_a_level_1_heading():
    assert detect_heading_level("Week 5: Git, GitHub & APIs") == 1


def test_month_with_em_dash_and_title_is_a_level_1_heading():
    assert detect_heading_level("Month 2 — Data, Text & Embeddings Foundations") == 1


def test_dotted_section_number_is_a_deeper_level():
    assert detect_heading_level("Section 4.1") == 2


def test_more_dotted_segments_increase_the_level():
    assert detect_heading_level("Section 4.1.2") == 3


def test_short_standalone_all_caps_section_title_is_a_heading():
    assert detect_heading_level("YOUR STRUCTURAL ADVANTAGE") == 2


# --- rejection of false positives ---


def test_all_caps_callout_with_colon_is_not_a_heading():
    # The exact example from the task spec: capitalized for emphasis, not a section
    # header, and must not be flagged as one just because it's all-caps.
    assert detect_heading_level("CRITICAL INSIGHT: GENERALISTS ARE LOSING GROUND") is None


def test_all_caps_without_numbering_is_not_a_heading():
    assert detect_heading_level("AI AGENT IDEAS BY DOMAIN") is None


def test_ordinary_sentence_starting_with_a_number_word_is_not_a_heading():
    assert detect_heading_level("Week 2 was really hard for most students in the cohort.") is None


def test_list_item_prefix_is_never_a_heading():
    assert detect_heading_level("- Master Git basics") is None
    assert detect_heading_level("● Build something every single week") is None
    assert detect_heading_level("1. First item in a numbered list") is None


def test_overly_long_line_is_not_a_heading_even_with_a_numbered_prefix():
    long_tail = "a very long descriptive title " * 5
    assert detect_heading_level(f"Month 2 — {long_tail}") is None


def test_plain_prose_paragraph_is_not_a_heading():
    text = "This is just a normal paragraph of prose that happens to be reasonably short."
    assert detect_heading_level(text) is None


def test_empty_text_is_not_a_heading():
    assert detect_heading_level("") is None
    assert detect_heading_level("   ") is None
