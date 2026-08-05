import sys
from pathlib import Path

from pydantic import ValidationError

from src.document_chunker.extractor import PDFExtractionError, extract_pdf
from src.document_chunker.loader import PDFLoadError, load_pdf
from src.document_chunker.schemas import PDFDocumentInput

def main() -> None:
    # Use CLI argument if provided; otherwise, fall back to default path
    path = sys.argv[1] if len(sys.argv) > 1 else "data/generic.pdf"
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

    print(f"Loaded: {document.path}")
    print(f"Encrypted: {reader.is_encrypted}")
    print(f"Pages: {len(reader.pages)}")

    try:
        extracted = extract_pdf(document, reader)
    except PDFExtractionError as exc:
        print(f"Failed to extract PDF: {exc}")
        sys.exit(1)

    print(f"Extracted pages: {extracted.page_count}")
    print(f"Total words: {extracted.word_count}")
    print(f"Total chars: {extracted.char_count}")


if __name__ == "__main__":
    main()