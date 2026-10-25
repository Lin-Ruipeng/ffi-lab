# ffi-lab：跨语言调用学习笔记

这个仓库用于逐个学习跨语言函数调用。每种调用场景拥有独立的课程目录、教程和示例，不在仓库根目录安装 npm 依赖。

| 课程 | 调用方向 | 内容 |
| --- | --- | --- |
| [01：TypeScript 调用 C++](01-ts-cpp-node-api/README.md) | TS → Node-API → C++ | 加法函数、CMake、ESM、测试、Git 提交 |
| [02：TypeScript 调用 Rust](02-ts-rust-node-api/README.md) | TS → Node-API → Rust | 加法函数、Cargo、napi-rs、自动类型声明、测试、Git 提交 |
| [03：TypeScript 异步调用 C++](03-ts-cpp-async-matrix/README.md) | TS → Promise / Node-API → C++ | 动态二维矩阵乘法、AsyncWorker、线程边界、并发测试 |
| [04：TypeScript 异步调用 Rust](04-ts-rust-async-matrix/README.md) | TS → Promise / Node-API → Rust | 动态二维矩阵乘法、AsyncTask、所有权、自动类型声明 |

每课独立配置工具链、安装依赖和管理锁文件。

## 番外

| 教程 | 内容 |
| --- | --- |
| [01：使用 GitHub CLI 发布本地仓库](extras/01-publish-to-github/README.md) | 第一课之后：登录、创建公开远端、首次推送、后续更新与排错 |

## 和 Agent 开始新实验

仓库的教学约定写在 [AGENTS.md](AGENTS.md)。clone 后，从仓库根目录启动支持该文件的 Agent，发送“开始学习”；尚未指定主题时，Agent 会先问：“你这次想学什么？”也可以直接说“我这次想学 TS 调用 Rust”，让 Agent 准备完整实验手册。

Agent 负责教材、对照成品和验证，你按手册亲手编写练习源码、测试、配置和文档，并执行 Git 提交。遇到不懂的地方随时提问，Agent 会结合当前进度解释。`AGENTS.md` 在 Agent 开始工作时提供约定，单独打开文件夹不会主动创建对话。

## 从哪里开始

首次学习可以打开[第一课教程](01-ts-cpp-node-api/README.md)，接着学习[第二课 Rust 加法](02-ts-rust-node-api/README.md)、[第三课 C++ 异步矩阵乘法](03-ts-cpp-async-matrix/README.md)和[第四课 Rust 异步矩阵乘法](04-ts-rust-async-matrix/README.md)。每课从第 0 节按顺序操作，在对应的 `practice/` 中亲手创建项目，并理解每份文件为什么存在。

```text
ffi-lab/                         # 唯一的 Git 仓库根目录
├── .gitignore
├── AGENTS.md                    # Agent 的实验教学约定
├── README.md
├── 01-ts-cpp-node-api/
│   ├── README.md                 # 完整教程
│   ├── VERIFICATION.md           # 实测环境、步骤和结果
│   ├── reference/                # 已验证的成品
│   └── practice/                 # 用户按手册创建
├── 02-ts-rust-node-api/
│   ├── README.md
│   ├── VERIFICATION.md
│   ├── reference/
│   └── practice/                 # 用户按手册创建
├── 03-ts-cpp-async-matrix/
│   ├── README.md
│   ├── VERIFICATION.md
│   ├── reference/
│   └── practice/                 # 用户按手册创建
└── 04-ts-rust-async-matrix/
    ├── README.md
    ├── VERIFICATION.md
    ├── reference/
    └── practice/                 # 第四课交付时不创建
```

`practice/` 的源码也可以提交到本仓库；其 `node_modules/`、`build/`、`dist/` 和 Rust 的 `target/` 会被根目录的 `.gitignore` 忽略。子目录共享根仓库，不需要再次 `git init`。

## 想先看看运行效果

先完成所选课程第 1 节的环境准备。以下命令均从仓库根目录开始，子 shell 结束后会回到原目录。

第一课：

```bash
(
  cd 01-ts-cpp-node-api/reference
  npm ci
  npm test
  npm start
)
```

预期：8 项测试通过，随后输出 `add(2, 3) = 5`。`npm test` 会先构建 C++ 和 TS。

第二课：

```bash
(
  cd 02-ts-rust-node-api/reference
  npm ci
  cargo fetch --locked
  npm test
  npm start
  npm run check
)
```

预期同样为 8 项测试通过、输出 `add(2, 3) = 5`，随后通过 Rust 格式、Clippy 和 TS 类型检查。`npm test` 会先构建 Rust、生成加载器与类型声明，再编译 TS。

第三课：

```bash
(
  cd 03-ts-cpp-async-matrix/reference
  npm ci
  npm test
  npm run check
  npm start
  npm run demo:heartbeat
)
```

预期 25 项集成测试通过，`2×3` 乘 `3×2` 得到 `[[58,64],[139,154]]`，并展示 `Promise.all` 和拒绝处理。心跳演示观察后台计算期间的事件循环，次数与耗时随机器变化。

第四课：

```bash
(
  cd 04-ts-rust-async-matrix/reference
  npm ci
  cargo fetch --locked
  npm test
  npm run check
  npm start
  npm run demo:heartbeat
)
```

预期 25 项真实 Rust 集成测试通过，主程序输出与第三课一致，并通过 rustfmt、Clippy 和 TS 类型检查。心跳演示观察 AsyncTask 后台计算，输入快照、输出与错误类型可和第三课对照。

## 验证范围

四课均在 Ubuntu 26.04.1、Node.js 24.21.0 上实际验证，第二、四课使用 Rust 1.99.1。详细工具版本、从空目录复走手册的结果和验证边界分别见[第一课验证记录](01-ts-cpp-node-api/VERIFICATION.md)、[第二课验证记录](02-ts-rust-node-api/VERIFICATION.md)、[第三课验证记录](03-ts-cpp-async-matrix/VERIFICATION.md)与[第四课验证记录](04-ts-rust-async-matrix/VERIFICATION.md)。

教程包含分阶段的本地提交命令；正式仓库的暂存、提交和推送由用户执行。
