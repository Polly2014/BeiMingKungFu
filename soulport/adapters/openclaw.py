"""
SoulPort adapter for OpenClaw — the first-class supported framework.
"""

from pathlib import Path
from typing import Optional

from . import ConfigFile, FrameworkAdapter, register_adapter


@register_adapter
class OpenClawAdapter(FrameworkAdapter):

    @property
    def name(self) -> str:
        return "openclaw"

    @property
    def display_name(self) -> str:
        return "OpenClaw"

    def detect(self, project_dir: Optional[Path] = None) -> bool:
        ws = self.find_workspace(project_dir)
        return ws is not None

    def find_workspace(self, project_dir: Optional[Path] = None) -> Optional[Path]:
        home = Path.home()
        candidates = [
            home / ".openclaw" / "workspace",
            home / ".config" / "openclaw" / "workspace",
        ]
        for c in candidates:
            if c.exists() and (c / "AGENTS.md").exists():
                return c
        return None

    def find_config_files(self, project_dir: Optional[Path] = None) -> list[ConfigFile]:
        home = Path.home()
        candidates = [
            home / ".openclaw" / "openclaw.json",
            home / ".config" / "openclaw" / "openclaw.json",
        ]
        for c in candidates:
            if c.exists():
                return [ConfigFile(
                    source_path=c,
                    archive_name="config/openclaw.json",
                    needs_redaction=True,
                    is_global=True,
                )]
        return []

    def detect_agent_name(self, workspace: Path) -> str:
        identity_file = workspace / "IDENTITY.md"
        if identity_file.exists():
            content = identity_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.strip().startswith("- **Name:**"):
                    name = line.split(":**")[1].strip().rstrip("*")
                    return name
        return "unknown-agent"

    def get_layer_definitions(self) -> dict[str, dict]:
        return {
            "identity": {
                "description": "Agent personality, name, and human context",
                "patterns": ["SOUL.md", "IDENTITY.md", "USER.md"],
            },
            "memory": {
                "description": "Long-term and daily memories",
                "patterns": ["MEMORY.md", "memory/**/*.md", "memory/**/*.json"],
            },
            "config": {
                "description": "Behavior rules, tool notes, routines",
                "patterns": ["AGENTS.md", "TOOLS.md", "HEARTBEAT.md"],
            },
            "skills": {
                "description": "Workspace skills",
                "patterns": ["skills/**/SKILL.md", "skills/**/*"],
            },
            "projects": {
                "description": "Project files and custom data",
                "patterns": [],
            },
        }
