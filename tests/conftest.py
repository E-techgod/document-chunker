import pytest
from pypdf import PdfWriter

from document_chunker.normalizer import normalize_document
from document_chunker.schemas import ExtractedDocument, ExtractedPage, NormalizedDocument, NormalizedPage


@pytest.fixture
def create_pdf(tmp_path):
    """Helper fixture to dynamically create test PDFs in a temporary folder."""

    def _generator(filename="valid.pdf", pages=1, encrypt_password=None, raw_bytes=None):
        file_path = tmp_path / filename

        if raw_bytes is not None:
            file_path.write_bytes(raw_bytes)
            return file_path

        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=100, height=100)

        if encrypt_password:
            writer.encrypt(encrypt_password)

        with open(file_path, "wb") as f:
            writer.write(f)

        return file_path

    return _generator


class FakePage:
    """Stand-in for a pypdf page, with full control over extract_text()."""

    def __init__(self, text, raise_error=False):
        self._text = text
        self._raise_error = raise_error

    def extract_text(self):
        if self._raise_error:
            raise RuntimeError("simulated extraction failure")
        return self._text


class FakeReader:
    """Stand-in for a pypdf PdfReader exposing only what extract_pdf needs."""

    def __init__(self, pages):
        self.pages = pages


@pytest.fixture
def fake_reader():
    """Build a FakeReader from a list of page texts.

    Each item is either the page's text (str | None), or a
    (text, raise_error) tuple to simulate a page whose extract_text()
    raises instead of returning.
    """

    def _generator(items):
        pages = []
        for item in items:
            if isinstance(item, tuple):
                text, raise_error = item
            else:
                text, raise_error = item, False
            pages.append(FakePage(text, raise_error=raise_error))
        return FakeReader(pages)

    return _generator


@pytest.fixture
def make_extract_document():
    """Build an ExtractDocument from a list of raw page texts, no PDF I/O involved."""

    def _generator(
        texts,
        document_id="doc1",
        file_name="doc1.pdf",
        file_path="/tmp/doc1.pdf",
        document_type=None,
    ):
        pages = [
            ExtractedPage(
                page_number=i,
                text=text,
            )
            for i, text in enumerate(texts, start=1)
        ]
        full_text = "\n\n".join(texts)
        return ExtractedDocument(
            document_id=document_id,
            file_name=file_name,
            file_path=file_path,
            document_type=document_type,
            pages=pages,
            full_text=full_text,
        )

    return _generator


@pytest.fixture
def make_normalized_document():
    """Build a NormalizedDocument directly from raw page texts, bypassing the normalization
    pipeline so tests can control full_text and page boundaries precisely (e.g. leftover
    whitespace normalize_document would otherwise have stripped)."""

    def _generator(
        texts,
        document_id="doc1",
        file_name="doc1.pdf",
        file_path="/tmp/doc1.pdf",
        document_type=None,
        full_text=None,
    ):
        pages = [
            NormalizedPage(page_number=i, text=text)
            for i, text in enumerate(texts, start=1)
        ]
        if full_text is None:
            full_text = "\n\n".join(texts)
        return NormalizedDocument(
            document_id=document_id,
            file_name=file_name,
            file_path=file_path,
            document_type=document_type,
            pages=pages,
            full_text=full_text,
        )

    return _generator


@pytest.fixture
def normalized_doc(make_extract_document):
    """Provide a representative normalized document for model/serialization tests."""
    document = make_extract_document(
        [
            "  First page has   extra spacing.  ",
            "Second page wraps\nacross lines.",
        ],
        document_id="normalized-doc",
        file_name="normalized.pdf",
        file_path="/tmp/normalized.pdf",
        document_type="report",
    )
    return normalize_document(document)
