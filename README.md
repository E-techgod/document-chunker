# `document-chunker`

## Package
- Name: `document-chunker`
- Version: `0.1.0`
- Python: `>=3.14`
- Build backend: `hatchling`
- Wheel package target: `src/document_chunker`

## Dependencies
- `pydantic>=2.13.4`
- `pypdf>=6.14.2`
- `pytest>=9.1.1`

## Repository Files
- `main.py`
- `pyproject.toml`
- `uv.lock`
- `src/document_chunker/schemas.py`
- `src/document_chunker/loader.py`
- `src/document_chunker/extractor.py`
- `tests/conftest.py`
- `tests/test_loader.py`
- `tests/test_extractor.py`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/graph.html`
- `graphify-out/graph.json`
- `data/BAWSE.pdf`
- `data/empty.pdf`
- `data/generic.pdf`
- `data/invoice.pdf`
- `data/receipt.pdf`
- `data/report.pdf`
- `data/resume.pdf`
- `data/sample.pdf`

## CLI
- Entry file: `main.py`
- Positional argument 1: PDF path
- Positional argument 2: PDF password
- Default PDF path: `data/generic.pdf`
- Default password: `""`
- Exit code `1` on `ValidationError`
- Exit code `1` on `PDFLoadError`
- Exit code `1` on `PDFExtractionError`
- Prints loaded path, encryption flag, page count, extracted page count, total word count, total char count

## Schemas

### `PDFDocumentInput`
- Base: `pydantic.BaseModel`
- Fields:
- `path: Path`
- `document_id: str | None = None`
- `document_type: str | None = None`
- Path validation checks:
- non-empty string after coercion check
- path exists
- path is a file
- suffix is `.pdf`
- file size is greater than `0`

### `ExtractDocumentPage`
- Base: `pydantic.BaseModel`
- Fields:
- `page_number: int` with `ge=1`
- `text: str`
- `word_count: int` with `ge=0`
- `char_count: int` with `ge=0`

### `ExtractDocument`
- Base: `pydantic.BaseModel`
- Fields:
- `document_id: str`
- `file_name: str`
- `file_path: Path`
- `document_type: str | None = None`
- `page_count: int` with `ge=1`
- `pages: list[ExtractDocumentPage]`
- `full_text: str`
- `word_count: int` with `ge=0`
- `char_count: int` with `ge=0`

### `NormalizedPage`
- Base: `pydantic.BaseModel`
- Fields:
- `page_number: int` with `ge=1`
- `text: str`
- `word_count: int` with `ge=0`
- `char_count: int` with `ge=0`

### `NormalizedDocument`
- Base: `pydantic.BaseModel`
- Fields:
- `document_id: str`
- `file_name: str`
- `file_path: Path`
- `document_type: str | None = None`
- `page_count: int` with `ge=1`
- `pages: list[NormalizedPage]`
- `full_text: str`
- `word_count: int` with `ge=0`
- `char_count: int` with `ge=0`
- `normalized_strategy: str | None = None`

## Loader
- File: `src/document_chunker/loader.py`
- Exception: `PDFLoadError`
- Function: `load_pdf(document: PDFDocumentInput, password: str = "") -> PdfReader`
- Uses: `pypdf.PdfReader`
- Uses: `pypdf.errors.PdfReadError`
- Behavior:
- opens `document.path` with `PdfReader`
- converts `PdfReadError` during open to `PDFLoadError`
- if encrypted, calls `reader.decrypt(password)`
- converts `NotImplementedError` during decrypt to `PDFLoadError`
- raises `PDFLoadError` when decrypt result is `0`
- reads `len(reader.pages)`
- converts `PdfReadError` during page access to `PDFLoadError`
- raises `PDFLoadError` when page count is less than `1`
- returns `PdfReader`

## Extractor
- File: `src/document_chunker/extractor.py`
- Exception: `PDFExtractionError`
- Function: `extract_pdf(document: PDFDocumentInput, reader: PdfReader) -> ExtractDocument`
- Behavior:
- iterates `reader.pages` in original order starting at page number `1`
- calls `page.extract_text()`
- converts `None` page text to `""`
- converts page extraction exceptions to `PDFExtractionError`
- preserves blank pages
- rejects documents when every page is blank or whitespace-only
- sets `full_text` to page texts joined by `"\n\n"`
- sets `document_id` to `document.document_id` or `document.path.stem`
- sets `file_name` to `document.path.name`
- sets `file_path` to `document.path`
- sets `document_type` to `document.document_type`
- sets `page_count` to number of pages
- sets `word_count` to sum of page word counts
- sets `char_count` to `len(full_text)`
- does not normalize extracted text

## Tests

### `tests/test_loader.py`
- validates valid PDF path input
- validates missing path rejection
- validates empty path rejection
- validates nonexistent path rejection
- validates directory path rejection
- validates non-`.pdf` extension rejection
- validates zero-byte file rejection
- validates optional metadata assignment
- validates invalid `document_id` type rejection
- validates successful loading of a 3-page PDF
- validates corrupted PDF rejection
- validates encrypted PDF rejection without password
- validates encrypted PDF rejection with wrong password
- validates encrypted PDF acceptance with correct password
- validates zero-page PDF rejection

### `tests/test_extractor.py`
- validates one extracted page per input page
- validates page ordering preservation
- validates blank page preservation
- validates `extract_text()` returning `None` as empty string
- validates rejection when all pages return `None`
- validates rejection when all pages are blank
- validates rejection when all pages are whitespace-only
- validates acceptance when at least one page has text
- validates page extraction failure conversion to `PDFExtractionError`
- validates `full_text` assembly with `"\n\n"`
- validates page and document count fields
- validates metadata preservation
- validates default `document_id` from file stem
- validates no text normalization

### `tests/conftest.py`
- fixture: `create_pdf(tmp_path)`
- helper writes valid PDFs, encrypted PDFs, or raw byte files
- fixture: `fake_reader()`
- support classes: `FakePage`, `FakeReader`

Change the extraction stratey to use layout instead reading raw stream objects 