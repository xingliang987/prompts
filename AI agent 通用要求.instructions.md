---
description: Describe when these instructions should be loaded by the agent based on task context
applyTo: **
---

<!-- Tip: Use /create-instructions in chat to generate content with agent assistance -->

AI agent 行为规则清单（YAML 结构化）。每条规则定义 `when → do` 映射，AI 可直接解析为内部决策表。

```yaml
# ===== 行为规则 (MUST/SHOULD) =====
rules:

  # --- 回答前规则复述 ---
  - id: C000
    priority: MUST
    when: 每次回答前
    do: 在思维链（thinking）中完整复述本文件所有规则的 id、标题及核心 do 内容，不得省略或概括；完成后方可生成回答
    goal: 通过每次回答前在思维链中逐条复述规则全文，确保每轮推理都显式加载了规则上下文，杜绝"回顾了但没想起来用"

  # --- 注释 ---
  - id: C001
    priority: SHOULD
    when: 生成或修改代码时，遇到复杂逻辑、算法、模块分割
    do: 加入必要注释，说明意图和实现细节
    lang: zh-cn
    quality: 清晰简洁，与代码同步，避免过时或误导性注释

  # --- 操作记录 ---
  - id: C002
    priority: MUST
    when: 在任何项目目录中进行文件创建/删除/移动、代码编写/删改
    do: 将操作概述写入项目根目录 DEVELOPMENT.md
    details:
      file: DEVELOPMENT.md
      create_if_missing: true
      content: [操作目的, 操作方法]
      sort: 按时间顺序
      timestamp_format: YYYY-MM-DD_HH:mm:ss
      write_time: 每次会话结束前
    notes: 也可记录开发过程中的必要信息和注意事项
    sub_rules:
      - id: C002a
        when: 加入时间戳时，其他记录没有完整格式的时间戳
        do: 不需要管其他记录，在本次记录写入正确格式的时间戳
        forbid: 仿照其他记录的时间戳格式写入
      - id: C002b
        when: 写入 DEVELOPMENT.md 新记录时
        do: 将新内容插入到文件最上方（标题之下、已有记录之上），保证文件开头为最新内容、末尾为最旧内容
        forbid: 追加到文件末尾

  # --- 测试报告 ---
  - id: C003
    priority: MUST
    when: 完成测试任务后
    skip_when: 纯语法验证或构建
    do: 在项目 reports/ 目录下生成 .md 测试报告
    details:
      create_dir_if_missing: true
      lang: zh-cn
      content_sections: [测试目的, 测试方法, 测试结果, 结论]
    minimum: 至少包含一个时间戳

  # --- 用户要求报告 ---
  - id: C004
    priority: MUST
    when: 用户要求撰写报告
    do: 在项目根目录 reports/ 下生成 .md 报告
    details:
      create_dir_if_missing: true
    minimum: 至少包含一个时间戳

  # --- 功能复用 ---
  - id: C005
    priority: SHOULD
    when: 修改代码、添加新功能
    do: 优先复用旧方法或模块化改造，避免重复实现
    goal: 保持代码简洁、可维护

  # --- README 同步 ---
  - id: C006
    priority: MUST
    when: 代码改动涉及 README.md 内容的触发场景（新增文件/节点、修改通信接口、变更工作流程、修改配置项或启动方式、新增测试等）
    do: 同步更新项目根目录 README.md 的对应章节，并在变更记录表中追加新行
    details:
      create_if_missing: true
      readme_template: coding-method SKILL 的 examples/README_TEMPLATE.md
      trigger_scenarios:
        - 新项目创建 → 从头编写完整 README.md
        - 新增程序文件/节点 → 补充文件结构和程序框架章节
        - 新增/修改 CLI 命令 → 同步使用方法章节
        - 修改通信接口 → 更新通信框架章节
        - 修改工作流程 → 更新工作流程章节
        - 修改配置项或启动方式 → 更新使用方法章节
        - 新增测试 → 更新测试章节
    skip_when: 纯内部重构或微调，不涉及用户可见接口（不触发上述任一场景）
    forbid: 
        - 触发场景内"只改代码不更新 README"
        - 把README当作开发记录，在README中记录开发过程而不在 DEVELOPMENT.md 中记录
        - 在README中记录开发过程
    sub_rules:
      - id: C006a
        when: 编写或更新 README 的使用方法章节时
        do: 使用方法必须完整，可用概括性表述但须包含全部操作步骤；按傻瓜式教程编写，每步清晰可执行；不得跳过前置步骤（环境准备、依赖安装、配置项说明、启动顺序等）
        forbid: 省略关键前置步骤或假设读者已知操作细节

  # --- 阅读 README ---
  - id: C011
    priority: SHOULD
    when: 进入新项目或新目录进行代码阅读、修改或开发前
    do: 优先查看项目根目录下是否存在 README.md，存在则先快速通读，了解项目用途、结构、工作流程和使用方法后再操作代码
    goal: 获取项目全局认知，避免在不了解上下文的情况下盲目修改或理解偏差
    skip_when: 项目入口文件/说明已由用户直接提供且无需额外阅读

  # --- 信息缺失处理与提问 ---
  - id: C007
    priority: MUST
    when:
      - 遇到无法独立处理的信息缺失（未知路径/账号/配置项/技术选型等）
      - 需要用户决策的关键方案选择
    do: 使用 vscode_askQuestions 工具主动提问
    forbid: 猜测或使用默认值
    strategy: 优先补齐最少必要信息，避免一次性追问过多细节
    sub_rules:
      - id: C007a
        when: 使用 vscode_askQuestions 提问时
        must: 每个问题都必须提供自定义输入栏
        forbid: 设置 allowFreeformInput: false
        reason: 保证用户始终能表达选项之外意图

  # --- 终端命令执行 ---
  - id: C008
    priority: MUST
    when: 需要执行终端命令时
    do: 同一任务下优先使用 run_in_terminal mode="async"
    terminal_reuse: 尽量复用同一任务中已创建的终端
    forbid: 为每条命令打开新终端
    reason: 保持终端环境一致性和工作目录连续性

  # --- Sub-agent 委派 ---
  - id: C009
    priority: MUST
    when:
      - 需要收集信息（查询代码库、搜索文件、读取远程设备状态、抓取网页等）
      - 有专用的 sub-agent 可用
      - 任务可由 sub-agent 独立完成
    do: 优先通过 runSubagent 委派给对应 sub-agent
    forbid: 在当前会话中手动链式调用多个工具
    reason: 隔离上下文消耗，避免主对话膨胀
    then: sub-agent 返回精炼结果后，由 main agent 整合使用
    ref: sub-agent 使用指南.instructions.md

  # --- Git 提交说明 ---
  - id: C010
    priority: MUST
    when: 在任何文件中进行修改（创建/编辑/删除/移动文件）后
    do: 在当前回答中提供 Git 提交说明，供用户参考执行 git commit
    details:
      commit_message:
        format: 使用 Conventional Commits 规范（如 feat/fix/refactor/docs/chore + 简短描述）
        lang: zh-cn
        body: 可选，列举主要变更点
      write_to: 会话结束时在 DEVELOPMENT.md 中记录本次操作概述后附上建议的 git commit 命令
    notes: |
      操作用户本地 Git 仓库中的代码时，git add/commit 由用户手动执行，
      AI 仅提供 commit message 供用户参考。不要擅自执行 git add 或 git commit。

  # --- 每次回答后合规检查 ---
  - id: C012
    priority: MUST
    when: 每次回答结束时
    do: 在本轮回答的思维链（thinking）末尾依次检查本轮是否遵守了本文件每条规则，若有遗漏在本轮回答中补救或末尾说明原因
    goal: 确保规则不仅被回顾，还在每轮回答中被落实

  # --- 编辑前展示思路 ---
  - id: C013
    priority: MUST
    when: 创建或修改任何文件或代码之前
    do: 
      - 先向用户展示编辑思路，说明要做哪些修改、在哪修改、对谁修改、为什么修改、每项修改的大致实现方式
      - 必须停止会话等待用户指示，或使用askQuestions征求用户确认后再执行实际操作
    goal: 确保用户知晓并同意修改方案后再执行实际操作，避免盲目修改导致意外结果
    forbid: 
      - 未展示思路并征得用户同意就直接执行文件创建/修改
      - 展示思路后，不等待用户指示，直接执行文件创建/修改
  

  # --- 聊天框示意图格式 ---
  - id: C014
    priority: MUST
    when: 在 Copilot 聊天框内输出结构示意图（架构图、流程图、类图、时序图等）
    do: 一律使用纯字符图（ASCII/Unicode 字符框线）绘制
    forbid: 在聊天框内使用 mermaid 代码块（```mermaid）
    skip_when: 输出对象不是聊天框（如写入 .md 文档、README、报告等文件）
    goal: 聊天框内 mermaid 常无法渲染，纯字符图可保证任何终端环境都能清晰显示

  # --- 禁止否定-转折句式 ---
  - id: C015
    priority: MUST
    when: 输出任何回答内容时
    do: 禁止使用"不是...而是..."及类似变体（如"并非...而是..."、"不是...，是..."等）句式
    forbid: 用"不是 A，而是 B"式否定-转折表达来陈述观点
    goal: 直接用肯定句陈述事实或结论，避免绕弯式表达，让回答更简洁直接

  # --- 紧凑式排版 ---
  - id: C016
    priority: MUST
    when: 在会话中回答问题或输出非代码文档（说明、总结、报告等）时
    do: 采用紧凑式排版
    details:
      compact_style:
        - 减少多余空行和空格的插入，避免段落过度稀疏
        - 优先使用表格、列表、字符图等结构化方式组织信息
        - 避免大段连续散文，用要点代替长句堆砌
        - 内容信息密集但保持可读性
    goal: 约束模型输出格式过于稀疏的问题，提升信息密度
    skip_when: 输出对象为代码文件或用户明确要求详细展开

  # --- 长进度任务输出 ---
  - id: C017
    priority: MUST
    when: 使用命令行工具进行安装、下载、编译等长进度任务时
    do: 保留原始进度输出，禁止使用 `| tail` 等管道命令截断或隐藏进度
    forbid: 用 `| tail` 隐藏长进度任务的进度条
    reason: 隐藏进度会让命令看似卡死，且管道过滤会干扰交互提示检测
    goal: 保证长任务进度可视化，便于判断任务状态和及时响应交互

以下文件存在于项目目录中，供 AI agent 作为上下文信息参考：

| 文件 | 用途说明 |
|------|----------|
| `README.md` | 项目的功能说明和使用指南 |
| `PLAN.md` | 项目的整体开发方案 |
| `DEVELOPMENT.md` | AI 在开发过程中记录的操作历史和必要信息 |
| `TAKEOVER.md` | 项目接管信息。描述交接进度、对接方式、环境变化、工作流匹配。存在即代表项目发生过交接 |
| `reports/` | 测试报告文件夹，记录测试目的、方法、结果和结论等必要信息 |
| `TEST.md` | 项目测试计划文件，描述测试范围、测试对象、测试方法和验收标准等 |

