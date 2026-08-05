import pytest
from pypdf import PdfWriter


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
