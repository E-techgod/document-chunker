from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field, model_validator

# Phase 1 data models for the Step 2 "Normalize + Preserve Structure" redesign.
#
# NormalizedBlock here is a *different*, unrelated shape from
# document_chunker.schemas.NormalizedBlock (block_type/items/table, used throughout the
# current chunker.py/normalizer.py/evaluator.py pipeline). This module is not wired into
# that pipeline yet - it exists on its own until a later phase connects the two. Import
# the one your caller actually needs; the class name is intentionally the same in both
# modules per the Step 2 spec, so always import by full module path, not by bare name.


class NormalizedBlock(BaseModel):
    """Common attributes shared by every reconstructed layout block."""

    block_id: str
    type: Literal["heading", "paragraph", "list", "table", "page_header", "page_footer"]
    text: str
    page: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    is_noise: bool = False


class HeadingBlock(NormalizedBlock):
    type: Literal["heading"] = "heading"
    level: int | None = None


class ParagraphBlock(NormalizedBlock):
    type: Literal["paragraph"] = "paragraph"


class PageHeaderBlock(NormalizedBlock):
    """A running header, detected by recurring text (or a page-number pattern) at the
    top of many pages - see noise_detector.detect_noise_lines. Kept as a normal block
    for traceability; is_noise marks it excludable from chunkable content."""

    type: Literal["page_header"] = "page_header"
    is_noise: bool = True


class PageFooterBlock(NormalizedBlock):
    """A running footer (page numbers, repeated branding/copyright), detected the same
    way as PageHeaderBlock but from the bottom of the page."""

    type: Literal["page_footer"] = "page_footer"
    is_noise: bool = True


class ListBlock(NormalizedBlock):
    type: Literal["list"] = "list"
    items: list[str] = Field(default_factory=list)


class TableBlock(NormalizedBlock):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    @computed_field
    @property
    def is_rectangular(self) -> bool:
        """Whether every row's length matches len(columns). Informational only - rows
        are not required to align (real-world tables are often ragged; see
        TableNormalizer), so this is never enforced as a validator."""
        return all(len(row) == len(self.columns) for row in self.rows)


AnyBlock = Annotated[
    HeadingBlock | ParagraphBlock | ListBlock | TableBlock | PageHeaderBlock | PageFooterBlock,
    Field(discriminator="type"),
]


class StructuredNormalizedDocument(BaseModel):
    """Root object for the Step 2 structured-normalization output."""

    document_id: str
    full_text: str
    blocks: list[AnyBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_block_ids(self) -> StructuredNormalizedDocument:
        seen: set[str] = set()
        for block in self.blocks:
            if block.block_id in seen:
                raise ValueError(f"duplicate block_id: {block.block_id!r}")
            seen.add(block.block_id)
        return self

    @property
    def content_blocks(self) -> list[AnyBlock]:
        """blocks excluding detected noise (page headers/footers, page numbers,
        repeated branding/copyright) - the set a chunker should consume. `blocks`
        itself keeps everything, noise included, for traceability."""
        return [block for block in self.blocks if not block.is_noise]

    def to_dict(self) -> dict:
        """Dump the document to a plain dict (debugging/inspection - no I/O)."""
        return self.model_dump()

    def to_json(self, **kwargs) -> str:
        """Dump the document to a JSON string (debugging/inspection - no I/O)."""
        return self.model_dump_json(**kwargs)

    def validate_spans(self) -> list[str]:
        """Check full_text[block.start_char:block.end_char] == block.text for every
        block. Returns violation messages, one per failing block; an empty list means
        every span is valid."""
        issues = []
        for block in self.blocks:
            actual = self.full_text[block.start_char : block.end_char]
            if actual != block.text:
                issues.append(
                    f"{block.block_id}: full_text[{block.start_char}:{block.end_char}] "
                    f"({actual!r}) does not match block.text ({block.text!r})"
                )
        return issues

    def assert_spans_valid(self) -> None:
        """Raise AssertionError if any block fails the span invariant."""
        issues = self.validate_spans()
        assert not issues, "; ".join(issues)
