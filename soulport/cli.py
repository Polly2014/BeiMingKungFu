"""
SoulPort CLI — command-line interface for soul transfer operations.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from . import __version__
from .core import (
    FileDiff, SoulDiff,
    absorb_soul, diff_soul, export_soul, inspect_soul, merge_souls,
)
from .doctor import DoctorReport, check_soul_health
from .manifest import Manifest

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

console = Console(force_terminal=True)


def _format_bytes(n: int) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


BANNER = """[bold cyan]
  ╔════════════════════════════════════════╗
  ║  🚀 SoulPort — Agent Soul Transfer    ║
  ╚════════════════════════════════════════╝[/]
  [dim]Your agent's soul is portable.[/]
"""


@click.group()
@click.version_option(__version__, prog_name="soulport")
def main():
    """🚀 SoulPort — Agent Soul Transfer

    Export, absorb, and merge AI agent identities across machines.
    """
    pass


@main.command()
@click.option("--workspace", "-w", type=click.Path(exists=True), default=None,
              help="Agent workspace path (auto-detects OpenClaw)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output .bm file path")
@click.option("--name", "-n", default=None,
              help="Override agent name")
@click.option("--include-projects", is_flag=True, default=False,
              help="Include project files (teams-bridge, etc.)")
@click.option("--no-config", is_flag=True, default=False,
              help="Skip system config export")
def export(workspace, output, name, include_projects, no_config):
    """📤 Export your agent's soul to a .bm package."""
    console.print(BANNER)
    
    ws = Path(workspace) if workspace else None
    out = Path(output) if output else None
    
    try:
        with console.status("[bold cyan]Scanning workspace..."):
            result = export_soul(
                workspace=ws,
                output=out,
                include_config=not no_config,
                include_projects=include_projects,
                name_override=name,
            )
        
        # Show what was exported
        manifest = inspect_soul(result)
        _print_manifest(manifest, title="Exported Soul")
        
        file_size = result.stat().st_size
        console.print(f"\n[bold green]✅ Soul exported to:[/] {result} ({_format_bytes(file_size)})")
        
        # Show redacted fields (P1-5: user should know what got sanitized)
        if manifest.redacted_fields:
            console.print(f"\n[bold yellow]🔒 Redacted {len(manifest.redacted_fields)} sensitive field(s):[/]")
            for field in manifest.redacted_fields:
                console.print(f"  [dim]• {field}[/]")
        
        console.print(f"\n[dim]Transfer this file to another machine and run:[/]")
        console.print(f"[bold]  soulport absorb {result.name}[/]\n")
        
    except FileNotFoundError as e:
        console.print(f"[bold red]❌ {e}[/]")
        sys.exit(1)


@main.command()
@click.argument("package", type=click.Path(exists=True))
@click.option("--workspace", "-w", type=click.Path(), default=None,
              help="Target workspace path (auto-detects OpenClaw)")
@click.option("--layers", "-l", multiple=True,
              help="Only absorb specific layers (memory, identity, config, skills)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview what would be absorbed without writing")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing files without asking")
def absorb(package, workspace, layers, dry_run, force):
    """🌀 Absorb a soul package into your agent."""
    console.print(BANNER)
    
    pkg = Path(package)
    ws = Path(workspace) if workspace else None
    layer_list = list(layers) if layers else None
    
    try:
        # Preview first
        manifest = inspect_soul(pkg)
        _print_manifest(manifest, title="Soul to Absorb")
        
        if not dry_run and not force:
            if not click.confirm("\n🌀 Proceed with absorption?"):
                console.print("[yellow]Cancelled.[/]")
                return
        
        with console.status("[bold cyan]Absorbing soul..."):
            summary = absorb_soul(
                package_path=pkg,
                target_workspace=ws,
                layers=layer_list,
                dry_run=dry_run,
                force=force,
            )
        
        # Print summary
        if dry_run:
            console.print("\n[bold yellow]🔍 Dry run — no files written[/]")
        
        console.print(f"\n[bold green]✅ Absorption complete![/]")
        console.print(f"  Files written: {summary['files_written']}")
        
        if summary.get("conflicts"):
            console.print(f"  [yellow]Conflicts (skipped): {len(summary['conflicts'])}[/]")
            for c in summary["conflicts"]:
                console.print(f"    ⚠️  {c}")
            console.print(f"  [dim]Use --force to overwrite, or manually merge.[/]")
        
        if summary.get("files_skipped"):
            console.print(f"  Files skipped: {summary['files_skipped']}")
        
        console.print()
        
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]❌ {e}[/]")
        sys.exit(1)


@main.command()
@click.argument("package", type=click.Path(exists=True))
def inspect(package):
    """🔍 Inspect a soul package without absorbing it."""
    console.print(BANNER)
    
    try:
        manifest = inspect_soul(Path(package))
        _print_manifest(manifest, title=f"Soul Package: {Path(package).name}")
        
        # Show redacted fields
        if manifest.redacted_fields:
            console.print(f"\n[yellow]🔒 Redacted sensitive fields:[/]")
            for field in manifest.redacted_fields:
                console.print(f"  • {field}")
        
        console.print()
        
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]❌ {e}[/]")
        sys.exit(1)


@main.command()
@click.argument("packages", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output merged .bm file")
def merge(packages, output):
    """🔄 Merge multiple soul packages into one."""
    console.print(BANNER)
    
    if len(packages) < 2:
        console.print("[bold red]❌ Need at least 2 packages to merge.[/]")
        sys.exit(1)
    
    pkg_paths = [Path(p) for p in packages]
    out = Path(output) if output else None
    
    try:
        # Show what we're merging
        console.print("[bold]Merging souls:[/]")
        for p in pkg_paths:
            m = inspect_soul(p)
            console.print(f"  • {p.name} — {m.agent_name} from {m.source_host}")
        
        with console.status("[bold cyan]Merging souls..."):
            result = merge_souls(packages=pkg_paths, output=out)
        
        manifest = inspect_soul(result)
        _print_manifest(manifest, title="Merged Soul")
        
        file_size = result.stat().st_size
        console.print(f"\n[bold green]✅ Merged soul saved to:[/] {result} ({_format_bytes(file_size)})\n")
        
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]❌ {e}[/]")
        sys.exit(1)


@main.command()
@click.option("--workspace", "-w", type=click.Path(exists=True), default=None,
              help="Agent workspace path (auto-detects OpenClaw)")
def doctor(workspace):
    """🩺 Check your agent's soul health across all five layers."""
    console.print(BANNER)

    from .scanner import find_openclaw_workspace

    ws = Path(workspace) if workspace else find_openclaw_workspace()
    if ws is None:
        console.print("[bold red]❌ Cannot find OpenClaw workspace. Use --workspace to specify.[/]")
        sys.exit(1)

    report = check_soul_health(ws)
    _print_doctor_report(report)


@main.command()
@click.option("--workspace", "-w", type=click.Path(exists=True), default=None,
              help="Agent workspace path (auto-detects OpenClaw)")
@click.option("--interval", "-i", default="6h",
              help="Backup interval (e.g. 6h, 30m, 1d)")
@click.option("--keep", "-k", default=10, type=int,
              help="Max snapshots to retain (default: 10)")
@click.option("--snapshot-dir", type=click.Path(), default=None,
              help="Snapshot directory (default: ~/.soulport/snapshots/)")
@click.option("--once", is_flag=True, default=False,
              help="Take one snapshot and exit (no daemon)")
def watch(workspace, interval, keep, snapshot_dir, once):
    """⏰ Auto-backup your agent's soul on a schedule.

    Runs as a daemon, periodically exporting workspace snapshots.
    Each snapshot records its parent's hash, forming a lineage chain.
    """
    console.print(BANNER)

    from .scanner import find_openclaw_workspace
    from .watcher import (
        DEFAULT_SNAPSHOT_DIR,
        cleanup_old_snapshots,
        get_parent_hash,
        parse_interval,
        take_snapshot,
        watch_loop,
    )

    ws = Path(workspace) if workspace else find_openclaw_workspace()
    if ws is None:
        console.print("[bold red]❌ Cannot find OpenClaw workspace. Use --workspace to specify.[/]")
        sys.exit(1)

    snap_dir = Path(snapshot_dir) if snapshot_dir else DEFAULT_SNAPSHOT_DIR
    interval_secs = parse_interval(interval)

    if once:
        # Single snapshot mode
        parent_hash = get_parent_hash(snap_dir)
        try:
            result = take_snapshot(ws, snap_dir, parent_hash)
            if result:
                removed = cleanup_old_snapshots(snap_dir, keep)
                console.print(f"[bold green]✅ Snapshot saved:[/] {result}")
                console.print(f"[dim]Retained {keep} snapshots, removed {removed or 0} old[/]")
            else:
                console.print("[yellow]⏭️ Snapshot already exists for this minute[/]")
        except Exception as e:
            console.print(f"[bold red]❌ Snapshot failed: {e}[/]")
            sys.exit(1)
        return

    # Daemon mode
    console.print(f"[bold cyan]⏰ Starting soul watch daemon[/]")
    console.print(f"  Workspace: [dim]{ws}[/]")
    console.print(f"  Snapshots: [dim]{snap_dir}[/]")
    console.print(f"  Interval:  [dim]{interval}[/]")
    console.print(f"  Retention: [dim]{keep} snapshots[/]")
    console.print(f"\n[dim]Press Ctrl+C to stop.[/]\n")

    def on_snapshot(path, parent_hash, removed):
        ts = datetime.now().strftime("%H:%M:%S")
        console.print(
            f"[green]📸 [{ts}] Snapshot:[/] {path.name} "
            f"[dim](parent: {parent_hash[:8]}..., cleaned {removed})[/]"
        )

    def on_error(e):
        ts = datetime.now().strftime("%H:%M:%S")
        console.print(f"[red]❌ [{ts}] Snapshot failed: {e}[/]")

    from datetime import datetime
    watch_loop(
        workspace=ws,
        snapshot_dir=snap_dir,
        interval=interval_secs,
        keep=keep,
        on_snapshot=on_snapshot,
        on_error=on_error,
    )

    console.print("\n[bold cyan]👋 Watch daemon stopped.[/]")


@main.command()
@click.argument("package", type=click.Path(exists=True))
@click.option("--workspace", "-w", type=click.Path(exists=True), default=None,
              help="Target workspace path (auto-detects OpenClaw)")
@click.option("--full", is_flag=True, default=False,
              help="Show unified diff for modified files")
def diff(package, workspace, full):
    """🔍 Compare a .bm package against your current workspace."""
    console.print(BANNER)

    pkg = Path(package)
    ws = Path(workspace) if workspace else None

    try:
        result = diff_soul(package_path=pkg, workspace=ws)
        _print_diff(result, show_full=full)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]❌ {e}[/]")
        sys.exit(1)


# ── Display helpers ────────────────────────────────────────────────

LAYER_EMOJIS = {
    "identity": "👤",
    "memory": "🧠",
    "config": "⚙️",
    "skills": "🛠️",
    "projects": "📁",
    "system": "🔧",
}


def _print_manifest(manifest: Manifest, title: str = "Soul Package"):
    """Pretty-print a manifest."""
    
    # Header panel
    header = Table.grid(padding=(0, 2))
    header.add_row("Agent", f"[bold]{manifest.agent_name}[/]")
    header.add_row("From", f"{manifest.source_host}")
    header.add_row("Framework", manifest.source_framework)
    header.add_row("Exported", manifest.exported_at[:19] if manifest.exported_at else "—")
    header.add_row("SoulPort", f"v{manifest.soulport_version}")
    
    if manifest.content_hash:
        header.add_row("Hash", f"[dim]{manifest.content_hash[:16]}...[/]")
    
    console.print(Panel(header, title=f"[bold]{title}[/]", border_style="cyan"))
    
    # Layers tree
    tree = Tree("[bold]📦 Layers[/]")
    
    total_files = 0
    total_bytes = 0
    
    for layer in manifest.layers:
        emoji = LAYER_EMOJIS.get(layer.name, "📄")
        branch = tree.add(
            f"{emoji} [bold]{layer.name}[/] — {layer.file_count} files "
            f"({_format_bytes(layer.total_bytes)})"
        )
        
        # Show first few files
        show_max = 5
        for f in layer.files[:show_max]:
            branch.add(f"[dim]{f}[/]")
        if len(layer.files) > show_max:
            branch.add(f"[dim]... and {len(layer.files) - show_max} more[/]")
        
        total_files += layer.file_count
        total_bytes += layer.total_bytes
    
    console.print(tree)
    console.print(f"[dim]Total: {total_files} files, {_format_bytes(total_bytes)}[/]")


STATUS_ICONS = {"ok": "[green]✅[/]", "warn": "[yellow]⚠️[/]", "missing": "[red]❌[/]"}


def _print_doctor_report(report: DoctorReport):
    """Pretty-print a doctor report."""

    # Header
    score = report.health_score
    if score >= 80:
        score_color = "green"
    elif score >= 50:
        score_color = "yellow"
    else:
        score_color = "red"

    header = Table.grid(padding=(0, 2))
    header.add_row("Agent", f"[bold]{report.agent_name}[/]")
    header.add_row("Workspace", f"[dim]{report.workspace}[/]")
    header.add_row("Health", f"[bold {score_color}]{score}/100[/]")
    header.add_row(
        "Summary",
        f"[green]{report.ok_count} ok[/] · [yellow]{report.warn_count} warn[/] · [red]{report.missing_count} missing[/]",
    )
    console.print(Panel(header, title="[bold]🩺 Soul Health Check[/]", border_style="cyan"))

    # Per-layer results
    current_layer = None
    for check in report.checks:
        if check.layer != current_layer:
            current_layer = check.layer
            emoji = LAYER_EMOJIS.get(current_layer, "📄")
            console.print(f"\n{emoji} [bold]{current_layer.title()}[/]")

        icon = STATUS_ICONS.get(check.status, "❓")
        console.print(f"  {icon} {check.name} — {check.detail}")
        if check.suggestion:
            console.print(f"      [dim]→ {check.suggestion}[/]")

    # Footer — aligned with SoulArena's 5-tier level system
    console.print()
    if score >= 81:
        console.print("[bold green]🌊 北冥-level soul! Transcendent.[/]")
    elif score >= 61:
        console.print("[bold green]🦅 Peng-level soul! Soaring high.[/]")
    elif score >= 41:
        console.print("[bold yellow]🐋 Kun-level soul! Deep and growing.[/]")
    elif score >= 21:
        console.print("[bold yellow]🐟 Fish-level soul. Keep swimming.[/]")
    else:
        console.print("[bold red]🥚 Egg-level soul. Just hatched — lots of room to grow![/]")

    console.print(f"\n[dim]See your soul's portrait at[/] [bold]soul.polly.wang[/]\n")


STATUS_COLORS = {
    "added": "green",
    "ws_only": "dim",
    "modified": "yellow",
    "unchanged": "dim",
}
STATUS_SYMBOLS = {
    "added": "+",
    "ws_only": "◦",
    "modified": "~",
    "unchanged": "=",
}


def _print_diff(result: SoulDiff, show_full: bool = False):
    """Pretty-print a soul diff."""

    # Header
    header = Table.grid(padding=(0, 2))
    header.add_row("Package", f"[bold]{result.package_name}[/]")
    header.add_row("Agent", f"[bold]{result.agent_name}[/]")
    header.add_row(
        "Summary",
        f"[green]+{len(result.added)} added[/] · "
        f"[yellow]~{len(result.modified)} modified[/] · "
        f"[dim]◦{len(result.ws_only)} ws-only (kept)[/] · "
        f"[dim]={len(result.unchanged)} unchanged[/]",
    )
    console.print(Panel(header, title="[bold]🔍 Soul Diff[/]", border_style="cyan"))

    if not result.added and not result.modified and not result.ws_only:
        console.print("\n[green]✅ Package matches workspace perfectly — nothing to change.[/]\n")
        return

    # Group by layer
    layers_seen: dict[str, list[FileDiff]] = {}
    for d in result.file_diffs:
        if d.status == "unchanged":
            continue
        layers_seen.setdefault(d.layer, []).append(d)

    for layer_name, diffs in layers_seen.items():
        emoji = LAYER_EMOJIS.get(layer_name, "📄")
        console.print(f"\n{emoji} [bold]{layer_name.title()}[/]")

        for d in sorted(diffs, key=lambda x: x.rel_path):
            color = STATUS_COLORS[d.status]
            symbol = STATUS_SYMBOLS[d.status]
            size_info = ""
            if d.status == "modified":
                size_info = f" ({_format_bytes(d.ws_size)} → {_format_bytes(d.pkg_size)})"
            elif d.status == "added":
                size_info = f" ({_format_bytes(d.pkg_size)})"
            elif d.status == "ws_only":
                size_info = f" ({_format_bytes(d.ws_size)}, won't be changed)"

            console.print(f"  [{color}]{symbol}[/] {d.rel_path}{size_info}")

            if show_full and d.diff_lines:
                for line in d.diff_lines[:50]:
                    line = line.rstrip("\n")
                    if line.startswith("+") and not line.startswith("+++"):
                        console.print(f"    [green]{line}[/]")
                    elif line.startswith("-") and not line.startswith("---"):
                        console.print(f"    [red]{line}[/]")
                    elif line.startswith("@@"):
                        console.print(f"    [cyan]{line}[/]")
                    else:
                        console.print(f"    [dim]{line}[/]")
                if len(d.diff_lines) > 50:
                    console.print(f"    [dim]... {len(d.diff_lines) - 50} more lines ({len(d.diff_lines)} total)[/]")

    console.print()


if __name__ == "__main__":
    main()
