"""
SoulPort scanner — discovers agent workspace files and categorizes them into layers.
"""

import os
import json
import re
from pathlib import Path
from typing import Optional

from .manifest import ManifestLayer


# ── Layer definitions ──────────────────────────────────────────────

LAYER_DEFINITIONS = {
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
        "patterns": [],  # catch-all for remaining files
    },
}

# Files/dirs to always skip
SKIP_PATTERNS = {
    ".git", "__pycache__", "node_modules", ".DS_Store", 
    "Thumbs.db", ".openclaw",
}

# ── Sensitive field patterns in config ─────────────────────────────

SENSITIVE_KEYS = {
    "token", "apiKey", "api_key", "apikey", "secret", 
    "password", "credential", "X-API-Key",
}


def is_sensitive_key(key: str) -> bool:
    """Check if a config key name looks sensitive."""
    key_lower = key.lower()
    return any(s.lower() in key_lower for s in SENSITIVE_KEYS)


def redact_config(config: dict, path: str = "") -> tuple[dict, list[str]]:
    """
    Deep-walk a config dict and redact sensitive values.
    Returns (redacted_config, list_of_redacted_paths).
    """
    redacted = {}
    redacted_paths = []
    
    for key, value in config.items():
        current_path = f"{path}.{key}" if path else key
        
        if isinstance(value, dict):
            sub_redacted, sub_paths = redact_config(value, current_path)
            redacted[key] = sub_redacted
            redacted_paths.extend(sub_paths)
        elif is_sensitive_key(key) and isinstance(value, str) and value:
            redacted[key] = "__SOULPORT_REDACTED__"
            redacted_paths.append(current_path)
        else:
            redacted[key] = value
    
    return redacted, redacted_paths


def scan_workspace(workspace_path: str | Path) -> list[ManifestLayer]:
    """
    Scan an agent workspace directory and categorize files into layers.
    """
    workspace = Path(workspace_path)
    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace}")
    
    # Collect all files from workspace
    all_files: set[str] = set()
    
    for root, dirs, files in os.walk(workspace):
        # Skip excluded dirs
        dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS]
        
        for f in files:
            if f in SKIP_PATTERNS:
                continue
            rel = os.path.relpath(os.path.join(root, f), workspace)
            rel = rel.replace("\\", "/")  # normalize to forward slash
            all_files.add(rel)
    
    # Note: We intentionally do NOT scan OpenClaw's built-in skills/ or extensions/.
    # Built-in skills are framework-provided (everyone has them), not part of the agent's soul.
    # Only user-created skills inside the workspace (skills/*.md) are counted.
    # This makes the "skills" dimension in SoulArena meaningful — it reflects
    # what the user actually customized, not what came pre-installed.
    
    # Categorize into layers
    layers: list[ManifestLayer] = []
    claimed: set[str] = set()
    
    for layer_name, layer_def in LAYER_DEFINITIONS.items():
        if layer_name == "projects":
            continue  # handle last as catch-all
        
        matched_files = []
        for pattern in layer_def["patterns"]:
            for f in all_files:
                if _matches_pattern(f, pattern) and f not in claimed:
                    matched_files.append(f)
                    claimed.add(f)
        
        if matched_files:
            total_bytes = sum(
                (workspace / f).stat().st_size
                for f in matched_files
                if (workspace / f).exists()
            )
            layers.append(ManifestLayer(
                name=layer_name,
                files=sorted(matched_files),
                file_count=len(matched_files),
                total_bytes=total_bytes,
                description=layer_def["description"],
            ))
    
    # Catch-all: remaining files go to "projects"
    remaining = all_files - claimed
    if remaining:
        total_bytes = sum(
            (workspace / f).stat().st_size
            for f in remaining
            if (workspace / f).exists()
        )
        layers.append(ManifestLayer(
            name="projects",
            files=sorted(remaining),
            file_count=len(remaining),
            total_bytes=total_bytes,
            description="Project files and custom data",
        ))
    
    return layers


def _matches_pattern(filepath: str, pattern: str) -> bool:
    """Simple glob-like matching."""
    if "**" in pattern:
        # e.g. "memory/**/*.md" → check prefix + suffix
        prefix = pattern.split("**")[0].rstrip("/")
        suffix = pattern.split("**")[-1].lstrip("/")
        if not filepath.startswith(prefix):
            return False
        if suffix and "*" in suffix:
            ext = suffix.replace("*", "")
            return filepath.endswith(ext) or not ext
        return True
    elif "*" in pattern:
        # e.g. "skills/*/SKILL.md"
        regex = pattern.replace("*", "[^/]+")
        return bool(re.match(f"^{regex}$", filepath))
    else:
        # Exact match
        return filepath == pattern


def find_openclaw_workspace() -> Optional[Path]:
    """Auto-detect OpenClaw workspace location."""
    home = Path.home()
    candidates = [
        home / ".openclaw" / "workspace",
        home / ".config" / "openclaw" / "workspace",
    ]
    for c in candidates:
        if c.exists() and (c / "AGENTS.md").exists():
            return c
    return None


def find_openclaw_config() -> Optional[Path]:
    """Auto-detect OpenClaw config file."""
    home = Path.home()
    candidates = [
        home / ".openclaw" / "openclaw.json",
        home / ".config" / "openclaw" / "openclaw.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def detect_agent_name(workspace: Path) -> str:
    """Try to detect the agent's name from IDENTITY.md."""
    identity_file = workspace / "IDENTITY.md"
    if identity_file.exists():
        content = identity_file.read_text(encoding="utf-8")
        # Look for "Name:" line
        for line in content.splitlines():
            if line.strip().startswith("- **Name:**"):
                name = line.split(":**")[1].strip().rstrip("*")
                return name
    return "unknown-agent"
