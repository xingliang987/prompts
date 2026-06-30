---
description: Describe when these instructions should be loaded by the agent based on task context
applyTo: **
---

<!-- Tip: Use /create-instructions in chat to generate content with agent assistance -->

Provide project context and coding guidelines that AI should follow when generating code, answering questions, or reviewing changes.

- 在程序中加入必要的注释，特别是对于复杂的逻辑或算法，以及不同功能模块的分割和说明，以帮助其他开发者理解代码的意图和实现细节。注释应该清晰、简洁，并且与代码保持同步，避免过时或误导性的注释。注释的文字说明应使用简体中文。

- **必须执行** ：AI agent 在任何项目目录中进行文件创建、删除、移动，代码编写、删改等操作时，必须将操作记录的概述写入项目文件内的DEVELOPMENT.md中，如果没有DEVELOPMENT.md，则需要在项目根目录创建一个。除了写入操作记录外，还需要对项目内容进行简要的说明，对每次的操作做简要说明，要求说明操作目的，操作方法。操作记录按照时间顺序写入，每次写入时标记时间戳。此外，也可以在DEVELOPMENT.md中记录开发过程中需要的必要信息，需要注意的问题等。操作记录必须在每次会话结束前写入，确保每次操作都有记录。

- AI agent在进行测试任务后，必须撰写测试报告（如果只有语法验证和构建则不需要撰写报告），记录在项目目录的reports文件夹，或其他用户指定的目录下。测试报告的叙述内容应使用简体中文。报告内容应包括测试目的、测试方法、测试结果、结论等必要信息，确保测试过程和结果的清晰记录和可追溯性。测试报告应该详细描述测试的步骤和结果，以便其他开发者能够理解测试的内容和意义，并且能够根据报告进行相应的调整和改进。

- AI agent在修改代码添加新功能时，应该尽可能考虑旧方法的复用，或模块化改造，尽可能避免重复的功能实现，保持代码的简洁和可维护性。

- AI agent在实现新功能后，必须在README.md中更新功能说明，确保文档与代码保持同步，便于其他开发者理解新功能的用途和使用方法。功能说明应该清晰、简洁，并且包含必要的示例和使用指南，以及主要通信接口的说明，以帮助其他开发者快速上手和正确使用新功能。如果没有README.md，则需要在项目根目录创建一个，并撰写项目的功能说明和使用指南。