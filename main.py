import sys
from pathlib import Path
from pydantic import ValidationError

from src.document_chunker.extractor import PDFExtractionError, extract_pdf
from src.document_chunker.loader import PDFLoadError, load_pdf
from src.document_chunker.schemas import PDFDocumentInput
from src.document_chunker.normalizer import normalize_document, normalize_text
from src.document_chunker.counting import count_words
from src.document_chunker.chunker import chunk_document, ChunkingConfig, ChunkingResult, DocumentChunk, NormalizedDocument
from src.document_chunker.evaluator import validate_chunks

def main() -> None:
    # Use CLI argument if provided; otherwise, fall back to default path
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample.pdf"
    password = sys.argv[2] if len(sys.argv) > 2 else ""

    try:
        document = PDFDocumentInput(path=Path(path))
    except ValidationError as exc:
        print(f"Invalid input: {exc}")
        sys.exit(1)

    try:
        reader = load_pdf(document, password=password)
    except PDFLoadError as exc:
        print(f"Failed to load PDF: {exc}")
        sys.exit(1)

    """print(f"\nLoaded: {document.path}")
    print(f"Document ID: {document.document_id or document.path.stem}")
    print(f"Document Type: {document.document_type or 'Not provided'}")
    print(f"Encrypted: {reader.is_encrypted}")
    print(f"Pages: {len(reader.pages)}\n")"""

    try:
        extracted = extract_pdf(document, reader)
    except PDFExtractionError as exc:
        print(f"Failed to extract PDF: {exc}")
        sys.exit(1)

    """print("Extraction complete: Raw text extracted from PDF pages.")
    #print(f"Full text: {extracted.full_text}")
    print(f"Extracted pages: {extracted.page_count}")
    print(f"Total words: {extracted.word_count}")
    print(f"Total chars: {extracted.char_count}\n")"""

    normalized = normalize_document(extracted)

    """print("Normalization complete: Text cleaned and normalized.")
    #print(f"Full text normalized: \n{normalized.full_text}\n") 
    print(f"Extracted normalized pages: {normalized.page_count}")
    print(f"Total normalized words: {normalized.word_count}")
    print(f"Total normalized chars: {normalized.char_count}\n")"""

    chunking_config = ChunkingConfig(max_chunk_size=1000, overlap_size=100)
    chunker = chunk_document(normalized, config=chunking_config)
    """print("Chunking complete: Document split into overlapping character chunks.")
    print(f"Total chunks created: {len(chunker.chunks)}")
    print(f"Chunk 0 : range {chunker.chunks[0].start_char}-{chunker.chunks[0].end_char}: {chunker.chunks[0].char_count} chars, {chunker.chunks[0].word_count} words")
    print(f"Chunk 1 : range {chunker.chunks[1].start_char}-{chunker.chunks[1].end_char}: {chunker.chunks[1].char_count} chars, {chunker.chunks[1].word_count} words")
    print(f"Chunk 2 : range {chunker.chunks[2].start_char}-{chunker.chunks[2].end_char}: {chunker.chunks[2].char_count} chars, {chunker.chunks[2].word_count} words")
    print(f"Chunk 3 : range {chunker.chunks[3].start_char}-{chunker.chunks[3].end_char}: {chunker.chunks[3].char_count} chars, {chunker.chunks[3].word_count} words")
    print(f"Chunk 4 : range {chunker.chunks[4].start_char}-{chunker.chunks[4].end_char}: {chunker.chunks[4].char_count} chars, {chunker.chunks[4].word_count} words")
    print(f"Chunk 5 : range {chunker.chunks[5].start_char}-{chunker.chunks[5].end_char}: {chunker.chunks[5].char_count} chars, {chunker.chunks[5].word_count} words")
    print(f"Chunk 6 : range {chunker.chunks[6].start_char}-{chunker.chunks[6].end_char}: {chunker.chunks[6].char_count} chars, {chunker.chunks[6].word_count} words")
    print(f"Chunk 7 : range {chunker.chunks[7].start_char}-{chunker.chunks[7].end_char}: {chunker.chunks[7].char_count} chars, {chunker.chunks[7].word_count} words")
    print(f"Chunk 8 : range {chunker.chunks[8].start_char}-{chunker.chunks[8].end_char}: {chunker.chunks[8].char_count} chars, {chunker.chunks[8].word_count} words\n")
"""
    print(f" ----------------------------------------------------------------------- Chunk 0 ----------------------------------------------------------------------- \n{chunker.chunks[0].text}\n")
    print(f" ----------------------------------------------------------------------- Chunk 1 ----------------------------------------------------------------------- \n{chunker.chunks[1].text}\n")
    print(f" ----------------------------------------------------------------------- Chunk 2 ----------------------------------------------------------------------- \n{chunker.chunks[2].text}\n")
    print(f" ----------------------------------------------------------------------- Chunk 3 ----------------------------------------------------------------------- \n{chunker.chunks[3].text}\n")

    report = validate_chunks(normalized, chunker, chunking_config)
    if report.is_valid:
        print("Chunk validation passed: all invariants hold.\n")
    else:
        print(f"Chunk validation FAILED: {len(report.issues)} issue(s) found.")
        for issue in report.issues:
            print(f"  [{issue.invariant}] chunk_index={issue.chunk_index}: {issue.message}")
        sys.exit(1)

    """ Saftery Checks for the extracted document to ensure consistency and correctness.
    full_text = "\n\n".join(page.text for page in extracted.pages)
    print(f"Total words in page {extracted.pages[0].page_number}: {extracted.pages[0].word_count}")
    print(f"Full text: {extracted.full_text}")
    print(len(extracted.full_text)) To see if the full text length matches the char count
    character_count = len(full_text)
    print(f"Character count (manual calculation): {character_count}")
    print(extracted.pages[0].text[:500])
    print(extracted.pages[0].text[-150:])
    print(extracted.pages[1].text[:150])
    assert extracted.page_count == len(extracted.pages) # Page Count Consistency Check
    assert extracted.word_count == sum(page.word_count for page in extracted.pages) # Word Count Aggregation Check
    assert extracted.char_count == len(extracted.full_text) # Character Count Match
    assert [page.page_number for page in extracted.pages] == [1, 2, 3, 4, 5, 6] # Page Ordering & Indexing Check
    assert extracted.full_text.strip() # . Non-Empty Text Validation

    This is for the normalization checks to ensure that the normalized text is consistent and correct.
    assert normalized.page_count == len(normalized.pages) # Page Count Consistency Check
    assert normalize_text("") == ""
    assert normalize_text("A   B") == "A B"
    assert normalize_text("A \n B") == "A\nB"
    assert normalize_text("A\n\n\n\nB") == "A\n\nB"
    assert normalize_text(normalize_text(normalized.full_text)) == normalize_text(normalized.full_text)

    assert normalized.page_count == len(normalized.pages)
    assert normalized.char_count == len(normalized.full_text)
    assert normalized.word_count == count_words(normalized.full_text)
    assert normalize_document(normalized).full_text
    """

if __name__ == "__main__":
    main()


    