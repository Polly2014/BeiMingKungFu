"""
Beiming core operations — export, absorb, merge, inspect.
"""

import hashlib
import json
import os
import platform
import shutil
import tarfile
import tempfile
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
        beiming_version=__version__,
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
            tmp = tempfile.mkdtemp(prefix="beiming-merge-")
            temp_dirs.append(tmp)
            with tarfile.open(pkg, "r:gz") as tar:
                tar.extractall(tmp, filter="data")
            manifests.append(_read_manifest(pkg))
        
        # Merge workspace files
        merged_workspace = Path(tempfile.mkdtemp(prefix="beiming-merged-ws-"))
        
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
            beiming_version=__version__,
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
