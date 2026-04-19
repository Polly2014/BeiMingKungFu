"""Tests for soulport.doctor — soul health check."""

import pytest
from pathlib import Path

from soulport.core import export_soul
from soulport.doctor import (
    CheckResult,
    DoctorReport,
    check_package_health,
    check_soul_health,
    _extract_dates_from_paths,
)


# ── DoctorReport properties ───────────────────────────────────────

class TestDoctorReport:
    def test_empty_report_score_zero(self):
        report = DoctorReport(workspace=Path("/tmp"), agent_name="test")
        assert report.health_score == 0

    def test_all_ok_score_100(self):
        report = DoctorReport(workspace=Path("/tmp"), agent_name="test")
        report.checks = [
            CheckResult(layer="identity", name="SOUL.md", status="ok", detail="ok"),
            CheckResult(layer="memory", name="MEMORY.md", status="ok", detail="ok"),
        ]
        assert report.health_score == 100

    def test_all_missing_score_0(self):
        report = DoctorReport(workspace=Path("/tmp"), agent_name="test")
        report.checks = [
            CheckResult(layer="identity", name="SOUL.md", status="missing", detail=""),
            CheckResult(layer="memory", name="MEMORY.md", status="missing", detail=""),
        ]
        assert report.health_score == 0

    def test_mixed_score(self):
        report = DoctorReport(workspace=Path("/tmp"), agent_name="test")
        report.checks = [
            CheckResult(layer="identity", name="SOUL.md", status="ok", detail="ok"),
            CheckResult(layer="memory", name="MEMORY.md", status="warn", detail="short"),
        ]
        # (100 + 50) / 2 = 75
        assert report.health_score == 75

    def test_counts(self):
        report = DoctorReport(workspace=Path("/tmp"), agent_name="test")
        report.checks = [
            CheckResult(layer="a", name="1", status="ok", detail=""),
            CheckResult(layer="a", name="2", status="ok", detail=""),
            CheckResult(layer="b", name="3", status="warn", detail=""),
            CheckResult(layer="c", name="4", status="missing", detail=""),
        ]
        assert report.ok_count == 2
        assert report.warn_count == 1
        assert report.missing_count == 1


# ── check_soul_health integration ─────────────────────────────────

class TestCheckSoulHealth:
    def test_empty_workspace(self, tmp_path):
        """Empty workspace should produce all missing/warn checks."""
        report = check_soul_health(tmp_path)
        assert report.agent_name == "unknown-agent"
        assert report.missing_count > 0
        assert report.health_score < 50

    def test_full_workspace(self, tmp_path):
        """Well-populated workspace should score high."""
        # Identity
        (tmp_path / "IDENTITY.md").write_text(
            "- **Name:** TestBot 🤖\nI am a helpful assistant with many capabilities."
            " " * 100  # ensure > 100 bytes
        , encoding="utf-8")
        (tmp_path / "SOUL.md").write_text("# Personality\n" + "I value helpfulness. " * 20, encoding="utf-8")
        (tmp_path / "USER.md").write_text("# Human\nTimezone: UTC", encoding="utf-8")
        # Memory
        (tmp_path / "MEMORY.md").write_text("# Memory Log\nLearned Python today.", encoding="utf-8")
        mem = tmp_path / "memory" / "2026"
        mem.mkdir(parents=True)
        (mem / "2026-03-30.md").write_text("Today I learned testing.", encoding="utf-8")
        # Config
        (tmp_path / "AGENTS.md").write_text("# Agent Rules\n" + "Be helpful. " * 10, encoding="utf-8")
        # Skills
        skill = tmp_path / "skills" / "coding"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Coding Skill", encoding="utf-8")

        report = check_soul_health(tmp_path)
        assert report.health_score >= 70
        assert report.ok_count >= 5

    def test_identity_warn_no_name(self, tmp_path):
        """IDENTITY.md without Name field should get a warn."""
        (tmp_path / "IDENTITY.md").write_text("Just some text without a name field " * 5, encoding="utf-8")
        report = check_soul_health(tmp_path)
        identity_checks = [c for c in report.checks if c.layer == "identity" and c.name == "IDENTITY.md"]
        assert len(identity_checks) == 1
        assert identity_checks[0].status == "warn"

    def test_soul_warn_short(self, tmp_path):
        """Short SOUL.md should get a warn."""
        (tmp_path / "SOUL.md").write_text("Hi", encoding="utf-8")
        report = check_soul_health(tmp_path)
        soul_checks = [c for c in report.checks if c.name == "SOUL.md"]
        assert len(soul_checks) == 1
        assert soul_checks[0].status == "warn"

    def test_skills_with_missing_skill_md(self, tmp_path):
        """Skill dir without SKILL.md should warn."""
        skill = tmp_path / "skills" / "incomplete"
        skill.mkdir(parents=True)
        (skill / "notes.txt").write_text("no SKILL.md here", encoding="utf-8")
        report = check_soul_health(tmp_path)
        skill_checks = [c for c in report.checks if c.layer == "skills"]
        # Should have a warn about missing SKILL.md
        warns = [c for c in skill_checks if c.status == "warn"]
        assert len(warns) >= 1

    def test_memory_dir_empty(self, tmp_path):
        """Empty memory/ directory should warn."""
        (tmp_path / "memory").mkdir()
        report = check_soul_health(tmp_path)
        mem_checks = [c for c in report.checks if c.name == "memory/ directory"]
        assert len(mem_checks) == 1
        assert mem_checks[0].status == "warn"

    def test_config_all_present(self, tmp_path):
        """All config files present should be ok."""
        (tmp_path / "AGENTS.md").write_text("# Rules\n" + "x " * 50, encoding="utf-8")
        (tmp_path / "TOOLS.md").write_text("# Tools\n" + "x " * 50, encoding="utf-8")
        (tmp_path / "HEARTBEAT.md").write_text("# Heartbeat\n" + "x " * 30, encoding="utf-8")
        report = check_soul_health(tmp_path)
        config_checks = [c for c in report.checks if c.layer == "config"]
        assert all(c.status == "ok" for c in config_checks)


# ── _extract_dates_from_paths ──────────────────────────────────────

class TestExtractDates:
    def test_standard_date_format(self, tmp_path):
        paths = [
            tmp_path / "2026-03-25.md",
            tmp_path / "2026-03-30.md",
        ]
        dates = _extract_dates_from_paths(paths)
        assert len(dates) == 2
        assert dates[0].month == 3
        assert dates[0].day == 25

    def test_no_date_in_path(self, tmp_path):
        paths = [tmp_path / "notes.md", tmp_path / "readme.md"]
        dates = _extract_dates_from_paths(paths)
        assert dates == []

    def test_invalid_date_skipped(self, tmp_path):
        paths = [tmp_path / "2026-13-45.md"]  # invalid month/day
        dates = _extract_dates_from_paths(paths)
        assert dates == []

    def test_date_in_nested_path(self, tmp_path):
        paths = [tmp_path / "memory" / "2026" / "2026-03-30.md"]
        dates = _extract_dates_from_paths(paths)
        assert len(dates) == 1


# ── Package-level health check ───────────────────────────────────

def _mk_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "IDENTITY.md").write_text("Name: Tester\n🤖\nRole: QA", encoding="utf-8")
    (ws / "SOUL.md").write_text("# Personality\n" * 30, encoding="utf-8")
    (ws / "MEMORY.md").write_text("# Memory\n- stuff\n", encoding="utf-8")
    (ws / "AGENTS.md").write_text("Must be kind. Always ship tests.", encoding="utf-8")
    mem = ws / "memory"
    mem.mkdir()
    (mem / "2026-04-18.md").write_text("yesterday", encoding="utf-8")
    (mem / "2026-04-19.md").write_text("today", encoding="utf-8")
    skills_dir = ws / "skills" / "writer"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("# writer", encoding="utf-8")
    return ws


class TestCheckPackageHealth:
    def test_runs_on_exported_bm(self, tmp_path):
        ws = _mk_ws(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "test.bm")
        report = check_package_health(bm)

        assert report.agent_name  # detected (at minimum "unknown-agent")
        assert report.workspace == bm
        assert len(report.checks) > 0
        assert 0 <= report.health_score <= 100

    def test_identity_layer_has_checks(self, tmp_path):
        ws = _mk_ws(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "test.bm")
        report = check_package_health(bm)
        layers = {c.layer for c in report.checks}
        assert "identity" in layers
        assert "memory" in layers
        assert "config" in layers
        assert "skills" in layers

    def test_missing_bm_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            check_package_health(tmp_path / "nope.bm")

    def test_detects_present_files(self, tmp_path):
        ws = _mk_ws(tmp_path)
        bm = export_soul(workspace=ws, output=tmp_path / "test.bm")
        report = check_package_health(bm)
        # At least one identity check should be ok
        identity_checks = [c for c in report.checks if c.layer == "identity"]
        assert any(c.status == "ok" for c in identity_checks)

    def test_warns_when_skills_have_no_skill_md(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "IDENTITY.md").write_text("Name: T\n🤖", encoding="utf-8")
        (ws / "SOUL.md").write_text("# soul" * 50, encoding="utf-8")
        (ws / "AGENTS.md").write_text("rules. must. always.", encoding="utf-8")
        # skill dir WITHOUT SKILL.md
        d = ws / "skills" / "empty-skill"
        d.mkdir(parents=True)
        (d / "notes.md").write_text("just notes", encoding="utf-8")

        bm = export_soul(workspace=ws, output=tmp_path / "test.bm")
        report = check_package_health(bm)
        skills_checks = [c for c in report.checks if c.layer == "skills"]
        assert any(c.status == "warn" for c in skills_checks)
