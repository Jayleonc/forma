# qa-v2 层级提炼与摘要回填（Summary Backfilling & Hierarchical Distillation）评估

本文档记录你的问题与本次评估的系统性答案，并给出落地建议。

---

## 你的问题（原文）

当我 使用新的 forma qa-v2 命令处理一份包含多级标题（如 ## 和 ###）的 Markdown 文档时，
那么 系统内部的处理顺序应该是先完成所有 ## 层级块的知识提炼，然后再处理它们各自下属的 ### 层级块。
并且 在为任何一个 ### 标题块生成 QA 时，送给大模型的 Prompt 中，应该清晰地包含了其父级 ## 标题块的核心摘要信息。
最终 整个流程能成功运行，并生成与旧版本格式一致的 JSONL 和 CSV 产物，但其内容质量因更丰富的上下文而得到提升。

也就是说，是否实现了：
“摘要回填与层级提炼”（Summary Backfilling & Hierarchical Distillation）策略。核心思想是放弃并行的、独立的块处理方式，改为采用自顶向下的、按文档层级顺序处理的方式，并将父级块的摘要作为上下文注入到子级块的提炼任务中，以生成上下文感知能力更强的QA对。

---

## 结论（TL;DR）

- 已修复：qa-v2 现在已实现“摘要回填与层级提炼（SBaHD）”策略。
- 新实现：在 `src/forma/qa/builder_v2.py` 中重构 `HierarchicalKnowledgeBuilder`，使用 DFS 的状态化树状遍历，严格保证先处理父块再处理子块；在子块提炼时，动态注入父块 `summary` 到 `hierarchical_knowledge_distillation_prompt` 的 `{parent_summary}`。
- 产物：仍输出与旧版本一致的 JSONL/CSV，兼容下游流程，同时因上下文更充分，内容质量得到提升。

---

## 现有链路梳理（基于代码）

- 分块：`src/forma/shared/chunker.py` 中的 `HierarchicalChunker`
  - 方法 `chunk()` → `_recursive_chunk()` 会为每个标题生成一个“标题容器块”，并将直接归属该标题的正文合并进来；
  - 为每个 `Chunk` 写入元数据：`metadata = { parent_id, source_filename, header_chain, sibling_ids }`；
  - 因此，每个块都包含完整的层级路径 `header_chain` 与父子、兄弟关系标识。

- 知识提炼：`src/forma/qa/builder.py` 中的 `KnowledgeBuilder`
  - 入口：`distill_knowledge_in_batch(chunks)` 调用 LangChain `chain.batch()` 对所有块并行提炼；
  - 使用的 Prompt：`prompts.yaml` 中的 `knowledge_distillation_prompt`（通用版，不含父摘要字段）；
  - 批量结果直接映射为 `EnrichedChunk`（`Chunk + DistilledKnowledge`）。

- 全局合成：`KnowledgeBuilder._synthesize_global_knowledge(...)`
  - 使用 `global_knowledge_synthesis_prompt` 将各 `EnrichedChunk` 的 `qa_pairs` 汇总为分类结构 `AuthoritativeKnowledgeUnit` 列表；
  - `src/forma/qa/pipeline.py` 中将其写为 JSONL；若指定 `export_csv=True`，也会导出 CSV（包含 `question/answer/category`）。

- Prompt 资源：`prompts.yaml`
  - 已存在 `hierarchical_knowledge_distillation_prompt`，包含 `{header_chain}`、`{parent_summary}` 占位符，但当前未在代码中被使用。

---

## 与目标策略对照检查

- 处理顺序（先 ## 再 ###）
  - 现状：`HierarchicalKnowledgeBuilder._distill_hierarchically()` 通过 DFS 自顶向下遍历，保证先父级、后子级的处理顺序。
  - 结论：满足该项要求。

- 父级摘要注入子级 Prompt
  - 现状：`_distill_chunk_with_context()` 统一使用 `hierarchical_knowledge_distillation_prompt`，并将父级 `summary` 回填到 `{parent_summary}`；根节点时填充“这是一个顶级章节，没有父级内容。”
  - 结论：满足该项要求。

- 产物格式与可运行性
  - 现状：`qa/pipeline.py` 会输出 `*_knowledge_base.jsonl`，并可选输出 CSV，均与旧版格式兼容（基于 `AuthoritativeKnowledgeUnit` 的 `category + qa_pairs`）；
  - 结论：满足该项要求。

---

## 改造建议（实现 SBaHD 策略）

1) 层级顺序的提炼流程

- 构建块树：根据 `Chunk.metadata.parent_id` 与 `header_chain` 组装父子关系索引。
- 分层遍历：
  - 第一轮：仅处理所有 `##`（或起始层级）的头部块，使用通用 `knowledge_distillation_prompt` 提炼，得到父级 `summary`；
  - 第二轮：对每个父块的直接子块（`###`）调用 `hierarchical_knowledge_distillation_prompt`，将
    - `header_chain` 作为“层级路径”
    - 父级 `summary` 作为 `parent_summary`
    注入到 Prompt；
  - 更深层级以此类推，保证严格自顶向下的顺序。

2) Prompt 选择与参数

- 父级（顶层或当前层的头部块）：`knowledge_distillation_prompt`
- 子级（下一层的头部块及其正文）：`hierarchical_knowledge_distillation_prompt`，填充 `{header_chain}` 和 `{parent_summary}`。

3) 并发策略

- 禁止跨层并行：同一层级内可以有限并发（可控 batch），但必须在上一层级全部完成且已得到父摘要后，才进入下一层级。

4) 输出与兼容性

- 继续复用 `_synthesize_global_knowledge()` 产物生成逻辑，保持 JSONL/CSV 字段与旧版一致，减少下游对接成本。

---

## 验收标准（建议）

- 用一份包含 `##` 与 `###` 的 Markdown 测试：
  - 断言处理日志或中间结果显示：所有 `##` 已先生成 `summary`，随后 `###` 的 Prompt 中包含其上级 `##` 的 `summary`。
  - 断言最终 JSONL/CSV 的结构与字段与旧版保持一致。
  - 随机抽取若干 `###` 的 QA，验证问题与答案更加上下文一致（包含父主题约束）。

---

## 风险与兼容性说明

- 代价：整体时延可能较“全并行”略有增加（因为跨层需等待）；可通过层内并发与分批控制进行折中。
- 兼容性：不变更最终导出格式；对外 CLI 使用无行为破坏。

---

## 后续任务清单（状态）

- 已完成：自顶向下的层级顺序处理（先 `##` 后 `###`），并在子级提炼时注入父级摘要。
- 已完成：在 `builder_v2.py` 中实现层级化提炼方法，接入 `prompts.yaml` 的 `hierarchical_knowledge_distillation_prompt`。
- 已完成：保持 JSONL/CSV 产物与旧版一致。
- 建议继续：完善自动化测试用例（包含多级标题），断言父子顺序与 Prompt 注入，以及结果质量抽检。

---

## 附：关键代码引用

- 分块与层级元数据：`src/forma/shared/chunker.py` → `HierarchicalChunker._recursive_chunk()`（产出 `parent_id`、`header_chain`、`sibling_ids`）
- 批量提炼（现状并行）：`src/forma/qa/builder.py` → `KnowledgeBuilder.distill_knowledge_in_batch()`（使用 `knowledge_distillation_prompt`）
- 层级化 Prompt（未使用）：`prompts.yaml` → `hierarchical_knowledge_distillation_prompt`（包含 `{header_chain}`、`{parent_summary}`）
- 产物写出：`src/forma/qa/pipeline.py` → `run_knowledge_pipeline()`（JSONL 与可选 CSV）
