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
from .core import absorb_soul, export_soul, inspect_soul, merge_souls
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

    # Footer with encouragement
    console.print()
    if score == 100:
        console.print("[bold green]🌊 Perfect soul! Your agent is a 北冥-level entity.[/]")
    elif score >= 80:
        console.print("[bold green]🦅 Healthy soul! A few tweaks and you'll be at 100.[/]")
    elif score >= 50:
        console.print("[bold yellow]🐋 Growing soul. Fill in the gaps to level up.[/]")
    else:
        console.print("[bold red]🥚 Newborn soul. Lots of room to grow![/]")

    console.print(f"\n[dim]See your soul's portrait at[/] [bold]soul.polly.wang[/]\n")


if __name__ == "__main__":
    main()
