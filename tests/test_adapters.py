"""Tests for SoulPort adapter framework, Claude Code adapter, and Copilot adapter."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from soulport.adapters import (
    FrameworkAdapter,
    detect_framework,
    get_adapter,
    list_adapters,
)
from soulport.adapters.claude_code import ClaudeCodeAdapter
from soulport.adapters.copilot import CopilotAdapter
from soulport.adapters.openclaw import OpenClawAdapter


# ── Registry tests ─────────────────────────────────────────────────

class TestAdapterRegistry:
    def test_list_adapters(self):
        adapters = list_adapters()
        assert "openclaw" in adapters
        assert "claude-code" in adapters
        assert "copilot" in adapters

    def test_get_adapter_openclaw(self):
        adapter = get_adapter("openclaw")
        assert isinstance(adapter, OpenClawAdapter)
        assert adapter.name == "openclaw"
        assert adapter.display_name == "OpenClaw"

    def test_get_adapter_claude_code(self):
        adapter = get_adapter("claude-code")
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter.name == "claude-code"
        assert adapter.display_name == "Claude Code"

    def test_get_adapter_unknown(self):
        with pytest.raises(ValueError, match="Unknown framework"):
            get_adapter("nonexistent")

    def test_detect_framework_with_claude_dir(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        detected = detect_framework(tmp_path)
        assert detected is not None
        assert detected.name == "claude-code"

    def test_detect_framework_with_claude_md(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md")
        detected = detect_framework(tmp_path)
        assert detected is not None
        assert detected.name == "claude-code"


# ── OpenClaw adapter tests ─────────────────────────────────────────

class TestOpenClawAdapter:
    def test_layer_definitions(self):
        adapter = OpenClawAdapter()
        defs = adapter.get_layer_definitions()
        assert "identity" in defs
        assert "memory" in defs
        assert "config" in defs
        assert "skills" in defs
        assert "projects" in defs
        assert "SOUL.md" in defs["identity"]["patterns"]

    def test_detect_agent_name_from_identity(self, tmp_path):
        adapter = OpenClawAdapter()
        (tmp_path / "IDENTITY.md").write_text("- **Name:** 小龙虾\n- **Role:** AI Assistant")
        assert adapter.detect_agent_name(tmp_path) == "小龙虾"

    def test_detect_agent_name_fallback(self, tmp_path):
        adapter = OpenClawAdapter()
        assert adapter.detect_agent_name(tmp_path) == "unknown-agent"

    def test_get_extra_export_files_empty(self):
        adapter = OpenClawAdapter()
        assert adapter.get_extra_export_files() == []

    def test_get_session_metadata_empty(self):
        adapter = OpenClawAdapter()
        assert adapter.get_session_metadata() == {}


# ── Claude Code adapter tests ──────────────────────────────────────

class TestClaudeCodeAdapter:
    def test_detect_with_claude_dir(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / ".claude").mkdir()
        assert adapter.detect(tmp_path) is True

    def test_detect_with_claude_md(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# Project Guide")
        assert adapter.detect(tmp_path) is True

    def test_detect_empty_dir(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        assert adapter.detect(tmp_path) is False

    def test_find_workspace(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / ".claude").mkdir()
        ws = adapter.find_workspace(tmp_path)
        assert ws == tmp_path

    def test_find_workspace_with_claude_md(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# Test")
        ws = adapter.find_workspace(tmp_path)
        assert ws == tmp_path

    def test_find_workspace_none(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        assert adapter.find_workspace(tmp_path) is None

    def test_detect_agent_name_from_claude_md(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md - SoulPort\n\nSome content")
        assert adapter.detect_agent_name(tmp_path) == "SoulPort"

    def test_detect_agent_name_simple_title(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# My Project\n\nGuide content")
        assert adapter.detect_agent_name(tmp_path) == "My Project"

    def test_detect_agent_name_plain_claude_md(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md\n\nJust a guide")
        # Falls back to directory name since title is just "CLAUDE.md"
        assert adapter.detect_agent_name(tmp_path) == tmp_path.name

    def test_detect_agent_name_no_file(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        assert adapter.detect_agent_name(tmp_path) == tmp_path.name

    def test_detect_agent_name_em_dash(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md — Jarvis Agent\n")
        assert adapter.detect_agent_name(tmp_path) == "Jarvis Agent"

    def test_layer_definitions(self):
        adapter = ClaudeCodeAdapter()
        defs = adapter.get_layer_definitions()
        assert "identity" in defs
        assert "CLAUDE.md" in defs["identity"]["patterns"]
        assert "skills" in defs
        assert ".claude/skills/**/SKILL.md" in defs["skills"]["patterns"]
        assert "config" in defs
        assert ".claude/settings.json" in defs["config"]["patterns"]

    def test_find_config_files_project_level(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text('{"env": {"KEY": "val"}}')
        local = claude_dir / "settings.local.json"
        local.write_text('{"permissions": {"allow": []}}')

        configs = adapter.find_config_files(tmp_path)
        # At least project-level ones
        project_configs = [c for c in configs if "project" in c.archive_name or "local" in c.archive_name]
        assert len(project_configs) == 2

        # settings.json needs redaction, settings.local.json does not
        settings_cf = [c for c in project_configs if "project-settings" in c.archive_name][0]
        local_cf = [c for c in project_configs if "settings-local" in c.archive_name][0]
        assert settings_cf.needs_redaction is True
        assert settings_cf.is_global is False
        assert local_cf.needs_redaction is False
        assert local_cf.is_global is False

    def test_find_config_files_global_flag(self, tmp_path):
        """Global configs should have is_global=True."""
        adapter = ClaudeCodeAdapter()
        configs = adapter.find_config_files(tmp_path)
        global_configs = [c for c in configs if c.is_global]
        for gc in global_configs:
            assert gc.is_global is True

    def test_get_extra_export_files(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        (tmp_path / "CLAUDE.md").write_text("# Test Project")
        extras = adapter.get_extra_export_files(tmp_path)
        assert len(extras) == 1
        assert extras[0][0] == tmp_path / "CLAUDE.md"
        assert extras[0][1] == "workspace/CLAUDE.md"

    def test_get_extra_export_files_no_claude_md(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        extras = adapter.get_extra_export_files(tmp_path)
        assert extras == []

    def test_session_metadata_empty(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        meta = adapter.get_session_metadata(tmp_path)
        # Should not crash even if ~/.claude/projects doesn't have a match
        assert isinstance(meta, dict)


# ── GitHub Copilot adapter tests ───────────────────────────────────

class TestCopilotAdapter:
    def test_name_and_display(self):
        adapter = CopilotAdapter()
        assert adapter.name == "copilot"
        assert adapter.display_name == "GitHub Copilot"

    def test_get_adapter(self):
        adapter = get_adapter("copilot")
        assert isinstance(adapter, CopilotAdapter)

    def test_detect_with_instructions(self, tmp_path):
        adapter = CopilotAdapter()
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("# Instructions")
        assert adapter.detect(tmp_path) is True

    def test_detect_with_prompts(self, tmp_path):
        adapter = CopilotAdapter()
        prompts = tmp_path / ".github" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "test.prompt.md").write_text("# Test prompt")
        assert adapter.detect(tmp_path) is True

    def test_detect_empty_dir(self, tmp_path):
        adapter = CopilotAdapter()
        assert adapter.detect(tmp_path) is False

    def test_detect_no_project_dir(self):
        adapter = CopilotAdapter()
        assert adapter.detect(None) is False

    def test_find_workspace(self, tmp_path):
        adapter = CopilotAdapter()
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("# Guide")
        ws = adapter.find_workspace(tmp_path)
        assert ws == tmp_path

    def test_find_workspace_none(self, tmp_path):
        adapter = CopilotAdapter()
        assert adapter.find_workspace(tmp_path) is None

    def test_detect_agent_name_from_instructions(self, tmp_path):
        adapter = CopilotAdapter()
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("# My Awesome Project\n\nSome guide")
        assert adapter.detect_agent_name(tmp_path) == "My Awesome Project"

    def test_detect_agent_name_fallback(self, tmp_path):
        adapter = CopilotAdapter()
        assert adapter.detect_agent_name(tmp_path) == tmp_path.name

    def test_detect_agent_name_symlink_to_claude_md(self, tmp_path):
        adapter = CopilotAdapter()
        # Create CLAUDE.md and symlink
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md - SoulPort\n\nProject guide")
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").symlink_to(tmp_path / "CLAUDE.md")
        assert adapter.detect_agent_name(tmp_path) == "SoulPort"

    def test_layer_definitions(self):
        adapter = CopilotAdapter()
        defs = adapter.get_layer_definitions()
        assert "identity" in defs
        assert ".github/copilot-instructions.md" in defs["identity"]["patterns"]
        assert "skills" in defs
        assert ".github/prompts/**/*.md" in defs["skills"]["patterns"]
        assert "config" in defs

    def test_find_config_files_project(self, tmp_path):
        adapter = CopilotAdapter()
        vscode = tmp_path / ".vscode"
        vscode.mkdir()
        (vscode / "settings.json").write_text('{"editor.fontSize": 14}')
        configs = adapter.find_config_files(tmp_path)
        proj_configs = [c for c in configs if not c.is_global]
        assert len(proj_configs) == 1
        assert proj_configs[0].needs_redaction is True
        assert proj_configs[0].is_global is False

    def test_session_metadata_empty(self, tmp_path):
        adapter = CopilotAdapter()
        meta = adapter.get_session_metadata(tmp_path)
        assert isinstance(meta, dict)

    def test_detect_framework_copilot(self, tmp_path):
        """Copilot project should be detected."""
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("# Guide")
        detected = detect_framework(tmp_path)
        assert detected is not None
        assert detected.name == "copilot"


# ── Integration: scan Copilot workspace ────────────────────────────

class TestCopilotScan:
    def test_scan_copilot_workspace(self, tmp_path):
        from soulport.scanner import scan_workspace

        # Identity
        gh = tmp_path / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("# Project Guide")

        # Skills (prompts)
        prompts = gh / "prompts"
        prompts.mkdir()
        (prompts / "BlogWriter.prompt.md").write_text("---\nmode: agent\n---\nWrite blogs")
        (prompts / "CodeReview.prompt.md").write_text("---\nmode: agent\n---\nReview code")

        # Config
        vscode = tmp_path / ".vscode"
        vscode.mkdir()
        (vscode / "settings.json").write_text("{}")

        adapter = CopilotAdapter()
        layers = scan_workspace(tmp_path, layer_defs=adapter.get_layer_definitions())

        layer_names = {l.name for l in layers}
        assert "identity" in layer_names
        assert "skills" in layer_names
        assert "config" in layer_names

        identity = next(l for l in layers if l.name == "identity")
        assert ".github/copilot-instructions.md" in identity.files

        skills = next(l for l in layers if l.name == "skills")
        assert any("BlogWriter" in f for f in skills.files)

    def test_export_copilot_round_trip(self, tmp_path):
        from soulport.core import export_soul, inspect_soul

        project = tmp_path / "myproject"
        project.mkdir()
        gh = project / ".github"
        gh.mkdir()
        (gh / "copilot-instructions.md").write_text("# CLAUDE.md - TestBot\n\nHello")
        prompts = gh / "prompts"
        prompts.mkdir()
        (prompts / "Writer.prompt.md").write_text("Write things")

        output = tmp_path / "test.bm"
        result = export_soul(
            framework="copilot",
            project_dir=project,
            output=output,
        )

        assert result.exists()
        manifest = inspect_soul(result)
        assert manifest.source_framework == "copilot"
        assert manifest.agent_name == "TestBot"
        layer_names = {l.name for l in manifest.layers}
        assert "identity" in layer_names
        assert "skills" in layer_names


# ── Integration: scan_workspace with Claude Code layers ────────────

class TestClaudeCodeScan:
    def test_scan_claude_code_workspace(self, tmp_path):
        """Build a minimal Claude Code workspace and scan it."""
        from soulport.scanner import scan_workspace

        # Identity
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md - TestAgent\n\nProject guide")

        # Config
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text('{"env": {}}')
        (claude_dir / "settings.local.json").write_text('{"permissions": {}}')

        # Skills
        skill_dir = claude_dir / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\nDoes testing")
        (skill_dir / "helper.py").write_text("print('hello')")

        # Memory (personal context)
        ctx_dir = tmp_path / "_personal_context"
        ctx_dir.mkdir()
        (ctx_dir / "notes.md").write_text("Some personal context")

        adapter = ClaudeCodeAdapter()
        layers = scan_workspace(tmp_path, layer_defs=adapter.get_layer_definitions())

        layer_names = {l.name for l in layers}
        assert "identity" in layer_names
        assert "skills" in layer_names
        assert "config" in layer_names
        assert "memory" in layer_names

        # Check identity has CLAUDE.md
        identity = next(l for l in layers if l.name == "identity")
        assert "CLAUDE.md" in identity.files

        # Check skills has the skill files
        skills = next(l for l in layers if l.name == "skills")
        assert any("SKILL.md" in f for f in skills.files)

        # Check config has settings
        config = next(l for l in layers if l.name == "config")
        assert any("settings.json" in f for f in config.files)

    def test_scan_no_overlap(self, tmp_path):
        """Files should only appear in one layer."""
        from soulport.scanner import scan_workspace

        (tmp_path / "CLAUDE.md").write_text("# Guide")
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}")
        skill_dir = claude_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# S1")

        adapter = ClaudeCodeAdapter()
        layers = scan_workspace(tmp_path, layer_defs=adapter.get_layer_definitions())

        all_files = []
        for l in layers:
            all_files.extend(l.files)
        assert len(all_files) == len(set(all_files)), "Files should not appear in multiple layers"


# ── Integration: full export round-trip ────────────────────────────

class TestClaudeCodeExport:
    def test_export_and_inspect(self, tmp_path):
        """Export a fake Claude Code project and inspect the .bm."""
        from soulport.core import export_soul, inspect_soul

        # Build minimal Claude Code project
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "CLAUDE.md").write_text("# CLAUDE.md - MyAgent\n\nProject guide here")
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text('{"env": {"MODEL": "opus"}}')
        skill_dir = claude_dir / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Code Review Skill")

        output = tmp_path / "test.bm"
        result = export_soul(
            framework="claude-code",
            project_dir=project,
            output=output,
        )

        assert result.exists()
        manifest = inspect_soul(result)
        assert manifest.source_framework == "claude-code"
        assert manifest.agent_name == "MyAgent"
        layer_names = {l.name for l in manifest.layers}
        assert "identity" in layer_names
        assert "skills" in layer_names
