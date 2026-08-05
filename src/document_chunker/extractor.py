from pypdf import PdfReader

from document_chunker.schemas import ExtractDocument, ExtractDocumentPage, PDFDocumentInput


class PDFExtractionError(Exception):
    """Raised when a PDF's text cannot be extracted."""


def extract_pdf(document: PDFDocumentInput, reader: PdfReader) -> ExtractDocument:
    """Extract raw per-page and full-document text from an opened PDF.

    Every page in `reader` gets a corresponding `ExtractDocumentPage`, in
    original order, whether or not it contains text — blank pages are kept
    as empty-string pages rather than dropped. The document is rejected
    only if every page yields no text at all. Page text is taken as-is
    from pypdf; no normalization is applied here.
    """
    pages: list[ExtractDocumentPage] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise PDFExtractionError(
                f"failed to extract text from page {page_number}: {document.path}"
            ) from exc

        pages.append(
            ExtractDocumentPage(
                page_number=page_number,
                text=text,
                word_count=len(text.split()),
                char_count=len(text),
            )
        )

    if not any(page.text.strip() for page in pages):
        raise PDFExtractionError(f"no extractable text found in document: {document.path}")

    full_text = "\n\n".join(page.text for page in pages)

    return ExtractDocument(
        document_id=document.document_id or document.path.stem,
        file_name=document.path.name,
        file_path=document.path,
        document_type=document.document_type,
        page_count=len(pages),
        pages=pages,
        full_text=full_text,
        word_count=sum(page.word_count for page in pages),
        char_count=len(full_text),
    )
