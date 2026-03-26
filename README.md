# 🚀 SoulPort — Agent Soul Transfer

> **`.bm` is the standard format for AI agent souls. The CLI is just the first consumer.**

SoulPort defines a cross-framework standard for AI agent identities — memories, personality, skills, configuration. Export from one machine, absorb into another, watch for changes, rollback when needed.

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
soulport merge a.bm b.bm -o out.bm # Merge multiple agent souls
soulport inspect ./agent.bm        # Preview package contents

# Diagnose
soulport doctor                     # Five-layer health check + score
soulport diff ./agent.bm           # Compare .bm vs current workspace

# Version control
soulport watch                      # Auto-backup daemon (6h default)
soulport watch --once               # Single snapshot for cron/scripts
soulport changelog                  # Show changes between snapshots
soulport rollback <hash>            # Restore to a previous snapshot
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

## Security

- API keys/tokens **auto-redacted** on export (`__SOULPORT_REDACTED__`)
- Path traversal protection on absorb (`resolve().relative_to()`)
- tarfile `filter='data'` on merge/extract
- `inspect` before absorb, `--dry-run` before rollback
- Pre-rollback auto-backup (opt out with `--no-backup`)

## File Format

`.bm` files are compressed archives (tar.gz) containing:
- `manifest.json` — metadata, version, content hash, parent hash
- `workspace/` — agent workspace files
- `config/` — sanitized system configuration

> **Why `.bm`?** Named after 北冥 (BěiMíng) — the mythical Northern Sea from Zhuangzi's *"Wandering Beyond"*, where a fish transforms into a bird. A soul's form is free.

## Supported Frameworks

- ✅ **OpenClaw** (first-class support)
- 🔜 Claude Desktop, Cursor, Windsurf via adapters

## Links

- **PyPI**: [pypi.org/project/soulport](https://pypi.org/project/soulport/)
- **Soul Arena**: [soul.polly.wang](https://soul.polly.wang) — upload your `.bm`, get a soul portrait
- **Blog**: [polly.wang](https://polly.wang) — development stories

## License

MIT

*Your agent's soul deserves to travel.* 🚀
