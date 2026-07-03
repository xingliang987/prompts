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

### Explore — 代码库探索

| 属性 | 说明 |
|------|------|
| **用途** | 只读式代码库快速搜索和问答 |
| **适用场景** | 查询代码库结构、搜索文件/文本、理解模块逻辑、项目结构梳理 |
| **工具** | `[read, search]` — 仅本地文件读取和搜索 |
| **参数** | 可指定细致程度: `quick` / `medium` / `thorough` |
| **调用示例** | `runSubagent("Explore", "找出项目中所有与日志相关的模块，返回模块列表和关键函数说明，thorough")` |

### RemoteInfoCollector — 远端信息搜集

| 属性 | 说明 |
|------|------|
| **用途** | 通过 SSH 在远端设备上执行诊断命令收集信息 |
| **适用场景** | 检查远端系统状态、远端代码、查看远端日志、排查错误、收集环境配置、联动 web 搜索 |
| **工具** | `[read, search, execute, web]` — 可 SSH、可搜索、可抓网页 |
| **边界** | 纯只读，不修改远端任何文件或配置 |
| **调用示例** | `runSubagent("RemoteInfoCollector", "检查 192.168.1.100 的系统状态和 ROS2 日志")` |


## 委派决策速查

```
任务需要搜本地信息？         → Explore
任务需要 SSH 到远端查状态、搜信息？    → RemoteInfoCollector
以上都不匹配？                      → 当前 agent 自行处理
```

## 注意事项

- Sub-agent 每次调用是**无状态**的，不适合需要连续追问的交互场景
- 调用时**明确描述任务目标和期望返回格式**，减少沟通开销
- Sub-agent 返回的**原始数据不直接展示给用户**，由 main agent 整合后呈现
- 新增 sub-agent 后记得同步更新本文件
