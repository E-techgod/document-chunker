# Graph Report - .  (2026-08-05)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 14 nodes · 13 edges · 5 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d7e0f442`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- PDFDocumentInput
- PDFLoadError
- load_pdf

## God Nodes (most connected - your core abstractions)
1. `PDFDocumentInput` - 5 edges
2. `load_pdf()` - 5 edges
3. `PDFLoadError` - 4 edges
4. `Raised when a PDF cannot be opened, is corrupted, or cannot be decrypted.` - 1 edges
5. `Validated input for loading a single PDF document.` - 1 edges
6. `Open and validate the PDF referenced by `document`.      Checks that the file ca` - 1 edges

## Surprising Connections (you probably didn't know these)
- `load_pdf()` --calls--> `PDFLoadError`  [EXTRACTED]
  loader.py → loader.py  _Bridges community 1 → community 2_
- `load_pdf()` --references--> `PDFDocumentInput`  [EXTRACTED]
  loader.py → loader.py  _Bridges community 0 → community 2_

## Import Cycles
- None detected.

## Communities (5 total, 0 thin omitted)

### Community 0 - "PDFDocumentInput"
Cohesion: 0.40
Nodes (4): BaseModel, PDFDocumentInput, Validated input for loading a single PDF document., Path

### Community 1 - "PDFLoadError"
Cohesion: 0.50
Nodes (3): Exception, PDFLoadError, Raised when a PDF cannot be opened, is corrupted, or cannot be decrypted.

### Community 2 - "load_pdf"
Cohesion: 0.67
Nodes (3): load_pdf(), Open and validate the PDF referenced by `document`.      Checks that the file ca, PdfReader

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PDFDocumentInput` connect `PDFDocumentInput` to `PDFLoadError`, `load_pdf`?**
  _High betweenness centrality (0.423) - this node is a cross-community bridge._
- **Why does `load_pdf()` connect `load_pdf` to `PDFDocumentInput`, `PDFLoadError`?**
  _High betweenness centrality (0.340) - this node is a cross-community bridge._
- **Why does `PDFLoadError` connect `PDFLoadError` to `load_pdf`?**
  _High betweenness centrality (0.244) - this node is a cross-community bridge._