"""Tests for soulport.scanner — workspace scanning and glob matching."""

import json
import pytest
from pathlib import Path

from soulport.scanner import (
    _matches_pattern,
    is_sensitive_key,
    redact_config,
    scan_workspace,
    detect_agent_name,
)


# ── _matches_pattern ───────────────────────────────────────────────

class TestMatchesPattern:
    """Test glob-like pattern matching (core of layer classification)."""

    def test_exact_match(self):
        assert _matches_pattern("SOUL.md", "SOUL.md")
        assert _matches_pattern("IDENTITY.md", "IDENTITY.md")

    def test_exact_no_match(self):
        assert not _matches_pattern("OTHER.md", "SOUL.md")

    def test_star_matches_filename(self):
        assert _matches_pattern("skills/foo/SKILL.md", "skills/*/SKILL.md")
        assert _matches_pattern("skills/bar/SKILL.md", "skills/*/SKILL.md")

    def test_star_does_not_cross_slash(self):
        assert not _matches_pattern("skills/a/b/SKILL.md", "skills/*/SKILL.md")

    def test_double_star_recursive(self):
        assert _matches_pattern("memory/2026/daily.md", "memory/**/*.md")
        assert _matches_pattern("memory/deep/nested/file.md", "memory/**/*.md")

    def test_double_star_one_level(self):
        assert _matches_pattern("memory/daily.md", "memory/**/*.md")

    def test_double_star_json(self):
        assert _matches_pattern("memory/data/state.json", "memory/**/*.json")

    def test_question_mark(self):
        assert _matches_pattern("file_a.md", "file_?.md")
        assert not _matches_pattern("file_ab.md", "file_?.md")

    def test_double_star_any_suffix(self):
        assert _matches_pattern("skills/translate/prompt.txt", "skills/**/*")
        assert _matches_pattern("skills/coding/SKILL.md", "skills/**/*")

    def test_no_match_outside_prefix(self):
        assert not _matches_pattern("other/SKILL.md", "skills/*/SKILL.md")

    def test_empty_pattern_edge(self):
        assert _matches_pattern("", "")

    def test_dot_in_filename(self):
        """Dots in filenames should be treated literally, not as regex wildcards."""
        assert _matches_pattern("config.json", "config.json")
        assert not _matches_pattern("configXjson", "config.json")


# ── is_sensitive_key / redact_config ───────────────────────────────

class TestRedaction:
    """Test sensitive key detection and config redaction."""

    def test_sensitive_keys_detected(self):
        assert is_sensitive_key("apiKey")
        assert is_sensitive_key("api_key")
        assert is_sensitive_key("token")
        assert is_sensitive_key("secret")
        assert is_sensitive_key("password")
        assert is_sensitive_key("X-API-Key")

    def test_non_sensitive_keys(self):
        assert not is_sensitive_key("model")
        assert not is_sensitive_key("name")
        assert not is_sensitive_key("endpoint")

    def test_redact_flat_config(self):
        config = {"model": "gpt-4", "apiKey": "sk-12345", "name": "bot"}
        redacted, paths = redact_config(config)
        assert redacted["model"] == "gpt-4"
        assert redacted["apiKey"] == "__SOULPORT_REDACTED__"
        assert redacted["name"] == "bot"
        assert "apiKey" in paths

    def test_redact_nested_config(self):
        config = {
            "server": {
                "host": "localhost",
                "token": "bearer-xyz"
            }
        }
        redacted, paths = redact_config(config)
        assert redacted["server"]["token"] == "__SOULPORT_REDACTED__"
        assert "server.token" in paths

    def test_redact_empty_value_not_redacted(self):
        """Empty string values should NOT be redacted (nothing to protect)."""
        config = {"apiKey": ""}
        redacted, paths = redact_config(config)
        assert redacted["apiKey"] == ""
        assert len(paths) == 0

    def test_redact_non_string_not_redacted(self):
        """Non-string sensitive values (booleans, numbers) stay as-is."""
        config = {"token": True, "secret": 42}
        redacted, paths = redact_config(config)
        assert redacted["token"] is True
        assert redacted["secret"] == 42
        assert len(paths) == 0


# ── scan_workspace ─────────────────────────────────────────────────

class TestScanWorkspace:
    """Test workspace scanning and layer categorization."""

    def test_scan_identity_layer(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("# My Soul")
        (tmp_path / "IDENTITY.md").write_text("# Identity")
        layers = scan_workspace(tmp_path)
        identity = next(l for l in layers if l.name == "identity")
        assert "SOUL.md" in identity.files
        assert "IDENTITY.md" in identity.files

    def test_scan_memory_layer(self, tmp_path):
        mem_dir = tmp_path / "memory" / "2026"
        mem_dir.mkdir(parents=True)
        (tmp_path / "MEMORY.md").write_text("# Memory")
        (mem_dir / "0330.md").write_text("Today")
        layers = scan_workspace(tmp_path)
        memory = next(l for l in layers if l.name == "memory")
        assert "MEMORY.md" in memory.files
        assert "memory/2026/0330.md" in memory.files

    def test_scan_skills_layer(self, tmp_path):
        skill_dir = tmp_path / "skills" / "translate"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Translate Skill")
        layers = scan_workspace(tmp_path)
        skills = next(l for l in layers if l.name == "skills")
        assert "skills/translate/SKILL.md" in skills.files

    def test_scan_config_layer(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Agents")
        (tmp_path / "TOOLS.md").write_text("# Tools")
        layers = scan_workspace(tmp_path)
        config = next(l for l in layers if l.name == "config")
        assert "AGENTS.md" in config.files
        assert "TOOLS.md" in config.files

    def test_scan_empty_workspace(self, tmp_path):
        layers = scan_workspace(tmp_path)
        assert layers == []

    def test_skip_patterns_excluded(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git stuff")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_text("bytecode")
        (tmp_path / "SOUL.md").write_text("# Soul")
        layers = scan_workspace(tmp_path)
        all_files = [f for l in layers for f in l.files]
        assert not any(".git" in f for f in all_files)
        assert not any("__pycache__" in f for f in all_files)

    def test_remaining_files_go_to_projects(self, tmp_path):
        (tmp_path / "random.txt").write_text("hello")
        layers = scan_workspace(tmp_path)
        projects = next(l for l in layers if l.name == "projects")
        assert "random.txt" in projects.files

    def test_file_count_and_bytes(self, tmp_path):
        content = "Hello World"
        (tmp_path / "SOUL.md").write_text(content)
        layers = scan_workspace(tmp_path)
        identity = next(l for l in layers if l.name == "identity")
        assert identity.file_count == 1
        assert identity.total_bytes == len(content.encode("utf-8"))

    def test_nonexistent_workspace_raises(self):
        with pytest.raises(FileNotFoundError):
            scan_workspace(Path("/nonexistent/path"))
