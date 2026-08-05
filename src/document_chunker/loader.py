from pypdf import PdfReader
from pypdf.errors import PdfReadError

from document_chunker.schemas import PDFDocumentInput


class PDFLoadError(Exception):
    """Raised when a PDF cannot be opened, is corrupted, or cannot be decrypted."""


def load_pdf(document: PDFDocumentInput, password: str = "") -> PdfReader:
    """Open and validate the PDF referenced by `document`.

    Checks that the file can be opened by pypdf, is not corrupted, is not
    encrypted (or can be decrypted with `password`), and contains at least
    one page. Returns the opened `PdfReader` on success.
    """
    try:
        reader = PdfReader(document.path)
    except PdfReadError as exc:
        raise PDFLoadError(f"file is corrupted or not a valid PDF: {document.path}") from exc

    if reader.is_encrypted:
        try:
            result = reader.decrypt(password)
        except NotImplementedError as exc:
            raise PDFLoadError(
                f"file uses an unsupported encryption method: {document.path}"
            ) from exc
        if result == 0:
            raise PDFLoadError(
                f"file is encrypted and could not be decrypted: {document.path}"
            )

    try:
        page_count = len(reader.pages)
    except PdfReadError as exc:
        raise PDFLoadError(f"file is corrupted or not a valid PDF: {document.path}") from exc

    if page_count < 1:
        raise PDFLoadError(f"file contains no pages: {document.path}")

    return reader



