"""
SoulPort core operations — export, absorb, merge, inspect, diff.
"""

import difflib
import hashlib
import json
import os
import platform
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

from . import __version__
from .manifest import Manifest, ManifestLayer
from .scanner import (
    detect_agent_name,
    find_openclaw_config,
    find_openclaw_workspace,
    redact_config,
    scan_workspace,
)


def export_soul(
    workspace: Optional[Path] = None,
    output: Optional[Path] = None,
    include_config: bool = True,
    include_projects: bool = False,
    name_override: Optional[str] = None,
) -> Path:
    """
    Export an agent's soul to a .bm package.
    
    Returns the path to the created .bm file.
    """
    # Auto-detect workspace
    if workspace is None:
        workspace = find_openclaw_workspace()
        if workspace is None:
            raise FileNotFoundError(
                "Cannot find OpenClaw workspace. "
                "Use --workspace to specify the path."
            )
    
    workspace = Path(workspace)
    
    # Detect agent name
    agent_name = name_override or detect_agent_name(workspace)
    
    # Scan workspace into layers
    layers = scan_workspace(workspace)
    
    # Filter out projects layer if not requested
    if not include_projects:
        layers = [l for l in layers if l.name != "projects"]
    
    # Build manifest
    manifest = Manifest(
        soulport_version=__version__,
        agent_name=agent_name,
        source_host=platform.node(),
        source_framework="openclaw",
        source_workspace=str(workspace),
        exported_at=datetime.now(timezone.utc).isoformat(),
        layers=layers,
    )
    
    # Generate output filename
    if output is None:
        safe_name = agent_name.replace(" ", "-")
        date_str = datetime.now().strftime("%Y-%m-%d")
        output = Path(f"{safe_name}-{date_str}.bm")
    
    # Create the .bm package (tar.gz)
    with tarfile.open(output, "w:gz") as tar:
        # Add manifest
        manifest_bytes = manifest.to_json().encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, BytesIO(manifest_bytes))
        
        # Add workspace files
        for layer in layers:
            for rel_path in layer.files:
                full_path = workspace / rel_path
                if full_path.exists():
                    tar.add(full_path, arcname=f"workspace/{rel_path}")
        
        # Add sanitized system config
        if include_config:
            config_path = find_openclaw_config()
            if config_path and config_path.exists():
                raw = config_path.read_text(encoding="utf-8")
                try:
                    config_data = json.loads(raw)
                    redacted, redacted_paths = redact_config(config_data)
                    manifest.redacted_fields = redacted_paths
                    
                    config_bytes = json.dumps(
                        redacted, indent=2, ensure_ascii=False
                    ).encode("utf-8")
                    info = tarfile.TarInfo(name="config/openclaw.json")
                    info.size = len(config_bytes)
                    tar.addfile(info, BytesIO(config_bytes))
                except json.JSONDecodeError:
                    pass  # skip if config is malformed
    
    # Compute content hash and rewrite manifest with it
    content_hash = _compute_file_hash(output)
    manifest.content_hash = content_hash
    
    # Rewrite the archive with updated manifest (hash + redacted_fields)
    _update_manifest_in_archive(output, manifest)
    
    return output


def absorb_soul(
    package_path: Path,
    target_workspace: Optional[Path] = None,
    layers: Optional[list[str]] = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """
    Absorb a .bm soul package into the current agent.
    
    Returns a summary of what was absorbed.
    """
    if target_workspace is None:
        target_workspace = find_openclaw_workspace()
        if target_workspace is None:
            raise FileNotFoundError(
                "Cannot find OpenClaw workspace. "
                "Use --workspace to specify the path."
            )
    
    target_workspace = Path(target_workspace)
    package_path = Path(package_path)
    
    if not package_path.exists():
        raise FileNotFoundError(f"Package not found: {package_path}")
    
    # Read manifest
    manifest = _read_manifest(package_path)
    
    # Determine which layers to absorb
    available_layers = {l.name for l in manifest.layers}
    if layers:
        selected = set(layers) & available_layers
    else:
        selected = available_layers
    
    summary = {
        "agent_name": manifest.agent_name,
        "source_host": manifest.source_host,
        "exported_at": manifest.exported_at,
        "layers_absorbed": [],
        "files_written": 0,
        "files_skipped": 0,
        "conflicts": [],
    }
    
    if dry_run:
        summary["dry_run"] = True
        for layer in manifest.layers:
            if layer.name in selected:
                summary["layers_absorbed"].append({
                    "name": layer.name,
                    "files": layer.files,
                    "file_count": layer.file_count,
                })
        return summary
    
    # Extract and apply
    with tarfile.open(package_path, "r:gz") as tar:
        for layer in manifest.layers:
            if layer.name not in selected:
                continue
            
            layer_summary = {
                "name": layer.name,
                "files_written": 0,
                "conflicts": [],
            }
            
            for rel_path in layer.files:
                member_name = f"workspace/{rel_path}"
                target_file = target_workspace / rel_path
                
                # Path traversal guard: ensure target stays within workspace
                try:
                    target_file.resolve().relative_to(target_workspace.resolve())
                except ValueError:
                    summary["files_skipped"] += 1
                    continue
                
                try:
                    member = tar.getmember(member_name)
                except KeyError:
                    continue
                
                # Check for conflicts
                if target_file.exists() and not force:
                    layer_summary["conflicts"].append(rel_path)
                    summary["conflicts"].append(rel_path)
                    summary["files_skipped"] += 1
                    continue
                
                # Extract
                target_file.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src:
                    if src:
                        target_file.write_bytes(src.read())
                        layer_summary["files_written"] += 1
                        summary["files_written"] += 1
            
            summary["layers_absorbed"].append(layer_summary)
    
    return summary


def inspect_soul(package_path: Path) -> Manifest:
    """Read and return the manifest from a .bm package."""
    return _read_manifest(package_path)


def merge_souls(
    packages: list[Path],
    output: Optional[Path] = None,
) -> Path:
    """
    Merge multiple .bm packages into one.
    
    Strategy:
    - memory: merge by timeline (union, deduplicate by filename)
    - identity: take from first package (primary)
    - config: union, flag conflicts
    - skills: union set
    """
    if len(packages) < 2:
        raise ValueError("Need at least 2 packages to merge")
    
    if output is None:
        output = Path(f"merged-{datetime.now().strftime('%Y-%m-%d')}.bm")
    
    # Extract all packages to temp dirs
    temp_dirs = []
    manifests = []
    
    try:
        for pkg in packages:
            tmp = tempfile.mkdtemp(prefix="soulport-merge-")
            temp_dirs.append(tmp)
            with tarfile.open(pkg, "r:gz") as tar:
                tar.extractall(tmp, filter="data")
            manifests.append(_read_manifest(pkg))
        
        # Merge workspace files
        merged_workspace = Path(tempfile.mkdtemp(prefix="soulport-merged-ws-"))
        
        for i, (tmp, manifest) in enumerate(zip(temp_dirs, manifests)):
            ws_dir = Path(tmp) / "workspace"
            if not ws_dir.exists():
                continue
            
            for root, dirs, files in os.walk(ws_dir):
                for f in files:
                    src = Path(root) / f
                    rel = os.path.relpath(src, ws_dir)
                    dst = merged_workspace / rel
                    
                    if dst.exists():
                        # Conflict resolution: memory files merge, others first-wins
                        if rel.startswith("memory/"):
                            # Memory: keep both if different content
                            if src.read_bytes() != dst.read_bytes():
                                # Append source info to differentiate
                                stem = dst.stem
                                suffix = dst.suffix
                                host = manifests[i].source_host or f"source-{i}"
                                new_name = f"{stem}-{host}{suffix}"
                                alt_dst = dst.parent / new_name
                                if not alt_dst.exists():
                                    dst.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(src, alt_dst)
                        # For identity/config: first package wins (skip)
                        continue
                    
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        
        # Re-export the merged workspace
        merged_layers = scan_workspace(merged_workspace)
        
        primary = manifests[0]
        merged_manifest = Manifest(
            soulport_version=__version__,
            agent_name=primary.agent_name,
            source_host=f"merged({', '.join(m.source_host for m in manifests)})",
            source_framework=primary.source_framework,
            source_workspace="<merged>",
            exported_at=datetime.now(timezone.utc).isoformat(),
            layers=merged_layers,
        )
        
        with tarfile.open(output, "w:gz") as tar:
            manifest_bytes = merged_manifest.to_json().encode("utf-8")
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest_bytes)
            tar.addfile(info, BytesIO(manifest_bytes))
            
            for layer in merged_layers:
                for rel_path in layer.files:
                    full_path = merged_workspace / rel_path
                    if full_path.exists():
                        tar.add(full_path, arcname=f"workspace/{rel_path}")
        
        return output
    
    finally:
        # Cleanup temp dirs
        for tmp in temp_dirs:
            shutil.rmtree(tmp, ignore_errors=True)
        if 'merged_workspace' in locals():
            shutil.rmtree(merged_workspace, ignore_errors=True)


# ── Internal helpers ───────────────────────────────────────────────

def _read_manifest(package_path: Path) -> Manifest:
    """Extract and parse manifest.json from a .bm package."""
    with tarfile.open(package_path, "r:gz") as tar:
        try:
            member = tar.getmember("manifest.json")
            f = tar.extractfile(member)
            if f is None:
                raise ValueError("Empty manifest")
            data = json.loads(f.read().decode("utf-8"))
            return Manifest.from_dict(data)
        except KeyError:
            raise ValueError(f"Invalid .bm package: no manifest.json found in {package_path}")


def _compute_file_hash(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _update_manifest_in_archive(archive_path: Path, manifest: Manifest):
    """Rewrite the manifest in an existing archive."""
    tmp_path = archive_path.with_suffix(".bm.tmp")
    
    with tarfile.open(archive_path, "r:gz") as old_tar:
        with tarfile.open(tmp_path, "w:gz") as new_tar:
            for member in old_tar.getmembers():
                if member.name == "manifest.json":
                    # Replace with updated manifest
                    manifest_bytes = manifest.to_json().encode("utf-8")
                    info = tarfile.TarInfo(name="manifest.json")
                    info.size = len(manifest_bytes)
                    new_tar.addfile(info, BytesIO(manifest_bytes))
                else:
                    f = old_tar.extractfile(member)
                    if f:
                        new_tar.addfile(member, f)
                    else:
                        new_tar.addfile(member)
    
    # Atomic replace
    tmp_path.replace(archive_path)


# ── Diff ───────────────────────────────────────────────────────────

@dataclass
class FileDiff:
    """Diff result for a single file."""
    rel_path: str
    status: str     # "added", "removed", "modified", "unchanged"
    layer: str      # which soul layer it belongs to
    pkg_size: int = 0
    ws_size: int = 0
    diff_lines: list[str] = field(default_factory=list)  # unified diff lines (text files only)


@dataclass
class SoulDiff:
    """Full diff between a .bm package and workspace."""
    package_name: str
    agent_name: str
    file_diffs: list[FileDiff] = field(default_factory=list)
    
    @property
    def added(self) -> list[FileDiff]:
        return [d for d in self.file_diffs if d.status == "added"]
    
    @property
    def ws_only(self) -> list[FileDiff]:
        return [d for d in self.file_diffs if d.status == "ws_only"]
    
    @property
    def removed(self) -> list[FileDiff]:
        """Alias for ws_only, kept for backward compat."""
        return self.ws_only
    
    @property
    def modified(self) -> list[FileDiff]:
        return [d for d in self.file_diffs if d.status == "modified"]
    
    @property
    def unchanged(self) -> list[FileDiff]:
        return [d for d in self.file_diffs if d.status == "unchanged"]


def diff_soul(
    package_path: Path,
    workspace: Optional[Path] = None,
    # TODO v0.3: add `target: Optional[Path] = None` for .bm vs .bm comparison
    #   (needed for changelog/lineage — compare two snapshots without a workspace)
) -> SoulDiff:
    """
    Compare a .bm package against the current workspace.
    Shows what would change if you absorbed this package.

    Uses _read_manifest() to parse the package and scan_workspace()
    to discover current workspace files for layer attribution.
    """
    if workspace is None:
        workspace = find_openclaw_workspace()
        if workspace is None:
            raise FileNotFoundError(
                "Cannot find OpenClaw workspace. Use --workspace to specify."
            )
    
    workspace = Path(workspace)
    package_path = Path(package_path)
    manifest = _read_manifest(package_path)
    
    # Build layer lookup: rel_path -> layer_name
    layer_map: dict[str, str] = {}
    for layer in manifest.layers:
        for f in layer.files:
            layer_map[f] = layer.name
    
    # All files in the package (under workspace/)
    pkg_files: dict[str, bytes] = {}
    with tarfile.open(package_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.startswith("workspace/") and member.isfile():
                rel = member.name[len("workspace/"):]
                f = tar.extractfile(member)
                if f:
                    pkg_files[rel] = f.read()
    
    # All files in current workspace (matching the same layer patterns)
    ws_files: set[str] = set()
    current_layers = scan_workspace(workspace)
    for layer in current_layers:
        for f in layer.files:
            ws_files.add(f)
            if f not in layer_map:
                layer_map[f] = layer.name
    
    all_paths = sorted(set(pkg_files.keys()) | ws_files)
    
    result = SoulDiff(
        package_name=package_path.name,
        agent_name=manifest.agent_name,
    )
    
    for rel_path in all_paths:
        in_pkg = rel_path in pkg_files
        in_ws = (workspace / rel_path).exists()
        layer = layer_map.get(rel_path, "unknown")
        
        if in_pkg and not in_ws:
            # File in package but not in workspace → would be added
            result.file_diffs.append(FileDiff(
                rel_path=rel_path, status="added", layer=layer,
                pkg_size=len(pkg_files[rel_path]),
            ))
        elif not in_pkg and in_ws:
            # File in workspace but not in package — absorb won't touch it
            ws_content = (workspace / rel_path).read_bytes()
            result.file_diffs.append(FileDiff(
                rel_path=rel_path, status="ws_only", layer=layer,
                ws_size=len(ws_content),
            ))
        elif in_pkg and in_ws:
            # Both exist → compare
            pkg_content = pkg_files[rel_path]
            ws_content = (workspace / rel_path).read_bytes()
            
            if pkg_content == ws_content:
                result.file_diffs.append(FileDiff(
                    rel_path=rel_path, status="unchanged", layer=layer,
                    pkg_size=len(pkg_content), ws_size=len(ws_content),
                ))
            else:
                diff_lines = _text_diff(rel_path, ws_content, pkg_content)
                result.file_diffs.append(FileDiff(
                    rel_path=rel_path, status="modified", layer=layer,
                    pkg_size=len(pkg_content), ws_size=len(ws_content),
                    diff_lines=diff_lines,
                ))
    
    return result


def _text_diff(filename: str, old_bytes: bytes, new_bytes: bytes) -> list[str]:
    """Generate unified diff for text files. Returns empty for binary or oversized."""
    # Skip diff for large files (>100KB) — O(n*m) memory/time
    if len(old_bytes) > 100_000 or len(new_bytes) > 100_000:
        return [f"(file too large for inline diff: {len(old_bytes)}→{len(new_bytes)} bytes)"]
    try:
        old_text = old_bytes.decode("utf-8").splitlines(keepends=True)
        new_text = new_bytes.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return ["(binary file changed)"]
    
    return list(difflib.unified_diff(
        old_text, new_text,
        fromfile=f"workspace/{filename}",
        tofile=f"package/{filename}",
        n=3,
    ))
