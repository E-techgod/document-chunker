from pathlib import Path
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pydantic import BaseModel, field_validator

class PDFLoadError(Exception):
    """Raised when a PDF cannot be opened, is corrupted, or cannot be decrypted."""

class PDFDocumentInput(BaseModel):
    """Validated input for loading a single PDF document."""

    path: Path
    document_id: str | None = None
    document_type: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: Path) -> Path:
        if not str(path).strip():
            raise ValueError("path must be provided")
        if not path.exists():
            raise ValueError(f"path does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"path is not a file: {path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"path must point to a .pdf file: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"file is empty: {path}")
        return path


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
