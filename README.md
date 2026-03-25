# 🌊 Beiming — Agent Soul Transfer

> *"北冥有鱼，其名为鲲。鲲之大，不知其几千里也。化而为鸟，其名为鹏。"*
> — 《庄子·逍遥游》

**Beiming** (北冥) is a tool for transferring, merging, and synchronizing AI agent identities across machines. Export your agent's memories, personality, skills, and configuration from one machine, and absorb them into another — instantly.

Think of it as **save/load for AI agents**, or in wuxia terms: the legendary **Beiming Divine Skill** (北冥神功) that absorbs others' inner power and makes it your own.

## Why?

AI agents accumulate value over time — memories, preferences, skills, configurations, personality. But when you set up a new machine, everything resets to zero.

Beiming solves this. Your agent's soul is portable.

## Quick Start

```bash
pip install beiming

# Export your agent's soul
beiming export

# On another machine, absorb it
beiming absorb ./xiaolongxia-2026-03-25.bm

# Merge multiple agents
beiming merge agent-A.bm agent-B.bm -o merged.bm

# Inspect before absorbing
beiming inspect ./xiaolongxia-2026-03-25.bm
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

When merging two agents, Beiming handles conflicts intelligently:

- **Memory**: Merged by timeline, deduplicated
- **Identity**: Kept from primary source (or AI-assisted fusion)
- **Config**: Union of capabilities, conflicts flagged for user decision
- **Skills**: Union set, version conflicts resolved

## Supported Agent Frameworks

- ✅ **OpenClaw** (first-class support)
- 🔜 More frameworks via adapter plugins

## File Format

Beiming packages are `.bm` files — a compressed archive containing:
- `manifest.json` — metadata, version, source info, content hash
- `workspace/` — the agent's workspace files
- `config/` — sanitized system configuration
- `signature` — integrity verification

## License

MIT

---

*Absorb the wisdom of a thousand agents. Become the Kunpeng.* 🐋➡️🦅
