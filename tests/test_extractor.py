import pytest

from document_chunker.extractor import PDFExtractionError, extract_pdf
from document_chunker.schemas import PDFDocumentInput


# --- page coverage, ordering, blank pages ---


def test_every_page_has_extracted_page(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["first", "second", "third"])

    extracted = extract_pdf(document, reader)

    assert len(extracted.pages) == 3
    assert [p.page_number for p in extracted.pages] == [1, 2, 3]


def test_page_ordering_preserved(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["alpha", "beta", "gamma"])

    extracted = extract_pdf(document, reader)

    assert [p.text for p in extracted.pages] == ["alpha", "beta", "gamma"]


def test_blank_pages_preserved_not_dropped(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["intro text", "", "closing text"])

    extracted = extract_pdf(document, reader)

    assert extracted.page_count == 3
    blank_page = extracted.pages[1]
    assert blank_page.page_number == 2
    assert blank_page.text == ""
    assert blank_page.word_count == 0
    assert blank_page.char_count == 0


# --- extract_text() returning None ---


def test_extract_text_none_is_treated_as_empty_string(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["some text", None])

    extracted = extract_pdf(document, reader)

    none_page = extracted.pages[1]
    assert none_page.text == ""
    assert none_page.word_count == 0
    assert none_page.char_count == 0


def test_all_pages_none_rejected_without_crashing(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader([None, None])

    with pytest.raises(PDFExtractionError, match="no extractable text"):
        extract_pdf(document, reader)


# --- rejection when no text is extractable ---


def test_rejects_document_with_all_blank_pages(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["", ""])

    with pytest.raises(PDFExtractionError, match="no extractable text"):
        extract_pdf(document, reader)


def test_rejects_document_with_only_whitespace_pages(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["   \n\t", "\n\n  "])

    with pytest.raises(PDFExtractionError, match="no extractable text"):
        extract_pdf(document, reader)


def test_accepts_document_with_at_least_one_text_page(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["", "some real text", ""])

    extracted = extract_pdf(document, reader)

    assert extracted.page_count == 3


# --- page extraction failures ---


def test_page_extraction_error_raises_pdf_extraction_error(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["fine", (None, True)])

    with pytest.raises(PDFExtractionError, match="page 2"):
        extract_pdf(document, reader)


# --- full text assembly ---


def test_full_text_assembled_consistently(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["page one", "page two", "page three"])

    extracted = extract_pdf(document, reader)

    assert extracted.full_text == "page one\n\npage two\n\npage three"


# --- counts ---


def test_page_and_document_counts_populated(create_pdf, fake_reader):
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["hello world", "foo bar baz"])

    extracted = extract_pdf(document, reader)

    assert extracted.page_count == 2
    assert extracted.pages[0].word_count == 2
    assert extracted.pages[0].char_count == len("hello world")
    assert extracted.pages[1].word_count == 3
    assert extracted.word_count == 5
    assert extracted.char_count == len(extracted.full_text)


# --- input metadata preserved ---


def test_input_metadata_preserved(create_pdf, fake_reader):
    pdf_path = create_pdf("invoice.pdf")
    document = PDFDocumentInput(
        path=pdf_path, document_id="doc-123", document_type="invoice"
    )
    reader = fake_reader(["some content"])

    extracted = extract_pdf(document, reader)

    assert extracted.document_id == "doc-123"
    assert extracted.document_type == "invoice"
    assert extracted.file_name == "invoice.pdf"
    assert extracted.file_path == pdf_path


def test_document_id_defaults_to_file_stem_when_missing(create_pdf, fake_reader):
    pdf_path = create_pdf("report.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader(["some content"])

    extracted = extract_pdf(document, reader)

    assert extracted.document_id == "report"


# --- no normalization ---


def test_no_normalization_applied(create_pdf, fake_reader):
    raw_text = "  Hello   WORLD  \n\n  Line Two  "
    pdf_path = create_pdf("doc.pdf")
    document = PDFDocumentInput(path=pdf_path)
    reader = fake_reader([raw_text])

    extracted = extract_pdf(document, reader)

    assert extracted.pages[0].text == raw_text
