"""
SoulPort adapters — framework-specific soul discovery and mapping.

Each adapter knows how to find, scan, and map an agent framework's files
into SoulPort's five-layer soul model (Identity/Memory/Config/Skills/System).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..manifest import ManifestLayer


@dataclass
class ConfigFile:
    """A config file discovered by an adapter, ready for export."""
    source_path: Path          # absolute path on disk
    archive_name: str          # path inside .bm (e.g. "config/settings.json")
    needs_redaction: bool = True
    is_global: bool = False    # True = user-level config (e.g. ~/.claude/), skipped unless --include-global


class FrameworkAdapter(ABC):
    """Base class for all framework adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Framework identifier used in manifest.source_framework."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for CLI output."""
        ...

    @abstractmethod
    def detect(self, project_dir: Optional[Path] = None) -> bool:
        """Return True if this framework is present in the environment."""
        ...

    @abstractmethod
    def find_workspace(self, project_dir: Optional[Path] = None) -> Optional[Path]:
        """Locate the agent workspace directory."""
        ...

    @abstractmethod
    def find_config_files(self, project_dir: Optional[Path] = None) -> list[ConfigFile]:
        """Locate system config files (will be redacted on export)."""
        ...

    @abstractmethod
    def detect_agent_name(self, workspace: Path) -> str:
        """Extract the agent's name from workspace files."""
        ...

    @abstractmethod
    def get_layer_definitions(self) -> dict[str, dict]:
        """Return layer definitions for this framework.

        Format: {
            "identity": {"description": "...", "patterns": ["SOUL.md", ...]},
            "memory":   {"description": "...", "patterns": [...]},
            ...
        }
        """
        ...

    def get_extra_export_files(self, project_dir: Optional[Path] = None) -> list[tuple[Path, str]]:
        """Return additional files to include in export as (source_path, archive_path).

        Override for frameworks that store soul files outside the workspace dir.
        """
        return []

    def get_session_metadata(self, project_dir: Optional[Path] = None) -> dict:
        """Return lightweight session metadata for manifest (not full transcripts).

        Default returns empty dict. Override to add session_count, date_range, etc.
        """
        return {}


# ── Adapter Registry ──────────────────────────────────────────────

_ADAPTERS: dict[str, type[FrameworkAdapter]] = {}


def register_adapter(cls: type[FrameworkAdapter]) -> type[FrameworkAdapter]:
    """Decorator to register a framework adapter."""
    instance = cls()
    _ADAPTERS[instance.name] = cls
    return cls


def get_adapter(name: str) -> FrameworkAdapter:
    """Get an adapter by framework name."""
    if name not in _ADAPTERS:
        available = ", ".join(sorted(_ADAPTERS.keys()))
        raise ValueError(f"Unknown framework '{name}'. Available: {available}")
    return _ADAPTERS[name]()


def detect_framework(project_dir: Optional[Path] = None) -> Optional[FrameworkAdapter]:
    """Auto-detect which framework is present, returning the first match.

    Priority is determined by adapter import order in this file.
    More specific/project-scoped adapters (Claude Code) should be imported
    before broader ones (OpenClaw which checks ~/.openclaw/ globally).
    """
    for cls in _ADAPTERS.values():
        adapter = cls()
        if adapter.detect(project_dir):
            return adapter
    return None


def list_adapters() -> list[str]:
    """Return list of registered framework names."""
    return sorted(_ADAPTERS.keys())


# ── Import adapters to trigger registration ───────────────────────
# Order matters for detect_framework(): more specific adapters first.

from . import claude_code  # noqa: E402, F401
from . import openclaw  # noqa: E402, F401
