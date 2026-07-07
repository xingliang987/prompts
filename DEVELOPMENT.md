# DEVELOPMENT.md - prompts 项目开发记录

## 项目说明

本目录存放 VS Code / GitHub Copilot 的自定义提示词配置（instructions、skills、prompt 模板等）。

---

## 操作记录

### 2026-07-02 — 修改 project-takeover SKILL：TAKEOVER 改为常规 .md 并移至项目根目录

- **操作目的**：将 TAKEOVER 产出物从 `.github/instructions/TAKEOVER.instructions.md` 改为项目根目录的 `TAKEOVER.md`（常规 Markdown 文件），不再放入 `.github/instructions/` 目录。
- **操作方法**：修改 `.agents/skills/project-takeover/SKILL.md`，更新所有涉及 TAKEOVER 路径和文件名的引用（YAML 描述、功能说明、核心原则、文件产出清单、第 3/5/6 步、质量检查清单等），保持 INFORMATION 不变。
- **变更要点**：
  - `TAKEOVER.instructions.md` → `TAKEOVER.md`
  - `接管信息.instructions.md` → `接管信息.md`
  - 路径从 `.github/instructions/` → 项目根目录
  - 文件产出清单树形结构调整，TAKEOVER 移出 `.github/instructions/` 层级

### 2026-07-02 — 简化「远程开发指南.instructions.md」

- **操作目的**：将远程开发指南大幅精简，保留核心原则与工作流主干，去除过多细节规则与示范。
- **操作方法**：用 PowerShell 重写 `.github/instructions/远程开发指南.instructions.md`，将其从 ~260 行细节规则压缩为 ~60 行的原则总纲 + 工作流骨架。所有详细规则、命令示例、PowerShell 转义备忘等完整内容保留在 `.agents/skills/remote-dev/SKILL.md` 中。
- **变更要点**：
  - 保留：核心原则（5 条）、7 步工作流主干、模式 A/B 定义、关键行为红线（5 条）
  - 移除：详细的子规则展开、终端卡死处理完整流程表格、PowerShell 转义详细示例、SSH 免密配置流程、信息缺失处理分类等
  - 新增：文件头引用声明，指向 `remote-dev` SKILL 获取完整内容

### 2026-07-02 — 修复两个 .instructions.md 文件的 UTF-8 BOM 编码问题

- **操作目的**：修复 `代码示范.instructions.md` 和 `远程开发指南.instructions.md` 因 UTF-8 BOM 编码导致 YAML 前置元数据无法被 VS Code 解析的问题，使它们能正确自动载入上下文。
- **操作方法**：使用 PowerShell 读取文件字节，检测并去除开头的 BOM 头（`EF BB BF`），然后用无 BOM 的 UTF-8 重写文件。
- **变更文件**：
  - `代码示范.instructions.md`：UTF-8 BOM → UTF-8 no BOM
  - `远程开发指南.instructions.md`：UTF-8 BOM → UTF-8 no BOM
- **效果**：去除 BOM 后，VS Code 能正确解析 YAML 前置元数据中的 `description` 和 `applyTo` 字段，系统自动载入机制将能匹配并加载这两个文件。

### 2026-07-03 — 新增终端复用规则到「AI agent 通用要求.instructions.md」

- **操作目的**：添加一条强制性规则，要求 AI agent 在同一任务下优先使用 `run_in_terminal` 的 `mode="async"` 模式，并尽量复用已创建的终端，避免为每条命令打开新终端。
- **操作方法**：在 `AI agent 通用要求.instructions.md` 的 `vscode_askQuestions` 规则之后、项目文件列表之前插入新的规则项。
- **变更文件**：`AI agent 通用要求.instructions.md`
- **规则内容**：同一任务下优先使用 `mode="async"`，复用已有终端，保持终端环境和工作目录的连续性。

### 2026-07-03 — 新增 RemoteInfoCollector 自定义 agent

- **操作目的**：创建一个专用 sub-agent，用于在远端设备上搜集信息（系统状态、日志、配置、进程等），设计原则为"严边界，宽行为"——在禁止修改/删除/安装等破坏性操作的前提下，允许自由 SSH 连接远端、执行诊断命令、搜索网络。
- **操作方法**：在 `prompts/` 目录下创建 `RemoteInfoCollector.agent.md`，配置 `tools: [read, search, execute, web]`，包含完整的禁止行为清单、允许行为清单、SSH 操作规范、常用诊断命令速查表和结构化输出模板。
- **设计要点**：
  - **严边界**：明确禁止修改文件、安装软件包、修改配置、启停服务、执行破坏性命令、修改本地文件、写入数据库等 7 类操作
  - **宽行为**：允许 SSH 连接、查看系统状态、读日志/配置、检查网络/硬件、环境信息收集、本地文件读取、网络搜索、Git 只读查询等 8 类操作
  - 参考 `remote-dev` SKILL 的 SSH 工作流模式（超时设置、终端复用等）
  - `user-invocable: true`，支持作为 sub-agent 被调用，也支持在代理选择器中直接选择使用

### 2026-07-03 — 重构 RemoteInfoCollector 输出格式：只给事实，支持上级指定收集范围

- **操作目的**：优化 sub-agent 的输出格式，使其更适合上级 agent 程序化读取；删除分析建议类输出，仅返回结构化事实数据；新增 `--collect=<类别>` 支持上级按需指定返回类别。
- **操作方法**：重写 `RemoteInfoCollector.agent.md` 第4步（结构化汇总）的输出模板，将原自然语言段落改为 `[COLLECT_RESULT]` / `=== 区块 ===` 的键值对格式，每个区块按类别组织（SYSTEM、RESOURCE、PROCESS、LOG、NETWORK、HARDWARE、ENV、CONFIG），同时移除原"分析建议"和"参考链接"部分，以 `[WEB_REF]` 轻量替代网络引用。新增 `--collect=<类别>` 指令支持上级按需筛选返回内容。
- **变更要点**：
  - 自然语言报告 → 结构化键值区块格式
  - 移除"分析建议""参考链接"→ 改为仅 `[WEB_REF]` 列出 URL
  - 新增 `--collect` 参数，支持上级 agent 指定返回类别

### 2026-07-03 — 新增 sub-agent 使用指南.instructions.md，通用要求中移除 agent 表格

- **操作目的**：将 sub-agent 列表从 `AI agent 通用要求.instructions.md` 中分离出来，创建独立的 `sub-agent 使用指南.instructions.md`，集中管理所有可用 sub-agent 的用途、场景和调用方式；同时统一要求所有 sub-agent 调用时必须指定 `DeepSeek V4 Flash (copilot)` 模型。
- **操作方法**：
  - `AI agent 通用要求.instructions.md`：将 sub-agent 表格替换为指向新指南文件的一行引用，保留"优先使用 sub-agent"的规则不变
  - 新建 `sub-agent 使用指南.instructions.md`：包含总则、3个可用 agent 的详细属性表（Explore / RemoteInfoCollector / Study）、委派决策速查和注意事项
- **变更要点**：
  - sub-agent 列表从通用要求中解耦，后续新增 agent 只需更新使用指南即可
  - 新增模型指定规则：所有 sub-agent 调用必须传 `model="DeepSeek V4 Flash (copilot)"`

### 2026-07-06 — 新增 Search-readonly 和 Search-command 两个自定义 agent

- **操作目的**：创建两个专用搜索 agent，替代已不可用的 Explore subagent：
  - **Search-readonly**：纯只读搜索，通过文件读取、代码搜索、网络浏览搜集信息，无命令执行能力
  - **Search-command**：命令行只读搜索，通过终端命令（Select-String、Get-ChildItem、git log 等）高效搜索本地代码
- **操作方法**：
  - 在 `prompts/` 目录下创建 `Search-readonly.agent.md`，配置 `tools: [read, search, web]`
  - 在 `prompts/` 目录下创建 `Search-command.agent.md`，配置 `tools: [read, search, execute]`
  - 更新 `sub-agent 使用指南.instructions.md`，新增两个 agent 的属性表和更新委派决策速查树
- **设计要点**：
  - **Search-readonly**：纯只读，无 `execute` 工具，无法执行任何终端命令；专注文件读写、搜索和网页浏览
  - **Search-command**：有 `execute` 工具但严格限定为读取型命令（`Select-String`/`Get-ChildItem`/`git log` 等），附完整禁止/允许命令清单
  - 两个 agent 都包含结构化输出模板（`[SEARCH_RESULT]`），便于上级 agent 程序化读取
  - 均设为 `user-invocable: true`，既可作为 sub-agent 调用，也可在代理选择器中直接选择使用

### 2026-07-06 — Explore agent 状态确认

- **事实记录**：
  - Copilot Chat 0.38 (2026-03-05) 发布说明中记载了 Explore subagent 的引入，原用于 Plan agent 委派代码库搜索。
  - 2026-07-02 18:57:37，`runSubagent("Explore", ...)` 调用成功并返回结果。
  - **2026-07-06 上午**，`runSubagent("Explore", ...)` 调用成功（"Explore inference webui code"）。
  - **2026-07-06 下午**，`runSubagent("Explore", ...)` 调用失败（"Explore 暂时不可用"）。
  - 两次调用在同一 VS Code 版本（1.127.0 / Copilot Chat 0.55.0）下，一次成功一次失败。
  - 搜索了 VS Code 安装目录、prompts 目录、所有扩展目录，均未找到名为 Explore 的 agent 定义文件（.agent.md 或其他形式）。
- **操作**：
  - `sub-agent 使用指南.instructions.md`：将 Explore 标记为"已不可用"，说明当前无法调用，列出替代方式

### 2026-07-06 — 结构化改造「AI agent 通用要求.instructions.md」

- **操作目的**：将上一步的 Markdown 表格规则进一步改造为 YAML 结构化格式，嵌入 Markdown 代码块中，使 AI 可直接解析为内部决策表。
- **操作方法**：重写 `AI agent 通用要求.instructions.md`，将 9 条行为规则组织为 YAML `rules` 数组，每条规则用键值对定义 `id/priority/when/do/details` 等字段；C007（提问）与旧 C008（输入栏）合并为 `C007 + C007a` 父子结构；C011（文件索引）移出规则列表，作为独立参考章节置于末尾。
- **变更要点**：
  - Markdown 表格 → YAML 代码块（`rules` 数组）
  - 规则编号精简：C001~C010 → C001~C009（合并 C007↔旧 C008）
  - 父子规则结构：C007（提问）内嵌 C007a（输入栏要求）
  - `skip_when` 字段：C003 测试报告明确排除纯语法验证
  - `forbid` 字段：明确定义禁止行为（猜测/默认值/开新终端）
  - 文件索引从规则中移出，独立为"项目上下文文件索引"章节
