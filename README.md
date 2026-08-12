# `Document Chunker`

`document-chunker` is a PDF processing pipeline that takes a local PDF through validation, loading, extraction, structured reconstruction, normalization, chunking, and chunk validation. The repo is still organized around small, testable stages with explicit schema boundaries, and the generated graph artifacts in `graphify-out/` make the runtime and test relationships easy to inspect.

This is not just "text extraction" anymore. The current codebase includes:

- input validation with `PDFDocumentInput`
- PDF loading and decryption checks
- page-by-page text extraction
- structured reconstruction into headings, paragraphs, lists, and tables
- noise detection for repeated headers, footers, and page numbers
- a bridge back into the normalized document model used for chunking
- multiple chunking strategies
- invariant-based chunk validation
- generated graph reports for codebase inspection

## Architecture

The generated graph in `graphify-out/GRAPH_REPORT.md`, `graphify-out/graph.json`, and `graphify-out/graph.html` currently reports:

- `653` nodes
- `1470` edges
- `24` communities
- no import cycles detected

```mermaid
flowchart LR
  main["main.py"]
  data["data/ PDFs"]
  graphify["graphify-out/
  GRAPH_REPORT.md
  graph.json
  graph.html"]
  tests["tests/
  stage + structure + validation suites"]

  subgraph core["src/document_chunker"]
    schemas["schemas.py
    shared models + chunking config"]
    loader["loader.py
    PDF loading"]
    extractor["extractor.py
    text extraction"]
    structured["paragraph_normalizer.py
    structured reconstruction"]
    step2["step2_pipeline.py
    structured validation"]
    bridge["structured_bridge.py
    bridge to normalized model"]
    chunker["chunker.py
    chunk generation"]
    evaluator["evaluator.py
    chunk validation"]
    strategies["chunking_strategies.py
    strategy selection"]
  end

  subgraph helpers["Structured helpers"]
    heading["heading_detector.py"]
    listd["list_detector.py"]
    noise["noise_detector.py"]
    paragraph["paragraph_normalizer.py"]
    table_norm["table_normalizer.py"]
    table_parse["table_parser.py"]
    structured_models["structured_models.py"]
  end

  data --> main
  main --> loader
  main --> extractor
  main --> structured
  main --> step2
  main --> bridge
  main --> chunker
  main --> evaluator
  main --> strategies

  loader --> schemas
  extractor --> schemas
  structured --> schemas
  bridge --> schemas
  chunker --> schemas
  evaluator --> schemas
  strategies --> schemas

  structured --> heading
  structured --> listd
  structured --> noise
  structured --> table_norm
  structured --> table_parse
  structured_models --> step2

  tests --> core
  tests --> helpers
  graphify -. maps repo relationships .-> core
  graphify -. surfaces test and module communities .-> tests
```

The graph's highest-connectivity nodes are centered on `build_structured_document()`, `chunk_document()`, `validate_chunks()`, `normalize_page()`, and `extract_pdf()`, which matches the codebase's real center of gravity: reconstructing document structure cleanly enough that chunking and validation remain trustworthy.

## Pipeline

The runtime flow exercised by `main.py` is:

```mermaid
flowchart TD
  input["PDF path + optional password"]
  validate["PDFDocumentInput"]
  load["load_pdf()"]
  extract["extract_pdf()"]
  structured["build_structured_document()"]
  step2["validate_structured_document()"]
  bridge["to_normalized_document()"]
  chunk["chunk_document()"]
  verify["validate_chunks()"]
  output["ChunkingResult + ChunkValidationReport"]

  input --> validate
  validate --> load
  load --> extract
  extract --> structured
  structured --> step2
  step2 --> bridge
  bridge --> chunk
  chunk --> verify
  verify --> output
```

## What Each Stage Does

**Validate**  
`PDFDocumentInput` rejects empty paths, missing files, non-files, non-`.pdf` inputs, and zero-byte files before any PDF work starts.

**Load**  
`load_pdf()` opens the file with `pypdf`, handles encrypted PDFs, and raises `PDFLoadError` for corrupted files, unreadable content, bad passwords, or empty page sets.

**Extract**  
`extract_pdf()` builds extracted document/page models from `pypdf` output. Blank pages are preserved, and the document is rejected only when the extracted result is effectively empty.

**Reconstruct Structure**  
`build_structured_document()` rebuilds cleaner document structure from extracted page text, classifying headings, paragraphs, lists, tables, and noise. The helper modules around it are where most of the layout-sensitive work now lives.

**Validate Structured Output**  
`validate_structured_document()` checks Step 2 invariants against the extracted source. `main.py` treats those findings as warnings rather than fatal errors because some known edge cases are documented limitations, not pipeline breakages.

**Bridge to the Chunking Model**  
`to_normalized_document()` converts the structured representation back into the normalized document shape expected by the chunker and evaluator.

**Chunk**  
`chunk_document()` converts normalized content into `DocumentChunk` objects. The repo currently supports:

- `v1.0`: character chunking with overlap
- `v2.1`: structural chunking with no context carry
- `v2.2`: structural chunking with context carry

`main.py` currently runs `v2.2` by default.

**Validate Chunks**  
`validate_chunks()` checks invariants such as order preservation, max-size rules, overlap behavior, non-whitespace coverage, traceability, offsets, structural integrity, and atomic element coverage.

## Repository Shape

```text
main.py
src/document_chunker/
  chunker.py
  chunking_strategies.py
  counting.py
  evaluator.py
  extractor.py
  heading_detector.py
  list_detector.py
  loader.py
  noise_detector.py
  normalizer.py
  paragraph_normalizer.py
  schemas.py
  step2_pipeline.py
  structured_bridge.py
  structured_models.py
  table_normalizer.py
  table_parser.py
tests/
graphify-out/
data/
```

At a high level:

- the core story is still validate -> extract -> reconstruct -> chunk -> verify
- the repo now has a real structured-document layer, not just flattened normalized text
- the tests are split across stage behavior, structural reconstruction, and invariant enforcement

## Running It

```bash
uv run main.py [path/to/file.pdf] [password]
```

If no arguments are provided, `main.py` defaults to `data/BAWSE.pdf`.

The runner currently:

- validates the input
- loads and extracts the PDF
- builds and checks the structured document
- bridges that structure into the normalized chunking model
- chunks with the active strategy
- prints chunk ranges and sample chunk contents
- validates the chunk output and exits non-zero on chunk invariant failures

## Tests

The graph report and current test tree show coverage across the pipeline and its structural helpers, including:

- `test_loader.py`
- `test_extractor.py`
- `test_normalizer.py`
- `test_normalizer_validation.py`
- `test_chunker.py`
- `test_evaluator.py`
- `test_heading_detector.py`
- `test_list_detector.py`
- `test_noise_detector.py`
- `test_paragraph_normalizer.py`
- `test_table_normalizer.py`
- `test_table_parser.py`
- `test_structured_bridge.py`
- `test_structured_models.py`

The suite is not just stage-by-stage smoke coverage. It also exercises structural reconstruction, heading/list heuristics, noise detection, table behavior, bridging, and chunk/evaluator invariants.

## Graph Artifacts

`graphify-out/` contains three useful outputs:

- `GRAPH_REPORT.md`: human-readable graph summary, community hubs, "god nodes", and graph freshness metadata
- `graph.json`: raw node/edge/community data for downstream tooling
- `graph.html`: interactive graph viewer

The HTML viewer includes:

- searchable nodes
- clickable node inspection
- neighbor browsing
- community legend/filtering
- graph statistics in the sidebar

Regenerate the graph with:

```bash
graphify update .
```

The current report was generated on `2026-08-12` and records commit `b9081536` as its source snapshot.
