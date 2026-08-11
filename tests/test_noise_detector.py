from document_chunker.noise_detector import detect_noise_lines

# Every page below uses at least 4 lines so the header zone (first `zone_size` non-blank
# lines) and footer zone (last `zone_size` non-blank lines) never overlap at the default
# zone_size=2 - keeps each assertion attributable to a single, unambiguous line.


# --- page-number patterns (fire immediately, independent of repetition/page count) ---


def test_bare_page_number_in_footer_zone_is_detected():
    pages = [
        ["Header A", "Header B", "Body text one.", "3"],
        ["Header C", "Header D", "Body text two.", "4"],
    ]

    result = detect_noise_lines(pages)

    assert result[0] == {3: "page_footer"}
    assert result[1] == {3: "page_footer"}


def test_page_n_of_m_pattern_is_detected():
    pages = [["Header A", "Header B", "Body text.", "Page 1 of 42"]]

    result = detect_noise_lines(pages)

    assert result[0] == {3: "page_footer"}


def test_dashed_page_number_pattern_is_detected():
    pages = [["Header A", "Header B", "Body text.", "- 3 -"]]

    result = detect_noise_lines(pages)

    assert result[0] == {3: "page_footer"}


def test_short_roman_numeral_footer_is_detected():
    pages = [["Header A", "Header B", "Body text.", "iv"]]

    result = detect_noise_lines(pages)

    assert result[0] == {3: "page_footer"}


def test_page_number_detected_even_with_a_single_page():
    pages = [["Header A", "Header B", "Body text.", "1"]]

    result = detect_noise_lines(pages)

    assert result[0] == {3: "page_footer"}


def test_bare_page_number_in_header_zone_is_detected():
    pages = [["1", "Report Title", "Body text.", "Footer note"]]

    result = detect_noise_lines(pages)

    assert result[0] == {0: "page_header"}


# --- repetition-based detection ---


def test_repeated_footer_text_across_pages_is_detected():
    pages = [
        ["Header one", "Header sub one", "Body one.", "Acme Corp Confidential"],
        ["Header two", "Header sub two", "Body two.", "Acme Corp Confidential"],
        ["Header three", "Header sub three", "Body three.", "Acme Corp Confidential"],
    ]

    result = detect_noise_lines(pages)

    assert result == [{3: "page_footer"}] * 3


def test_repeated_footer_with_variable_internal_padding_is_still_detected():
    # Layout-mode PDF extraction right-aligns "Brand ... Page N" on one line with a
    # gap width that depends on the page's other content - the visual column padding
    # differs per page even though the footer is logically identical.
    pages = [
        ["Body one.", "Acme Corp" + " " * 30 + "Page 1"],
        ["Body two.", "Acme Corp" + " " * 45 + "Page 2"],
        ["Body three.", "Acme Corp" + " " * 12 + "Page 3"],
    ]

    result = detect_noise_lines(pages)

    assert all(page_result == {1: "page_footer"} for page_result in result)


def test_repeated_footer_with_changing_year_is_still_detected():
    pages = [
        ["Header one", "Header sub one", "Body one.", "© 2021 Acme Corp"],
        ["Header two", "Header sub two", "Body two.", "© 2022 Acme Corp"],
        ["Header three", "Header sub three", "Body three.", "© 2023 Acme Corp"],
    ]

    result = detect_noise_lines(pages)

    assert result == [{3: "page_footer"}] * 3


def test_repeated_header_is_classified_separately_from_footer():
    pages = [
        ["Running Title", "Unique sub one", "Body one.", "Unique footer one"],
        ["Running Title", "Unique sub two", "Body two.", "Unique footer two"],
        ["Running Title", "Unique sub three", "Body three.", "Unique footer three"],
    ]

    result = detect_noise_lines(pages)

    assert result == [{0: "page_header"}] * 3


def test_repetition_below_page_count_threshold_is_not_detected():
    pages = [
        ["Header one", "Header sub one", "Body one.", "Acme Corp Confidential"],
        ["Header two", "Header sub two", "Body two.", "Acme Corp Confidential"],
    ]

    result = detect_noise_lines(pages)

    assert result == [{}, {}]


# --- no false positives ---


def test_unique_non_repeated_lines_are_not_flagged():
    pages = [
        ["First page opening line", "Sub one", "Body one.", "Closing note one"],
        ["Second page opening line", "Sub two", "Body two.", "Closing note two"],
        ["Third page opening line", "Sub three", "Body three.", "Closing note three"],
    ]

    result = detect_noise_lines(pages)

    assert result == [{}, {}, {}]


def test_repeated_line_outside_the_header_footer_zone_is_not_flagged():
    pages = [
        ["Heading", "Subheading", "Repeated mid-page line", "Body one.", "Footer A", "Footer B"],
        ["Heading", "Subheading", "Repeated mid-page line", "Body two.", "Footer A", "Footer B"],
        ["Heading", "Subheading", "Repeated mid-page line", "Body three.", "Footer A", "Footer B"],
    ]

    result = detect_noise_lines(pages, zone_size=2)

    for page_result in result:
        assert 2 not in page_result  # "Repeated mid-page line" sits outside both zones


# --- index alignment with blank lines ---


def test_noise_line_indices_skip_over_blank_lines_correctly():
    pages = [
        ["Running Title", "", "Section one", "Body one.", "", "Footer A", "Footer B"],
        ["Running Title", "", "Section two", "Body two.", "", "Footer A", "Footer B"],
        ["Running Title", "", "Section three", "Body three.", "", "Footer A", "Footer B"],
    ]

    result = detect_noise_lines(pages)

    # header zone = first two non-blank lines: index 0 ("Running Title", repeated) and
    # index 2 ("Section N", varies per page); footer zone = last two non-blank lines:
    # indices 5 and 6 ("Footer A"/"Footer B"), both repeated verbatim.
    assert result == [{0: "page_header", 5: "page_footer", 6: "page_footer"}] * 3
