from src.document_chunker.chunker import chunk_document
from src.document_chunker.normalizer import normalize_document
from src.document_chunker.quality import evaluate_chunk_quality, format_quality_comparison
from src.document_chunker.schemas import ChunkingConfig


def _normalized(make_extract_document, texts):
    return normalize_document(make_extract_document(texts))


_MIXED_TEXT = (
    "IMPORTANT NOTICE\n\n"
    "This is a simple paragraph explaining something in detail for testing purposes.\n\n"
    "- First item in the list\n"
    "- Second item in the list\n"
    "- Third item in the list\n\n"
    "Name | Role | Score\n"
    "Alice | Engineer | 90\n"
    "Bob | Manager | 85\n"
)


# --- avg utilization / tiny chunks ---


def test_avg_utilization_is_full_for_tightly_packed_character_chunks(
    make_normalized_document,
):
    full_text = "ABCDEFGHIJKLMNOPQ"  # 17 chars
    document = make_normalized_document([full_text], full_text=full_text)
    config = ChunkingConfig(
        max_chunk_size=5, overlap_size=0, chunking_strategy="characters"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    # 3 full 5-char chunks + a final 2-char chunk: (1 + 1 + 1 + 0.4) / 4 == 0.85
    assert report.chunk_count == 4
    assert report.avg_utilization == 0.85


def test_tiny_chunk_ratio_flags_chunks_under_ten_percent_of_max_size(
    make_normalized_document,
):
    # Final chunk is 2 chars, well under 10% of a 100-char max - it's the only tiny one.
    document = make_normalized_document(["A" * 22], full_text="A" * 22)
    config = ChunkingConfig(
        max_chunk_size=100, overlap_size=0, chunking_strategy="characters"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.tiny_chunk_count == 0
    assert report.tiny_chunk_ratio == 0.0


# --- structural splits, evaluated against the document's own structure ---


def test_character_strategy_splits_words_bullets_and_table_rows(make_extract_document):
    document = _normalized(make_extract_document, [_MIXED_TEXT])
    config = ChunkingConfig(
        max_chunk_size=40, overlap_size=0, chunking_strategy="characters"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.word_splits > 0
    assert report.bullet_splits > 0
    assert report.table_row_splits > 0


def test_structural_strategy_never_splits_words_bullets_or_table_rows(
    make_extract_document,
):
    document = _normalized(make_extract_document, [_MIXED_TEXT])
    config = ChunkingConfig(
        max_chunk_size=40, overlap_size=0, chunking_strategy="structural"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.word_splits == 0
    assert report.bullet_splits == 0
    assert report.table_row_splits == 0


def test_word_split_requires_boundary_strictly_inside_a_token(make_extract_document):
    # A boundary landing exactly on the space between two words is not a word split.
    document = _normalized(make_extract_document, ["hello world"])
    assert document.full_text == "hello world"
    config = ChunkingConfig(
        max_chunk_size=5, overlap_size=0, chunking_strategy="characters"
    )
    result = chunk_document(document, config)
    assert [c.text for c in result.chunks] == ["hello", " worl", "d"]

    report = evaluate_chunk_quality(document, result, config)

    assert report.word_splits == 1  # only the "worl"/"d" cut is mid-word


# --- context overhead / coverage ---


def test_overlap_overhead_is_zero_when_no_overlap_configured(make_normalized_document):
    document = make_normalized_document(["A" * 30], full_text="A" * 30)
    config = ChunkingConfig(
        max_chunk_size=10, overlap_size=0, chunking_strategy="characters"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.context_overhead == 0.0
    assert report.overhead_source == "none"
    assert report.context_coverage is None


def test_overlap_overhead_is_positive_when_overlap_configured(make_normalized_document):
    document = make_normalized_document(["A" * 30], full_text="A" * 30)
    config = ChunkingConfig(
        max_chunk_size=10, overlap_size=3, chunking_strategy="characters"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.context_overhead > 0
    assert report.overhead_source == "overlap"
    assert report.context_coverage is None


def test_structural_without_context_carry_has_no_overhead_and_no_coverage(
    make_extract_document,
):
    document = _normalized(make_extract_document, [_MIXED_TEXT])
    config = ChunkingConfig(
        max_chunk_size=40,
        overlap_size=0,
        chunking_strategy="structural",
        propagate_context=False,
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.context_overhead == 0.0
    assert report.overhead_source == "none"
    assert report.context_coverage is None


def test_structural_with_context_carry_reports_overhead_and_full_coverage(
    make_extract_document,
):
    document = _normalized(make_extract_document, [_MIXED_TEXT])
    config = ChunkingConfig(
        max_chunk_size=40,
        overlap_size=0,
        chunking_strategy="structural",
        propagate_context=True,
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.overhead_source == "context_prefix"
    assert report.context_overhead > 0
    # Every non-heading-opening chunk gets a context_prefix by construction.
    assert report.context_coverage == 1.0


def test_context_coverage_exempts_the_documents_opening_paragraph(make_extract_document):
    """The document's very first structural unit has no governing heading and no previous
    unit to fall back on, so _resolve_context_prefix() legitimately has nothing to attach -
    even a fully working pipeline can't give it a context_prefix. _context_coverage() exempts
    that opening chunk the same way it exempts heading-opening chunks, rather than counting
    it as a miss no fix could ever satisfy. Every later chunk that opens without its own
    heading is still held to the normal standard."""
    text = (
        "This is a simple paragraph explaining something in detail for testing purposes.\n\n"
        "IMPORTANT NOTICE\n\n"
        "This is a simple paragraph explaining something in detail for testing purposes.\n\n"
    )
    document = _normalized(make_extract_document, [text])
    config = ChunkingConfig(
        max_chunk_size=40,
        overlap_size=0,
        chunking_strategy="structural",
        propagate_context=True,
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    opening_chunk, heading_chunk, later_chunk = result.chunks
    assert opening_chunk.context_prefix == ""  # no heading exists yet - exempt, not a miss
    assert heading_chunk.context_prefix == ""  # opens on its own heading - exempt, not a miss
    assert later_chunk.context_prefix == "IMPORTANT NOTICE"  # heading now exists - satisfied

    # Only later_chunk needs context; it got one, so coverage is full.
    assert report.context_coverage == 1.0


# --- validity delegates to the existing validator ---


def test_is_valid_reflects_validate_chunks(make_normalized_document):
    document = make_normalized_document(["ABCDEFGHIJKL"], full_text="ABCDEFGHIJKL")
    config = ChunkingConfig(
        max_chunk_size=5, overlap_size=2, chunking_strategy="characters"
    )
    result = chunk_document(document, config)

    report = evaluate_chunk_quality(document, result, config)

    assert report.is_valid is True


# --- comparison table formatting ---


def test_format_quality_comparison_includes_every_metric_and_label(
    make_extract_document,
):
    document = _normalized(make_extract_document, [_MIXED_TEXT])
    reports = {}
    for label, strategy, propagate in [
        ("V1", "characters", False),
        ("V2.1", "structural", False),
        ("V2.2", "structural", True),
    ]:
        config = ChunkingConfig(
            max_chunk_size=40,
            overlap_size=5 if strategy == "characters" else 0,
            chunking_strategy=strategy,
            propagate_context=propagate,
        )
        result = chunk_document(document, config)
        reports[label] = evaluate_chunk_quality(document, result, config)

    table = format_quality_comparison(reports)

    for label in reports:
        assert label in table
    for metric in [
        "Valid",
        "Chunks",
        "Avg utilization",
        "Tiny chunks",
        "Context coverage",
    ]:
        assert metric in table
    assert "N/A" in table  # V1 and V2.1 have no context-coverage mechanism
    assert "*" in table  # V1's overlap-based overhead is footnoted


def test_format_quality_comparison_empty_reports_is_empty_string():
    assert format_quality_comparison({}) == ""
