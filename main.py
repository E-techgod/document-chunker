import sys
from pathlib import Path

from pydantic import ValidationError

from src.document_chunker.loader import PDFDocumentInput, PDFLoadError, load_pdf


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <path-to-pdf> [password]")
        sys.exit(1)

    path = sys.argv[1]
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


if __name__ == "__main__":
    main()
