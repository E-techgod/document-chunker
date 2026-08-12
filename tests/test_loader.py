import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from document_chunker.loader import PDFLoadError, load_pdf
from document_chunker.schemas import PDFDocumentInput

# --- PDFDocumentInput ---


def test_valid_pdf_path(create_pdf):
    pdf_path = create_pdf("sample.pdf")
    document = PDFDocumentInput(path=pdf_path)
    assert document.path == pdf_path
    assert document.document_id is None
    assert document.document_type is None


def test_missing_path():
    with pytest.raises(ValidationError):
        PDFDocumentInput(path=None)


def test_empty_path():
    # An empty string resolves to Path("."), which exists but is a directory,
    # not a file, so it fails the "is_file" check rather than "must be provided".
    with pytest.raises(ValidationError, match="not a file"):
        PDFDocumentInput(path="")


def test_path_does_not_exist(tmp_path):
    fake_path = tmp_path / "ghost.pdf"
    with pytest.raises(ValidationError, match="does not exist"):
        PDFDocumentInput(path=fake_path)


def test_path_is_directory_not_file(tmp_path):
    with pytest.raises(ValidationError, match="not a file"):
        PDFDocumentInput(path=tmp_path)


def test_invalid_extension(tmp_path):
    wrong_ext = tmp_path / "report.docx"
    wrong_ext.write_text("hello world")
    with pytest.raises(ValidationError, match=r"\.pdf file"):
        PDFDocumentInput(path=wrong_ext)


def test_zero_byte_file(tmp_path):
    empty_file = tmp_path / "empty.pdf"
    empty_file.touch()
    with pytest.raises(ValidationError, match="file is empty"):
        PDFDocumentInput(path=empty_file)


def test_optional_metadata_provided(create_pdf):
    pdf_path = create_pdf("meta.pdf")
    document = PDFDocumentInput(
        path=pdf_path, document_id="123-abc", document_type="invoice"
    )
    assert document.document_id == "123-abc"
    assert document.document_type == "invoice"


def test_document_id_wrong_type(create_pdf):
    pdf_path = create_pdf("meta.pdf")
    with pytest.raises(ValidationError):
        PDFDocumentInput(path=pdf_path, document_id=123)


# --- load_pdf ---


def test_load_valid_pdf(create_pdf):
    pdf_path = create_pdf("sample.pdf", pages=3)
    document = PDFDocumentInput(path=pdf_path)
    reader = load_pdf(document)
    assert reader.is_encrypted is False
    assert len(reader.pages) == 3


def test_load_corrupted_pdf(create_pdf):
    bad_pdf = create_pdf("corrupt.pdf", raw_bytes=b"NOT_A_REAL_PDF_HEADER_DATA")
    document = PDFDocumentInput(path=bad_pdf)
    with pytest.raises(PDFLoadError, match="corrupted"):
        load_pdf(document)


def test_load_encrypted_pdf_without_password(create_pdf):
    encrypted_pdf = create_pdf("secret.pdf", encrypt_password="supersecretpassword")
    document = PDFDocumentInput(path=encrypted_pdf)
    with pytest.raises(PDFLoadError, match="encrypted"):
        load_pdf(document)


def test_load_encrypted_pdf_with_wrong_password(create_pdf):
    encrypted_pdf = create_pdf("secret.pdf", encrypt_password="supersecretpassword")
    document = PDFDocumentInput(path=encrypted_pdf)
    with pytest.raises(PDFLoadError, match="encrypted"):
        load_pdf(document, password="wrong-password")


def test_load_encrypted_pdf_with_correct_password(create_pdf):
    encrypted_pdf = create_pdf("secret.pdf", encrypt_password="supersecretpassword")
    document = PDFDocumentInput(path=encrypted_pdf)
    reader = load_pdf(document, password="supersecretpassword")
    assert reader.is_encrypted is True
    assert len(reader.pages) == 1


def test_load_zero_page_pdf(tmp_path):
    zero_page = tmp_path / "zero_pages.pdf"
    writer = PdfWriter()  # No pages added
    with open(zero_page, "wb") as f:
        writer.write(f)

    document = PDFDocumentInput(path=zero_page)
    with pytest.raises(PDFLoadError, match="no pages"):
        load_pdf(document)
