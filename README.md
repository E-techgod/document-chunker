# `document-chunker`

## Entry Point

- Script entry point: [`main.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/main.py:1)
- Callable entry function: `main()`
- Package metadata file: [`pyproject.toml`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/pyproject.toml:1)
- Console script entry points: none declared in `pyproject.toml`
- Default PDF path when no CLI argument is provided: `data/generic.pdf`

## Main Call Flow

1. `main.py:main()` reads `sys.argv[1]` as `path` or defaults to `data/generic.pdf`.
2. `main.py:main()` reads `sys.argv[2]` as `password` or defaults to `""`.
3. `main.py:main()` constructs `PDFDocumentInput(path=Path(path))`.
4. `PDFDocumentInput.validate_path()` checks that the path exists, is a file, has `.pdf` suffix, and is not empty.
5. `main.py:main()` calls `load_pdf(document, password=password)`.
6. `load_pdf()` constructs `PdfReader(document.path)`.
7. `load_pdf()` decrypts the reader when `reader.is_encrypted` is true.
8. `load_pdf()` checks `len(reader.pages) >= 1`.
9. `main.py:main()` prints loaded path, encryption state, and page count.
10. `main.py:main()` calls `extract_pdf(document, reader)`.
11. `extract_pdf()` iterates `reader.pages` in order.
12. `extract_pdf()` calls `page.extract_text()` for each page.
13. `extract_pdf()` builds `ExtractDocumentPage` items with `page_number`, `text`, `word_count`, and `char_count`.
14. `extract_pdf()` rejects the document when every page is blank or whitespace-only after extraction.
15. `extract_pdf()` joins page text with `"\n\n"` into `full_text`.
16. `extract_pdf()` returns `ExtractDocument`.
17. `main.py:main()` prints extracted page count, total word count, and total char count.
18. `main.py:main()` exits with status `1` on `ValidationError`, `PDFLoadError`, or `PDFExtractionError`.

## Key Modules

- [`main.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/main.py:1): CLI script; builds `PDFDocumentInput`; calls `load_pdf()` and `extract_pdf()`; prints summary values; handles `ValidationError`, `PDFLoadError`, and `PDFExtractionError`.
- [`src/document_chunker/schemas.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/src/document_chunker/schemas.py:1): defines `PDFDocumentInput`, `ExtractDocumentPage`, `ExtractDocument`, `NormalizedPage`, and `NormalizedDocument`.
- [`src/document_chunker/loader.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/src/document_chunker/loader.py:1): defines `PDFLoadError`; opens PDFs with `PdfReader`; handles corrupted PDFs, unsupported encryption, failed decryption, and zero-page PDFs.
- [`src/document_chunker/extractor.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/src/document_chunker/extractor.py:1): defines `PDFExtractionError`; extracts per-page text; preserves blank pages; rejects documents with no extractable text; returns `ExtractDocument`.
- [`tests/conftest.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/tests/conftest.py:1): defines `create_pdf` and `fake_reader` fixtures; defines `FakePage` and `FakeReader` test doubles.
- [`tests/test_loader.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/tests/test_loader.py:1): tests `PDFDocumentInput` validation and `load_pdf()`.
- [`tests/test_extractor.py`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/tests/test_extractor.py:1): tests `extract_pdf()`.

## Test Count

- Total test functions: `29`
- `tests/test_loader.py`: `15`
- `tests/test_extractor.py`: `14`

## Dependencies

- Python requirement: `>=3.14`
- Runtime dependencies:
  - `pydantic>=2.13.4`
  - `pypdf>=6.14.2`
- Declared project dependency:
  - `pytest>=9.1.1`
- Build dependency:
  - `hatchling`

## Graph Facts

- Graph report file: [`graphify-out/GRAPH_REPORT.md`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/graphify-out/GRAPH_REPORT.md:1)
- Graph HTML file: [`graphify-out/graph.html`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/graphify-out/graph.html:1)
- Graph JSON file: [`graphify-out/graph.json`](/Users/eliasarellanocampos/EAC/Applied%20AI%20-%20GenAI%20Engineer%20@%20Austin/Week8/document-chunker/graphify-out/graph.json:1)
- Graph nodes: `38`
- Graph edges: `84`
- Graph communities: `8`
- Graph report commit reference: `4ceaacb1`
- Graph report import cycles: none detected
