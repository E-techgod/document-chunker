from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from src.document_chunker.counting import count_words

NormalizationStrategy = Literal[
    "characters",
    "structural",
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
            raise ValueError("path must be provided")  # Convert input into Path
        if not path.exists():
            raise ValueError(f"path does not exist: {path}")  # Check path exists
        if not path.is_file():
            raise ValueError(f"path is not a file: {path}")  # Check path is a file
        if path.suffix.lower() != ".pdf":
            raise ValueError(
                f"path must point to a .pdf file: {path}"
            )  # Check extension is .pdf
        if path.stat().st_size == 0:
            raise ValueError(
                f"file is empty: {path}"
            )  # Check size is greater than zero
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
    start_char: int = Field(default=0, ge=0)
    end_char: int = Field(default=0, ge=0)


class NormalizedPage(BaseModel):
    page_number: int = Field(
        ge=1
    )  # Field level validation to ensure page_number is greater than or equal to 1
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

    @computed_field  # Validation to ensure that the page_count is equal to the length of the pages list
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


class ChunkingConfig(
    BaseModel
):  # The rules: How to chunk the document into smaller pieces for processing
    max_chunk_size: int = Field(default=1000, ge=1)
    overlap_size: int = Field(default=100, ge=0)
    chunking_strategy: Literal["characters", "structural"] = "characters"
    propagate_context: bool = (
        False  # structural only, TRUE to activate (v2.2); ignored for "characters"
    )


class DocumentChunk(
    BaseModel
):  # One Chunk: Represents one chunk only: Represents a chunk of a document, with metadata and content
    document_id: str
    chunk_id: str
    chunk_index: int = Field(ge=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    text: str
    page_numbers: list[int] = Field(default_factory=list)
    word_count: int = Field(default=0, ge=0)
    char_count: int = Field(default=0, ge=0)
    context_prefix: str = ""

    @computed_field
    @property
    def contextualized_text(self) -> str:
        return (
            f"{self.context_prefix}\n{self.text}" if self.context_prefix else self.text
        )

    @field_validator("word_count", "char_count", mode="before")
    @classmethod
    def validate_counts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("word_count and char_count must be non-negative")
        return value


class ChunkingResult(
    BaseModel
):  # The whole chunking output: Represents the whole document after chunking: Represents the result of chunking a document, with metadata and chunks
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None
    chunks: list[DocumentChunk] = Field(default_factory=list)
    chunking_strategy: str | None = None

    @computed_field
    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @computed_field
    @property
    def total_word_count(self) -> int:
        return sum(chunk.word_count for chunk in self.chunks)

    @computed_field
    @property
    def total_char_count(self) -> int:
        return sum(chunk.char_count for chunk in self.chunks)


class ChunkValidationIssue(
    BaseModel
):  # One broken invariant, tied to the chunk (if any) where it was found
    invariant: str
    chunk_index: int | None = None
    message: str


class ChunkValidationReport(
    BaseModel
):  # The full set of invariant violations found for one ChunkingResult
    document_id: str
    issues: list[ChunkValidationIssue] = Field(default_factory=list)

    @computed_field
    @property
    def is_valid(self) -> bool:
        return not self.issues


OverheadSource = Literal["overlap", "context_prefix", "none"]


class ChunkQualityReport(BaseModel):
    """Quantitative quality scoring for one ChunkingResult - how good a chunking is, as
    opposed to ChunkValidationReport's pass/fail invariant check. Lets V1 (character),
    V2.1 (structural), and V2.2 (structural + context carry) be compared side by side on
    the same document."""

    document_id: str
    chunking_strategy: str
    propagate_context: bool
    is_valid: bool
    chunk_count: int = Field(ge=0)
    avg_utilization: float = Field(ge=0)  # mean chunk char_count / max_chunk_size
    tiny_chunk_count: int = Field(default=0, ge=0)
    tiny_chunk_ratio: float = Field(
        default=0, ge=0, le=1
    )  # share of chunks under TINY_CHUNK_RATIO of max size
    word_splits: int = Field(
        default=0, ge=0
    )  # chunk boundaries cutting through a word inside a heading/paragraph
    bullet_splits: int = Field(
        default=0, ge=0
    )  # chunk boundaries cutting through a list item
    table_row_splits: int = Field(
        default=0, ge=0
    )  # chunk boundaries cutting through a table row
    context_overhead: float = Field(
        default=0, ge=0
    )  # redundant chars (overlap or context_prefix) / total chars
    overhead_source: OverheadSource = (
        "none"  # which mechanism produced context_overhead, for display
    )
    context_coverage: float | None = Field(
        default=None, ge=0, le=1
    )  # None when propagate_context is off (N/A)
