import sys
from pathlib import Path
from pydantic import ValidationError

from src.document_chunker.extractor import PDFExtractionError, extract_pdf
from src.document_chunker.loader import PDFLoadError, load_pdf
from src.document_chunker.schemas import PDFDocumentInput
from src.document_chunker.normalizer import normalize_document, normalize_text

def main() -> None:
    # Use CLI argument if provided; otherwise, fall back to default path
    path = sys.argv[1] if len(sys.argv) > 1 else "data/BAWSE.pdf"
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

    print(f"\nLoaded: {document.path}")
    print(f"Document ID: {document.document_id or document.path.stem}")
    print(f"Document Type: {document.document_type or 'Not provided'}")
    print(f"Encrypted: {reader.is_encrypted}")
    print(f"Pages: {len(reader.pages)}\n")

    try:
        extracted = extract_pdf(document, reader)
    except PDFExtractionError as exc:
        print(f"Failed to extract PDF: {exc}")
        sys.exit(1)

    print("Extraction complete: Raw text extracted from PDF pages.")
    #print(f"Full text: {extracted.full_text}")
    print(f"Extracted pages: {extracted.page_count}")
    print(f"Total words: {extracted.word_count}")
    print(f"Total chars: {extracted.char_count}\n")

    normalized = normalize_document(extracted)

    print("Normalization complete: Text cleaned and normalized.\n")
    print(f"Full text normalized: \n{normalized.full_text}\n") 
    print(f"Extracted normalized pages: {normalized.page_count}")
    print(f"Total normalized words: {normalized.word_count}")
    print(f"Total normalized chars: {normalized.char_count}\n")


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
    """

if __name__ == "__main__":
    main()