"""Tests for soulport.scorer — five-dimension statistical scoring."""

from pathlib import Path

import pytest

from soulport.core import export_soul
from soulport.scorer import (
    DimensionScore,
    SoulScores,
    analyze_bm_file,
    extract_skill_dirs,
    score_from_analysis,
    score_habit_maturity,
    score_memory_depth,
    score_personality_richness,
    score_skill_breadth,
    score_soul,
    score_uniqueness,
)


# ── Helpers ────────────────────────────────────────────────────────

def _rich_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "IDENTITY.md").write_text(
        "Name: Agent\n\n- **role**: tester\n- **stage**: mature\n", encoding="utf-8"
    )
    (ws / "SOUL.md").write_text(
        "# Personality\n## Values\nCurious.\n## Style\nCheerful.\n" * 5, encoding="utf-8"
    )
    (ws / "USER.md").write_text("Polly. Shanghai." * 40, encoding="utf-8")
    (ws / "MEMORY.md").write_text("# Memory\n" + ("- entry\n" * 100), encoding="utf-8")
    (ws / "AGENTS.md").write_text(
        "Must write tests. Always review. Never skip CI. Prefer stability." * 10, encoding="utf-8"
    )
    (ws / "TOOLS.md").write_text("git notes.\n" * 50, encoding="utf-8")
    (ws / "HEARTBEAT.md").write_text("Every day: export. Daily routine.", encoding="utf-8")

    mem_dir = ws / "memory"
    mem_dir.mkdir()
    for day in range(1, 25):
        (mem_dir / f"2026-04-{day:02d}.md").write_text(f"day {day}\n" * 20, encoding="utf-8")

    skills = ws / "skills"
    for name in ("blog-writer", "code-diffusion", "paper-figurer", "design-kit"):
        d = skills / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\nHelpful skill content.\n" * 20, encoding="utf-8")
    return ws


def _thin_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws-thin"
    ws.mkdir()
    (ws / "IDENTITY.md").write_text("Name: A\n🤖", encoding="utf-8")
    (ws / "AGENTS.md").write_text("Tiny.", encoding="utf-8")
    return ws


# ── analyze_bm_file ───────────────────────────────────────────────

class TestAnalyze:
    def test_extracts_manifest_fields(self, tmp_path):
        ws = _rich_workspace(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "rich.bm")
        a = analyze_bm_file(bm)

        assert a["agent_name"]
        assert a["content_hash"]
        assert a["source_framework"]
        assert a["total_bytes"] > 0

    def test_extracts_five_layer_signals(self, tmp_path):
        ws = _rich_workspace(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "rich.bm")
        a = analyze_bm_file(bm)

        assert a["soul_md"], "SOUL.md content should be extracted"
        assert a["identity_md"], "IDENTITY.md content should be extracted"
        assert a["user_md"], "USER.md content should be extracted"
        assert a["agents_md"], "AGENTS.md content should be extracted"
        assert a["memory_count"] >= 24
        assert a["skill_count"] == 4
        assert a["memory_span_days"] > 0

    def test_works_on_thin_workspace(self, tmp_path):
        ws = _thin_workspace(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "thin.bm")
        a = analyze_bm_file(bm)
        assert a["memory_count"] == 0
        assert a["skill_count"] == 0


# ── Individual stats functions ────────────────────────────────────

class TestStats:
    def test_memory_depth_monotonic(self):
        low = score_memory_depth({"memory_count": 1, "memory_span_days": 0, "memory_md_size": 100})
        high = score_memory_depth({"memory_count": 100, "memory_span_days": 300, "memory_md_size": 10000})
        assert 0 <= low < high <= 100

    def test_personality_monotonic(self):
        low = score_personality_richness({"soul_md": "", "identity_md": "", "user_md": ""})
        high = score_personality_richness({
            "soul_md": "# Header\n" * 20 + "long content " * 500,
            "identity_md": "- **name**: X\n- **role**: Y\n" * 20,
            "user_md": "context " * 500,
        })
        assert low < high

    def test_habits_rewards_custom_rules(self):
        plain = score_habit_maturity({"agents_md": "hello world", "tools_md": "", "heartbeat_md": ""})
        rules = score_habit_maturity({
            "agents_md": "must do X. always do Y. never skip Z. " * 20,
            "tools_md": "",
            "heartbeat_md": "",
        })
        assert rules > plain

    def test_skills_monotonic(self):
        low = score_skill_breadth({"skill_count": 0, "skill_dirs": [], "skill_total_bytes": 0})
        high = score_skill_breadth({
            "skill_count": 15,
            "skill_dirs": ["blog-writer", "code-dev", "design-kit", "data-analy", "deploy-ops"],
            "skill_total_bytes": 100_000,
        })
        assert low < high

    def test_uniqueness_floor_and_ceiling(self):
        low = score_uniqueness({"soul_md": "", "skill_count": 0, "memory_count": 0, "total_bytes": 0})
        high = score_uniqueness({
            "soul_md": "x" * 10_000,
            "skill_count": 20,
            "memory_count": 100,
            "total_bytes": 500_000,
        })
        assert 0 <= low < high <= 100


# ── High-level API ───────────────────────────────────────────────

class TestScoreFromAnalysis:
    def test_returns_valid_soul_scores(self, tmp_path):
        ws = _rich_workspace(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "rich.bm")
        a = analyze_bm_file(bm)
        scores = score_from_analysis(a)

        assert isinstance(scores, SoulScores)
        for d in (
            scores.memory_depth,
            scores.personality_richness,
            scores.habit_maturity,
            scores.skill_breadth,
            scores.uniqueness,
        ):
            assert isinstance(d, DimensionScore)
            assert 0 <= d.raw_score <= 100
            assert 0 <= d.weight <= 1

        assert 0 <= scores.total_score <= 100

    def test_total_is_weighted_sum(self, tmp_path):
        ws = _rich_workspace(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "rich.bm")
        scores = score_from_analysis(analyze_bm_file(bm))
        expected = sum((
            scores.memory_depth.weighted_score,
            scores.personality_richness.weighted_score,
            scores.habit_maturity.weighted_score,
            scores.skill_breadth.weighted_score,
            scores.uniqueness.weighted_score,
        ))
        assert scores.total_score == pytest.approx(expected, abs=0.15)

    def test_to_dict_is_json_serializable(self, tmp_path):
        import json
        ws = _rich_workspace(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "rich.bm")
        scores = score_from_analysis(analyze_bm_file(bm))
        payload = json.dumps(scores.to_dict(), ensure_ascii=False)
        assert "memory_depth" in payload
        assert "total_score" in payload


class TestScoreSoul:
    def test_rich_scores_higher_than_thin(self, tmp_path):
        rich_bm = export_soul(workspace=_rich_workspace(tmp_path), output=tmp_path / "r.bm")
        thin_bm = export_soul(workspace=_thin_workspace(tmp_path), output=tmp_path / "t.bm")

        rich_scores, _ = score_soul(rich_bm)
        thin_scores, _ = score_soul(thin_bm)

        assert rich_scores.total_score > thin_scores.total_score

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            score_soul(tmp_path / "does-not-exist.bm")


# ── extract_skill_dirs (shared helper between scorer + doctor) ────

class TestExtractSkillDirs:
    def test_openclaw_skills_layout(self):
        files = {
            "skills/blog-writer/SKILL.md": "x",
            "skills/blog-writer/helper.py": "y",
            "skills/memory-keeper/SKILL.md": "z",
        }
        all_dirs, with_md = extract_skill_dirs(files)
        assert all_dirs == {"blog-writer", "memory-keeper"}
        assert with_md == {"blog-writer", "memory-keeper"}

    def test_claude_code_skills_layout(self):
        files = {
            ".claude/skills/paper-writer/SKILL.md": "x",
            ".claude/skills/paper-writer/template.md": "y",
        }
        all_dirs, with_md = extract_skill_dirs(files)
        assert all_dirs == {"paper-writer"}
        assert with_md == {"paper-writer"}

    def test_copilot_prompts_layout(self):
        files = {
            ".github/prompts/translate.prompt.md": "x",
            ".github/prompts/review.prompt.md": "y",
        }
        all_dirs, with_md = extract_skill_dirs(files)
        # prompts have no SKILL.md, but dirs should still be captured via stem
        assert "translate.prompt" in all_dirs or "translate" in all_dirs
        assert with_md == set()

    def test_skill_md_detection_skips_non_skill(self):
        files = {"skills/foo/README.md": "x"}
        all_dirs, with_md = extract_skill_dirs(files)
        assert all_dirs == {"foo"}
        assert with_md == set()

    def test_doctor_and_scorer_agree(self):
        """Regression guard: doctor's removed inline logic must match scorer."""
        files = {
            "skills/a/SKILL.md": "x",
            "skills/b/helper.md": "y",
            ".claude/skills/c/SKILL.md": "z",
        }
        all_dirs, with_md = extract_skill_dirs(files)
        assert all_dirs == {"a", "b", "c"}
        assert with_md == {"a", "c"}
