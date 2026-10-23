# ffi-lab：跨语言调用学习笔记

这个仓库用于逐个学习跨语言函数调用。每种调用场景拥有独立的课程目录、教程和示例，不在仓库根目录安装 npm 依赖。

| 课程 | 调用方向 | 内容 |
| --- | --- | --- |
| [01：TypeScript 调用 C++](01-ts-cpp-node-api/README.md) | TS → Node-API → C++ | 加法函数、CMake、ESM、测试、Git 提交 |

后续可以继续添加 TS → Rust 等课程，每课独立配置工具链。

## 番外

| 教程 | 内容 |
| --- | --- |
| [01：使用 GitHub CLI 发布本地仓库](extras/01-publish-to-github/README.md) | 第一课之后：登录、创建公开远端、首次推送、后续更新与排错 |

## 和 Agent 开始新实验

仓库的教学约定写在 [AGENTS.md](AGENTS.md)。clone 后，从仓库根目录启动支持该文件的 Agent，发送“开始学习”；尚未指定主题时，Agent 会先问：“你这次想学什么？”也可以直接说“我这次想学 TS 调用 Rust”，让 Agent 准备完整实验手册。

Agent 负责教材、对照成品和验证，你按手册亲手编写练习源码、测试、配置和文档，并执行 Git 提交。遇到不懂的地方随时提问，Agent 会结合当前进度解释。`AGENTS.md` 在 Agent 开始工作时提供约定，单独打开文件夹不会主动创建对话。

## 从哪里开始

打开 [第一课教程](01-ts-cpp-node-api/README.md)，从第 0 节按顺序操作。教程的目标是让你能在 `practice/` 中亲手创建项目，并理解每份文件为什么存在。

```text
ffi-lab/                         # 唯一的 Git 仓库根目录
├── .gitignore
├── AGENTS.md                 # Agent 的实验教学约定
├── README.md
└── 01-ts-cpp-node-api/
    ├── README.md                # 完整教程
    ├── VERIFICATION.md          # 实测环境、步骤和结果
    ├── reference/               # 已验证的成品
    └── practice/                # 你跟着教程创建；交付时尚不存在
```

`practice/` 的源码也可以提交到本仓库；其 `node_modules/`、`build/` 和 `dist/` 会被根目录的 `.gitignore` 忽略。子目录不需要再次 `git init`。

## 想先看看运行效果

先完成教程第 1 节的环境准备，再执行：

```bash
cd /home/folin/文档/Code/ffi-lab/01-ts-cpp-node-api/reference
npm ci
npm test
npm start
```

预期：8 项测试通过，随后输出 `add(2, 3) = 5`。`npm test` 会先构建 C++ 和 TS。

## 验证范围

第一课在 Ubuntu 26.04.1、Node.js 24.21.0 上实际验证。详细版本、从空目录复走教程的结果和工具准备方式见 [验证记录](01-ts-cpp-node-api/VERIFICATION.md)。

仓库已初始化为 `main` 分支，尚未代你执行正式 Git 提交。教程包含分阶段提交命令。
