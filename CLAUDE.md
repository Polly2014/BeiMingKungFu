# CLAUDE.md — SoulPort

## Project Overview

AI Agent 灵魂迁移工具 — 导出、吸收、合并 Agent 的记忆/人格/技能/配置。

核心理念：**AI Agent 换电脑不该失忆，灵魂应该是可移植的。**

> 前身为"北冥神功 (BeiMingKungFu)"，v0.2.0 起正式更名为 **SoulPort** —— Soul + Port(able)，更国际化、更直觉。

## Commands

```bash
cd X-Workspace/SoulPort
pip install -e .                # 本地安装

soulport export                 # 导出当前 Agent 灵魂 → .bm 文件
soulport absorb ./xxx.bm       # 在新机器还原灵魂
soulport merge a.bm b.bm -o merged.bm  # 合并多个 Agent 灵魂
soulport inspect ./xxx.bm      # 预览包内容（不执行）
```

## Architecture

```
SoulPort/                         # (原 BeiMingKungFu/)
├── pyproject.toml                # Hatchling 打包 + CLI 入口
├── soulport/                     # (原 beiming/)
│   ├── __init__.py               # 版本号
│   ├── cli.py                    # Click CLI (273行, export/absorb/merge/inspect)
│   ├── core.py                   # 核心逻辑 (374行, tar.gz 打包/解包/合并)
│   ├── manifest.py               # 包元数据 (manifest.json, 内容哈希)
│   └── scanner.py                # 工作区扫描 (209行, 5层文件发现)
└── README.md
```

总代码量: ~954 行，4 个核心文件。

## 灵魂五层结构

| 层 | 文件 | 说明 |
|----|------|------|
| 🧠 Memory | `MEMORY.md`, `memory/*.md` | 长期记忆 + 日记 |
| 👤 Identity | `SOUL.md`, `IDENTITY.md`, `USER.md` | 人格、名字、人类上下文 |
| ⚙️ Config | `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md` | 行为规则、工具笔记 |
| 🛠️ Skills | `skills/*/SKILL.md` | 已安装的 Skill |
| 🔧 System | `openclaw.json` (脱敏) | MCP servers、模型配置 |

## 安全

- API Key/Token 导出时自动脱敏 (`__SOULPORT_REDACTED__`)
- absorb 路径校验（`resolve().relative_to()` 防 path traversal）
- merge 使用 `extractall(filter='data')` 防 tarfile 路径穿越
- absorb 前可 inspect 预览，确认后才生效
- export 完成后显示被脱敏的字段列表

## 支持的 Agent 框架

- ✅ OpenClaw (一等公民支持)
- 🔜 更多框架通过 adapter 插件

## .bm 文件格式

压缩归档 (tar.gz)，包含:
- `manifest.json` — 元数据、版本、来源、内容哈希
- `workspace/` — Agent 工作区文件
- `config/` — 脱敏后的系统配置
- `signature` — 完整性校验

## 相关项目

- **OpenClaw** (`X-Workspace/openclaw/`) — SoulPort 的首要适配目标
- **TideWatch** (`X-Workspace/TideWatch-MCP-Server/`) — 通过 OpenClaw MCP 接入
- **SoulArena** (`X-Workspace/SoulArena/`) — 灵魂竞技场 Web 平台

## Roadmap

### v0.1.0 ✅ MVP (2026-03-25) — as BeiMingKungFu
- [x] export / absorb / merge / inspect 四件套
- [x] 灵魂五层架构（Identity/Memory/Config/Skills/System）
- [x] API Key 自动脱敏 (`__BEIMING_REDACTED__`)
- [x] Manifest SHA256 完整性校验
- [x] 小龙虾 Review P0+P1 安全修复 (8.5→9.0)
- [x] PyPI 发布：`pip install beimingkungfu`

### v0.2.0 ✅ Rename + Polish (2026-03-26)
- [x] 品牌重命名：BeiMingKungFu → SoulPort
- [x] PyPI 新包：`pip install soulport`
- [x] CLI 命令：`beiming` → `soulport`
- [x] 脱敏标记：`__SOULPORT_REDACTED__`
- [ ] `soulport diff` — absorb 前内容级别差异对比
- [ ] 选择性 absorb 交互 — Rich 选择器，逐层勾选
- [ ] 修 P1-4 glob 匹配 — `_matches_pattern` 的 `**` 边界 case 收紧

### v0.3 — 加密
- [ ] `--encrypt` 回归 — `cryptography.Fernet` 对称加密，passphrase 派生密钥

### v0.4 — 智能合并（护城河）
- [ ] LLM-assisted merge — 合并 MEMORY.md 时调 LLM 做语义去重 + 时间线整理
- [ ] Identity fusion — 两个 SOUL.md 合并时 LLM 辅助生成融合人格（需人类确认）
- 核心差异化：不是粗暴 copy，是自然融合

### v0.5 — 生态
- [ ] Framework adapters — 插件化适配 Claude Desktop / Cursor / Windsurf 等
- [ ] `soulport registry` — 公共 skill 市场基础设施（skills 层单独发布）
- [ ] 增量导出（delta）— 类似 git pack，不每次全量

### 🚀 远期 — 灵魂竞技场
- [x] **Soul Arena** — Agent 灵魂趣味评估 + PK 平台（`soul.polly.wang`）
- [ ] 多 agent 灵魂网络 — A/B/C 记忆技能互通共享（带权限控制）
- [ ] 灵魂版本控制 — `soulport checkpoint` + `soulport rollback`

### 冰箱
- 云传输（push/pull/QR）— 需要后端基础设施，等有用户量再做
- 雪球式 Agent 成长追踪 — 定期 export 自动对比成长曲线
