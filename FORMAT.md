# .bm Format Specification

> Version: 1  
> Status: Living Document  
> Last Updated: 2026-03-30  

## Overview

`.bm` is the standard portable format for AI agent cognitive state — memory, personality, skills, configuration, and system settings packaged into a single transferable archive.

> The name `.bm` comes from 北冥 (BěiMíng), the mythical Northern Sea from Zhuangzi's *"Wandering Beyond"*, where a fish transforms into a bird that soars across the sky. An agent's soul should be equally free to move between forms.

## File Structure

A `.bm` file is a **gzip-compressed tar archive** (`.tar.gz`) with a fixed internal layout:

```
<agent-name>-<date>.bm
├── manifest.json           # REQUIRED — package metadata
├── workspace/              # Agent workspace files, organized by layer
│   ├── SOUL.md             #   identity layer
│   ├── IDENTITY.md         #   identity layer
│   ├── USER.md             #   identity layer
│   ├── MEMORY.md           #   memory layer
│   ├── memory/             #   memory layer (subdirectories)
│   │   └── 2026/
│   │       └── 0330.md
│   ├── AGENTS.md           #   config layer
│   ├── TOOLS.md            #   config layer
│   ├── HEARTBEAT.md        #   config layer
│   └── skills/             #   skills layer
│       ├── translate/
│       │   └── SKILL.md
│       └── coding/
│           └── SKILL.md
├── config/                 # OPTIONAL — sanitized system config
│   └── openclaw.json       #   API keys replaced with __SOULPORT_REDACTED__
└── signature               # RESERVED — future integrity verification
```

## manifest.json Schema

```jsonc
{
  // ── Format ──
  "version": "1",                        // manifest schema version (string)
  "soulport_version": "0.6.1",           // SoulPort tool version that created this package

  // ── Source ──
  "agent_name": "小龙虾",                // agent's display name
  "source_host": "pollys-macbook",       // hostname where exported
  "source_framework": "openclaw",        // originating agent framework
  "source_workspace": "/path/to/ws",     // original workspace path (informational)

  // ── Timestamps ──
  "exported_at": "2026-03-30T12:00:00+00:00",  // ISO 8601 UTC

  // ── Content ──
  "layers": [
    {
      "name": "identity",                // layer name (see Five-Layer Model)
      "description": "Agent personality, name, and human context",
      "files": ["SOUL.md", "IDENTITY.md", "USER.md"],
      "file_count": 3,
      "total_bytes": 4096
    }
    // ... more layers
  ],

  // ── Security ──
  "redacted_fields": [                   // JSON paths that were sanitized
    "mcpServers.tidewatch.env.API_KEY",
    "apiKey"
  ],
  "content_hash": "abcdef1234567890...",    // SHA-256 hex digest (no algorithm prefix)
  "encrypted": false,                    // reserved for future use

  // ── Lineage ──
  "parent_hash": "1234567890abcdef...",     // content_hash of previous export (Soul Lineage)
  "merge_parents": [],                   // content_hashes of merge sources (DAG)
  "merge_strategy": ""                   // "" | "file" | "semantic"

  // ── Soul Shards ──
  "selected_layers": []                  // non-empty = Soul Shard (e.g. ["skills"])
}
```

### Field Requirements

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `version` | Yes | `"1"` | Schema version. Consumers MUST reject unknown major versions. |
| `soulport_version` | Yes | — | Tool version, for compatibility diagnostics |
| `agent_name` | Yes | — | Display name. May contain emoji and Unicode. |
| `source_host` | No | `""` | Informational only |
| `source_framework` | No | `"openclaw"` | Adapter identifier for cross-framework import |
| `exported_at` | Yes | — | ISO 8601 timestamp |
| `layers` | Yes | `[]` | May be empty (e.g. Soul Shards with no matching files) |
| `redacted_fields` | No | `[]` | Dot-notation JSON paths of sanitized secrets |
| `content_hash` | Yes | — | SHA-256 hex digest of the .bm file itself |
| `parent_hash` | No | `""` | Empty if first export; set by `soulport export` |
| `merge_parents` | No | `[]` | Set by `soulport merge`; forms a DAG |
| `merge_strategy` | No | `""` | `"file"` for basic merge, `"semantic"` for LLM-assisted |
| `encrypted` | No | `false` | Reserved. No encryption implemented yet. |
| `selected_layers` | No | `[]` | Non-empty marks the package as a Soul Shard. Lists the layer names that were explicitly selected during export. |

## Five-Layer Model

Every agent cognitive state is decomposed into five semantic layers:

| Layer | Name | Typical Files | Purpose |
|-------|------|---------------|---------|
| 🧠 | **memory** | `MEMORY.md`, `memory/**/*.md` | Long-term memory, daily journals, learned facts |
| 👤 | **identity** | `SOUL.md`, `IDENTITY.md`, `USER.md` | Personality, values, human context |
| ⚙️ | **config** | `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md` | Behavioral rules, tool usage notes, routines |
| 🛠️ | **skills** | `skills/*/SKILL.md` | Installed domain-specific skills |
| 🔧 | **system** | `config/openclaw.json` | MCP servers, model config (sanitized) |

### Layer Classification Rules

Files are classified into layers by glob pattern matching:

```
identity:  SOUL.md, IDENTITY.md, USER.md
memory:    MEMORY.md, memory/**/*.md, memory/**/*.json
config:    AGENTS.md, TOOLS.md, HEARTBEAT.md
skills:    skills/**/SKILL.md, skills/**/*
projects:  (catch-all for remaining files, excluded by default)
```

The `system` layer is special — it's not scanned from the workspace directory but extracted from the framework's configuration file (e.g. `openclaw.json`) and stored under `config/` in the archive.

## Soul Shards

A **Soul Shard** is a `.bm` package that contains only selected layers. It uses the exact same format — the only difference is that `layers` contains a subset.

```bash
# Export only skills (for sharing)
soulport export --layers skills -o my-skills.bm

# Export identity + memory (for backup)
soulport export -l identity -l memory -o personal.bm
```

Shards are fully compatible with `absorb`, `inspect`, `diff`, and `merge`.

## Security Model

### Credential Redaction

During export, all values matching sensitive key patterns (`token`, `apiKey`, `api_key`, `secret`, `password`, `credential`, `X-API-Key`) are replaced with the literal string:

```
__SOULPORT_REDACTED__
```

This is **irreversible by design**. The philosophy: *souls migrate, keys don't.* New credentials should be configured on the destination machine.

### Path Safety

- `absorb` validates that all extracted paths resolve within the target workspace (`resolve().relative_to()`)
- `merge` uses `extractall(filter='data')` to prevent tar path traversal attacks
- Cloud endpoints use `safe_name` regex + `is_relative_to()` double guard

## Lineage

Each `.bm` package records its ancestry:

- **`parent_hash`**: The `content_hash` of the previous export from the same workspace, forming a linear chain.
- **`merge_parents`**: When two packages are merged, both source hashes are recorded, forming a DAG (directed acyclic graph).
- **`merge_strategy`**: Whether the merge used file-level (`"file"`) or LLM-assisted semantic (`"semantic"`) reconciliation.

```
export₁ ──→ export₂ ──→ export₃
                              ↘
                               merge₁ ──→ export₄
                              ↗
         export_A ──→ export_B
```

## Compatibility

### Version Negotiation

The `version` field uses integer versioning (as a string). Rules:

- **Same major version**: Fully compatible. New optional fields may be added without bumping the version.
- **Higher major version**: Consumer SHOULD warn but MAY attempt best-effort parsing.
- **Lower major version**: Always compatible (forward compatibility guaranteed).

Minor additions (e.g. new optional fields like `selected_layers`) do NOT change the version number. Version bumps are reserved for breaking structural changes only.

### Framework Adapters

The `source_framework` field identifies which agent framework created the package. Adapters translate framework-specific file layouts into the five-layer model:

| Framework | `source_framework` | Status |
|-----------|-------------------|--------|
| OpenClaw | `"openclaw"` | ✅ Native support |
| Claude Desktop | `"claude-desktop"` | 🔜 Planned (v1.0) |
| Cursor | `"cursor"` | 🔜 Planned (v1.0) |

Cross-framework conversion: `soulport convert --from cursor --to openclaw` (planned).

## MIME Type

Recommended: `application/x-soulport+gzip`

File extension: `.bm`
