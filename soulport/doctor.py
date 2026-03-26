"""
SoulPort doctor — soul health check across all five layers.
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .scanner import LAYER_DEFINITIONS, SKIP_PATTERNS, find_openclaw_config


# ── Health check definitions ───────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a single health check."""
    layer: str       # e.g. "identity", "memory"
    name: str        # human-readable check name
    status: str      # "ok", "warn", "missing"
    detail: str      # what was found
    suggestion: str = ""  # how to fix (only if warn/missing)


@dataclass
class DoctorReport:
    """Full doctor report."""
    workspace: Path
    agent_name: str
    checks: list[CheckResult] = field(default_factory=list)
    
    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "ok")
    
    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")
    
    @property
    def missing_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "missing")
    
    @property
    def health_score(self) -> int:
        """0-100 health score."""
        if not self.checks:
            return 0
        total = len(self.checks)
        score = (self.ok_count * 100 + self.warn_count * 50) / total
        return round(score)


def check_soul_health(workspace: Path) -> DoctorReport:
    """Run all health checks on a workspace."""
    from .scanner import detect_agent_name

    report = DoctorReport(
        workspace=workspace,
        agent_name=detect_agent_name(workspace),
    )

    _check_identity(workspace, report)
    _check_memory(workspace, report)
    _check_config(workspace, report)
    _check_skills(workspace, report)
    _check_system(workspace, report)

    return report


# ── Layer checks ───────────────────────────────────────────────────

def _check_identity(ws: Path, report: DoctorReport):
    """Check identity layer: SOUL.md, IDENTITY.md, USER.md."""
    layer = "identity"

    # IDENTITY.md — core identity file
    identity = ws / "IDENTITY.md"
    if identity.exists():
        content = identity.read_text(encoding="utf-8")
        size = identity.stat().st_size
        has_name = "Name:" in content or "name:" in content
        has_emoji = any(c for c in content if ord(c) > 0x1F000)

        if has_name and has_emoji and size > 100:
            report.checks.append(CheckResult(
                layer=layer, name="IDENTITY.md",
                status="ok",
                detail=f"{size} bytes, name field found",
            ))
        else:
            issues = []
            if not has_name:
                issues.append("no Name field")
            if not has_emoji:
                issues.append("no emoji")
            if size <= 100:
                issues.append(f"very short ({size} bytes)")
            report.checks.append(CheckResult(
                layer=layer, name="IDENTITY.md",
                status="warn",
                detail=", ".join(issues),
                suggestion="Add agent name, emoji, role description to IDENTITY.md",
            ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="IDENTITY.md",
            status="missing",
            detail="File not found",
            suggestion="Create IDENTITY.md with your agent's name, emoji, and role",
        ))

    # SOUL.md — personality/values
    soul = ws / "SOUL.md"
    if soul.exists():
        size = soul.stat().st_size
        if size > 200:
            report.checks.append(CheckResult(
                layer=layer, name="SOUL.md",
                status="ok",
                detail=f"{size} bytes",
            ))
        else:
            report.checks.append(CheckResult(
                layer=layer, name="SOUL.md",
                status="warn",
                detail=f"Short ({size} bytes)",
                suggestion="Expand SOUL.md with personality traits, values, communication style",
            ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="SOUL.md",
            status="missing",
            detail="File not found",
            suggestion="Create SOUL.md describing your agent's personality and values",
        ))

    # USER.md — human context
    user = ws / "USER.md"
    if user.exists():
        report.checks.append(CheckResult(
            layer=layer, name="USER.md",
            status="ok",
            detail=f"{user.stat().st_size} bytes",
        ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="USER.md",
            status="warn",
            detail="File not found (optional but recommended)",
            suggestion="Create USER.md with context about the human (preferences, timezone, etc.)",
        ))


def _check_memory(ws: Path, report: DoctorReport):
    """Check memory layer: MEMORY.md + memory/ directory."""
    layer = "memory"

    # MEMORY.md — long-term memory
    memory_md = ws / "MEMORY.md"
    if memory_md.exists():
        size = memory_md.stat().st_size
        report.checks.append(CheckResult(
            layer=layer, name="MEMORY.md",
            status="ok",
            detail=f"{size} bytes",
        ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="MEMORY.md",
            status="missing",
            detail="File not found",
            suggestion="Create MEMORY.md for long-term memory storage",
        ))

    # memory/ directory — daily/topical memories
    memory_dir = ws / "memory"
    if memory_dir.is_dir():
        md_files = list(memory_dir.rglob("*.md"))
        json_files = list(memory_dir.rglob("*.json"))
        total_files = len(md_files) + len(json_files)

        if total_files == 0:
            report.checks.append(CheckResult(
                layer=layer, name="memory/ directory",
                status="warn",
                detail="Directory exists but empty",
                suggestion="Start recording memories in memory/ (daily notes, reflections)",
            ))
        else:
            # Check time span
            dates = _extract_dates_from_paths(md_files)
            span_str = ""
            if len(dates) >= 2:
                span = (max(dates) - min(dates)).days
                span_str = f", spanning {span} days"
            elif len(dates) == 1:
                span_str = ", 1 day"

            density = "rich" if total_files > 20 else "growing" if total_files > 5 else "starting"
            report.checks.append(CheckResult(
                layer=layer, name="memory/ directory",
                status="ok",
                detail=f"{total_files} files ({len(md_files)} md, {len(json_files)} json){span_str} — {density}",
            ))

            # Check for dormancy: last memory too old?
            if dates:
                days_since_last = (datetime.now() - max(dates)).days
                if days_since_last > 7:
                    report.checks.append(CheckResult(
                        layer=layer, name="Recent activity",
                        status="warn",
                        detail=f"Last memory was {days_since_last} days ago",
                        suggestion="Your agent might be dormant — try `soulport export` to capture recent state",
                    ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="memory/ directory",
            status="missing",
            detail="Directory not found",
            suggestion="Create memory/ directory for daily and topical memories",
        ))


def _check_config(ws: Path, report: DoctorReport):
    """Check config layer: AGENTS.md, TOOLS.md, HEARTBEAT.md."""
    layer = "config"

    checks = {
        "AGENTS.md": {
            "required": True,
            "min_size": 50,
            "suggestion": "AGENTS.md defines your agent's behavior rules and capabilities",
        },
        "TOOLS.md": {
            "required": False,
            "min_size": 50,
            "suggestion": "TOOLS.md stores notes about tools your agent has used",
        },
        "HEARTBEAT.md": {
            "required": False,
            "min_size": 30,
            "suggestion": "HEARTBEAT.md defines recurring tasks and routines",
        },
    }

    for filename, spec in checks.items():
        filepath = ws / filename
        if filepath.exists():
            size = filepath.stat().st_size
            if size >= spec["min_size"]:
                report.checks.append(CheckResult(
                    layer=layer, name=filename,
                    status="ok",
                    detail=f"{size} bytes",
                ))
            else:
                report.checks.append(CheckResult(
                    layer=layer, name=filename,
                    status="warn",
                    detail=f"Very short ({size} bytes)",
                    suggestion=f"Expand {filename} — {spec['suggestion']}",
                ))
        else:
            report.checks.append(CheckResult(
                layer=layer, name=filename,
                status="missing" if spec["required"] else "warn",
                detail="File not found",
                suggestion=spec["suggestion"],
            ))


def _check_skills(ws: Path, report: DoctorReport):
    """Check skills layer: skills/ directory with SKILL.md files."""
    layer = "skills"

    skills_dir = ws / "skills"
    if skills_dir.is_dir():
        # Reuse scanner's SKIP_PATTERNS to filter out build artifacts (.git, __pycache__, etc.)
        skill_dirs = [
            d for d in skills_dir.iterdir()
            if d.is_dir() and d.name not in SKIP_PATTERNS
        ]
        skill_count = sum(1 for d in skill_dirs if (d / "SKILL.md").exists())
        missing_skill_md = [
            d.name for d in skill_dirs if not (d / "SKILL.md").exists()
        ]

        if skill_count > 0:
            report.checks.append(CheckResult(
                layer=layer, name="Custom skills",
                status="ok",
                detail=f"{skill_count} skill(s) with SKILL.md",
            ))
        else:
            report.checks.append(CheckResult(
                layer=layer, name="Custom skills",
                status="warn",
                detail="No skills with SKILL.md found",
                suggestion="Add custom skills in skills/<name>/SKILL.md",
            ))

        if missing_skill_md:
            report.checks.append(CheckResult(
                layer=layer, name="SKILL.md coverage",
                status="warn",
                detail=f"{len(missing_skill_md)} skill dir(s) missing SKILL.md: {', '.join(missing_skill_md[:3])}",
                suggestion="Each skill directory should have a SKILL.md defining its capabilities",
            ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="Custom skills",
            status="warn",
            detail="No skills/ directory (this is normal for new agents)",
            suggestion="Custom skills make your agent unique — add them as you grow",
        ))


def _check_system(ws: Path, report: DoctorReport):
    """Check system layer: openclaw.json config."""
    layer = "system"

    config_path = find_openclaw_config()
    if config_path and config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            keys = list(data.keys())
            report.checks.append(CheckResult(
                layer=layer, name="openclaw.json",
                status="ok",
                detail=f"Found, {len(keys)} top-level keys",
            ))
        except (json.JSONDecodeError, OSError):
            report.checks.append(CheckResult(
                layer=layer, name="openclaw.json",
                status="warn",
                detail="File exists but failed to parse",
                suggestion="Check openclaw.json for syntax errors",
            ))
    else:
        report.checks.append(CheckResult(
            layer=layer, name="openclaw.json",
            status="warn",
            detail="Config not found (looked in ~/.openclaw/ and ~/.config/openclaw/)",
            suggestion="System config is exported during `soulport export` for portability",
        ))


# ── Helpers ────────────────────────────────────────────────────────

def _extract_dates_from_paths(paths: list[Path]) -> list[datetime]:
    """Try to extract dates from file paths like memory/2026-03-25.md."""
    dates = []
    date_pattern = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
    for p in paths:
        match = date_pattern.search(str(p))
        if match:
            try:
                dates.append(datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                ))
            except ValueError:
                pass
    return dates
