from pathlib import Path

from pydantic import BaseModel, field_validator, Field


class PDFDocumentInput(BaseModel):
    """Validated input for loading a single PDF document."""

    path: Path
    document_id: str | None = None
    document_type: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: Path) -> Path:
        if not str(path).strip():
            raise ValueError("path must be provided") # Convert input into Path
        if not path.exists():
            raise ValueError(f"path does not exist: {path}") # Check path exists
        if not path.is_file():
            raise ValueError(f"path is not a file: {path}") # Check path is a file
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"path must point to a .pdf file: {path}") # Check extension is .pdf
        if path.stat().st_size == 0:
            raise ValueError(f"file is empty: {path}") # Check size is greater than zero
        return path 

class ExtractDocumentPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    word_count: int =  Field(ge=0)
    char_count: int =  Field(ge=0)

class ExtractDocument(BaseModel):
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None

    page_count: int  = Field(ge=1)
    pages: list[ExtractDocumentPage]

    full_text: str
    word_count: int  = Field(ge=0)
    char_count: int = Field(ge=0)

class NormalizedPage(BaseModel):
    page_number: int  = Field(ge=1)
    text: str
    word_count: int  = Field(ge=0)
    char_count: int = Field(ge=0)

class NormalizedDocument(BaseModel):
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None

    page_count: int = Field(ge=1)
    pages: list[NormalizedPage]

    full_text: str
    word_count: int = Field(ge=0)
    char_count: int = Field(ge=0)

    normalized_strategy: str | None = None