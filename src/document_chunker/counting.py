import re

_WORD_RE = re.compile(r"\b\w+(?:[-/'’]\w+)*\b", re.UNICODE)


def count_words(text: str) -> int:
    """Count word-like tokens while ignoring structural separators such as table pipes."""
    return len(_WORD_RE.findall(text))
