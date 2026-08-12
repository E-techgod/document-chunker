import sys
from pathlib import Path

from pydantic import ValidationError

from src.document_chunker.chunker import chunk_document
from src.document_chunker.chunking_strategies import get_chunking_strategy
from src.document_chunker.extractor import PDFExtractionError, extract_pdf
from src.document_chunker.loader import PDFLoadError, load_pdf
from src.document_chunker.paragraph_normalizer import build_structured_document
from src.document_chunker.quality import evaluate_chunk_quality, format_quality_comparison
from src.document_chunker.schemas import PDFDocumentInput
from src.document_chunker.structured_bridge import to_normalized_document

STRATEGY_LABELS = {"v1.0": "V1", "v2.1": "V2.1", "v2.2": "V2.2"}


def main() -> None:
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

    try:
        extracted = extract_pdf(document, reader)
    except PDFExtractionError as exc:
        print(f"Failed to extract PDF: {exc}")
        sys.exit(1)

    structured = build_structured_document(extracted)
    normalized = to_normalized_document(extracted, structured)

    reports = {}
    for strategy_name, label in STRATEGY_LABELS.items():
        _, chunking_config = get_chunking_strategy(strategy_name)
        result = chunk_document(normalized, config=chunking_config)
        reports[label] = evaluate_chunk_quality(normalized, result, chunking_config)

    print(f"Chunk quality comparison for {document.path}\n")
    print(format_quality_comparison(reports))


if __name__ == "__main__":
    main()
