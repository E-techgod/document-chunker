import pytest

from document_chunker.chunker import chunk_document
from document_chunker.normalizer import normalize_document
from document_chunker.schemas import ChunkingConfig


# --- happy path ---


def test_chunk_document_produces_expected_offsets(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text="ABCDEFGHIJKL")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=5, overlap_size=2))

    assert [c.text for c in result.chunks] == ["ABCDE", "DEFGH", "GHIJK", "JKL"]
    assert [(c.start_char, c.end_char) for c in result.chunks] == [
        (0, 5),
        (3, 8),
        (6, 11),
        (9, 12),
    ]
    assert [c.chunk_index for c in result.chunks] == [0, 1, 2, 3]
    assert [c.chunk_id for c in result.chunks] == [
        "doc1_chunk_0",
        "doc1_chunk_1",
        "doc1_chunk_2",
        "doc1_chunk_3",
    ]


def test_chunk_document_word_and_char_counts_match_text(make_normalized_document):
    document = make_normalized_document(["hello world foo bar"], full_text="hello world foo bar")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=11, overlap_size=0))

    for chunk in result.chunks:
        assert chunk.char_count == len(chunk.text)
        assert chunk.word_count == len(chunk.text.split())


def test_chunk_document_preserves_document_metadata(make_normalized_document):
    document = make_normalized_document(
        ["some text"],
        document_id="doc-42",
        file_name="report.pdf",
        file_path="/data/report.pdf",
        document_type="report",
    )
    result = chunk_document(document, ChunkingConfig(max_chunk_size=5, overlap_size=0))

    assert result.document_id == "doc-42"
    assert result.file_name == "report.pdf"
    assert str(result.file_path) == "/data/report.pdf"
    assert result.document_type == "report"
    assert all(chunk.document_id == "doc-42" for chunk in result.chunks)


def test_chunk_document_records_chunking_strategy(make_normalized_document):
    document = make_normalized_document(["some text"], full_text="some text")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=5, overlap_size=0))

    assert result.chunking_strategy == "characters"


def test_chunk_document_computed_totals_match_chunks(make_normalized_document):
    document = make_normalized_document(["hello world foo bar"], full_text="hello world foo bar")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=7, overlap_size=2))

    assert result.chunk_count == len(result.chunks)
    assert result.total_word_count == sum(c.word_count for c in result.chunks)
    assert result.total_char_count == sum(c.char_count for c in result.chunks)


def test_chunk_document_uses_default_config_when_none_given(make_normalized_document):
    document = make_normalized_document(["short text"], full_text="short text")
    result = chunk_document(document)

    assert result.chunk_count == 1
    assert result.chunks[0].text == "short text"


def test_chunk_document_page_numbers_reflect_overlapping_pages(make_normalized_document):
    texts = ["Page one content here.", "Page two content here."]
    document = make_normalized_document(texts)  # full_text joins with "\n\n"

    result = chunk_document(document, ChunkingConfig(max_chunk_size=30, overlap_size=0))

    assert result.chunks[0].page_numbers == [1, 2]
    assert result.chunks[1].page_numbers == [2]


# --- edge cases ---


def test_empty_document_returns_zero_chunks(make_normalized_document):
    document = make_normalized_document([""], full_text="")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=100, overlap_size=10))

    assert result.chunks == []
    assert result.chunk_count == 0


def test_document_smaller_than_chunk_size_returns_a_single_chunk(make_normalized_document):
    document = make_normalized_document(["short text"], full_text="short text")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=1000, overlap_size=200))

    assert len(result.chunks) == 1
    assert result.chunks[0].text == "short text"
    assert result.chunks[0].start_char == 0
    assert result.chunks[0].end_char == len("short text")


def test_final_chunk_is_not_padded(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text="ABCDEFGHIJKL")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=5, overlap_size=0))

    last_chunk = result.chunks[-1]
    assert last_chunk.text == "KL"
    assert last_chunk.char_count == 2
    assert len(last_chunk.text) < 5


def test_overlap_zero_produces_contiguous_non_overlapping_chunks(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text="ABCDEFGHIJKL")
    result = chunk_document(document, ChunkingConfig(max_chunk_size=4, overlap_size=0))

    assert [c.text for c in result.chunks] == ["ABCD", "EFGH", "IJKL"]
    for earlier, later in zip(result.chunks, result.chunks[1:]):
        assert earlier.end_char == later.start_char


@pytest.mark.parametrize("overlap_size", [10, 15])
def test_overlap_size_greater_or_equal_to_max_chunk_size_is_invalid(make_normalized_document, overlap_size):
    document = make_normalized_document(["some reasonably long piece of text"])

    with pytest.raises(ValueError):
        chunk_document(document, ChunkingConfig(max_chunk_size=10, overlap_size=overlap_size))


def test_whitespace_only_chunks_are_skipped(make_normalized_document):
    # Simulates text normalization missing a run of whitespace: the sliding
    # window would otherwise carve out chunks that are pure whitespace.
    full_text = "AAAAA" + " " * 10 + "BBBBB"
    document = make_normalized_document(["AAAAA", "BBBBB"], full_text=full_text)

    result = chunk_document(document, ChunkingConfig(max_chunk_size=5, overlap_size=0))

    assert [c.text for c in result.chunks] == ["AAAAA", "BBBBB"]
    assert all(chunk.text.strip() for chunk in result.chunks)
    # chunk_index stays sequential over the retained chunks, no gaps left by skips.
    assert [c.chunk_index for c in result.chunks] == [0, 1]
    # but original offsets into full_text are preserved, not renumbered.
    assert result.chunks[1].start_char == 15
    assert result.chunks[1].end_char == 20


# --- structural strategy (v2.1) ---


def _normalized(make_extract_document, texts):
    return normalize_document(make_extract_document(texts))


def test_structural_strategy_packs_headings_paragraphs_lists_and_tables_atomically(make_extract_document):
    text = (
        "IMPORTANT NOTICE:\n\n"
        "This is a simple paragraph explaining something in detail for testing purposes.\n\n"
        "- First item in the list\n"
        "- Second item in the list\n"
        "- Third item in the list\n\n"
        "Name | Role | Score\n"
        "Alice | Engineer | 90\n"
        "Bob | Manager | 85\n"
    )
    document = _normalized(make_extract_document, [text])

    result = chunk_document(document, ChunkingConfig(max_chunk_size=60, overlap_size=0, chunking_strategy="structural"))

    assert result.chunking_strategy == "structural"
    assert [c.text for c in result.chunks] == [
        "IMPORTANT NOTICE:",
        "This is a simple paragraph explaining something in detail for testing purposes.",
        "- First item in the list\n- Second item in the list",
        "- Third item in the list\n\nName | Role | Score",
        "Alice | Engineer | 90\nBob | Manager | 85",
    ]


def test_structural_strategy_closes_chunk_before_element_that_would_overflow(make_extract_document):
    document = _normalized(
        make_extract_document,
        ["- First item in the list\n- Second item in the list\n- Third item in the list"],
    )

    result = chunk_document(document, ChunkingConfig(max_chunk_size=50, overlap_size=0, chunking_strategy="structural"))

    assert result.chunks[0].text == "- First item in the list\n- Second item in the list"
    assert result.chunks[1].text == "- Third item in the list"
    assert all(len(c.text) <= 50 for c in result.chunks)


def test_structural_strategy_splits_oversized_paragraph_at_sentence_boundaries(make_extract_document):
    sentences = [f"This is sentence number {i} in a very long paragraph. " for i in range(1, 6)]
    text = "".join(sentences).strip()
    document = _normalized(make_extract_document, [text])

    result = chunk_document(document, ChunkingConfig(max_chunk_size=60, overlap_size=0, chunking_strategy="structural"))

    assert len(result.chunks) > 1
    for chunk in result.chunks:
        # Every chunk boundary lands on a sentence boundary, never mid-sentence.
        assert chunk.text.rstrip().endswith(".")


def test_structural_strategy_allows_chunks_to_span_page_boundaries(make_extract_document):
    document = _normalized(
        make_extract_document,
        ["This is page one paragraph.", "This is page two paragraph."],
    )

    result = chunk_document(document, ChunkingConfig(max_chunk_size=200, overlap_size=0, chunking_strategy="structural"))

    assert len(result.chunks) == 1
    assert result.chunks[0].page_numbers == [1, 2]


def test_structural_strategy_produces_no_overlap_between_chunks(make_extract_document):
    text = (
        "- First item in the list\n"
        "- Second item in the list\n"
        "- Third item in the list\n\n"
        "Name | Role | Score\n"
        "Alice | Engineer | 90\n"
    )
    document = _normalized(make_extract_document, [text])

    result = chunk_document(document, ChunkingConfig(max_chunk_size=50, overlap_size=0, chunking_strategy="structural"))

    for earlier, later in zip(result.chunks, result.chunks[1:]):
        assert later.start_char >= earlier.end_char


# --- structural context propagation (v2.2) ---


def test_context_disabled_by_default_reproduces_v21_output(make_extract_document):
    text = "WEEK 4 OVERVIEW\n\n- Master Git basics\n- Call public REST APIs\n- Push to GitHub\n"
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=50, overlap_size=0, chunking_strategy="structural")

    with_flag_off = chunk_document(document, config)
    without_flag = chunk_document(document, config.model_copy(update={"propagate_context": False}))

    assert [(c.start_char, c.end_char, c.text) for c in with_flag_off.chunks] == [
        (c.start_char, c.end_char, c.text) for c in without_flag.chunks
    ]
    assert all(c.context_prefix == "" for c in with_flag_off.chunks)


def test_orphaned_chunk_gets_governing_heading_prepended(make_extract_document):
    text = (
        "WEEK 4 OVERVIEW\n\n"
        "- Master Git basics\n"
        "- Call public REST APIs\n"
        "- Push your first project to GitHub\n"
        "- Build: Weather CLI app using a public API\n"
    )
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=67, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    assert result.chunks[0].context_prefix == ""
    assert result.chunks[0].text.startswith("WEEK 4 OVERVIEW")
    assert result.chunks[1].context_prefix == "WEEK 4 OVERVIEW"
    assert "WEEK 4 OVERVIEW" not in result.chunks[1].text


def test_chunk_opening_on_its_own_heading_gets_no_prefix(make_extract_document):
    text = "WEEK 4 OVERVIEW\n\n- item one\n\nWEEK 9 OVERVIEW\n\n- item two\n"
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=16, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    heading_chunks = [c for c in result.chunks if c.text.startswith("WEEK")]
    assert heading_chunks
    assert all(c.context_prefix == "" for c in heading_chunks)


def test_table_continuation_gets_heading_and_header_row_prepended(make_extract_document):
    text = (
        "TABLE OVERVIEW\n\n"
        "Name | Role | Score\n"
        "Alice | Engineer | 90\n"
        "Bob | Manager | 85\n"
    )
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=55, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    continuation_chunks = [c for c in result.chunks if c.text.startswith("Alice") or c.text.startswith("Bob")]
    assert continuation_chunks
    for chunk in continuation_chunks:
        assert chunk.context_prefix == "TABLE OVERVIEW\nName | Role | Score"
        # The header row is never redundantly repeated inside its own chunk.
        assert chunk.text.count("Name | Role | Score") == 0


def test_table_split_across_page_break_inherits_header_from_previous_page(make_extract_document):
    # normalize_page runs per-page, so a table that continues onto the next page becomes
    # two blocks: page 1's has the header, page 2's starts straight into data rows and
    # has no header of its own (a numeric first row can never look like a header row).
    document = _normalized(
        make_extract_document,
        [
            "SALES REPORT\n\nName | Region | Amount\nAlice | East | 100\nBob | West | 200\n",
            "Carl | North | 150\nDana | South | 175\n",
        ],
    )
    config = ChunkingConfig(max_chunk_size=40, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    page_two_chunks = [c for c in result.chunks if 2 in c.page_numbers]
    assert page_two_chunks
    for chunk in page_two_chunks:
        assert chunk.context_prefix == "SALES REPORT\nName | Region | Amount"


def test_table_continuation_header_resets_after_non_table_block(make_extract_document):
    # An unrelated table on page 2, separated from page 1's table by a paragraph, must
    # not inherit page 1's header - the run of table units is broken by the paragraph.
    document = _normalized(
        make_extract_document,
        [
            "Name | Region | Amount\nAlice | East | 100\n",
            "This is an unrelated paragraph that closes out the section for readers today.\n\nX | Y\n1 | 2\n",
        ],
    )
    config = ChunkingConfig(max_chunk_size=40, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    # The header row is no longer left stranded alone (v2.2 fix): it now packs together
    # with its own row in one chunk rather than repeating a fallback context that would
    # have leaked page 1's unrelated header.
    unrelated_table_chunk = next(c for c in result.chunks if "1 | 2" in c.text)
    assert "Name | Region | Amount" not in unrelated_table_chunk.context_prefix
    assert "Name | Region | Amount" not in unrelated_table_chunk.text


def test_table_header_never_emitted_alone_when_it_cannot_share_a_chunk_with_a_row(make_extract_document):
    # The header row alone fits under max_chunk_size, but header + even one data row does
    # not. The header must never open a chunk with zero rows attached to it - instead the
    # next row is forced in anyway, and that chunk is allowed to exceed max_chunk_size.
    header = "A_Very_Long_Column_Name_One | Another_Extremely_Long_Column_Name_Two | Third_Column"
    row1 = "1 | 2 | 3"
    row2 = "4 | 5 | 6"
    text = f"{header}\n{row1}\n{row2}\n"
    document = _normalized(make_extract_document, [text])
    max_chunk_size = len(header) + 5
    config = ChunkingConfig(
        max_chunk_size=max_chunk_size, overlap_size=0, chunking_strategy="structural", propagate_context=True
    )

    result = chunk_document(document, config)

    header_only_chunks = [c for c in result.chunks if c.text.strip() == header]
    assert header_only_chunks == []

    first_chunk = next(c for c in result.chunks if c.text.startswith(header))
    assert first_chunk.text == f"{header}\n{row1}"
    assert first_chunk.context_prefix == ""
    assert (first_chunk.end_char - first_chunk.start_char) > max_chunk_size

    second_chunk = next(c for c in result.chunks if row2 in c.text)
    assert second_chunk.context_prefix == header
    assert row1 not in second_chunk.text


def test_table_header_and_row_pack_together_when_they_fit(make_extract_document):
    # The normal, common case: header + row comfortably fit together, so no forcing is
    # needed and the chunk stays within max_chunk_size.
    text = "Name | Role | Score\nAlice | Engineer | 90\n"
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=1000, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    assert len(result.chunks) == 1
    assert result.chunks[0].text == "Name | Role | Score\nAlice | Engineer | 90"
    assert result.chunks[0].end_char - result.chunks[0].start_char <= config.max_chunk_size


def test_no_heading_falls_back_to_previous_units_text(make_extract_document):
    text = "- alpha item\n- beta item\n- gamma item\n"
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=15, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    assert result.chunks[0].context_prefix == ""
    for earlier, later in zip(result.chunks, result.chunks[1:]):
        assert later.context_prefix == earlier.text


def test_contextualized_text_combines_prefix_and_text(make_extract_document):
    text = "WEEK 4 OVERVIEW\n\n- item one\n- item two\n"
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(max_chunk_size=30, overlap_size=0, chunking_strategy="structural", propagate_context=True)

    result = chunk_document(document, config)

    for chunk in result.chunks:
        if chunk.context_prefix:
            assert chunk.contextualized_text == f"{chunk.context_prefix}\n{chunk.text}"
        else:
            assert chunk.contextualized_text == chunk.text


def test_context_prefix_counts_against_max_chunk_size_budget(make_extract_document):
    text = (
        "WEEK 4 OVERVIEW\n\n"
        "- Master Git basics\n"
        "- Call public REST APIs\n"
        "- Push your first project to GitHub\n"
        "- Build: Weather CLI app using a public API\n"
    )
    document = _normalized(make_extract_document, [text])
    max_chunk_size = 67
    config = ChunkingConfig(
        max_chunk_size=max_chunk_size, overlap_size=0, chunking_strategy="structural", propagate_context=True
    )

    result = chunk_document(document, config)

    for chunk in result.chunks:
        own_size = chunk.end_char - chunk.start_char
        reserved = len(chunk.context_prefix) + 1 if chunk.context_prefix else 0
        # Own content is packed to fit within the reduced budget (no unit in this
        # text is individually oversized, so the single-oversized-unit exception
        # never kicks in here).
        assert own_size <= max_chunk_size - reserved
