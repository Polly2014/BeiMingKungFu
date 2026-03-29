"""Tests for soulport.doctor — soul health check."""

import pytest
from pathlib import Path

from soulport.doctor import (
    CheckResult,
    DoctorReport,
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
        )
        (tmp_path / "SOUL.md").write_text("# Personality\n" + "I value helpfulness. " * 20)
        (tmp_path / "USER.md").write_text("# Human\nTimezone: UTC")
        # Memory
        (tmp_path / "MEMORY.md").write_text("# Memory Log\nLearned Python today.")
        mem = tmp_path / "memory" / "2026"
        mem.mkdir(parents=True)
        (mem / "2026-03-30.md").write_text("Today I learned testing.")
        # Config
        (tmp_path / "AGENTS.md").write_text("# Agent Rules\n" + "Be helpful. " * 10)
        # Skills
        skill = tmp_path / "skills" / "coding"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Coding Skill")

        report = check_soul_health(tmp_path)
        assert report.health_score >= 70
        assert report.ok_count >= 5

    def test_identity_warn_no_name(self, tmp_path):
        """IDENTITY.md without Name field should get a warn."""
        (tmp_path / "IDENTITY.md").write_text("Just some text without a name field " * 5)
        report = check_soul_health(tmp_path)
        identity_checks = [c for c in report.checks if c.layer == "identity" and c.name == "IDENTITY.md"]
        assert len(identity_checks) == 1
        assert identity_checks[0].status == "warn"

    def test_soul_warn_short(self, tmp_path):
        """Short SOUL.md should get a warn."""
        (tmp_path / "SOUL.md").write_text("Hi")
        report = check_soul_health(tmp_path)
        soul_checks = [c for c in report.checks if c.name == "SOUL.md"]
        assert len(soul_checks) == 1
        assert soul_checks[0].status == "warn"

    def test_skills_with_missing_skill_md(self, tmp_path):
        """Skill dir without SKILL.md should warn."""
        skill = tmp_path / "skills" / "incomplete"
        skill.mkdir(parents=True)
        (skill / "notes.txt").write_text("no SKILL.md here")
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
        (tmp_path / "AGENTS.md").write_text("# Rules\n" + "x " * 50)
        (tmp_path / "TOOLS.md").write_text("# Tools\n" + "x " * 50)
        (tmp_path / "HEARTBEAT.md").write_text("# Heartbeat\n" + "x " * 30)
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
