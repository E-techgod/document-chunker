import pytest

from document_chunker.chunker import chunk_document
from document_chunker.evaluator import (
    COVERAGE,
    MAX_SIZE,
    OFFSETS,
    ORDER,
    OVERLAP,
    TRACEABILITY,
    validate_chunks,
)
from document_chunker.schemas import ChunkingConfig, ChunkingResult, DocumentChunk


# --- valid chunkings pass cleanly ---


def test_valid_chunking_from_chunk_document_has_no_issues(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text="ABCDEFGHIJKL")
    config = ChunkingConfig(max_chunk_size=5, overlap_size=2)
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert report.is_valid
    assert report.issues == []
    assert report.document_id == document.document_id


def test_valid_chunking_with_skipped_whitespace_chunk_has_no_issues(make_normalized_document):
    full_text = "AAAAA" + " " * 10 + "BBBBB"
    document = make_normalized_document(["AAAAA", "BBBBB"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert report.is_valid


def test_empty_document_has_no_issues(make_normalized_document):
    document = make_normalized_document([""], full_text="")
    config = ChunkingConfig(max_chunk_size=100, overlap_size=10)
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert report.is_valid


# --- invariant 1: order preservation ---


def test_out_of_order_chunk_index_is_flagged(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJ"], full_text="ABCDEFGHIJ")
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = chunk_document(document, config)
    result.chunks[0], result.chunks[1] = result.chunks[1], result.chunks[0]

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == ORDER for issue in report.issues)


# --- invariant 2: maximum size ---


def test_oversized_chunk_is_flagged(make_normalized_document):
    full_text = "ABCDEFGHIJ"
    document = make_normalized_document(["ABCDEFGHIJ"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=0,
                end_char=10,
                text=full_text,
                word_count=1,
                char_count=10,
            )
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == MAX_SIZE for issue in report.issues)


def test_oversized_chunk_is_not_flagged_under_structural_strategy(make_normalized_document):
    # The structural strategy treats max_chunk_size as a soft target: a single
    # unsplittable element (e.g. one long sentence) may legitimately overflow it.
    full_text = "ABCDEFGHIJ"
    document = make_normalized_document(["ABCDEFGHIJ"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0, chunking_strategy="structural")
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunking_strategy="structural",
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=0,
                end_char=10,
                text=full_text,
                word_count=1,
                char_count=10,
            )
        ],
    )

    report = validate_chunks(document, result, config)

    assert report.is_valid
    assert not any(issue.invariant == MAX_SIZE for issue in report.issues)


# --- invariant 3: correct overlap ---


def test_wrong_overlap_between_adjacent_full_sized_chunks_is_flagged(make_normalized_document):
    full_text = "ABCDEFGHIJKL"
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=2)
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=0,
                end_char=5,
                text=full_text[0:5],
                word_count=1,
                char_count=5,
            ),
            # Should start at 3 (5 - overlap_size 2) to overlap correctly; starts at 5 instead.
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_1",
                chunk_index=1,
                start_char=5,
                end_char=10,
                text=full_text[5:10],
                word_count=1,
                char_count=5,
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == OVERLAP for issue in report.issues)


def test_overlap_not_checked_across_a_skipped_whitespace_chunk(make_normalized_document):
    # With overlap_size=0 and a 10-char whitespace gap, chunk_document skips two
    # whitespace-only spans, leaving a real gap between the "AAAAA" and "BBBBB"
    # chunks in the output. That gap must not be held to the overlap formula.
    full_text = "AAAAA" + " " * 10 + "BBBBB"
    document = make_normalized_document(["AAAAA", "BBBBB"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = chunk_document(document, config)
    assert result.chunk_count == 2  # sanity check: the skip actually happened

    report = validate_chunks(document, result, config)

    assert not any(issue.invariant == OVERLAP for issue in report.issues)


# --- invariant 4: coverage ---


def test_missing_non_whitespace_coverage_is_flagged(make_normalized_document):
    full_text = "ABCDEFGHIJ"
    document = make_normalized_document(["ABCDEFGHIJ"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=0,
                end_char=5,
                text=full_text[0:5],
                word_count=1,
                char_count=5,
            ),
            # Gap [5:10) is dropped entirely, unlike the whitespace-skip case.
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == COVERAGE for issue in report.issues)


def test_whitespace_only_gap_is_not_flagged_as_missing_coverage(make_normalized_document):
    full_text = "AAAAA" + " " * 10 + "BBBBB"
    document = make_normalized_document(["AAAAA", "BBBBB"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert not any(issue.invariant == COVERAGE for issue in report.issues)


# --- invariant 5: traceability ---


def test_chunk_text_not_matching_full_text_slice_is_flagged(make_normalized_document):
    full_text = "ABCDEFGHIJ"
    document = make_normalized_document(["ABCDEFGHIJ"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=0,
                end_char=5,
                text="wrong",
                word_count=1,
                char_count=5,
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == TRACEABILITY for issue in report.issues)


# --- invariant 6: offsets ---


def test_out_of_bounds_offsets_are_flagged(make_normalized_document):
    full_text = "ABCDEFGHIJ"
    document = make_normalized_document(["ABCDEFGHIJ"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=0,
                end_char=50,
                text=full_text,
                word_count=1,
                char_count=len(full_text),
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == OFFSETS for issue in report.issues)


def test_start_char_out_of_order_is_flagged(make_normalized_document):
    full_text = "ABCDEFGHIJ"
    document = make_normalized_document(["ABCDEFGHIJ"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = ChunkingResult(
        document_id=document.document_id,
        file_name=document.file_name,
        file_path=document.file_path,
        chunks=[
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_0",
                chunk_index=0,
                start_char=5,
                end_char=10,
                text=full_text[5:10],
                word_count=1,
                char_count=5,
            ),
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_1",
                chunk_index=1,
                start_char=0,
                end_char=5,
                text=full_text[0:5],
                word_count=1,
                char_count=5,
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == OFFSETS for issue in report.issues)
