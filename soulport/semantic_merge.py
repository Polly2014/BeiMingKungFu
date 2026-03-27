"""
SoulPort semantic merge — LLM-assisted cognitive state reconciliation.

Uses LLM to intelligently merge divergent agent memories, identities,
and configurations. This is the core differentiator (Patent Claim Group E).

Merge decision matrix:
- File only in A → keep as-is (zero LLM)
- File only in B → keep as-is (zero LLM)
- Both identical  → keep as-is (zero LLM)
- Both different + Memory/Identity → LLM semantic merge
- Both different + Config → LLM merge
- Both different + Skills → keep newer version (by content length)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm_config import LLMConfig, load_llm_config

logger = logging.getLogger(__name__)


# ── LLM Client ────────────────────────────────────────────────────

async def _call_llm(prompt: str, config: LLMConfig) -> str:
    """Call LLM via OpenAI-compatible API."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{config.api_base}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json={
                "model": config.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.3,  # low temperature for deterministic merging
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


MEMORY_MERGE_PROMPT = """You are merging two versions of an AI agent's memory file: "{filename}"

These two versions diverged because the same agent was used on different machines.
Your job is to produce a single, unified version.

=== VERSION A (source: {source_a}) ===
{text_a}

=== VERSION B (source: {source_b}) ===
{text_b}

Rules:
1. If both describe the same event, keep the MORE DETAILED version
2. Deduplicate semantically equivalent entries (not just exact text match)
3. Maintain chronological order (earliest first)
4. Preserve unique details that only appear in one version
5. Keep the original markdown structure and formatting
6. Do NOT add any commentary or explanation — output ONLY the merged content

At the very end, add a single HTML comment with your merge decisions:
<!-- merge note: [brief description of what was deduplicated/reordered/kept] -->

Output the merged file:"""

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
    """Merge a single file using LLM if needed."""

    # Identical → no merge needed
    if content_a == content_b:
        return MergeResult(
            rel_path=rel_path, strategy="identical", layer=layer,
            content=content_a,
        )

    # Skills → keep longer version (assumed more evolved)
    if layer == "skills":
        if len(content_b) >= len(content_a):
            return MergeResult(
                rel_path=rel_path, strategy="keep_newer", layer=layer,
                content=content_b, merge_note="Kept version B (longer/newer)",
            )
        else:
            return MergeResult(
                rel_path=rel_path, strategy="keep_newer", layer=layer,
                content=content_a, merge_note="Kept version A (longer)",
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

    # Choose prompt based on layer
    if layer in ("memory",):
        prompt = MEMORY_MERGE_PROMPT
    elif layer in ("identity",):
        prompt = IDENTITY_MERGE_PROMPT
    else:  # config, system, unknown
        prompt = CONFIG_MERGE_PROMPT

    prompt = prompt.format(
        filename=rel_path,
        text_a=text_a[:8000],  # truncate to avoid token limits
        text_b=text_b[:8000],
        source_a=source_a,
        source_b=source_b,
    )

    try:
        merged_text = await _call_llm(prompt, config)
        # Extract merge note
        merge_note = ""
        if "<!-- merge note:" in merged_text:
            note_start = merged_text.index("<!-- merge note:")
            merge_note = merged_text[note_start:].strip()

        return MergeResult(
            rel_path=rel_path, strategy="llm_merge", layer=layer,
            content=merged_text.encode("utf-8"),
            merge_note=merge_note,
        )
    except Exception as e:
        logger.warning(f"LLM merge failed for {rel_path}: {e}. Falling back to keep-both.")
        # Fallback: concatenate with separator
        fallback = (
            f"<!-- MERGE CONFLICT: LLM failed ({e}). Both versions kept. -->\n\n"
            f"<!-- === VERSION A === -->\n{text_a}\n\n"
            f"<!-- === VERSION B === -->\n{text_b}\n"
        ).encode("utf-8")
        return MergeResult(
            rel_path=rel_path, strategy="llm_failed", layer=layer,
            content=fallback,
            merge_note=f"LLM failed: {e}",
        )


async def semantic_merge_packages(
    files_a: dict[str, bytes],
    files_b: dict[str, bytes],
    layer_map: dict[str, str],
    source_a: str = "source-A",
    source_b: str = "source-B",
    config: Optional[LLMConfig] = None,
) -> SemanticMergeReport:
    """Merge all files from two packages using semantic strategies."""
    if config is None:
        config = load_llm_config()

    report = SemanticMergeReport()
    all_paths = sorted(set(files_a.keys()) | set(files_b.keys()))

    # Separate into LLM-needed and no-LLM
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
        elif in_a and in_b:
            # Need merge — may or may not call LLM
            tasks.append(merge_file_semantic(
                rel_path, files_a[rel_path], files_b[rel_path],
                layer, source_a, source_b, config,
            ))

    # Run LLM merges in parallel
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
