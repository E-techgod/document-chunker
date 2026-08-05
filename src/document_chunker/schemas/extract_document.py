from pathlib import Path

from pydantic import BaseModel


class ExtractDocumentPage(BaseModel):
    page_number: int

    raw_text: str
    normalized_text: str

    raw_word_count: int
    normalized_word_count: int

    raw_char_count: int
    normalized_char_count: int


class ExtractDocument(BaseModel):
    document_id: str
    file_name: str
    file_path: Path
    document_type: str | None = None

    page_count: int
    pages: list[ExtractDocumentPage]

    raw_full_text: str
    normalized_full_text: str

    raw_word_count: int
    normalized_word_count: int

    raw_char_count: int
    normalized_char_count: int
