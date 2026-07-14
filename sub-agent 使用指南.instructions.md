---
description: 罗列当前可用的 sub-agent 列表及其适用场景，供 AI agent 在需要委派任务时参考
applyTo: **
---

# Sub-agent 使用指南

## 总则

- 当任务可拆分为独立子任务时，**优先委派给对应的 sub-agent** 执行，以隔离上下文消耗
- **所有 sub-agent 调用建议优先指定模型为 `DeepSeek V4 Flash (copilot)`**，确保统一推理性能和成本控制
- 调用格式：`runSubagent("AgentName", "任务描述", model="DeepSeek V4 Flash (copilot)")`
- Sub-agent 返回精炼结果后由 main agent 整合使用

## 可用 sub-agent 一览

### Search-readonly — 纯只读本地+网络搜索

| 属性 | 说明 |
|------|------|
| **用途** | 纯只读搜索，通过文件读取、代码搜索、网络浏览搜集信息 |
| **适用场景** | 搜索代码、阅读文件、查文档、搜网页、研究代码逻辑、浏览目录结构 |
| **工具** | `[read, search, web]` — 只能读/搜/查网页 |
| **边界** | 无命令执行能力，不修改任何文件 |
| **调用示例** | `runSubagent("Search-readonly", "查找项目中的日志工具类定义和用法")` |

### Search-command — 命令行只读搜索

| 属性 | 说明 |
|------|------|
| **用途** | 通过终端命令（`Select-String`、`Get-ChildItem`、`git log` 等）高效搜索本地代码 |
| **适用场景** | 大规模文本搜索、Git 历史查询、批量文件匹配、需要命令行管道过滤的复杂搜索 |
| **工具** | `[read, search, execute]` — 可执行命令，但只限读取型 |
| **边界** | 只执行读取型命令（grep/find/git log等），不修改任何文件或系统状态 |
| **调用示例** | `runSubagent("Search-command", "在所有 Python 文件中搜索 'def handle_' 开头的函数")` |

### Search-remote — 远端信息搜集

| 属性 | 说明 |
|------|------|
| **用途** | 通过 SSH 在远端设备上执行诊断命令收集信息 |
| **适用场景** | 检查远端系统状态、远端代码、查看远端日志、排查错误、收集环境配置、联动 web 搜索 |
| **工具** | `[read, search, execute, web]` — 可 SSH、可搜索、可抓网页 |
| **边界** | 纯只读，不修改远端任何文件或配置 |
| **调用示例** | `runSubagent("Search-remote", "检查 192.168.1.100 的系统状态和 ROS2 日志")` |


## 委派决策速查

```
任务需要纯读本地/网络信息？         → Search-readonly（读/搜/网页）
任务需要命令行高效搜索本地？        → Search-command（grep/git/find）
任务需要 SSH 到远端查状态、搜信息？  → Search-remote
以上都不匹配？                      → 当前 agent 自行处理
```

## 注意事项

- Sub-agent 每次调用是**无状态**的，不适合需要连续追问的交互场景
- 调用时**明确描述任务目标和期望返回格式**，减少沟通开销
- Sub-agent 返回的**原始数据不直接展示给用户**，由 main agent 整合后呈现
- 新增 sub-agent 后记得同步更新本文件
