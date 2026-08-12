from document_chunker.list_detector import is_continuation_line, match_list_item

# --- marker recognition and prefix stripping ---


def test_symbol_bullets_are_recognized_and_stripped():
    assert match_list_item("• First item") == "First item"
    assert match_list_item("⁃ Second item") == "Second item"
    assert match_list_item("■ Third item") == "Third item"
    assert match_list_item("– Fourth item") == "Fourth item"
    assert match_list_item("* Fifth item") == "Fifth item"
    assert match_list_item("- Sixth item") == "Sixth item"


def test_numbered_dot_marker_is_recognized_and_stripped():
    assert match_list_item("1. First item") == "First item"
    assert match_list_item("12. Twelfth item") == "Twelfth item"


def test_numbered_paren_marker_is_recognized_and_stripped():
    assert match_list_item("2) Second item") == "Second item"


def test_lettered_paren_marker_is_recognized_and_stripped():
    assert match_list_item("(a) Sub point") == "Sub point"
    assert match_list_item("(1) Numeric sub point") == "Numeric sub point"


def test_single_letter_dot_marker_is_recognized_and_stripped():
    assert match_list_item("A. Capitalized item") == "Capitalized item"
    assert match_list_item("a) Lowercase item") == "Lowercase item"
    assert match_list_item("i. Roman numeral item") == "Roman numeral item"


def test_bracketed_number_marker_is_recognized_and_stripped():
    assert match_list_item("[1] Bracketed item") == "Bracketed item"


def test_excess_whitespace_after_marker_is_trimmed():
    assert match_list_item("●   Learn functions, arguments, return values, scope") == (
        "Learn functions, arguments, return values, scope"
    )


# --- rejection ---


def test_marker_with_no_content_is_rejected():
    assert match_list_item("- ") is None
    assert match_list_item("•") is None


def test_plain_prose_line_is_not_a_list_item():
    assert match_list_item("This is just a normal sentence.") is None


def test_marker_must_be_at_line_start():
    assert match_list_item("Some text - not a bullet") is None


# --- continuation detection ---


def test_deeper_indented_line_is_a_continuation():
    assert (
        is_continuation_line("      wrapped continuation text", marker_indent=4) is True
    )


def test_same_indent_as_marker_is_still_a_continuation():
    # Real extracted text often wraps a continuation line at the same column as its
    # marker, not deeper than it - see list_detector's docstring.
    assert is_continuation_line("    same indent as marker", marker_indent=4) is True


def test_shallower_indent_than_marker_is_not_a_continuation():
    assert is_continuation_line("no indent at all", marker_indent=4) is False
    assert is_continuation_line("  slightly indented", marker_indent=4) is False
