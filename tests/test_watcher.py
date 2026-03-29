"""Tests for soulport.watcher — snapshots, lineage, and cleanup."""

import pytest
from pathlib import Path

from soulport.core import export_soul, inspect_soul
from soulport.watcher import (
    cleanup_old_snapshots,
    find_snapshot_by_hash,
    get_latest_snapshot,
    get_parent_hash,
    list_snapshots,
    parse_interval,
    take_snapshot,
    workspace_fingerprint,
)


# ── Helpers ────────────────────────────────────────────────────────

def _create_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "SOUL.md").write_text("# My Agent\nI am helpful.")
    (ws / "IDENTITY.md").write_text("- **Name:** TestBot\n🤖")
    (ws / "MEMORY.md").write_text("# Memory\n- Learned testing")
    return ws


# ── parse_interval ─────────────────────────────────────────────────

class TestParseInterval:
    def test_hours(self):
        assert parse_interval("6h") == 6 * 3600

    def test_minutes(self):
        assert parse_interval("30m") == 30 * 60

    def test_days(self):
        assert parse_interval("1d") == 86400

    def test_seconds(self):
        assert parse_interval("120s") == 120

    def test_bare_number(self):
        assert parse_interval("3600") == 3600

    def test_whitespace(self):
        assert parse_interval("  2h  ") == 7200

    def test_case_insensitive(self):
        assert parse_interval("6H") == 6 * 3600


# ── workspace_fingerprint ──────────────────────────────────────────

class TestWorkspaceFingerprint:
    def test_same_workspace_same_fingerprint(self, tmp_path):
        ws = _create_workspace(tmp_path)
        fp1 = workspace_fingerprint(ws)
        fp2 = workspace_fingerprint(ws)
        assert fp1 == fp2

    def test_modified_workspace_different_fingerprint(self, tmp_path):
        ws = _create_workspace(tmp_path)
        fp1 = workspace_fingerprint(ws)
        (ws / "SOUL.md").write_text("# Changed content")
        fp2 = workspace_fingerprint(ws)
        assert fp1 != fp2

    def test_fingerprint_is_hex(self, tmp_path):
        ws = _create_workspace(tmp_path)
        fp = workspace_fingerprint(ws)
        assert len(fp) == 64  # SHA256
        int(fp, 16)  # should not raise


# ── take_snapshot ──────────────────────────────────────────────────

class TestTakeSnapshot:
    def test_creates_bm_file(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        result = take_snapshot(ws, snap_dir)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".bm"

    def test_creates_fingerprint_file(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        result = take_snapshot(ws, snap_dir)
        fp_file = result.with_suffix(".fp")
        assert fp_file.exists()
        assert len(fp_file.read_text()) == 64

    def test_skip_if_unchanged(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        # First snapshot
        first = take_snapshot(ws, snap_dir)
        assert first is not None
        parent_hash = inspect_soul(first).content_hash
        # Second snapshot — should be skipped (unchanged)
        second = take_snapshot(ws, snap_dir, parent_hash=parent_hash, skip_if_unchanged=True)
        assert second is None

    def test_no_skip_if_changed(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        first = take_snapshot(ws, snap_dir)
        parent_hash = inspect_soul(first).content_hash
        # Need 1.1s sleep: fingerprint uses int(mtime), filename has seconds
        import time; time.sleep(1.1)
        (ws / "SOUL.md").write_text("# Completely different soul after change")
        second = take_snapshot(ws, snap_dir, parent_hash=parent_hash, skip_if_unchanged=True)
        assert second is not None

    def test_lineage_parent_hash(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        first = take_snapshot(ws, snap_dir)
        parent_hash = inspect_soul(first).content_hash
        import time; time.sleep(1.1)
        (ws / "SOUL.md").write_text("# Updated soul for lineage test - new content")
        second = take_snapshot(ws, snap_dir, parent_hash=parent_hash, skip_if_unchanged=False)
        assert second is not None
        manifest = inspect_soul(second)
        assert manifest.parent_hash == parent_hash


# ── list_snapshots / find / get ────────────────────────────────────

class TestSnapshotQueries:
    def test_list_snapshots(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        take_snapshot(ws, snap_dir)
        import time; time.sleep(1.1)  # different second → different filename
        (ws / "SOUL.md").write_text("# v2 changed")
        take_snapshot(ws, snap_dir, skip_if_unchanged=False)
        snaps = list_snapshots(snap_dir)
        assert len(snaps) == 2
        assert snaps[0]["name"].endswith(".bm")

    def test_list_empty_dir(self, tmp_path):
        assert list_snapshots(tmp_path / "nonexistent") == []

    def test_get_latest_snapshot(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        take_snapshot(ws, snap_dir)
        latest = get_latest_snapshot(snap_dir)
        assert latest is not None
        assert latest.suffix == ".bm"

    def test_get_latest_none(self, tmp_path):
        assert get_latest_snapshot(tmp_path / "empty") is None

    def test_get_parent_hash(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        first = take_snapshot(ws, snap_dir)
        ph = get_parent_hash(snap_dir)
        assert ph == inspect_soul(first).content_hash

    def test_get_parent_hash_empty(self, tmp_path):
        assert get_parent_hash(tmp_path / "empty") == ""

    def test_find_snapshot_by_hash(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        result = take_snapshot(ws, snap_dir)
        manifest = inspect_soul(result)
        found = find_snapshot_by_hash(snap_dir, manifest.content_hash[:8])
        assert found == result

    def test_find_snapshot_not_found(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        assert find_snapshot_by_hash(snap_dir, "zzzznotexist") is None

    def test_find_snapshot_ambiguous(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        take_snapshot(ws, snap_dir)
        import time; time.sleep(1.1)
        (ws / "SOUL.md").write_text("# Changed for ambiguous test")
        take_snapshot(ws, snap_dir, skip_if_unchanged=False)
        # Both hashes start with some common hex chars — use empty prefix
        with pytest.raises(ValueError, match="Ambiguous"):
            find_snapshot_by_hash(snap_dir, "")


# ── cleanup_old_snapshots ──────────────────────────────────────────

class TestCleanup:
    def test_cleanup_keeps_n(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        import time
        for i in range(5):
            (ws / "SOUL.md").write_text(f"# Version {i} with unique content")
            time.sleep(1.1)  # different second → different filename
            take_snapshot(ws, snap_dir, skip_if_unchanged=False)
        assert len(list(snap_dir.glob("*.bm"))) == 5
        removed = cleanup_old_snapshots(snap_dir, keep=3)
        assert removed == 2
        assert len(list(snap_dir.glob("*.bm"))) == 3

    def test_cleanup_removes_fp_files(self, tmp_path):
        ws = _create_workspace(tmp_path)
        snap_dir = tmp_path / "snapshots"
        import time
        for i in range(3):
            (ws / "SOUL.md").write_text(f"# Version {i} cleanup fp test")
            time.sleep(1.1)
            take_snapshot(ws, snap_dir, skip_if_unchanged=False)
        cleanup_old_snapshots(snap_dir, keep=1)
        assert len(list(snap_dir.glob("*.fp"))) <= 1

    def test_cleanup_empty_dir(self, tmp_path):
        assert cleanup_old_snapshots(tmp_path / "nonexistent", keep=5) == 0
