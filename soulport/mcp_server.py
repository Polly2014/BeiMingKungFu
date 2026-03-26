"""
SoulPort MCP Server — let agents manage their own souls.

Exposes SoulPort operations as MCP tools so AI agents can
programmatically export, diagnose, diff, and monitor their
cognitive state without human intervention.

Usage:
    # stdio mode (for local MCP clients like Claude Desktop / OpenClaw)
    soulport-mcp

    # HTTP mode (for remote access)
    soulport-mcp --http --port 8891

Only read-only and create operations are exposed.
Destructive operations (absorb, merge, rollback) require human confirmation
and are intentionally excluded from MCP.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from . import __version__
from .core import diff_soul, export_soul, inspect_soul, changelog
from .doctor import check_soul_health
from .scanner import find_openclaw_workspace, detect_agent_name
from .watcher import (
    DEFAULT_SNAPSHOT_DIR,
    cleanup_old_snapshots,
    get_latest_snapshot,
    get_parent_hash,
    list_snapshots,
    take_snapshot,
)

mcp = FastMCP("SoulPort")


@mcp.tool()
def soulport_export(
    workspace: Optional[str] = None,
    output: Optional[str] = None,
) -> str:
    """Export your agent's soul to a .bm package.

    Creates a snapshot of your current cognitive state (memory, identity,
    config, skills, system) as a portable .bm file.

    Args:
        workspace: Agent workspace path (auto-detects OpenClaw if omitted)
        output: Output .bm file path (auto-generated if omitted)
    """
    ws = Path(workspace) if workspace else None
    out = Path(output) if output else None

    try:
        result = export_soul(workspace=ws, output=out)
        manifest = inspect_soul(result)
        size_kb = result.stat().st_size / 1024

        layers_summary = ", ".join(
            f"{l.name}({l.file_count})" for l in manifest.layers
        )
        return (
            f"✅ Soul exported: {result}\n"
            f"Agent: {manifest.agent_name}\n"
            f"Size: {size_kb:.1f} KB\n"
            f"Layers: {layers_summary}\n"
            f"Hash: {manifest.content_hash[:16]}..."
        )
    except Exception as e:
        return f"❌ Export failed: {e}"


@mcp.tool()
def soulport_doctor(workspace: Optional[str] = None) -> str:
    """Check your soul's health across all five layers.

    Evaluates identity, memory, config, skills, and system layers,
    returning a health score (0-100) with actionable suggestions.

    Args:
        workspace: Agent workspace path (auto-detects OpenClaw if omitted)
    """
    ws = Path(workspace) if workspace else find_openclaw_workspace()
    if ws is None:
        return "❌ Cannot find OpenClaw workspace. Specify workspace path."

    report = check_soul_health(ws)

    lines = [
        f"🩺 Soul Health: {report.health_score}/100",
        f"Agent: {report.agent_name}",
        f"Summary: {report.ok_count} ok, {report.warn_count} warn, {report.missing_count} missing",
        "",
    ]

    for check in report.checks:
        icon = {"ok": "✅", "warn": "⚠️", "missing": "❌"}.get(check.status, "?")
        lines.append(f"{icon} [{check.layer}] {check.name} — {check.detail}")
        if check.suggestion:
            lines.append(f"   → {check.suggestion}")

    return "\n".join(lines)


@mcp.tool()
def soulport_diff(
    package_path: str,
    workspace: Optional[str] = None,
) -> str:
    """Compare a .bm package against your current workspace.

    Shows what would change if you absorbed this package:
    added files, modified files, and files only in workspace.

    Args:
        package_path: Path to the .bm file to compare
        workspace: Agent workspace path (auto-detects OpenClaw if omitted)
    """
    pkg = Path(package_path)
    ws = Path(workspace) if workspace else None

    try:
        result = diff_soul(package_path=pkg, workspace=ws)
        lines = [
            f"🔍 Diff: {result.package_name}",
            f"+{len(result.added)} added, ~{len(result.modified)} modified, "
            f"◦{len(result.ws_only)} ws-only, ={len(result.unchanged)} unchanged",
            "",
        ]

        for d in result.file_diffs:
            if d.status == "unchanged":
                continue
            symbol = {
                "added": "+", "modified": "~",
                "ws_only": "◦", "removed": "-",
            }.get(d.status, "?")
            lines.append(f"  {symbol} [{d.layer}] {d.rel_path}")

        return "\n".join(lines) if len(lines) > 3 else "\n".join(lines) + "\nNo changes."
    except Exception as e:
        return f"❌ Diff failed: {e}"


@mcp.tool()
def soulport_changelog(
    count: int = 5,
    snapshot_dir: Optional[str] = None,
) -> str:
    """Show recent changes between soul snapshots.

    Compares consecutive snapshots and reports per-layer changes.
    Requires at least 2 snapshots (created by `soulport watch` or `soulport_export`).

    Args:
        count: Number of recent changes to show (default: 5)
        snapshot_dir: Snapshot directory (default: ~/.soulport/snapshots/)
    """
    snap_dir = Path(snapshot_dir) if snapshot_dir else DEFAULT_SNAPSHOT_DIR

    if not snap_dir.exists():
        return "❌ No snapshots found. Run soulport_export or soulport watch --once first."

    entries = changelog(snap_dir, count=count)
    if not entries:
        bm_count = len(list(snap_dir.glob("*.bm")))
        return f"Need at least 2 snapshots (found {bm_count}). Take another snapshot after making changes."

    lines = [f"📜 Soul Changelog — last {len(entries)} change(s)", ""]

    for i, entry in enumerate(entries):
        ts = entry["exported_at"][:19] if entry["exported_at"] else "?"
        lines.append(f"#{i+1} {entry['old_hash']}→{entry['new_hash']} ({ts})")

        has_changes = False
        for layer_name, counts in sorted(entry["summary"].items()):
            parts = []
            if counts.get("added"):
                parts.append(f"+{counts['added']}")
            if counts.get("modified"):
                parts.append(f"~{counts['modified']}")
            if counts.get("removed"):
                parts.append(f"-{counts['removed']}")
            if parts:
                has_changes = True
                lines.append(f"  {layer_name}: {' '.join(parts)}")

        if not has_changes:
            lines.append("  (no changes)")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def soulport_status(
    workspace: Optional[str] = None,
    snapshot_dir: Optional[str] = None,
) -> str:
    """Show current soul status: last backup, snapshot count, health score.

    A quick overview of your agent's soul state — useful for deciding
    whether to export, or checking if watch is keeping things up to date.

    Args:
        workspace: Agent workspace path (auto-detects OpenClaw if omitted)
        snapshot_dir: Snapshot directory (default: ~/.soulport/snapshots/)
    """
    ws = Path(workspace) if workspace else find_openclaw_workspace()
    snap_dir = Path(snapshot_dir) if snapshot_dir else DEFAULT_SNAPSHOT_DIR

    lines = [f"🚀 SoulPort v{__version__}", ""]

    # Agent info
    if ws:
        agent_name = detect_agent_name(ws)
        lines.append(f"Agent: {agent_name}")
        lines.append(f"Workspace: {ws}")
    else:
        lines.append("Agent: (workspace not found)")

    # Health score (lightweight — for details use soulport_doctor)
    if ws:
        report = check_soul_health(ws)
        lines.append(f"Health: {report.health_score}/100 (use soulport_doctor for details)")

    # Snapshot info
    lines.append("")
    if snap_dir.exists():
        snapshots = list_snapshots(snap_dir)
        lines.append(f"Snapshots: {len(snapshots)} in {snap_dir}")

        if snapshots:
            latest = snapshots[0]  # newest first
            lines.append(f"Latest: {latest['name']}")
            lines.append(f"  Exported: {latest['exported_at'][:19]}")
            lines.append(f"  Hash: {latest['content_hash'][:16]}...")
            size_kb = latest['size'] / 1024
            lines.append(f"  Size: {size_kb:.1f} KB")
    else:
        lines.append("Snapshots: none (run soulport_export to create first)")

    return "\n".join(lines)


@mcp.tool()
def soulport_snapshot(
    workspace: Optional[str] = None,
    snapshot_dir: Optional[str] = None,
) -> str:
    """Take a single soul snapshot (like `soulport watch --once`).

    Creates a backup with lineage tracking. Skips if workspace
    hasn't changed since last snapshot.

    Args:
        workspace: Agent workspace path (auto-detects OpenClaw if omitted)
        snapshot_dir: Snapshot directory (default: ~/.soulport/snapshots/)
    """
    ws = Path(workspace) if workspace else find_openclaw_workspace()
    if ws is None:
        return "❌ Cannot find OpenClaw workspace. Specify workspace path."

    snap_dir = Path(snapshot_dir) if snapshot_dir else DEFAULT_SNAPSHOT_DIR
    parent_hash = get_parent_hash(snap_dir)

    try:
        result = take_snapshot(ws, snap_dir, parent_hash)
        if result:
            cleanup_old_snapshots(snap_dir, keep=10)
            return f"✅ Snapshot saved: {result.name}"
        else:
            # Give Agent context for why it was skipped
            latest = get_latest_snapshot(snap_dir)
            latest_info = f" (latest: {latest.name})" if latest else ""
            return f"⏭️ No changes since last snapshot — skipped{latest_info}"
    except Exception as e:
        return f"❌ Snapshot failed: {e}"


# ── Entry point ────────────────────────────────────────────────────

def main():
    """Run the SoulPort MCP Server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="SoulPort MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode")
    parser.add_argument("--port", type=int, default=8891, help="HTTP port (default: 8891)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    args = parser.parse_args()

    if args.http:
        if args.host != "127.0.0.1":
            import sys
            print(
                f"⚠️  WARNING: Binding to {args.host} exposes SoulPort MCP to the network.\n"
                "   No authentication is configured. Consider adding API key middleware\n"
                "   or using a reverse proxy with auth.",
                file=sys.stderr,
            )
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
