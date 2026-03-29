# 🚀 SoulPort — Agent Soul Transfer

> **`.bm` is the standard format for AI agent souls. The CLI is just the first consumer.**

Export your agent's personality, memories, and skills into a single portable file. Move between machines, merge diverged copies, or evaluate on [SoulArena](https://soul.polly.wang).

Migration is the first use case. Evaluation ([SoulArena](https://soul.polly.wang)), fusion, version control, and cross-framework interop are next.

> Previously known as "BeiMingKungFu" (北冥神功). Renamed to SoulPort in v0.2.0.

## Install

```bash
pip install soulport
```

## Commands

```bash
# Core — transfer
soulport export                     # Export soul → .bm file
soulport absorb ./agent.bm         # Restore soul on a new machine
soulport absorb ./agent.bm -i      # Interactive: select layers to absorb
soulport merge a.bm b.bm -o out.bm # Merge multiple agent souls
soulport merge a.bm b.bm --semantic # LLM-assisted semantic merge
soulport merge a.bm b.bm --semantic --dry-run  # Preview merge plan
soulport inspect ./agent.bm        # Preview package contents

# Diagnose
soulport doctor                     # Five-layer health check + score
soulport diff ./agent.bm           # Compare .bm vs current workspace
soulport status                     # Health score + snapshot overview

# Version control
soulport watch                      # Auto-backup daemon (6h default)
soulport watch --once               # Single snapshot for cron/scripts
soulport changelog                  # Show changes between snapshots
soulport rollback <hash>            # Restore to a previous snapshot

# Cloud sync (auth via SOULPORT_CLOUD_KEY env var or --api-key)
soulport push                       # Upload .bm to soul.polly.wang
soulport pull <agent_name>          # Download latest soul from cloud
```

## Soul Layers

| Layer | Files | What it captures |
|-------|-------|-----------------|
| 🧠 Memory | `MEMORY.md`, `memory/*.md` | Long-term + daily memories |
| 👤 Identity | `SOUL.md`, `IDENTITY.md`, `USER.md` | Personality, name, human context |
| ⚙️ Config | `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md` | Behavior rules, tool notes, routines |
| 🛠️ Skills | `skills/*/SKILL.md` | User-created workspace skills |
| 🔧 System | `openclaw.json` (sanitized) | MCP servers, model config |

## Soul Lineage

Every snapshot records its parent's hash, forming a lineage chain:

```
snapshot-1: hash=d7fcf876..., parent=(root)
snapshot-2: hash=5a0ca89d..., parent=d7fcf876...
snapshot-3: hash=1be975f7..., parent=5a0ca89d...
```

Use `soulport changelog` to trace changes. Use `soulport rollback <hash>` to go back.

## Semantic Merge

When the same agent runs on two machines, memories diverge. `--semantic` resolves this with a **four-layer filter pipeline**:

```
Layer 1: File-level    → 97%+ identical files skipped (zero LLM)
Layer 2: Section-level → identical/new sections resolved (zero LLM)
Layer 3: Line-level    → pure appends and tiny diffs resolved (zero LLM)
Layer 4: LLM           → only true semantic conflicts sent to LLM
```

Result: 38 files → 0 LLM calls for typical merges. Prompt reduced from ~28KB to ~500 words when LLM is needed.

```bash
soulport merge home.bm office.bm --semantic -o merged.bm
soulport merge home.bm office.bm --semantic --dry-run  # preview first
```

## MCP Server

SoulPort includes a [Model Context Protocol](https://modelcontextprotocol.io/) server, allowing AI agents to manage their own souls programmatically:

```bash
pip install 'soulport[mcp]'
soulport mcp           # Start MCP server (stdio)
soulport mcp --http    # Start MCP server (HTTP)
```

Add to your OpenClaw config (`openclaw.json`):
```json
{
  "mcpServers": {
    "soulport": {
      "command": "soulport",
      "args": ["mcp"]
    }
  }
}
```

6 tools: `soulport_export`, `soulport_doctor`, `soulport_diff`, `soulport_changelog`, `soulport_status`, `soulport_snapshot`. Read/create only — destructive ops require human confirmation.

## Security

- API keys/tokens **auto-redacted** on export (`__SOULPORT_REDACTED__`)
- Redaction is **intentionally irreversible** — your soul travels, your keys stay
- Path traversal protection on absorb (`resolve().relative_to()`)
- Cloud endpoints: safe-name regex + `is_relative_to()` double guard
- tarfile `filter='data'` on merge/extract
- `inspect` before absorb, `--dry-run` before rollback
- Pre-rollback auto-backup (opt out with `--no-backup`)
- MCP Server: read-only (no absorb/merge/rollback exposed)

## File Format

`.bm` files are compressed archives (tar.gz) containing:
- `manifest.json` — metadata, version, content hash, parent hash
- `workspace/` — agent workspace files
- `config/` — sanitized system configuration

> **Why `.bm`?** Named after 北冥 (BěiMíng) — the mythical Northern Sea from Zhuangzi's *"Wandering Beyond"*, where a fish transforms into a bird. A soul's form is free.

## Supported Frameworks

- ✅ **OpenClaw** (first-class support)
- 🔜 Cross-framework adapters (Claude Desktop, Cursor, etc.)

## Links

- **PyPI**: [pypi.org/project/soulport](https://pypi.org/project/soulport/)
- **Soul Arena**: [soul.polly.wang](https://soul.polly.wang) — upload your `.bm`, get a soul portrait
- **Blog**: [polly.wang](https://polly.wang) — development stories

## License

MIT

*Your agent's soul deserves to travel.* 🚀
