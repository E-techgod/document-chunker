
from src.document_chunker.chunking.chunker import chunk_document
from src.document_chunker.chunking.evaluator import (
    ATOMIC_ELEMENT_COVERAGE,
    ELEMENT_ORDER,
    MAX_SIZE,
    NON_WHITESPACE_COVERAGE,
    OFFSETS,
    ORDER,
    OVERLAP,
    STRUCTURAL_INTEGRITY,
    TRACEABILITY,
    validate_chunks,
)
from src.document_chunker.normalization.normalizer import normalize_document
from src.document_chunker.schemas import (
    ChunkingConfig,
    ChunkingResult,
    DocumentChunk,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedPage,
)

# --- valid chunkings pass cleanly ---


def test_valid_chunking_from_chunk_document_has_no_issues(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text="ABCDEFGHIJKL")
    config = ChunkingConfig(max_chunk_size=5, overlap_size=2)
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert report.is_valid
    assert report.issues == []
    assert report.document_id == document.document_id


def test_valid_chunking_with_skipped_whitespace_chunk_has_no_issues(
    make_normalized_document,
):
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


def test_oversized_chunk_is_not_flagged_under_structural_strategy(
    make_extract_document,
):
    # The structural strategy treats max_chunk_size as a soft target: a single
    # unsplittable element (e.g. one long run-on sentence, no punctuation to split on)
    # may legitimately overflow it.
    text = ("word " * 40).strip() + "."
    document = normalize_document(make_extract_document([text]))
    config = ChunkingConfig(
        max_chunk_size=50, overlap_size=0, chunking_strategy="structural"
    )
    result = chunk_document(document, config)
    assert (
        len(result.chunks) == 1
    )  # sanity check: the whole thing stayed one oversized chunk
    assert len(result.chunks[0].text) > config.max_chunk_size

    report = validate_chunks(document, result, config)

    assert report.is_valid
    assert not any(issue.invariant == MAX_SIZE for issue in report.issues)


def test_oversized_chunk_from_multiple_packed_elements_is_still_flagged_under_structural_strategy(
    make_extract_document,
):
    # Unlike a single unsplittable element, a chunk that overflows max_chunk_size because
    # several elements were packed together is still a bug, not a legitimate exception.
    text = "- first item\n- second item"
    document = normalize_document(make_extract_document([text]))
    # Both items are well under 20 chars, so neither is individually oversized.
    config = ChunkingConfig(
        max_chunk_size=20, overlap_size=0, chunking_strategy="structural"
    )
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
                end_char=len(document.full_text),
                text=document.full_text,
                word_count=1,
                char_count=len(document.full_text),
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == MAX_SIZE for issue in report.issues)


def test_forced_table_header_row_pair_is_not_flagged_under_context_propagation(
    make_extract_document,
):
    # A table header row that can't share a chunk with even one row gets forced to pair
    # with the next row anyway (see chunker._pack_table_run), rather than ever being
    # emitted alone. That forced pair is a legitimate oversized exception, like a single
    # unsplittable element.
    header = "A_Very_Long_Column_Name_One | Another_Extremely_Long_Column_Name_Two | Third_Column"
    text = f"{header}\n1 | 2 | 3\n4 | 5 | 6\n"
    document = normalize_document(make_extract_document([text]))
    config = ChunkingConfig(
        max_chunk_size=len(header) + 5,
        overlap_size=0,
        chunking_strategy="structural",
        propagate_context=True,
    )
    result = chunk_document(document, config)
    forced_chunk = next(c for c in result.chunks if c.text.startswith(header))
    assert (
        forced_chunk.end_char - forced_chunk.start_char
    ) > config.max_chunk_size  # sanity check

    report = validate_chunks(document, result, config)

    assert report.is_valid
    assert not any(issue.invariant == MAX_SIZE for issue in report.issues)


def test_oversized_multi_row_table_chunk_is_still_flagged_under_context_propagation(
    make_extract_document,
):
    # A chunk spanning a header plus two rows, when header+first-row alone would already
    # have fit, is not a legitimate forced pairing - it's still a bug and must be flagged.
    text = "X | Y\n1 | 2\n3 | 4\n"
    document = normalize_document(make_extract_document([text]))
    config = ChunkingConfig(
        max_chunk_size=10,
        overlap_size=0,
        chunking_strategy="structural",
        propagate_context=True,
    )
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
                end_char=len(document.full_text),
                text=document.full_text,
                word_count=1,
                char_count=len(document.full_text),
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == MAX_SIZE for issue in report.issues)


# --- invariant 3: correct overlap ---


def test_wrong_overlap_between_adjacent_full_sized_chunks_is_flagged(
    make_normalized_document,
):
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


def test_overlap_not_checked_across_a_skipped_whitespace_chunk(
    make_normalized_document,
):
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
    assert any(issue.invariant == NON_WHITESPACE_COVERAGE for issue in report.issues)


def test_whitespace_only_gap_is_not_flagged_as_missing_coverage(
    make_normalized_document,
):
    full_text = "AAAAA" + " " * 10 + "BBBBB"
    document = make_normalized_document(["AAAAA", "BBBBB"], full_text=full_text)
    config = ChunkingConfig(max_chunk_size=5, overlap_size=0)
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert not any(
        issue.invariant == NON_WHITESPACE_COVERAGE for issue in report.issues
    )


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


# --- structural-only invariants (v2.1) ---


def test_valid_structural_chunking_has_no_issues(make_extract_document):
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
    document = normalize_document(make_extract_document([text]))
    config = ChunkingConfig(
        max_chunk_size=60, overlap_size=0, chunking_strategy="structural"
    )
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert report.is_valid
    assert report.issues == []


def test_overlapping_structural_elements_are_flagged(make_extract_document):
    # Elements are extracted from block offsets; a bug there could make two
    # elements overlap or run backwards. Hand-build that broken state directly.
    page = NormalizedPage(
        page_number=1,
        text="ABCDEFGHIJ",
        blocks=[
            NormalizedBlock(
                block_type="paragraph", text="ABCDE", start_char=0, end_char=5
            ),
            NormalizedBlock(
                block_type="paragraph", text="DEFGH", start_char=3, end_char=8
            ),
        ],
    )
    document = NormalizedDocument(
        document_id="doc1",
        file_name="doc1.pdf",
        file_path="/tmp/doc1.pdf",
        pages=[page],
        full_text="ABCDEFGHIJ",
    )
    config = ChunkingConfig(
        max_chunk_size=100, overlap_size=0, chunking_strategy="structural"
    )
    result = chunk_document(document, config)

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == ELEMENT_ORDER for issue in report.issues)


def test_element_split_across_chunks_is_flagged(make_extract_document):
    document = normalize_document(make_extract_document(["ABCDEFGHIJ"]))
    config = ChunkingConfig(
        max_chunk_size=100, overlap_size=0, chunking_strategy="structural"
    )
    # The whole page is one paragraph element; hand-split it across two chunks,
    # which a correct structural chunker would never do for a non-oversized element.
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
                end_char=5,
                text=document.full_text[0:5],
                word_count=1,
                char_count=5,
            ),
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_1",
                chunk_index=1,
                start_char=5,
                end_char=10,
                text=document.full_text[5:10],
                word_count=1,
                char_count=5,
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == ATOMIC_ELEMENT_COVERAGE for issue in report.issues)


def test_chunk_boundary_splitting_a_bullet_is_flagged(make_extract_document):
    document = normalize_document(make_extract_document(["- item one\n- item two"]))
    config = ChunkingConfig(
        max_chunk_size=100, overlap_size=0, chunking_strategy="structural"
    )
    # Cuts the first bullet in half instead of landing on an item/sentence boundary.
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
                end_char=5,
                text=document.full_text[0:5],
                word_count=1,
                char_count=5,
            ),
            DocumentChunk(
                document_id=document.document_id,
                chunk_id="doc1_chunk_1",
                chunk_index=1,
                start_char=5,
                end_char=len(document.full_text),
                text=document.full_text[5:],
                word_count=1,
                char_count=len(document.full_text) - 5,
            ),
        ],
    )

    report = validate_chunks(document, result, config)

    assert not report.is_valid
    assert any(issue.invariant == STRUCTURAL_INTEGRITY for issue in report.issues)
