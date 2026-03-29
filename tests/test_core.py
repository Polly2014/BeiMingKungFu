"""Tests for soulport.core — export, absorb, inspect, diff, merge."""

import json
import tarfile
import pytest
from io import BytesIO
from pathlib import Path

from soulport.core import (
    absorb_soul,
    diff_packages,
    diff_soul,
    export_soul,
    inspect_soul,
    merge_souls,
)
from soulport.manifest import Manifest, ManifestLayer


# ── Helpers ────────────────────────────────────────────────────────

def _create_workspace(tmp_path: Path) -> Path:
    """Create a minimal valid workspace for testing."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "SOUL.md").write_text("# My Agent\nI am a helpful assistant.")
    (ws / "IDENTITY.md").write_text("Name: TestBot\n🤖")
    (ws / "MEMORY.md").write_text("# Memory\n- Learned Python today")
    (ws / "AGENTS.md").write_text("# Agent Config\n- Be helpful")
    skill_dir = ws / "skills" / "coding"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Coding Skill\nWrite clean code.")
    return ws


def _create_bm(tmp_path: Path, ws: Path, name: str = "test") -> Path:
    """Export a workspace to a .bm file."""
    out = tmp_path / f"{name}.bm"
    return export_soul(workspace=ws, output=out)


# ── Export ─────────────────────────────────────────────────────────

class TestExport:
    def test_export_creates_file(self, tmp_path):
        ws = _create_workspace(tmp_path)
        out = tmp_path / "test.bm"
        result = export_soul(workspace=ws, output=out)
        assert result.exists()
        assert result.suffix == ".bm"

    def test_export_contains_manifest(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        with tarfile.open(bm, "r:gz") as tar:
            names = tar.getnames()
            assert "manifest.json" in names

    def test_export_contains_workspace_files(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        with tarfile.open(bm, "r:gz") as tar:
            names = tar.getnames()
            assert "workspace/SOUL.md" in names
            assert "workspace/IDENTITY.md" in names

    def test_export_manifest_has_layers(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        manifest = inspect_soul(bm)
        layer_names = {l.name for l in manifest.layers}
        assert "identity" in layer_names
        assert "memory" in layer_names

    def test_export_has_content_hash(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        manifest = inspect_soul(bm)
        assert len(manifest.content_hash) == 64  # SHA256 hex

    def test_export_name_override(self, tmp_path):
        ws = _create_workspace(tmp_path)
        out = tmp_path / "custom.bm"
        export_soul(workspace=ws, output=out, name_override="CustomBot")
        manifest = inspect_soul(out)
        assert manifest.agent_name == "CustomBot"

    def test_export_nonexistent_workspace_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            export_soul(workspace=tmp_path / "nope", output=tmp_path / "out.bm")


# ── Soul Shards (selective layer export) ───────────────────────────

class TestSoulShards:
    def test_export_single_layer(self, tmp_path):
        ws = _create_workspace(tmp_path)
        out = tmp_path / "skills-only.bm"
        export_soul(workspace=ws, output=out, selected_layers=["skills"])
        manifest = inspect_soul(out)
        layer_names = {l.name for l in manifest.layers}
        assert layer_names == {"skills"}

    def test_export_multiple_layers(self, tmp_path):
        ws = _create_workspace(tmp_path)
        out = tmp_path / "shard.bm"
        export_soul(workspace=ws, output=out, selected_layers=["identity", "memory"])
        manifest = inspect_soul(out)
        layer_names = {l.name for l in manifest.layers}
        assert "identity" in layer_names
        assert "memory" in layer_names
        assert "config" not in layer_names
        assert "skills" not in layer_names

    def test_shard_excludes_config_file(self, tmp_path):
        """When exporting a shard, config/openclaw.json should NOT be included."""
        ws = _create_workspace(tmp_path)
        out = tmp_path / "shard.bm"
        export_soul(workspace=ws, output=out, selected_layers=["skills"])
        with tarfile.open(out, "r:gz") as tar:
            names = tar.getnames()
            assert not any(n.startswith("config/") for n in names)

    def test_shard_absorb_only_selected(self, tmp_path):
        """A shard should only contain files from selected layers."""
        ws = _create_workspace(tmp_path)
        out = tmp_path / "identity-shard.bm"
        export_soul(workspace=ws, output=out, selected_layers=["identity"])
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(out, target_workspace=target, force=True)
        assert (target / "SOUL.md").exists()
        assert (target / "IDENTITY.md").exists()
        assert not (target / "MEMORY.md").exists()
        assert not (target / "AGENTS.md").exists()

    def test_shard_empty_layers_creates_minimal(self, tmp_path):
        """Selecting a nonexistent layer should create a .bm with no workspace files."""
        ws = _create_workspace(tmp_path)
        out = tmp_path / "empty.bm"
        export_soul(workspace=ws, output=out, selected_layers=["nonexistent"])
        manifest = inspect_soul(out)
        assert len(manifest.layers) == 0

    def test_shard_manifest_has_selected_layers(self, tmp_path):
        """Shard manifest should record which layers were selected."""
        ws = _create_workspace(tmp_path)
        out = tmp_path / "shard.bm"
        export_soul(workspace=ws, output=out, selected_layers=["skills", "memory"])
        manifest = inspect_soul(out)
        assert set(manifest.selected_layers) == {"skills", "memory"}

    def test_full_export_has_empty_selected_layers(self, tmp_path):
        """Full export should have empty selected_layers (not a shard)."""
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        manifest = inspect_soul(bm)
        assert manifest.selected_layers == []


# ── Inspect ────────────────────────────────────────────────────────

class TestInspect:
    def test_inspect_returns_manifest(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        manifest = inspect_soul(bm)
        assert isinstance(manifest, Manifest)
        assert manifest.soulport_version

    def test_inspect_invalid_package_raises(self, tmp_path):
        bad = tmp_path / "bad.bm"
        bad.write_bytes(b"not a tar.gz")
        with pytest.raises(Exception):
            inspect_soul(bad)


# ── Absorb ─────────────────────────────────────────────────────────

class TestAbsorb:
    def test_absorb_writes_files(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(bm, target_workspace=target, force=True)
        assert summary["files_written"] > 0
        assert (target / "SOUL.md").exists()

    def test_absorb_dry_run_no_write(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(bm, target_workspace=target, dry_run=True)
        assert summary.get("dry_run") is True
        assert not (target / "SOUL.md").exists()

    def test_absorb_selective_layers(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(bm, target_workspace=target, layers=["identity"], force=True)
        assert (target / "SOUL.md").exists()
        assert not (target / "MEMORY.md").exists()

    def test_absorb_conflict_without_force(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        (target / "SOUL.md").write_text("Existing content")
        summary = absorb_soul(bm, target_workspace=target, force=False)
        assert len(summary["conflicts"]) > 0
        # Existing file should NOT be overwritten
        assert (target / "SOUL.md").read_text() == "Existing content"

    def test_absorb_redacted_fields_in_summary(self, tmp_path):
        """Verify that absorb returns redacted_fields from manifest."""
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(bm, target_workspace=target, force=True)
        assert "redacted_fields" in summary
        assert isinstance(summary["redacted_fields"], list)

    def test_absorb_detects_redacted_in_files(self, tmp_path):
        """Verify that absorb scans package files for __SOULPORT_REDACTED__ markers."""
        ws = _create_workspace(tmp_path)
        # Write a file with a REDACTED marker into the workspace
        (ws / "AGENTS.md").write_text("api_key: __SOULPORT_REDACTED__\nmodel: gpt-4")
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(bm, target_workspace=target, force=True)
        assert "redacted_in_files" in summary
        # Package path includes workspace/ prefix
        assert any("AGENTS.md" in f for f in summary["redacted_in_files"])

    def test_absorb_detects_redacted_in_config(self, tmp_path):
        """Verify that config/openclaw.json REDACTED markers are detected.
        
        This is the most important case — API keys live in config/, not workspace/.
        """
        ws = _create_workspace(tmp_path)
        # Export with a config that has sensitive fields
        bm = _create_bm(tmp_path, ws)
        
        # Manually inject a config/openclaw.json with REDACTED into the .bm
        patched_bm = tmp_path / "patched.bm"
        config_content = json.dumps({
            "model": "gpt-4",
            "apiKey": "__SOULPORT_REDACTED__",
            "mcpServers": {"tidewatch": {"token": "__SOULPORT_REDACTED__"}}
        }).encode("utf-8")
        
        with tarfile.open(bm, "r:gz") as old_tar:
            with tarfile.open(patched_bm, "w:gz") as new_tar:
                for member in old_tar.getmembers():
                    f = old_tar.extractfile(member)
                    if f:
                        new_tar.addfile(member, BytesIO(f.read()))
                    else:
                        new_tar.addfile(member)
                # Add config file
                info = tarfile.TarInfo(name="config/openclaw.json")
                info.size = len(config_content)
                new_tar.addfile(info, BytesIO(config_content))
        
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(patched_bm, target_workspace=target, force=True)
        assert any("config/openclaw.json" in f for f in summary["redacted_in_files"])

    def test_absorb_dry_run_shows_redacted(self, tmp_path):
        """Verify that dry_run mode also reports REDACTED markers."""
        ws = _create_workspace(tmp_path)
        (ws / "AGENTS.md").write_text("token: __SOULPORT_REDACTED__")
        bm = _create_bm(tmp_path, ws)
        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(bm, target_workspace=target, dry_run=True)
        assert summary.get("dry_run") is True
        assert len(summary["redacted_in_files"]) > 0

    def test_absorb_path_traversal_blocked(self, tmp_path):
        """Ensure path traversal attempts are blocked."""
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)

        # Manually craft a .bm with a path traversal attempt
        evil_bm = tmp_path / "evil.bm"
        with tarfile.open(bm, "r:gz") as old_tar:
            with tarfile.open(evil_bm, "w:gz") as new_tar:
                for member in old_tar.getmembers():
                    f = old_tar.extractfile(member)
                    if member.name == "manifest.json" and f:
                        data = json.loads(f.read())
                        # Inject a path traversal into a layer's files
                        data["layers"][0]["files"].append("../../etc/passwd")
                        new_data = json.dumps(data).encode()
                        info = tarfile.TarInfo(name="manifest.json")
                        info.size = len(new_data)
                        new_tar.addfile(info, BytesIO(new_data))
                    elif f:
                        new_tar.addfile(member, f)
                    else:
                        new_tar.addfile(member)

        target = tmp_path / "target_ws"
        target.mkdir()
        summary = absorb_soul(evil_bm, target_workspace=target, force=True)
        assert summary["files_skipped"] > 0


# ── Diff ───────────────────────────────────────────────────────────

class TestDiff:
    def test_diff_identical(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        result = diff_soul(bm, workspace=ws)
        assert len(result.modified) == 0
        assert len(result.unchanged) > 0

    def test_diff_detects_modification(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        # Modify workspace after export
        (ws / "SOUL.md").write_text("# Changed Agent")
        result = diff_soul(bm, workspace=ws)
        modified_files = [d.rel_path for d in result.modified]
        assert "SOUL.md" in modified_files

    def test_diff_detects_added(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        # Remove a file from workspace
        (ws / "SOUL.md").unlink()
        result = diff_soul(bm, workspace=ws)
        added_files = [d.rel_path for d in result.added]
        assert "SOUL.md" in added_files

    def test_diff_packages(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm1 = _create_bm(tmp_path, ws, name="v1")
        (ws / "SOUL.md").write_text("# Updated Soul")
        bm2 = _create_bm(tmp_path, ws, name="v2")
        result = diff_packages(bm1, bm2)
        modified_files = [d.rel_path for d in result.modified]
        assert "SOUL.md" in modified_files


# ── Merge (file-level) ────────────────────────────────────────────

class TestMerge:
    def test_merge_two_packages(self, tmp_path):
        ws1 = _create_workspace(tmp_path / "ws1_parent")
        ws2 = _create_workspace(tmp_path / "ws2_parent")
        # Make ws2 different
        (ws2 / "SOUL.md").write_text("# Second Agent\nI am different.")
        mem_dir = ws2 / "memory" / "extra"
        mem_dir.mkdir(parents=True)
        (mem_dir / "new.md").write_text("# New memory")

        bm1 = _create_bm(tmp_path, ws1, name="a")
        bm2 = _create_bm(tmp_path, ws2, name="b")
        out = tmp_path / "merged.bm"
        result = merge_souls([bm1, bm2], output=out)
        assert result.exists()
        manifest = inspect_soul(result)
        all_files = [f for l in manifest.layers for f in l.files]
        assert "SOUL.md" in all_files

    def test_merge_less_than_two_raises(self, tmp_path):
        ws = _create_workspace(tmp_path)
        bm = _create_bm(tmp_path, ws)
        with pytest.raises(ValueError, match="at least 2"):
            merge_souls([bm])


# ── Manifest ───────────────────────────────────────────────────────

class TestManifest:
    def test_manifest_roundtrip(self):
        m = Manifest(
            agent_name="TestBot",
            source_host="laptop",
            layers=[ManifestLayer(name="identity", files=["SOUL.md"], file_count=1)],
            redacted_fields=["server.token"],
            content_hash="abc123",
        )
        data = m.to_dict()
        restored = Manifest.from_dict(data)
        assert restored.agent_name == "TestBot"
        assert restored.redacted_fields == ["server.token"]
        assert restored.content_hash == "abc123"
        assert restored.layers[0].name == "identity"

    def test_manifest_json_roundtrip(self):
        m = Manifest(agent_name="JSON Test", layers=[])
        json_str = m.to_json()
        data = json.loads(json_str)
        restored = Manifest.from_dict(data)
        assert restored.agent_name == "JSON Test"

    def test_manifest_from_dict_defaults(self):
        """Missing fields should get sensible defaults."""
        m = Manifest.from_dict({})
        assert m.agent_name == ""
        assert m.layers == []
        assert m.redacted_fields == []
        assert m.encrypted is False

    def test_manifest_lineage_fields(self):
        m = Manifest(
            parent_hash="abc",
            merge_parents=["abc", "def"],
            merge_strategy="semantic",
        )
        d = m.to_dict()
        assert d["parent_hash"] == "abc"
        assert d["merge_parents"] == ["abc", "def"]
        assert d["merge_strategy"] == "semantic"
