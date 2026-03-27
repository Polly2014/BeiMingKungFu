# Four-Layer Semantic Merge Pipeline

> Architecture design for SoulPort v0.6.1 — strengthens Patent Claim Group E

---

## Problem

v0.6 的 `semantic_merge.py` 和已有的 diff 基础设施（`diff_packages()`, `_text_diff()`）完全平行，没有交集。语义合并自己重新实现了文件比较和层分类，而已有能力被浪费了。

更关键的：**LLM 介入时机太早**。当前逻辑是"section 级不同就整段扔 LLM"，但大部分 section 差异是纯追加或微调——根本不需要语义理解。

## Solution: Four-Layer Filter Pipeline

```
Layer 1: File-Level (diff_packages)
  ├── added     → keep (零 LLM)
  ├── removed   → keep (零 LLM)
  ├── unchanged → keep (零 LLM)
  └── modified  → Layer 2

Layer 2: Section-Level (_split_sections)
  ├── identical section    → keep (零 LLM)
  ├── only-in-A / only-in-B → append (零 LLM)
  └── both-modified        → Layer 3

Layer 3: Line-Level (_text_diff / difflib)
  ├── pure append (B is superset of A) → keep B (零 LLM)
  ├── tiny diff (< 5 lines changed)    → keep B (零 LLM)
  ├── medium diff                       → LLM with unified diff (小 prompt)
  └── large diff (> 50% changed)        → LLM with both versions (大 prompt)

Layer 4: LLM Semantic Merge
  Input:  unified diff + version B (medium) OR both versions (large)
  Output: merged section + merge note comment
```

## Why This Matters

### For Users
- 99% 的场景零 LLM 调用 → 瞬间完成
- 只有真正的语义冲突才等 LLM → 更快、更便宜
- merge note 精确到行级 → 审计更方便

### For Patent (Claim Group E)
当前 Claim 13 描述的是"用 LLM 合并记忆"——太宽泛，prior art 容易挑战（任何人都可以说"我也用 LLM 合并"）。

四层过滤是 **novel 的方法**：
- 每层是一个独立的决策算法
- 层与层之间有明确的过滤关系
- LLM 只是最后一层的执行者，不是整个方法的核心
- "结构化过滤 + 语义兜底" 这个组合方式是新的

建议修改 Claim 13 为：
> "A method for merging divergent cognitive states comprising a multi-layer filter pipeline where structural diff at file, section, and line granularity progressively eliminates cases that don't require semantic understanding, with a language model invoked only for the residual conflicts that survive all structural filters."

### For Implementation
- 复用 `diff_packages()` + `_text_diff()` 已有代码
- 减少 `semantic_merge.py` 的重复逻辑
- LLM prompt 从 ~20KB 缩小到 ~500 字（unified diff）
- CopilotX gateway 120s 超时不再是问题

## Layer Interaction

```
                    38 files in two .bm packages
                              │
                    ┌─────────┴─────────┐
           Layer 1: diff_packages()
                    │
           37 identical          1 modified (MEMORY.md)
           (skip)                    │
                              ┌──────┴──────┐
                     Layer 2: _split_sections()
                              │
                    12 identical    3 only-B    1 both-modified
                    sections       (append)     section
                                                │
                                         ┌──────┴──────┐
                                Layer 3: _text_diff()
                                         │
                                    +3 lines added   conflict: 5 lines
                                    (keep B)         changed differently
                                                          │
                                                   Layer 4: LLM
                                                   "这 5 行有语义冲突，
                                                    请根据 diff 合并"
```

**结果：38 files → 1 LLM 调用，prompt 仅 ~500 字。**

## Implementation TODO

1. `semantic_merge_packages()` 调用 `diff_packages()` 做 Layer 1
2. Layer 3 新增行级分析函数 `_classify_diff()`
3. LLM prompt 改为接收 unified diff 而不是两个完整文本
4. 更新 PATENT-DRAFT.md Claim 13

---

_Created: 2026-03-27 | Source: 保利 × 小龙虾 × 数字保利 三方深度讨论_
