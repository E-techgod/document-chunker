from document_chunker.normalizer import normalize_page
from document_chunker.schemas import ExtractedPage


def test_wrapped_last_column_merges_into_the_same_cell():
    # Realistic layout-mode PDF extraction: columns are character-offset aligned, and a
    # continuation line for the last column starts at that column's own offset.
    page = ExtractedPage(
        page_number=1,
        text=(
            "Industry              % of Postings          Key Use Cases\n"
            "Manufacturing / Auto   6%                     Predictive maintenance, computer vision, supply\n"
            "                                              chain\n"
        ),
    )

    normalized = normalize_page(page)
    table = next(b.table for b in normalized.blocks if b.block_type == "table")

    assert table.header == ["Industry", "% of Postings", "Key Use Cases"]
    assert table.rows == [
        [
            "Manufacturing / Auto",
            "6%",
            "Predictive maintenance, computer vision, supply chain",
        ],
    ]


def test_wrapped_middle_and_last_column_merge_on_one_continuation_line():
    # A single continuation line can carry wrapped text for two different columns at
    # once, each positioned at its own column's offset - neither touches column 0.
    page = ExtractedPage(
        page_number=1,
        text=(
            "Industry              Solution                        Impact\n"
            "Education / Training  Course content personalizer +   Scales 1 instructor to 10x\n"
            "                       student Q&A; agent              students\n"
        ),
    )

    normalized = normalize_page(page)
    table = next(b.table for b in normalized.blocks if b.block_type == "table")

    assert table.header == ["Industry", "Solution", "Impact"]
    assert table.rows == [
        [
            "Education / Training",
            "Course content personalizer + student Q&A; agent",
            "Scales 1 instructor to 10x students",
        ],
    ]


def test_new_row_still_detected_via_column_zero_alignment():
    # A line whose first segment aligns with column 0 starts a fresh logical row, even
    # right after a multi-line row was just closed out.
    page = ExtractedPage(
        page_number=1,
        text=(
            "Industry           Solution                Impact\n"
            "Marketing          Content agent +          $3K/month retainer\n"
            "                    brief generator\n"
            "Consulting         Research aggregator      2x proposal output\n"
        ),
    )

    normalized = normalize_page(page)
    table = next(b.table for b in normalized.blocks if b.block_type == "table")

    assert table.rows == [
        ["Marketing", "Content agent + brief generator", "$3K/month retainer"],
        ["Consulting", "Research aggregator", "2x proposal output"],
    ]


def test_row_order_preserved_across_multiple_wrapped_rows():
    page = ExtractedPage(
        page_number=1,
        text=(
            "Industry           Solution                Impact\n"
            "Sales              CRM enrichment +         20% pipeline increase\n"
            "                    outreach generator\n"
            "Marketing          Content agent +          $3K/month retainer\n"
            "                    brief generator\n"
            "Real Estate        Document summarizer      $500 per transaction\n"
        ),
    )

    normalized = normalize_page(page)
    table = next(b.table for b in normalized.blocks if b.block_type == "table")

    assert [row[0] for row in table.rows] == ["Sales", "Marketing", "Real Estate"]
    assert table.rows[0][1] == "CRM enrichment + outreach generator"
    assert table.rows[1][1] == "Content agent + brief generator"


def test_normalized_spans_locate_table_text_within_page_text_after_merge():
    # The reconstructed table's rendered text must still be locatable at the block's own
    # start_char:end_char within the page's full normalized text.
    page = ExtractedPage(
        page_number=1,
        text=(
            "Industry              % of Postings          Key Use Cases\n"
            "Manufacturing / Auto   6%                     Predictive maintenance, computer vision, supply\n"
            "                                              chain\n"
        ),
    )

    normalized = normalize_page(page)
    table_block = next(b for b in normalized.blocks if b.block_type == "table")

    assert normalized.text[table_block.start_char : table_block.end_char] == (
        "Industry | % of Postings | Key Use Cases\n"
        "Manufacturing / Auto | 6% | Predictive maintenance, computer vision, supply chain"
    )
