import pytest
from pypdf import PdfWriter

@pytest.fixture
def create_pdf(tmp_path):
    """Helper fixture to dynamically create test PDFs in a temporary folder."""
    def _generator(filename="valid.pdf", pages=1, encrypt_password=None, raw_bytes=None):
        file_path = tmp_path / filename
        
        # If testing corrupt/raw non-PDF bytes
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

import pytest
from pathlib import Path
from src.document_chunker.loader import PDFDocumentInput, load_pdf  # Import your actual validator class

def test_valid_pdf_path(create_pdf):
    pdf_path = create_pdf("sample.pdf")
    validator = PDFDocumentInput(pdf_path)
    assert validator.validate() is True

def test_missing_or_invalid_path_types():
    with pytest.raises((ValueError, TypeError)):
        PDFDocumentInput(None).validate()
    with pytest.raises((ValueError, TypeError)):
        PDFDocumentInput("").validate()

def test_path_does_not_exist(tmp_path):
    fake_path = tmp_path / "ghost.pdf"
    with pytest.raises(FileNotFoundError):
        PDFDocumentInput(fake_path).validate()

def test_path_is_directory_not_file(tmp_path):
    # tmp_path is a directory, not a file
    with pytest.raises(ValueError, match="not a file"):
        PDFDocumentInput(tmp_path).validate()

def test_invalid_extension(tmp_path):
    wrong_ext = tmp_path / "report.docx"
    wrong_ext.write_text("hello world")
    with pytest.raises(ValueError, match="extension"):
        PDFDocumentInput(wrong_ext).validate()

def test_zero_byte_file(tmp_path):
    empty_file = tmp_path / "empty.pdf"
    empty_file.touch()  # Creates a 0-byte file
    with pytest.raises(ValueError, match="empty|zero bytes"):
        PDFDocumentInput(empty_file).validate()

@pytest.mark.parametrize("doc_id,doc_type,is_valid", [
    ("123-abc", "invoice", True),
    ("", "invoice", False),
    (123, None, False),
])
def test_optional_metadata_validation(create_pdf, doc_id, doc_type, is_valid):
    pdf_path = create_pdf("meta.pdf")
    if is_valid:
        validator = PDFDocumentInput(pdf_path, document_id=doc_id, document_type=doc_type)
        assert validator.validate() is True
    else:
        with pytest.raises(ValueError):
            PDFDocumentInput(pdf_path, document_id=doc_id, document_type=doc_type).validate()



from src.document_chunker.loader import load_pdf  # Import your PDF opening function

def test_corrupted_pdf_file(create_pdf):
    # Create a file named .pdf but containing plain string text
    bad_pdf = create_pdf("corrupt.pdf", raw_bytes=b"NOT_A_REAL_PDF_HEADER_DATA")
    with pytest.raises(ValueError, match="corrupt|invalid PDF"):
        load_pdf(bad_pdf)

def test_encrypted_pdf(create_pdf):
    encrypted_pdf = create_pdf("secret.pdf", encrypt_password="supersecretpassword")
    # Expect failure if no password provided
    with pytest.raises(ValueError, match="encrypted"):
        load_pdf(encrypted_pdf)

def test_zero_page_pdf(tmp_path):
    # Create a valid PDF header/structure, but forcibly strip pages
    zero_page = tmp_path / "zero_pages.pdf"
    writer = PdfWriter()  # No pages added
    with open(zero_page, "wb") as f:
        writer.write(f)
        
    with pytest.raises(ValueError, match="at least one page"):
        load_pdf(zero_page)