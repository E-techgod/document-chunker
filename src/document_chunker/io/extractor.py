from pydantic import BaseModel
from pypdf import PdfReader

from src.document_chunker.schemas import (
    ExtractedDocument,
    ExtractedPage,
    PDFDocumentInput,
)


class PDFExtractionError(Exception):
    """Raised when a PDF's text cannot be extracted."""


class ExtractionConfig(BaseModel):
    extraction_mode: str = "layout"
    layout_mode_space_vertically: bool = False


def _extract_page_text(page: object, config: ExtractionConfig) -> str:
    """Call `extract_text` with config when supported, otherwise fall back."""
    extract_text = page.extract_text
    kwargs = config.model_dump()

    try:
        return extract_text(**kwargs) or ""
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return extract_text() or ""


def extract_pdf(document: PDFDocumentInput, reader: PdfReader) -> ExtractedDocument:
    """Extract raw per-page and full-document text from an opened PDF.

    Every page in `reader` gets a corresponding `ExtractDocumentPage`, in
    original order, whether or not it contains text — blank pages are kept
    as empty-string pages rather than dropped. The document is rejected
    only if every page yields no text at all. Page text is taken as-is
    from pypdf; no normalization is applied here.
    """
    pages: list[ExtractedPage] = []
    config = ExtractionConfig()

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = _extract_page_text(page, config)
        except Exception as exc:
            raise PDFExtractionError(
                f"failed to extract text from page {page_number}: {document.path}"
            ) from exc

        pages.append(
            ExtractedPage(
                page_number=page_number,
                text=text,
            )
        )

    if not any(page.text.strip() for page in pages):
        raise PDFExtractionError(
            f"no extractable text found in document: {document.path}"
        )

    full_text = "\n\n".join(page.text for page in pages)

    return ExtractedDocument(
        document_id=document.document_id or document.path.stem,
        file_name=document.path.name,
        file_path=document.path,
        document_type=document.document_type,
        pages=pages,
        full_text=full_text,
    )
