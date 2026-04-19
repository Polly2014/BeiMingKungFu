"""
SoulPort scorer — five-dimension statistical scoring for Agent souls.

Scores a .bm package across 5 dimensions (0-100 each):
    🧠 Memory Depth       25%  — memory count, span, density, main-file size
    👤 Personality        25%  — SOUL.md richness, IDENTITY.md fields, USER.md
    ⚙️ Habit Maturity    15%  — AGENTS.md rules, TOOLS.md notes, HEARTBEAT.md
    🛠️ Skill Breadth     20%  — skill count, diversity, total bytes
    🎭 Uniqueness         15%  — soul size, skills, memories, overall footprint

This module provides **statistical scoring only** (zero external dependencies,
no LLM calls). It is framework-agnostic: works with OpenClaw, Claude Code,
GitHub Copilot, or any .bm package conforming to FORMAT.md v1.

For LLM-augmented scoring (5-dim LLM evaluation + biography generation),
downstream consumers (e.g. SoulArena) layer their own LLM logic on top of
`analyze_bm_file()` + the stats functions here.

Public API:
    analyze_bm_file(bm_path) -> dict            — extract all scorable signals
    score_soul(bm_path) -> SoulScores            — one-shot stats scoring
    score_from_analysis(analysis) -> SoulScores  — score pre-computed analysis

    score_memory_depth(analysis) -> float
    score_personality_richness(analysis) -> float
    score_habit_maturity(analysis) -> float
    score_skill_breadth(analysis) -> float
    score_uniqueness(analysis) -> float
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .core import inspect_soul, read_soul
from .manifest import Manifest


# ── Data classes ───────────────────────────────────────────────────

@dataclass
class DimensionScore:
    """Single dimension score result."""
    name: str           # e.g. "Memory Depth"
    name_zh: str        # e.g. "记忆深度"
    emoji: str          # e.g. "🧠"
    raw_score: float    # 0-100
    weight: float       # e.g. 0.25
    weighted_score: float  # raw_score * weight

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SoulScores:
    """Full five-dimension scoring result."""
    memory_depth: DimensionScore
    personality_richness: DimensionScore
    habit_maturity: DimensionScore
    skill_breadth: DimensionScore
    uniqueness: DimensionScore
    total_score: float  # weighted sum (0-100)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_depth": self.memory_depth.to_dict(),
            "personality_richness": self.personality_richness.to_dict(),
            "habit_maturity": self.habit_maturity.to_dict(),
            "skill_breadth": self.skill_breadth.to_dict(),
            "uniqueness": self.uniqueness.to_dict(),
            "total_score": self.total_score,
        }


# ── Dimension weights ─────────────────────────────────────────────

WEIGHTS = {
    "memory": 0.25,
    "personality": 0.25,
    "habits": 0.15,
    "skills": 0.20,
    "uniqueness": 0.15,
}

DIMENSIONS = {
    "memory": ("Memory Depth", "记忆深度", "🧠"),
    "personality": ("Personality Richness", "人格丰富度", "👤"),
    "habits": ("Habit Maturity", "习惯成熟度", "⚙️"),
    "skills": ("Skill Breadth", "技能广度", "🛠️"),
    "uniqueness": ("Uniqueness", "独特性", "🎭"),
}


# ── Analysis (extract scorable signals from .bm) ──────────────────

def analyze_bm_file(bm_path: Path) -> dict[str, Any]:
    """
    Extract all data needed for scoring from a .bm package.

    Uses read_soul() internally — no direct tar operations.
    Framework-agnostic: works with OpenClaw, Claude Code, GitHub Copilot.

    Returns a dict with:
        - agent_name, source_host, source_framework, exported_at, content_hash
        - identity_content, memory_md, config_content, skill_descriptions
        - skill_count, skill_dirs
        - memory_count, memory_span_days, memory_dates
        - total_bytes, layer_summary
        - Legacy aliases: soul_md, identity_md, user_md, agents_md, tools_md, heartbeat_md
    """
    manifest: Manifest = inspect_soul(bm_path)

    result: dict[str, Any] = {
        "agent_name": manifest.agent_name,
        "source_host": manifest.source_host,
        "exported_at": manifest.exported_at,
        "content_hash": manifest.content_hash,
        "source_framework": getattr(manifest, "source_framework", ""),
        "layer_summary": {},
        "total_bytes": 0,
    }

    for layer in manifest.layers:
        result["layer_summary"][layer.name] = {
            "file_count": layer.file_count,
            "total_bytes": layer.total_bytes,
            "files": layer.files,
        }
        result["total_bytes"] += layer.total_bytes

    contents = read_soul(bm_path)

    # --- Identity ---
    identity_files = contents.get("identity", {})
    identity_parts = [f"--- {f} ---\n{c}" for f, c in identity_files.items() if c]
    result["identity_content"] = "\n\n".join(identity_parts)
    # Legacy aliases for stat functions (OpenClaw-native names, fall back to CLAUDE.md)
    result["soul_md"] = (
        _find_basename(identity_files, "SOUL.md")
        or _find_basename(identity_files, "CLAUDE.md")
        or _find_basename(identity_files, "copilot-instructions.md")
        or ""
    )
    result["identity_md"] = _find_basename(identity_files, "IDENTITY.md") or ""
    result["user_md"] = _find_basename(identity_files, "USER.md") or ""

    # --- Memory ---
    memory_files = contents.get("memory", {})
    result["memory_count"] = len(memory_files)

    main_memory = (
        _find_basename(memory_files, "MEMORY.md")
        or memory_files.get("memory/MEMORY.md", "")
    )
    if not main_memory and memory_files:
        # Fallback: no canonical MEMORY.md → concatenate all memory files
        # (capped at 100 KB). Note: ``memory_md_size`` then reflects this
        # aggregate, so md_score may skew higher than with a single main file.
        # That's intentional: non-OpenClaw agents legitimately have no root
        # MEMORY.md and we still want to credit accumulated memory content.
        parts = []
        total_read = 0
        for f, c in memory_files.items():
            if total_read > 100_000:
                break
            parts.append(f"--- {f} ---\n{c}")
            total_read += len(c.encode("utf-8"))
        main_memory = "\n\n".join(parts)

    result["memory_md"] = main_memory
    result["memory_md_size"] = len(main_memory.encode("utf-8"))

    memory_dates: list[str] = []
    for f in memory_files:
        fname = Path(f).stem
        if re.match(r"\d{4}-\d{2}-\d{2}", fname):
            memory_dates.append(fname[:10])
    memory_dates.sort()
    result["memory_dates"] = memory_dates
    result["memory_total_bytes"] = result["layer_summary"].get("memory", {}).get("total_bytes", 0)

    if len(memory_dates) >= 2:
        try:
            first = datetime.strptime(memory_dates[0], "%Y-%m-%d")
            last = datetime.strptime(memory_dates[-1], "%Y-%m-%d")
            result["memory_span_days"] = (last - first).days
        except ValueError:
            result["memory_span_days"] = 0
    else:
        result["memory_span_days"] = 0

    # --- Config ---
    config_files = contents.get("config", {})
    config_parts = [f"--- {f} ---\n{c}" for f, c in config_files.items() if c]
    result["config_content"] = "\n\n".join(config_parts)
    result["agents_md"] = _find_basename(config_files, "AGENTS.md") or ""
    result["tools_md"] = _find_basename(config_files, "TOOLS.md") or ""
    result["heartbeat_md"] = _find_basename(config_files, "HEARTBEAT.md") or ""

    # --- Skills ---
    skill_files = contents.get("skills", {})
    skill_dirs, _ = extract_skill_dirs(skill_files)

    result["skill_count"] = len(skill_dirs)
    result["skill_dirs"] = sorted(skill_dirs)
    result["skill_total_bytes"] = result["layer_summary"].get("skills", {}).get("total_bytes", 0)

    skill_descriptions = []
    seen_skills: set[str] = set()
    for f, content in skill_files.items():
        if not (f.endswith(".md") or f.endswith(".prompt.md")):
            continue
        if not content:
            continue
        skill_name = Path(f).parent.name or Path(f).stem
        if skill_name in seen_skills or skill_name in ("skills", "prompts", ".claude", ".github"):
            continue
        seen_skills.add(skill_name)

        lines = content.strip().split("\n")
        title = skill_name
        desc = ""
        for line in lines:
            if line.startswith("# ") and title == skill_name:
                title = line.lstrip("# ").strip()
            elif line.strip() and not line.startswith("#") and not desc:
                desc = line.strip()[:150]
        skill_descriptions.append(f"- {title}: {desc}" if desc else f"- {title}")

    result["skill_descriptions"] = "\n".join(skill_descriptions) if skill_descriptions else "（无技能）"

    return result


def _find_basename(files: dict[str, str], basename: str) -> str | None:
    """Find content by basename in a {path: content} dict."""
    for path, content in files.items():
        if Path(path).name == basename:
            return content
    return None


def extract_skill_dirs(skill_files: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Extract skill directory names from a {path: content_or_any} map.

    Returns ``(all_dirs, dirs_with_skill_md)``. Shared by :mod:`soulport.scorer`
    and :mod:`soulport.doctor` so both use identical heuristics.

    The path may be nested (e.g. ``.claude/skills/blog-writer/SKILL.md``,
    ``.github/prompts/translate.prompt.md``, ``skills/memory-keeper/SKILL.md``);
    known umbrella segments are skipped so we land on the real skill name.
    """
    all_dirs: set[str] = set()
    with_skill_md: set[str] = set()
    umbrella = {"skills", ".claude", ".github", "prompts"}

    for path in skill_files:
        parts = path.split("/")
        skill_name: str | None = None
        for i, part in enumerate(parts):
            if part in umbrella:
                continue
            if i < len(parts) - 1:
                skill_name = part
                break
        if skill_name is None:
            stem = Path(path).stem
            if stem:
                skill_name = stem
        if not skill_name:
            continue
        all_dirs.add(skill_name)
        if Path(path).name in ("SKILL.md", "skill.md"):
            with_skill_md.add(skill_name)

    return all_dirs, with_skill_md


# ── Statistical scoring functions ─────────────────────────────────

def score_memory_depth(analysis: dict) -> float:
    """🧠 Memory Depth (0-100) = count + span + density + main-file size."""
    count = analysis.get("memory_count", 0)
    count_score = min(40, 40 * math.log1p(count) / math.log1p(100))

    span = analysis.get("memory_span_days", 0)
    span_score = min(25, 25 * math.log1p(span) / math.log1p(365))

    if span > 0:
        density = count / (span / 30)
        density_score = min(15, 15 * math.log1p(density) / math.log1p(30))
    elif count > 0:
        density_score = 8
    else:
        density_score = 0

    md_size = analysis.get("memory_md_size", 0)
    md_score = min(20, 20 * math.log1p(md_size) / math.log1p(5000))

    return min(100, count_score + span_score + density_score + md_score)


def score_personality_richness(analysis: dict) -> float:
    """👤 Personality (0-100) = SOUL.md size+structure + IDENTITY fields + USER.md."""
    soul = analysis.get("soul_md", "")
    soul_size = len(soul.encode("utf-8"))
    soul_score = min(30, 30 * math.log1p(soul_size) / math.log1p(3000))

    headings = len(re.findall(r"^#{1,3}\s", soul, re.MULTILINE))
    soul_score += min(10, headings * 2)

    identity = analysis.get("identity_md", "")
    # Field count: support `- **Name`, `- Name:`/`Name：`, and `## Name`/`### Name`
    # heading forms so IDENTITY.md with mixed bullet/heading layout isn't under-scored.
    fields = len(re.findall(r"^[-*]\s+\*\*\w+", identity, re.MULTILINE))
    fields += len(re.findall(r"^[-*]\s+\w+\s*[:：]", identity, re.MULTILINE))
    fields += len(re.findall(r"^#{2,3}\s+\w+", identity, re.MULTILINE))
    identity_score = min(30, fields * 3)

    user = analysis.get("user_md", "")
    user_size = len(user.encode("utf-8"))
    user_score = min(30, 30 * math.log1p(user_size) / math.log1p(2000))

    return min(100, soul_score + identity_score + user_score)


def score_habit_maturity(analysis: dict) -> float:
    """⚙️ Habits (0-100) = AGENTS.md (with rule heuristics) + TOOLS.md + HEARTBEAT.md."""
    agents = analysis.get("agents_md", "")
    agents_size = len(agents.encode("utf-8"))
    agents_score = min(30, 30 * math.log1p(agents_size) / math.log1p(3000))
    rules = len(re.findall(r"(?:must|always|never|should|prefer|avoid)", agents, re.IGNORECASE))
    agents_score += min(10, rules * 2)

    tools = analysis.get("tools_md", "")
    tools_size = len(tools.encode("utf-8"))
    tools_score = min(30, 30 * math.log1p(tools_size) / math.log1p(2000))

    heartbeat = analysis.get("heartbeat_md", "")
    hb_size = len(heartbeat.encode("utf-8"))
    hb_score = min(20, 20 * math.log1p(hb_size) / math.log1p(1500))
    tasks = len(re.findall(r"(?:every|daily|weekly|cron|schedule|routine)", heartbeat, re.IGNORECASE))
    hb_score += min(10, tasks * 2)

    return min(100, agents_score + tools_score + hb_score)


def score_skill_breadth(analysis: dict) -> float:
    """🛠️ Skills (0-100) = count + diversity (categories) + total bytes."""
    count = analysis.get("skill_count", 0)
    dirs = analysis.get("skill_dirs", [])

    count_score = min(60, 60 * math.log1p(count) / math.log1p(20))

    category_keywords = {
        "writing": ["writer", "blog", "paper", "doc", "write"],
        "coding": ["code", "dev", "debug", "build", "test"],
        "design": ["design", "figur", "chart", "draw", "svg"],
        "data": ["data", "analy", "stat", "ml", "ai"],
        "ops": ["deploy", "ops", "ci", "cd", "monitor"],
        "communication": ["chat", "mail", "message", "translate"],
        "creative": ["video", "music", "art", "creative", "soul"],
        "system": ["memory", "config", "optim", "system"],
    }
    categories: set[str] = set()
    for skill_name in dirs:
        skill_lower = skill_name.lower()
        for cat, keywords in category_keywords.items():
            if any(kw in skill_lower for kw in keywords):
                categories.add(cat)
                break
        else:
            categories.add("other")

    diversity_score = min(20, len(categories) * 4)

    total_bytes = analysis.get("skill_total_bytes", 0)
    bytes_score = min(20, 20 * math.log1p(total_bytes) / math.log1p(50_000))

    return min(100, count_score + diversity_score + bytes_score)


def score_uniqueness(analysis: dict) -> float:
    """🎭 Uniqueness (0-100) — soul footprint estimation.

    Stats-only uniqueness is weak by nature (LLM-augmented scoring dominates here).
    Uses: identity footprint (SOUL.md → fallback full identity_content for non-OpenClaw
    frameworks like Claude Code / Copilot), skill count, memory count, total package bytes.
    """
    score = 0.0
    # Identity footprint: prefer SOUL.md (OpenClaw), fall back to full identity_content
    # so Claude Code / Copilot agents whose personality lives in CLAUDE.md +
    # copilot-instructions.md aren't capped artificially low.
    soul_size = len(analysis.get("soul_md", "").encode("utf-8"))
    if soul_size == 0:
        soul_size = len(analysis.get("identity_content", "").encode("utf-8"))
    score += min(30, 30 * math.log1p(soul_size) / math.log1p(5000))
    skill_count = analysis.get("skill_count", 0)
    score += min(30, skill_count * 3)
    memory_count = analysis.get("memory_count", 0)
    score += min(20, 20 * math.log1p(memory_count) / math.log1p(50))
    total_kb = analysis.get("total_bytes", 0) / 1024
    score += min(20, 20 * math.log1p(total_kb) / math.log1p(200))
    return min(100, score)


# ── High-level API ────────────────────────────────────────────────

def score_from_analysis(analysis: dict) -> SoulScores:
    """Score a soul from pre-computed analysis dict (stats-only)."""
    raw = {
        "memory": score_memory_depth(analysis),
        "personality": score_personality_richness(analysis),
        "habits": score_habit_maturity(analysis),
        "skills": score_skill_breadth(analysis),
        "uniqueness": score_uniqueness(analysis),
    }

    dim_scores: dict[str, DimensionScore] = {}
    for key, (name_en, name_zh, emoji) in DIMENSIONS.items():
        dim_scores[key] = DimensionScore(
            name=name_en,
            name_zh=name_zh,
            emoji=emoji,
            raw_score=round(raw[key], 1),
            weight=WEIGHTS[key],
            weighted_score=round(raw[key] * WEIGHTS[key], 1),
        )

    total = round(sum(d.weighted_score for d in dim_scores.values()), 1)

    return SoulScores(
        memory_depth=dim_scores["memory"],
        personality_richness=dim_scores["personality"],
        habit_maturity=dim_scores["habits"],
        skill_breadth=dim_scores["skills"],
        uniqueness=dim_scores["uniqueness"],
        total_score=total,
    )


def score_soul(bm_path: Path) -> tuple[SoulScores, dict]:
    """Convenience: analyze + score in one call. Returns (scores, analysis)."""
    analysis = analyze_bm_file(bm_path)
    return score_from_analysis(analysis), analysis
