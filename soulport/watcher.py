"""
SoulPort watcher — automatic soul backup daemon.

Periodically exports workspace snapshots to ~/.soulport/snapshots/,
maintaining a lineage chain via parent_hash in manifest.json.
"""

import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import __version__
from .core import _compute_file_hash, _read_manifest, export_soul


# ── Constants ──────────────────────────────────────────────────────

DEFAULT_SNAPSHOT_DIR = Path.home() / ".soulport" / "snapshots"
DEFAULT_INTERVAL_SECONDS = 6 * 3600  # 6 hours
DEFAULT_KEEP = 10


def parse_interval(s: str) -> int:
    """Parse interval string like '6h', '30m', '1d' into seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("d"):
        return int(s[:-1]) * 86400
    elif s.endswith("s"):
        return int(s[:-1])
    else:
        return int(s)


def get_latest_snapshot(snapshot_dir: Path) -> Optional[Path]:
    """Find the most recent .bm file in the snapshot directory."""
    if not snapshot_dir.exists():
        return None
    bm_files = sorted(snapshot_dir.glob("*.bm"), key=lambda p: p.stat().st_mtime)
    return bm_files[-1] if bm_files else None


def get_parent_hash(snapshot_dir: Path) -> str:
    """Read content_hash from the latest snapshot for lineage chain."""
    latest = get_latest_snapshot(snapshot_dir)
    if latest is None:
        return ""
    try:
        manifest = _read_manifest(latest)
        return manifest.content_hash
    except (ValueError, OSError):
        return ""


def take_snapshot(
    workspace: Path,
    snapshot_dir: Path,
    parent_hash: str = "",
) -> Optional[Path]:
    """
    Take a single snapshot: export workspace → snapshot_dir.
    Returns the path to the created .bm file, or None on failure.
    """
    from .scanner import detect_agent_name

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    agent_name = detect_agent_name(workspace)
    safe_name = agent_name.replace(" ", "-")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    output = snapshot_dir / f"{safe_name}-{timestamp}.bm"

    # Avoid overwriting if same minute
    if output.exists():
        return None

    try:
        result = export_soul(
            workspace=workspace,
            output=output,
            include_config=True,
            include_projects=False,
        )

        # Inject parent_hash into the manifest for lineage
        if parent_hash:
            _inject_parent_hash(result, parent_hash)

        return result
    except Exception:
        # Clean up partial file on failure
        if output.exists():
            output.unlink()
        raise


def _inject_parent_hash(bm_path: Path, parent_hash: str):
    """Add parent_hash to an existing .bm package's manifest."""
    import json
    import tarfile
    from io import BytesIO

    manifest = _read_manifest(bm_path)
    manifest.parent_hash = parent_hash

    tmp_path = bm_path.with_suffix(".bm.tmp")
    with tarfile.open(bm_path, "r:gz") as old_tar:
        with tarfile.open(tmp_path, "w:gz") as new_tar:
            for member in old_tar.getmembers():
                if member.name == "manifest.json":
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

    tmp_path.replace(bm_path)


def cleanup_old_snapshots(snapshot_dir: Path, keep: int):
    """Remove old snapshots, keeping the most recent `keep` files."""
    if not snapshot_dir.exists():
        return
    bm_files = sorted(snapshot_dir.glob("*.bm"), key=lambda p: p.stat().st_mtime)
    to_remove = bm_files[:-keep] if len(bm_files) > keep else []
    for f in to_remove:
        f.unlink()
    return len(to_remove)


def watch_loop(
    workspace: Path,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    interval: int = DEFAULT_INTERVAL_SECONDS,
    keep: int = DEFAULT_KEEP,
    on_snapshot=None,
    on_error=None,
):
    """
    Main watch loop. Runs until SIGTERM/SIGINT.

    Args:
        workspace: Agent workspace path
        snapshot_dir: Where to store .bm snapshots
        interval: Seconds between snapshots
        keep: Max snapshots to retain
        on_snapshot: Callback(path, parent_hash) after each snapshot
        on_error: Callback(exception) on snapshot failure
    """
    running = True

    def _handle_signal(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Take first snapshot immediately
    parent_hash = get_parent_hash(snapshot_dir)

    while running:
        try:
            result = take_snapshot(workspace, snapshot_dir, parent_hash)
            if result:
                parent_hash = _compute_file_hash(result)
                removed = cleanup_old_snapshots(snapshot_dir, keep)
                if on_snapshot:
                    on_snapshot(result, parent_hash, removed or 0)
        except Exception as e:
            if on_error:
                on_error(e)

        # Sleep in small increments so SIGTERM is responsive
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)
