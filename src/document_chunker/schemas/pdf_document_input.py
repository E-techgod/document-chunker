from pathlib import Path

from pydantic import BaseModel, field_validator


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
