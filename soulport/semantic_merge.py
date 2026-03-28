"""
SoulPort semantic merge — four-layer cognitive state reconciliation.

Four-layer filter pipeline (Patent Claim Group E):
  Layer 1 (file):    diff_packages() → added/removed/unchanged skip LLM
  Layer 2 (section): _split_sections() → identical/new sections skip LLM
  Layer 3 (line):    _classify_diff() → pure append/tiny changes skip LLM
  Layer 4 (LLM):     only true semantic conflicts reach the model

Each layer eliminates cases that don't need semantic understanding.
LLM is the last resort, not the first tool.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm_config import LLMConfig, load_llm_config

logger = logging.getLogger(__name__)


# ── LLM Client ────────────────────────────────────────────────────

async def _call_llm(prompt: str, config: LLMConfig) -> str:
    """Call LLM via OpenAI-compatible API."""
    import httpx

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{config.api_base}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json={
                "model": config.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8192,
                "temperature": 0.3,  # low temp for deterministic, reproducible merging
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# ── Merge Functions ────────────────────────────────────────────────

@dataclass
class MergeResult:
    """Result of merging a single file."""
    rel_path: str
    strategy: str    # "keep_a", "keep_b", "identical", "llm_merge", "keep_newer", "llm_failed"
    layer: str
    content: bytes   # the merged content
    merge_note: str = ""  # what the LLM decided


@dataclass
class SemanticMergeReport:
    """Full report of a semantic merge operation."""
    results: list[MergeResult] = field(default_factory=list)
    llm_calls: int = 0
    llm_failures: int = 0

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.strategy] = counts.get(r.strategy, 0) + 1
        return counts


DIFF_MERGE_PROMPT = """A markdown section has conflicting changes between two versions.
File: "{filename}", Section: "{section_title}"

Here is the unified diff (- = version A, + = version B):
```diff
{unified_diff}
```

Version B (the newer version):
{text_b}

Merge rules:
1. Start from version B as the base
2. Incorporate any unique additions from version A (shown as - lines) that aren't superseded by B
3. Deduplicate semantically equivalent content
4. Preserve chronological order
5. Output ONLY the merged section content

At the very end, add: <!-- merge: [brief description] -->

Output:"""

IDENTITY_MERGE_PROMPT = """Two versions of the same AI agent's personality file have diverged: "{filename}"

=== VERSION A (source: {source_a}) ===
{text_a}

=== VERSION B (source: {source_b}) ===
{text_b}

Synthesize a unified version that:
1. Incorporates personality evolution from BOTH versions
2. Resolves contradictions by preferring the more specific/recent description
3. Preserves ALL unique personality traits from both
4. Keeps the original markdown format

At the very end, add:
<!-- merge note: [what traits were merged/which version was preferred for conflicts] -->

Output the fused file:"""

CONFIG_MERGE_PROMPT = """Two versions of an AI agent's configuration file have diverged: "{filename}"

=== VERSION A ===
{text_a}

=== VERSION B ===
{text_b}

Merge rules:
1. Union all rules/entries from both versions
2. If a rule appears in both but with different values, prefer VERSION B (assumed newer)
3. Remove exact duplicates
4. Maintain the original format

At the very end, add:
<!-- merge note: [what was unioned/which conflicts were resolved] -->

Output the merged config:"""


async def merge_file_semantic(
    rel_path: str,
    content_a: bytes,
    content_b: bytes,
    layer: str,
    source_a: str,
    source_b: str,
    config: LLMConfig,
) -> MergeResult:
    """Merge a single MODIFIED file using Layers 2-4.
    
    Called only for files that Layer 1 identified as 'modified' (both exist, different content).
    """

    # Skills → keep version B (assumed newer in merge order)
    # Future: compare manifest exported_at timestamps for more accurate selection
    if layer == "skills":
        return MergeResult(
            rel_path=rel_path, strategy="keep_newer", layer=layer,
            content=content_b, merge_note="Kept version B (second package, assumed newer)",
        )

    # Try to decode as text for LLM merge
    try:
        text_a = content_a.decode("utf-8")
        text_b = content_b.decode("utf-8")
    except UnicodeDecodeError:
        # Binary file — keep B (assumed newer)
        return MergeResult(
            rel_path=rel_path, strategy="keep_newer", layer=layer,
            content=content_b, merge_note="Binary file, kept version B",
        )

    # Identity files: small enough for whole-file LLM merge
    if layer in ("identity",):
        prompt = IDENTITY_MERGE_PROMPT.format(
            filename=rel_path, text_a=text_a, text_b=text_b,
            source_a=source_a, source_b=source_b,
        )
        try:
            merged = await _call_llm(prompt, config)
            merge_note = ""
            if "<!-- merge" in merged:
                merge_note = merged[merged.index("<!-- merge"):].strip()
            return MergeResult(
                rel_path=rel_path, strategy="llm_merge", layer=layer,
                content=merged.encode("utf-8"), merge_note=merge_note,
            )
        except Exception as e:
            logger.warning(f"LLM merge failed for {rel_path}: {e}")
            return MergeResult(
                rel_path=rel_path, strategy="llm_failed", layer=layer,
                content=content_b,
                merge_note=f"> \u26a0\ufe0f LLM fusion failed: {e}. Kept version B.",
            )

    # Memory + Config: Layer 2 (section) + Layer 3 (line) + Layer 4 (LLM)
    sections_a = _split_sections(text_a)
    sections_b = _split_sections(text_b)

    all_titles = list(dict.fromkeys(list(sections_a.keys()) + list(sections_b.keys())))
    merged_sections = []
    llm_used = False
    merge_notes = []

    for title in all_titles:
        sa = sections_a.get(title, "")
        sb = sections_b.get(title, "")

        # Layer 2: Section-level filter
        if sa == sb:
            merged_sections.append(sb if sb else sa)
        elif not sa:
            merged_sections.append(sb)
            merge_notes.append(f"+B: {title}")
        elif not sb:
            merged_sections.append(sa)
            merge_notes.append(f"+A: {title}")
        else:
            # Layer 3: Line-level classification
            diff_class, diff_text = _classify_diff(sa, sb)

            if diff_class == "pure_append":
                # B is a superset of A — just keep B
                merged_sections.append(sb)
                merge_notes.append(f"append: {title}")
            elif diff_class == "tiny":
                # < 5 lines changed — not worth LLM, keep B
                merged_sections.append(sb)
                merge_notes.append(f"tiny→B: {title}")
            else:  # "medium" or "large" — Layer 4: LLM semantic merge
                label = "diff" if diff_class == "medium" else "full"
                prompt = DIFF_MERGE_PROMPT.format(
                    filename=rel_path, section_title=title,
                    unified_diff=diff_text, text_b=sb,
                )
                try:
                    merged_text = await _call_llm(prompt, config)
                    merged_sections.append(merged_text)
                    llm_used = True
                    merge_notes.append(f"LLM({label}): {title}")
                except Exception as e:
                    merged_sections.append(sb)
                    merge_notes.append(f"fail→B: {title}")

    final_text = "\n\n".join(merged_sections)
    note = "; ".join(merge_notes) if merge_notes else "all sections identical"

    return MergeResult(
        rel_path=rel_path,
        strategy="llm_merge" if llm_used else "section_diff",
        layer=layer,
        content=final_text.encode("utf-8"),
        merge_note=f"<!-- merge note: {note} -->",
    )


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown text into sections by heading (## or #).
    
    Returns {heading_line: full_section_text} preserving order.
    Content before the first heading goes under key "__preamble__".
    """
    sections: dict[str, str] = {}
    current_key = "__preamble__"
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        if re.match(r'^#{1,3}\s', line):
            # Save previous section
            if current_lines:
                sections[current_key] = "".join(current_lines)
            current_key = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Save last section
    if current_lines:
        sections[current_key] = "".join(current_lines)

    return sections


def _classify_diff(text_a: str, text_b: str) -> tuple[str, str]:
    """Layer 3: Classify the line-level difference between two text sections.
    
    Returns (classification, unified_diff_text):
    - "pure_append": B contains everything in A plus more (zero LLM needed)
    - "tiny": < 5 lines changed (not worth LLM, keep B)
    - "medium": 5-50% of lines differ (send unified diff to LLM)
    - "large": > 50% of lines differ (send both versions to LLM)
    """
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    # Check pure append: B starts with A's content
    if text_b.startswith(text_a.rstrip()):
        return "pure_append", ""

    # Generate unified diff
    diff_lines = list(difflib.unified_diff(
        lines_a, lines_b, fromfile="A", tofile="B", n=2
    ))
    diff_text = "".join(diff_lines)

    # Count actual changes (ignore diff headers)
    added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
    total_changes = added + removed

    if total_changes < 5:
        return "tiny", diff_text

    total_lines = max(len(lines_a), len(lines_b), 1)
    change_ratio = total_changes / total_lines

    if change_ratio > 0.5:
        return "large", diff_text
    else:
        return "medium", diff_text


async def semantic_merge_packages(
    files_a: dict[str, bytes],
    files_b: dict[str, bytes],
    layer_map: dict[str, str],
    source_a: str = "source-A",
    source_b: str = "source-B",
    config: Optional[LLMConfig] = None,
) -> SemanticMergeReport:
    """Merge all files using four-layer filter pipeline.
    
    Layer 1 (file): classify files as added/removed/unchanged/modified
    Layers 2-4: handled inside merge_file_semantic() for modified files
    """
    if config is None:
        config = load_llm_config()

    report = SemanticMergeReport()
    all_paths = sorted(set(files_a.keys()) | set(files_b.keys()))

    # Layer 1: File-level classification (replaces manual comparison)
    tasks = []
    for rel_path in all_paths:
        in_a = rel_path in files_a
        in_b = rel_path in files_b
        layer = layer_map.get(rel_path, "unknown")

        if in_a and not in_b:
            report.results.append(MergeResult(
                rel_path=rel_path, strategy="keep_a", layer=layer,
                content=files_a[rel_path],
            ))
        elif in_b and not in_a:
            report.results.append(MergeResult(
                rel_path=rel_path, strategy="keep_b", layer=layer,
                content=files_b[rel_path],
            ))
        elif files_a[rel_path] == files_b[rel_path]:
            # Layer 1 filter: identical files → skip entirely
            report.results.append(MergeResult(
                rel_path=rel_path, strategy="identical", layer=layer,
                content=files_a[rel_path],
            ))
        else:
            # Modified file → Layers 2-4 inside merge_file_semantic
            tasks.append(merge_file_semantic(
                rel_path, files_a[rel_path], files_b[rel_path],
                layer, source_a, source_b, config,
            ))

    # Run merge tasks in parallel (LLM calls are async)
    if tasks:
        merge_results = await asyncio.gather(*tasks)
        for r in merge_results:
            report.results.append(r)
            if r.strategy == "llm_merge":
                report.llm_calls += 1
            elif r.strategy == "llm_failed":
                report.llm_calls += 1
                report.llm_failures += 1

    return report
