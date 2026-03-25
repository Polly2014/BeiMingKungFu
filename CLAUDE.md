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

## Roadmap

### v0.1.0 ✅ MVP (2026-03-25)
- [x] export / absorb / merge / inspect 四件套
- [x] 灵魂五层架构（Identity/Memory/Config/Skills/System）
- [x] API Key 自动脱敏 (`__BEIMING_REDACTED__`)
- [x] Manifest SHA256 完整性校验
- [x] 小龙虾 Review P0+P1 安全修复 (8.5→9.0)
- [x] PyPI 发布：`pip install beimingkungfu`

### v0.2 — 打磨核心体验
- [ ] `beiming diff` — absorb 前内容级别差异对比（不只是文件列表）
- [ ] 选择性 absorb 交互 — Rich 选择器，逐层勾选，冲突逐个 diff
- [ ] 修 P1-4 glob 匹配 — `_matches_pattern` 的 `**` 边界 case 收紧

### v0.3 — 加密
- [ ] `--encrypt` 回归 — `cryptography.Fernet` 对称加密，passphrase 派生密钥

### v0.4 — 智能合并（护城河）
- [ ] LLM-assisted merge — 合并 MEMORY.md 时调 LLM 做语义去重 + 时间线整理
- [ ] Identity fusion — 两个 SOUL.md 合并时 LLM 辅助生成融合人格（需人类确认）
- 这才是"北冥神功"的真正内涵：不是粗暴 copy，是自然融合

### v0.5 — 生态
- [ ] Framework adapters — 插件化适配 Claude Desktop / Cursor / Windsurf 等
- [ ] `beiming registry` — 公共 skill 市场基础设施（skills 层单独发布）
- [ ] 增量导出（delta）— 类似 git pack，不每次全量

### 🌊 远期 — 灵魂竞技场
- [ ] **Soul Arena** — Agent 灵魂趣味评估 + PK 平台（Azure VM 部署）
  - 上传 .bm 文件 → 自动分析灵魂特征（记忆量/技能树/人格倾向/活跃度）
  - 灵魂 PK：两个 Agent 的灵魂对比 → 雷达图 + 趣味点评（LLM 生成）
  - 排行榜：最博学 / 技能最多 / 记忆最深 / 最有个性
  - Web 前端 + 后端 API（可复用 TideWatch 的 Azure VM）
- [ ] 多 agent 灵魂网络 — A/B/C 记忆技能互通共享（带权限控制）
- [ ] 灵魂版本控制 — `beiming checkpoint` + `beiming rollback`

### 冰箱
- 云传输（push/pull/QR）— 需要后端基础设施，等有用户量再做
- 雪球式 Agent 成长追踪 — 定期 export 自动对比成长曲线
