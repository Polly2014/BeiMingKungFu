"""
SoulPort manifest schema — defines what's inside a .bm package.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json
import hashlib


@dataclass
class ManifestLayer:
    """A single layer in the soul package."""
    name: str                    # e.g. "memory", "identity", "config", "skills", "system"
    files: list[str]             # relative paths included
    file_count: int = 0
    total_bytes: int = 0
    description: str = ""


@dataclass
class Manifest:
    """Root manifest for a .bm soul package."""
    
    # Identity
    version: str = "1"                       # manifest schema version
    soulport_version: str = "0.2.0"          # soulport tool version
    
    # Source
    agent_name: str = ""                     # e.g. "小龙虾"
    source_host: str = ""                    # hostname where exported
    source_framework: str = "openclaw"       # agent framework
    source_workspace: str = ""               # original workspace path
    
    # Timestamps
    exported_at: str = ""                    # ISO timestamp
    
    # Content
    layers: list[ManifestLayer] = field(default_factory=list)
    
    # Security
    redacted_fields: list[str] = field(default_factory=list)  # what was sanitized
    content_hash: str = ""                   # SHA256 of all content
    encrypted: bool = False
    
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "soulport_version": self.soulport_version,
            "agent_name": self.agent_name,
            "source_host": self.source_host,
            "source_framework": self.source_framework,
            "source_workspace": self.source_workspace,
            "exported_at": self.exported_at,
            "layers": [
                {
                    "name": l.name,
                    "files": l.files,
                    "file_count": l.file_count,
                    "total_bytes": l.total_bytes,
                    "description": l.description,
                }
                for l in self.layers
            ],
            "redacted_fields": self.redacted_fields,
            "content_hash": self.content_hash,
            "encrypted": self.encrypted,
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        layers = [
            ManifestLayer(**l) for l in data.get("layers", [])
        ]
        return cls(
            version=data.get("version", "1"),
            soulport_version=data.get("soulport_version") or data.get("beiming_version", "0.2.0"),
            agent_name=data.get("agent_name", ""),
            source_host=data.get("source_host", ""),
            source_framework=data.get("source_framework", "openclaw"),
            source_workspace=data.get("source_workspace", ""),
            exported_at=data.get("exported_at", ""),
            layers=layers,
            redacted_fields=data.get("redacted_fields", []),
            content_hash=data.get("content_hash", ""),
            encrypted=data.get("encrypted", False),
        )
