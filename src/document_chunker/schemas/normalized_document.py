from pathlib import Path

from pydantic import BaseModel


class NormalizedPage(BaseModel):
    page_number: int
    text: str

    word_count: int
    character_count: int


class NormalizedDocument(BaseModel):
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None

    page_count: int
    pages: list[NormalizedPage]

    full_text: str
    word_count: int
    character_count: int

    normalization_strategy: str
