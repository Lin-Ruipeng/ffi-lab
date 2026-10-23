# 第二课验证记录

验证日期：2026-10-23（Asia/Singapore）。本记录对应同目录手册与 `reference/` 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x64，glibc |
| Node.js / npm | 24.21.0 / 12.2.1 |
| Rust / Cargo | 1.99.1 / 1.99.1，stable-x86_64-unknown-linux-gnu |
| rustfmt / Clippy | 1.10.0-stable / 0.1.99 |
| 系统 C 编译器与链接驱动 | GCC 15.2.0 |
| Git / 终端 | 2.53.0 / zsh |
| 运行时支持 / 插件声明的 Node-API | 10 / 8 |
| TypeScript / @types/node | 7.0.2 / 24.19.2 |
| @napi-rs/cli | 3.10.9 |
| napi / napi-derive / napi-build | 3.15.0 / 3.6.13 / 2.6.0 |
| Rust edition / crate-type | 2024 / cdylib |

直接依赖精确固定，间接依赖由成品的 `package-lock.json` 与 `Cargo.lock` 记录。

## 工具准备边界

使用机器已有的 Node、Rust stable、rustfmt、Clippy、系统编译工具和 Git。没有运行 sudo 安装、Rust 安装器或更新、可选 nvm 切换，也没有改动全局 npm 工具或真实仓库的 Git 配置。

教程中的这些条件式环境准备步骤属于安装指引，不声明为本次已执行。npm 和 Cargo 依赖下载、实际构建及测试使用现有工具链完成。

## 已验证的成品行为

已执行 `npm install`、`cargo generate-lockfile`、`npm test`、`npm start` 和 `npm run check`，随后完成锁文件重装与清理重建：

```bash
npm ci
cargo fetch --locked
npm run clean
npm test
npm start
npm run check
```

- 8 项集成测试通过，真实调用本机 `.node`；没有 mock 或 JS 加法替代实现。
- 覆盖正数、负数、零、小数误差、NaN、Infinity，以及两处参数的非数值、缺少参数和多余参数。
- 动态传入字符串、undefined、null、boolean、对象、bigint 时抛出 JS `Error`，`code` 为 `InvalidArg`。
- 缺少参数被当作 undefined 拒绝，多余参数被忽略；`add(2, 3, 4)` 的动态调用结果为 5。
- rustfmt、Clippy（警告视为错误）和 TS 类型检查通过。
- `build/index.d.ts` 自动声明 `add(a: number, b: number): number`；ELF 检查确认 `.node` 是本机 x86-64 共享库。

关键输出：

```text
Finished `release` profile [optimized]
ℹ tests 8
ℹ pass 8
ℹ fail 0
add(2, 3) = 5
Error InvalidArg Expect value to be Number, but received String
```

## 从手册重建练习项目

在 `/tmp` 下建立独立 Git clone，复用当前已有历史，不改正式仓库。验证项目路径特意包含中文和空格：`含空格的练习仓库/02-ts-rust-node-api/practice`。练习目录从不存在开始，安装、源码创建与提交均在临时副本中进行。

- 按手册顺序解析文件块与命令块，执行 `npm init -y`，再从手册写入配置和源码；没有从 `reference/` 复制练习源码或锁文件。
- 从 11 个完整文件块重建根忽略规则与 10 份项目文件；`package-lock.json`、`Cargo.lock` 分别通过 npm 和 Cargo 生成。
- 核对 10 份手写项目文件与两套生成锁文件，均与成品逐字节一致。
- 手册共 25 个 bash 命令块，实际顺序执行其中 21 个，包括环境检查、依赖获取、构建、检查、演示、测试、锁文件重装、清理重建、异目录启动、诊断和 Git 流程。
- 跳过的 4 个条件式命令块分别为 sudo 安装、Rust 安装与组件添加、可选 nvm 切换、Git 身份占位配置。验证专用 Git 身份通过进程环境提供，未修改任何真实仓库或全局身份配置。
- 复走过程中的四次 `npm test` 与一次直接 Node 测试均为 8 项通过、0 项失败；中间完成一次 npm 重装和一次 Cargo/JS 产物清理后重建。

## 路径、类型与缺失产物检查

- 从临时仓库根目录运行相对入口，以及从 `/tmp` 运行入口绝对路径，均输出 `add(2, 3) = 5`。中文和空格路径没有影响生成加载器或动态导入。
- 在临时项目中将 `.node` 移到构建目录之外，启动进程退出码为 1，包含 `Cannot find native binding`；恢复原文件后重新启动成功。确认缺少插件时不会由 JS 加法或其他降级实现接管。
- 生成加载器的 `__napiBindingTarget` 实测为 `native`。`file` 确认 `.node` 为 x86-64 ELF 共享库，`nm -D` 确认导出 `napi_register_module_v1`。
- 临时添加一份类型探针，分别把返回值赋给 string、传入 string、缺少参数、传入多余参数；`tsc --noEmit` 按预期失败，分别报告 TS2322、TS2345 与 TS2554。删除探针后未留下变更，说明调用方确实使用了生成的数值与参数声明。

## Git 流程与交付检查

只在临时副本实际执行手册的三个学习里程碑：

```text
chore: configure TypeScript Rust addon project
feat: call Rust add from TypeScript through Node-API
test: verify Rust addon behavior and document the lab
```

之后另行验证教材维护段的提交命令：

```text
docs: add verified TypeScript to Rust lesson and reference
```

每个提交均执行手册中的状态、差异、明确路径暂存、暂存差异、提交及后续状态/历史检查。临时仓库最终干净；两套锁文件进入历史，`node_modules/`、`target/`、`build/`、`dist/` 与 `.node` 没有进入版本历史。

交付时还核对手册文件块与成品一致、Markdown 本地链接目标存在、Git 忽略规则与命令工作目录正确、`git diff --check` 通过。正式仓库暂存区保持为空，第一课目录与既有历史未修改，第二课 `practice/` 未创建。

## 验证范围

仅声明本机 Ubuntu/Linux x64、Node 24、Rust 1.99.1 下的结果。未验证 macOS、Windows、其他架构或 Node 主版本、Wasm、跨平台发布和异步调用。

两套锁文件用于复现已交付依赖树；首次手抄项目重新解析间接依赖时可能与成品不同。没有运行任何真实仓库的暂存、提交或推送；第二课 `practice/` 留给用户创建，第一课练习保持原状。
