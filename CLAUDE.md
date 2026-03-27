# CLAUDE.md - SoulPort

## Project Overview

AI Agent 灵魂的标准格式与工具链 - 导出、吸收、合并、监控 Agent 的记忆/人格/技能/配置。

核心理念：**`.bm` 是 Agent 灵魂的标准格式，CLI 只是第一个消费者。**

> 为什么是独立工具而不是框架内置功能？SoulPort 不只是迁移--它定义了 Agent 灵魂的跨框架标准。迁移是第一个用例，评估（SoulArena）、融合、版本控制、跨框架互操作是后续用例。这些不该被锁在某一个框架里。

> 前身为"北冥神功 (BeiMingKungFu)"，v0.2.0 起正式更名为 **SoulPort** -- Soul + Port(able)。

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
│   ├── cli.py                    # Click CLI (export/absorb/merge/inspect/doctor)
│   ├── core.py                   # 核心逻辑 (tar.gz 打包/解包/合并)
│   ├── doctor.py                 # 灵魂健康检查 (五层诊断 + 评分)
│   ├── manifest.py               # 包元数据 (manifest.json, 内容哈希)
│   └── scanner.py                # 工作区扫描 (5层文件发现)
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

> `.bm` — originally named after 北冥 (BěiMíng), the mythical Northern Sea from Zhuangzi's *"Wandering Beyond"*, where a fish transforms into a bird. A soul's form is free.

压缩归档 (tar.gz)，包含:
- `manifest.json` — 元数据、版本、来源、内容哈希
- `workspace/` — Agent 工作区文件
- `config/` — 脱敏后的系统配置
- `signature` — 完整性校验

## 相关项目

- **OpenClaw** (`X-Workspace/openclaw/`) - SoulPort 的首要适配目标
- **TideWatch** (`X-Workspace/TideWatch-MCP-Server/`) - 通过 OpenClaw MCP 接入
- **SoulArena** (`X-Workspace/SoulArena/`) - 灵魂竞技场 Web 平台

## Target Users

- **P0: 多机器开发者** - 家/公司/VPS 跑同一个 agent，灵魂需要同步（换电脑不失忆）
- **P1: 框架切换者** - Cursor → OpenClaw、Claude Desktop → Windsurf，不想从零开始
- **P2: Agent 社区贡献者** - 分享带故事的 skill（"这个翻译技能是连续翻译5本书进化出来的"）
- **P3: Agent 爱好者/围观群众** - SoulArena 上传灵魂看画像、排行、PK（轻度用户，传播主力）

## Competitive Landscape

目前无直接竞品。各框架有零散的 import/export（OpenClaw 的 workspace 文件、Cursor 的 .cursorrules），但都是框架锁定的单层文件，没有跨框架标准，没有五层抽象，没有灵魂评估。

最接近的类比是 **dotfiles 管理器**（stow / chezmoi / yadm）--但它们管的是 shell 配置不是 agent 灵魂，没有记忆/人格/技能的语义层。

护城河不在 CLI 代码本身（954行谁都能写），而在：
1. **`.bm` 格式的先发标准** - 第一个定义 agent 灵魂标准格式的人拿走生态位
2. **SoulArena 社交飞轮** - 上传 → 画像 → 分享 → 更多上传，数据壁垒
3. **跨框架适配网络效应** - 支持的框架越多，迁移路径越多，价值越大
4. **LLM-assisted merge（v0.6）** - 语义级灵魂融合，纯工程抄不走

## Success Metrics

| 阶段 | 指标 | 目标 |
|------|------|------|
| v0.2 | PyPI weekly downloads | 100+ |
| v0.4 | SoulArena 灵魂上传数 | 50+ |
| v0.6 | GitHub stars | 200+ |
| v1.0 | 支持框架数 | 3+ |

## Development Process

每个功能实现后需经过 **小龙虾 Review + Baoli 确认** 双重验收：
1. 实现 → 本地测试通过
2. 小龙虾 Code Review（评分 + P0/P1/P2 分级建议）
3. 修复 Review 意见 → 再次确认
4. 合并 + 更新 CLAUDE.md Roadmap

## Roadmap

### v0.1.0 ✅ MVP (2026-03-25) - as BeiMingKungFu
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
- [x] Skill 扫描修复：只统计自定义 skill，不含内置

### v0.2.x - 打磨核心体验
- [x] `soulport doctor` - 灵魂健康检查（五层完整性 + 评分 + 建议 + SoulArena 引流）
- [x] `soulport diff` - absorb 前内容级别差异对比（逐层 +/~/◦ + --full unified diff）
- [ ] 选择性 absorb 交互 - Rich 选择器，逐层勾选
- [ ] 修 P1-4 glob 匹配 - `_matches_pattern` 的 `**` 边界 case 收紧

### v0.3 ✅ 日活基础 (2026-03-27)
- [x] `soulport watch` - 守护进程，自动定期备份（每天/每6h/on-change + skip-if-unchanged）
- [x] 灵魂谱系 (Soul Lineage) - manifest.json `parent_hash` 字段，形成族谱链
- [x] `soulport changelog` - 对比快照，生成灵魂变更日志（逐层摘要 + --full 文件详情）
- [x] `soulport rollback <hash>` - 回滚到指定快照（--dry-run 预览 + --force 执行）

### v0.4 ✅ MCP + 社交 (2026-03-27)
- [x] SoulPort MCP Server - 6 tools (export/doctor/diff/changelog/status/snapshot), FastMCP, stdio+HTTP
- [x] `soulport status` CLI - 健康分 + 快照概览
- [ ] SoulArena PNG 导出 - og:image 社交分享基础设施
- [ ] 灵魂碑片 (Soul Shards) - 按层选择性导出/分享

### v0.5 - 云传输
- [ ] `soulport push` / `soulport pull` — Azure VM 自建，复用 SoulArena FastAPI (soul.polly.wang/api/push + /api/pull)
- [ ] SoulArena 同机直通：push → /data/soulport/{agent_id}/ → SoulArena 直接读取，零网络跳
- [ ] 认证：API Key header（每个 agent 一个 token）
- [ ] 存储 backend 抽象层（LocalStorage），以后可换 R2

### v0.6 - 智能合并（护城河 + 专利核心）
- [ ] LLM-assisted merge - 合并 MEMORY.md 时调 LLM 做语义去重 + 时间线整理
- [ ] Identity fusion - 两个 SOUL.md 合并时 LLM 辅助生成融合人格

### v1.0 - 跨框架
- [ ] Claude Desktop adapter (P0, 用户量最大)
- [ ] Cursor adapter (P1, .cursorrules)
- [ ] `soulport convert --from cursor --to openclaw`
- [ ] .bm 格式版本化 (FORMAT.md, magic bytes, 兼容矩阵)

### 🚀 远期
- [x] **Soul Arena** — Agent 灵魂评估 + 社交平台（`soul.polly.wang`）
- [ ] 灵魂 DNA 指纹 — 基于五维评分+记忆关键词的程序化唯一视觉身份（替代通用雷达图，增强分享卡片辨识度）
- [ ] `soulport resume` — 为 Agent 生成"简历"（经验/技能/性格/亮点，类比人类求职简历）
- [ ] 多 agent 灵魂网络 — A/B/C 记忆技能互通共享（带权限控制）

### 冰箱
- 加密 (`--encrypt`) — 脱敏已兜底凭证泄露，传输链路有 SSH/HTTPS。等企业场景/合规要求再加，不做默认行为
