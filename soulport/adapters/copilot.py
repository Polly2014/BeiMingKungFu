"""
SoulPort adapter for GitHub Copilot — Microsoft's AI pair programmer in VS Code.

GitHub Copilot stores soul files across project and VS Code storage:
- Project-level: .github/copilot-instructions.md (identity), .github/prompts/ (skills)
- Workspace-level: VS Code workspaceStorage (memories, chat sessions)
- Global-level: VS Code globalStorage + user settings

Five-layer mapping:
  Identity → .github/copilot-instructions.md
  Memory   → workspaceStorage/{id}/GitHub.copilot-chat/memory-tool/memories/
  Config   → .vscode/settings.json
  Skills   → .github/prompts/*.prompt.md
  System   → VS Code global settings (redacted)
"""

import json
import os
from pathlib import Path
from typing import Optional

from . import ConfigFile, FrameworkAdapter, register_adapter


# VS Code storage base path per platform
def _vscode_storage_base() -> Path:
    """Return VS Code user data directory for the current platform."""
    import platform as plat
    system = plat.system()
    home = Path.home()
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Code" / "User"
    elif system == "Linux":
        return home / ".config" / "Code" / "User"
    else:  # Windows
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        return Path(appdata) / "Code" / "User"


def _find_workspace_storage(project_dir: Path) -> Optional[Path]:
    """Find the VS Code workspaceStorage directory for a given project.

    VS Code hashes the workspace URI to create the storage folder name.
    We scan workspace.json files to match by folder path.
    """
    base = _vscode_storage_base() / "workspaceStorage"
    if not base.is_dir():
        return None

    project_str = str(project_dir.resolve())

    for d in base.iterdir():
        if not d.is_dir():
            continue
        ws_json = d / "workspace.json"
        if ws_json.exists():
            try:
                data = json.loads(ws_json.read_text(encoding="utf-8"))
                folder = data.get("folder", "")
                # folder is a URI like file:///Users/polly/... or file:///C:/...
                if folder.startswith("file://"):
                    folder_path = folder[7:]  # strip file://
                    # Windows: file:///C:/Users/... → /C:/Users/... → C:/Users/...
                    if len(folder_path) >= 3 and folder_path[0] == "/" and folder_path[2] == ":":
                        folder_path = folder_path[1:]
                    if folder_path.rstrip("/") == project_str.rstrip("/"):
                        return d
            except (json.JSONDecodeError, OSError):
                continue
    return None


@register_adapter
class CopilotAdapter(FrameworkAdapter):

    @property
    def name(self) -> str:
        return "copilot"

    @property
    def display_name(self) -> str:
        return "GitHub Copilot"

    def detect(self, project_dir: Optional[Path] = None) -> bool:
        """Detect Copilot by .github/copilot-instructions.md or .github/prompts/."""
        if not project_dir:
            return False
        p = Path(project_dir)
        if (p / ".github" / "copilot-instructions.md").exists():
            return True
        if (p / ".github" / "prompts").is_dir():
            return True
        return False

    def find_workspace(self, project_dir: Optional[Path] = None) -> Optional[Path]:
        """Copilot workspace = project dir containing .github/ copilot files."""
        if project_dir:
            p = Path(project_dir)
            if (p / ".github" / "copilot-instructions.md").exists() or \
               (p / ".github" / "prompts").is_dir():
                return p
        return None

    def find_config_files(self, project_dir: Optional[Path] = None) -> list[ConfigFile]:
        configs: list[ConfigFile] = []

        if project_dir:
            p = Path(project_dir)
            # .vscode/settings.json — project-level config
            vscode_settings = p / ".vscode" / "settings.json"
            if vscode_settings.exists():
                configs.append(ConfigFile(
                    source_path=vscode_settings,
                    archive_name="config/copilot/vscode-settings.json",
                    needs_redaction=True,  # may contain API keys
                    is_global=False,
                ))

        # Global VS Code settings
        global_settings = _vscode_storage_base() / "settings.json"
        if global_settings.exists():
            configs.append(ConfigFile(
                source_path=global_settings,
                archive_name="config/copilot/global-vscode-settings.json",
                needs_redaction=True,
                is_global=True,
            ))

        return configs

    def detect_agent_name(self, workspace: Path) -> str:
        """Extract agent name from copilot-instructions.md or directory name."""
        instructions = workspace / ".github" / "copilot-instructions.md"
        # Resolve symlinks to read actual content
        if instructions.exists():
            target = instructions.resolve()
            if target.exists():
                try:
                    content = target.read_text(encoding="utf-8")
                    for line in content.splitlines()[:20]:
                        line = line.strip()
                        if line.startswith("# "):
                            title = line[2:].strip()
                            # Strip common prefixes
                            for prefix in ("CLAUDE.md - ", "CLAUDE.md — "):
                                if title.startswith(prefix):
                                    return title[len(prefix):].strip()
                            if title not in ("CLAUDE.md", "copilot-instructions.md"):
                                return title
                except OSError:
                    pass
        return workspace.name or "unknown-agent"

    def get_layer_definitions(self) -> dict[str, dict]:
        return {
            "identity": {
                "description": "Copilot instructions and agent identity",
                "patterns": [
                    ".github/copilot-instructions.md",
                ],
            },
            "memory": {
                "description": "Copilot memories (repo-scoped)",
                "patterns": [],  # memories are outside workspace, handled by get_extra_export_files
            },
            "config": {
                "description": "VS Code project settings",
                "patterns": [
                    ".vscode/settings.json",
                ],
            },
            "skills": {
                "description": "Copilot prompt files (reusable prompts)",
                "patterns": [
                    ".github/prompts/**/*.md",
                    ".github/prompts/**/*.json",
                ],
            },
            "projects": {
                "description": "Project files and custom data",
                "patterns": [],
            },
        }

    def get_extra_export_files(self, project_dir: Optional[Path] = None) -> list[tuple[Path, str]]:
        """Include Copilot memories from VS Code workspaceStorage.

        Memories live in the VS Code storage directory, not in the project dir,
        so they need special handling during export.
        """
        extras = []
        if not project_dir:
            return extras

        ws_storage = _find_workspace_storage(Path(project_dir))
        if not ws_storage:
            return extras

        # Memory files from memory-tool/memories/
        memories_dir = ws_storage / "GitHub.copilot-chat" / "memory-tool" / "memories"
        if memories_dir.is_dir():
            for md_file in memories_dir.rglob("*.md"):
                rel = md_file.relative_to(memories_dir)
                extras.append((md_file, f"workspace/memories/{rel}"))

        return extras

    def get_session_metadata(self, project_dir: Optional[Path] = None) -> dict:
        """Gather lightweight session stats from VS Code workspace storage."""
        metadata: dict = {}
        if not project_dir:
            return metadata

        ws_storage = _find_workspace_storage(Path(project_dir))
        if not ws_storage:
            return metadata

        copilot_dir = ws_storage / "GitHub.copilot-chat"
        if not copilot_dir.is_dir():
            return metadata

        # Count chat session resources
        sessions_dir = copilot_dir / "chat-session-resources"
        if sessions_dir.is_dir():
            session_dirs = [d for d in sessions_dir.iterdir() if d.is_dir()]
            metadata["session_count"] = len(session_dirs)

        # Count memory files
        memories_dir = copilot_dir / "memory-tool" / "memories"
        if memories_dir.is_dir():
            memory_files = list(memories_dir.rglob("*.md"))
            metadata["memory_count"] = len(memory_files)

        # Prompt count
        if project_dir:
            prompts_dir = Path(project_dir) / ".github" / "prompts"
            if prompts_dir.is_dir():
                prompt_files = list(prompts_dir.glob("*.prompt.md"))
                metadata["prompt_count"] = len(prompt_files)

        return metadata
