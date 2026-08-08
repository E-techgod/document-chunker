import pytest

from document_chunker.chunker import chunk_document
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
