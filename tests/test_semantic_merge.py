"""Tests for soulport.semantic_merge — four-layer filter pipeline."""

import pytest

from soulport.semantic_merge import (
    _classify_diff,
    _split_sections,
)


# ── _split_sections ────────────────────────────────────────────────

class TestSplitSections:
    def test_single_section(self):
        text = "# Hello\nWorld\nFoo"
        sections = _split_sections(text)
        assert "# Hello" in sections
        assert "World" in sections["# Hello"]

    def test_multiple_sections(self):
        text = "# A\nContent A\n## B\nContent B\n## C\nContent C"
        sections = _split_sections(text)
        assert "# A" in sections
        assert "## B" in sections
        assert "## C" in sections
        assert "Content A" in sections["# A"]
        assert "Content B" in sections["## B"]

    def test_preamble_before_heading(self):
        text = "Some preamble\n# First\nContent"
        sections = _split_sections(text)
        assert "__preamble__" in sections
        assert "Some preamble" in sections["__preamble__"]

    def test_empty_text(self):
        sections = _split_sections("")
        # Empty string has no splitlines output → no sections created
        assert sections == {}

    def test_preserves_heading_in_content(self):
        """Section content should include the heading line itself."""
        text = "## Title\nBody line 1\nBody line 2"
        sections = _split_sections(text)
        assert sections["## Title"].startswith("## Title")

    def test_h3_recognized(self):
        text = "### Sub\nContent"
        sections = _split_sections(text)
        assert "### Sub" in sections

    def test_h4_not_split(self):
        """Only h1-h3 should split sections."""
        text = "# Main\n#### Detail\nContent"
        sections = _split_sections(text)
        assert "#### Detail" not in sections
        # h4 should be part of the # Main section
        assert "#### Detail" in sections["# Main"]


# ── _classify_diff ─────────────────────────────────────────────────

class TestClassifyDiff:
    def test_pure_append(self):
        text_a = "Line 1\nLine 2"
        text_b = "Line 1\nLine 2\nLine 3\nLine 4"
        classification, _ = _classify_diff(text_a, text_b)
        assert classification == "pure_append"

    def test_tiny_change(self):
        text_a = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10"
        text_b = "Line 1\nLine 2\nChanged\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10"
        classification, diff_text = _classify_diff(text_a, text_b)
        assert classification == "tiny"
        assert diff_text  # should have some diff output

    def test_medium_change(self):
        # 40 lines, change 4 of them → ~20% change ratio → medium
        lines_a = [f"Line {i}" for i in range(40)]
        lines_b = lines_a.copy()
        for i in range(10, 14):
            lines_b[i] = f"Changed {i}"
        text_a = "\n".join(lines_a)
        text_b = "\n".join(lines_b)
        classification, _ = _classify_diff(text_a, text_b)
        assert classification == "medium"

    def test_large_change(self):
        text_a = "A\nB\nC\nD\nE"
        text_b = "V\nW\nX\nY\nZ"
        classification, _ = _classify_diff(text_a, text_b)
        assert classification == "large"

    def test_identical_is_pure_append(self):
        """Identical text should classify as pure_append (B starts with A)."""
        text = "Same content"
        classification, _ = _classify_diff(text, text)
        assert classification == "pure_append"

    def test_diff_text_returned_for_non_append(self):
        text_a = "Alpha\nBeta"
        text_b = "Alpha\nGamma"
        _, diff_text = _classify_diff(text_a, text_b)
        assert "Alpha" in diff_text or "-Beta" in diff_text or "+Gamma" in diff_text
