# CLAUDE.md — 北冥神功 (BeiMingKungFu)

## Project Overview

AI Agent 灵魂迁移工具 — 导出、吸收、合并 Agent 的记忆/人格/技能/配置。

核心理念：**AI Agent 换电脑不该失忆，灵魂应该是可移植的。**

命名灵感：吸星大法粗暴 copy 有冲突，北冥神功自然融合无副作用。

## Commands

```bash
cd X-Workspace/BeiMingKungFu
pip install -e .              # 本地安装

beiming export                # 导出当前 Agent 灵魂 → .bm 文件
beiming absorb ./xxx.bm       # 在新机器还原灵魂
beiming merge a.bm b.bm -o merged.bm  # 合并多个 Agent 灵魂
beiming inspect ./xxx.bm      # 预览包内容（不执行）
```

## Architecture

```
BeiMingKungFu/
├── pyproject.toml            # Hatchling 打包 + CLI 入口
├── beiming/
│   ├── __init__.py           # 版本号
│   ├── cli.py                # Click CLI (273行, export/absorb/merge/inspect)
│   ├── core.py               # 核心逻辑 (374行, tar.gz 打包/解包/合并)
│   ├── manifest.py           # 包元数据 (manifest.json, 内容哈希)
│   └── scanner.py            # 工作区扫描 (209行, 5层文件发现)
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

- API Key/Token 导出时自动脱敏 (`__BEIMING_REDACTED__`)
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

- **OpenClaw** (`X-Workspace/openclaw/`) — BeiMing 的首要适配目标
- **TideWatch** (`X-Workspace/TideWatch-MCP-Server/`) — 通过 OpenClaw MCP 接入
