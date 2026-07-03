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
