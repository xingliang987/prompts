---
description: Describe when these instructions should be loaded by the agent based on task context
applyTo: **
---

<!-- Tip: Use /create-instructions in chat to generate content with agent assistance -->

AI agent 行为规则清单（YAML 结构化）。每条规则定义 `when → do` 映射，AI 可直接解析为内部决策表。

```yaml
# ===== 行为规则 (MUST/SHOULD) =====
rules:

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
    when: 实现新功能后
    do: 更新 README.md（不存在则创建），保持文档与代码同步
    details:
      readme_content: [功能说明, 使用示例, 使用指南, 主要通信接口说明]

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
```

---

## 项目上下文文件索引

以下文件存在于项目目录中，供 AI agent 作为上下文信息参考：

| 文件 | 用途说明 |
|------|----------|
| `README.md` | 项目的功能说明和使用指南 |
| `PLAN.md` | 项目的整体开发方案 |
| `DEVELOPMENT.md` | AI 在开发过程中记录的操作历史和必要信息 |
| `TAKEOVER.md` | 项目接管信息。描述交接进度、对接方式、环境变化、工作流匹配。存在即代表项目发生过交接 |
| `reports/` | 测试报告文件夹，记录测试目的、方法、结果和结论等必要信息 |

