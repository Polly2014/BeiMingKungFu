# 🚀 SoulPort — Agent Soul Transfer

> *Your agent's soul is portable.*

**SoulPort** is a tool for transferring, merging, and synchronizing AI agent identities across machines. Export your agent's memories, personality, skills, and configuration from one machine, and absorb them into another — instantly.

Think of it as **save/load for AI agents** — Soul + Port(able).

> Previously known as "BeiMingKungFu" (北冥神功). Renamed to SoulPort in v0.2.0 for a more international, intuitive brand.

## Why?

AI agents accumulate value over time — memories, preferences, skills, configurations, personality. But when you set up a new machine, everything resets to zero.

SoulPort solves this. Your agent's soul is portable.

## Quick Start

```bash
pip install soulport

# Export your agent's soul
soulport export

# On another machine, absorb it
soulport absorb ./xiaolongxia-2026-03-25.bm

# Merge multiple agents
soulport merge agent-A.bm agent-B.bm -o merged.bm

# Inspect before absorbing
soulport inspect ./xiaolongxia-2026-03-25.bm
```

## What Gets Transferred?

| Layer | Files | Description |
|-------|-------|-------------|
| 🧠 Memory | `MEMORY.md`, `memory/*.md` | Long-term and daily memories |
| 👤 Identity | `SOUL.md`, `IDENTITY.md`, `USER.md` | Personality, name, human context |
| ⚙️ Config | `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md` | Behavior rules, tool notes, routines |
| 🛠️ Skills | `skills/*/SKILL.md` | Installed workspace skills |
| 🔧 System | `openclaw.json` (sanitized) | MCP servers, model config, plugins |

## Security

- API keys and tokens are **redacted by default** on export
- Optional encryption with `--encrypt` flag
- Sensitive fields are marked and require manual confirmation on absorb
- You always see what's coming in before it takes effect

## Merge Intelligence

When merging two agents, SoulPort handles conflicts intelligently:

- **Memory**: Merged by timeline, deduplicated
- **Identity**: Kept from primary source (or AI-assisted fusion)
- **Config**: Union of capabilities, conflicts flagged for user decision
- **Skills**: Union set, version conflicts resolved

## Supported Agent Frameworks

- ✅ **OpenClaw** (first-class support)
- 🔜 More frameworks via adapter plugins

## File Format

SoulPort packages are `.bm` files — a compressed archive containing:
- `manifest.json` — metadata, version, source info, content hash
- `workspace/` — the agent's workspace files
- `config/` — sanitized system configuration
- `signature` — integrity verification

## License

MIT

---

*Your agent's soul deserves to travel.* 🚀
