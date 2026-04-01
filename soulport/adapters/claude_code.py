"""
SoulPort adapter for Claude Code — Anthropic's CLI/VS Code coding agent.

Claude Code stores soul files across two locations:
- Project-level: .claude/ (skills, project settings) + CLAUDE.md (identity+config)
- Global-level:  ~/.claude/ (global settings, session history, MCP servers)

Five-layer mapping:
  Identity → CLAUDE.md (project root)
  Memory   → (lightweight: session count + date range in manifest metadata)
  Config   → .claude/settings.json + .claude/settings.local.json
  Skills   → .claude/skills/*/SKILL.md
  System   → ~/.claude/settings.json (global, redacted)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import ConfigFile, FrameworkAdapter, register_adapter


@register_adapter
class ClaudeCodeAdapter(FrameworkAdapter):

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def detect(self, project_dir: Optional[Path] = None) -> bool:
        """Detect Claude Code by .claude/ dir or CLAUDE.md in project root.

        Only checks project-level markers. Global ~/.claude/ is not enough
        to claim a project belongs to Claude Code.
        """
        if project_dir and (project_dir / ".claude").is_dir():
            return True
        if project_dir and (project_dir / "CLAUDE.md").exists():
            return True
        return False

    def find_workspace(self, project_dir: Optional[Path] = None) -> Optional[Path]:
        """Claude Code workspace = the project dir containing .claude/ + CLAUDE.md.

        Unlike OpenClaw which has a single ~/.openclaw/workspace, Claude Code
        operates per-project. The caller must provide project_dir.
        """
        if project_dir:
            p = Path(project_dir)
            if (p / ".claude").is_dir() or (p / "CLAUDE.md").exists():
                return p
        return None

    def find_config_files(self, project_dir: Optional[Path] = None) -> list[ConfigFile]:
        """Collect config files from both project and global levels."""
        configs: list[ConfigFile] = []

        # Project-level configs
        if project_dir:
            p = Path(project_dir)
            proj_settings = p / ".claude" / "settings.json"
            if proj_settings.exists():
                configs.append(ConfigFile(
                    source_path=proj_settings,
                    archive_name="config/claude-code/project-settings.json",
                    needs_redaction=True,
                ))

            proj_local = p / ".claude" / "settings.local.json"
            if proj_local.exists():
                configs.append(ConfigFile(
                    source_path=proj_local,
                    archive_name="config/claude-code/settings-local.json",
                    needs_redaction=False,  # permissions allow-list only, no secrets
                    is_global=False,
                ))

        # Global-level configs (opt-in via --global, but always discovered)
        global_dir = Path.home() / ".claude"
        if global_dir.is_dir():
            global_settings = global_dir / "settings.json"
            if global_settings.exists():
                configs.append(ConfigFile(
                    source_path=global_settings,
                    archive_name="config/claude-code/global-settings.json",
                    needs_redaction=True,
                    is_global=True,
                ))

            global_config = global_dir / "config.json"
            if global_config.exists():
                configs.append(ConfigFile(
                    source_path=global_config,
                    archive_name="config/claude-code/config.json",
                    needs_redaction=True,  # contains API key name
                    is_global=True,
                ))

        return configs

    def detect_agent_name(self, workspace: Path) -> str:
        """Extract agent name from CLAUDE.md header or project directory name."""
        claude_md = workspace / "CLAUDE.md"
        if claude_md.exists():
            try:
                content = claude_md.read_text(encoding="utf-8")
                for line in content.splitlines()[:20]:
                    line = line.strip()
                    # Look for "# CLAUDE.md - ProjectName" or "# ProjectName"
                    if line.startswith("# "):
                        title = line[2:].strip()
                        # Strip common prefixes
                        for prefix in ("CLAUDE.md - ", "CLAUDE.md — "):
                            if title.startswith(prefix):
                                return title[len(prefix):].strip()
                        if title != "CLAUDE.md":
                            return title
            except OSError:
                pass
        return workspace.name or "unknown-agent"

    def get_layer_definitions(self) -> dict[str, dict]:
        return {
            "identity": {
                "description": "Agent identity and project guide (CLAUDE.md)",
                "patterns": ["CLAUDE.md"],
            },
            "memory": {
                "description": "Planning documents and memory files",
                "patterns": [
                    ".claude/plans/**/*.md",
                    "_personal_context/**/*.md",
                    "_project_context/**/*.md",
                ],
            },
            "config": {
                "description": "Project settings and permissions",
                "patterns": [
                    ".claude/settings.json",
                    ".claude/settings.local.json",
                ],
            },
            "skills": {
                "description": "Claude Code skills",
                "patterns": [
                    ".claude/skills/**/SKILL.md",
                    ".claude/skills/**/*",
                ],
            },
            "projects": {
                "description": "Project files and custom data",
                "patterns": [],
            },
        }

    def get_extra_export_files(self, project_dir: Optional[Path] = None) -> list[tuple[Path, str]]:
        """Include CLAUDE.md from project root in export.

        CLAUDE.md sits at project root, not inside .claude/, so it needs
        special handling during export (it's outside the workspace scan dir).
        """
        extras = []
        if project_dir:
            claude_md = Path(project_dir) / "CLAUDE.md"
            if claude_md.exists():
                extras.append((claude_md, "workspace/CLAUDE.md"))
        return extras

    def get_session_metadata(self, project_dir: Optional[Path] = None) -> dict:
        """Gather lightweight session stats without exporting full transcripts."""
        global_dir = Path.home() / ".claude"
        if not global_dir.is_dir():
            return {}

        projects_dir = global_dir / "projects"
        if not projects_dir.is_dir():
            return {}

        # Find matching project directory by encoded path
        metadata: dict = {}
        if project_dir:
            encoded = str(Path(project_dir).resolve()).replace("/", "-")
            if encoded.startswith("-"):
                encoded = encoded  # keep leading dash from /Users → -Users

            for d in projects_dir.iterdir():
                if d.is_dir() and d.name == encoded:
                    # Count session files
                    jsonl_files = list(d.glob("*.jsonl"))
                    metadata["session_count"] = len(jsonl_files)

                    # Date range from file modification times
                    if jsonl_files:
                        mtimes = [f.stat().st_mtime for f in jsonl_files]
                        earliest = datetime.fromtimestamp(min(mtimes))
                        latest = datetime.fromtimestamp(max(mtimes))
                        metadata["earliest_session"] = earliest.strftime("%Y-%m-%d")
                        metadata["latest_session"] = latest.strftime("%Y-%m-%d")

                    break

        # Also count plans
        plans_dir = global_dir / "plans"
        if plans_dir.is_dir():
            plan_files = list(plans_dir.glob("*.md"))
            metadata["plan_count"] = len(plan_files)

        return metadata
