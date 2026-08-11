import re

from document_chunker.normalizer import _measure_indent

# Phase 4 of the Step 2 redesign: list-item detection for paragraph_normalizer's
# _split_into_blocks. Like heading detection (Phase 3), there's no font/coordinate
# metadata to work from - the "Indentation/Alignment" signal from the task spec is
# approximated using each physical line's own leading whitespace (already meaningful in
# real single-column PDF extraction, per this repo's own sample data), the same way
# normalizer.py's existing _is_list_continuation already does for the current pipeline:
# a continuation line belongs to the item above it when indented further than that
# item's own marker.

_LIST_MARKER_RE = re.compile(
    r"^(?:"
    r"[•⁃■●→–*\-]"         # symbol bullets ('●'/'→' are the actual bullets in this repo's own sample PDFs)
    r"|\d+[.)]"             # 1.  2)
    r"|\([A-Za-z0-9]+\)"    # (a)  (1)
    r"|[A-Za-z][.)]"        # A.  a)  i.
    r"|\[\d+\]"             # [1]
    r")\s+"
)


def match_list_item(line: str) -> str | None:
    """The item text with its leading bullet/number marker stripped and surrounding
    whitespace trimmed, if `line` starts with a recognized list marker; else None (also
    None for a marker with nothing after it, e.g. a bare "-")."""
    match = _LIST_MARKER_RE.match(line)
    if not match:
        return None
    remainder = line[match.end() :].strip()
    return remainder or None


def is_continuation_line(raw_line: str, marker_indent: int) -> bool:
    """Whether `raw_line` (unstripped, so its own leading whitespace is intact) wraps
    the list item whose marker started at `marker_indent`. Real extracted text doesn't
    reliably indent a wrapped line past its marker's own column - often it lines up
    exactly with it, not with the text after the bullet symbol - so this only rules out
    lines indented *less* than the marker (the body-paragraph margin), rather than
    requiring strictly deeper indent."""
    return _measure_indent(raw_line) >= marker_indent
