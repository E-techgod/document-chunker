from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator, Field, field_validator, computed_field
from document_chunker.counting import count_words

NormalizationStrategy = Literal[
    "conservative",
    "structural",
    "layout_preserving",
]

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

class ExtractedPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    
    @computed_field
    @property
    def word_count(self) -> int:
        return count_words(self.text)

    @computed_field
    @property
    def char_count(self) -> int:
        return len(self.text)

class ExtractedDocument(BaseModel):
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None
    pages: list[ExtractedPage]
    full_text: str

    @computed_field
    @property
    def page_count(self) -> int:
        return len(self.pages)

    @computed_field
    @property
    def word_count(self) -> int:
        return sum(page.word_count for page in self.pages)

    @computed_field
    @property
    def char_count(self) -> int:
        return len(self.full_text)

class NormalizedTable(BaseModel):
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class NormalizedBlock(BaseModel):
    block_type: Literal["heading", "paragraph", "list", "table"]
    text: str | None = None
    items: list[str] = Field(default_factory=list)
    table: NormalizedTable | None = None


class NormalizedPage(BaseModel):
    page_number: int  = Field(ge=1) # Field level validation to ensure page_number is greater than or equal to 1
    text: str
    blocks: list[NormalizedBlock] = Field(default_factory=list)

    @computed_field
    @property
    def word_count(self) -> int:
        return count_words(self.text)

    @computed_field
    @property
    def char_count(self) -> int:
        return len(self.text)

class NormalizedDocument(BaseModel):
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None
    pages: list[NormalizedPage]
    full_text: str
    normalized_strategy: str | None = None
   
    @computed_field
    @property
    def page_count(self) -> int:
        return len(self.pages)

    @computed_field
    @property
    def word_count(self) -> int:
        return sum(page.word_count for page in self.pages)

    @computed_field
    @property
    def char_count(self) -> int:
        return len(self.full_text)

