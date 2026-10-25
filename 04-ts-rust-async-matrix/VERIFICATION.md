# 第四课验证记录

验证日期：2026-10-23（Asia/Singapore）。对应本课手册与 `reference/` 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x64，glibc |
| Node.js / npm | 24.21.0 / 12.2.1 |
| Rust / Cargo | 1.99.1 / 1.99.1，stable-x86_64-unknown-linux-gnu |
| rustfmt / Clippy | 1.10.0-stable / 0.1.99 |
| 系统链接驱动 | GCC 15.2.0 |
| Git / 终端 | 2.53.0 / zsh |
| Node 支持 / 插件选择的 Node-API | 10 / 8 |
| TypeScript / @types/node | 7.0.2 / 24.19.2 |
| @napi-rs/cli | 3.10.9 |
| napi / napi-derive / napi-build | 3.15.0 / 3.6.13 / 2.6.0 |
| Rust edition / crate-type | 2024 / cdylib |

依赖精确约束与锁文件见成品；未增加 Tokio、第三方矩阵库或其他课程的构建依赖。

## 工具准备边界

使用已有工具链，没有执行教程中的 sudo 安装、Rust 安装器或更新、可选 nvm 切换及 Git 身份配置。npm 与 Cargo 依赖获取、真实编译和检查均实际完成。

## 已完成的成品验证

执行并通过安装、Cargo 锁文件生成、构建、25 项集成测试、rustfmt、Clippy 和 TS 类型检查；随后完成：

```bash
npm ci
cargo fetch --locked
npm run clean
npm test
npm run check
npm start
npm run demo:heartbeat
```

固定输出：

```text
submitted; JavaScript continues before await
2x3 * 3x2 = [[58,64],[139,154]]
Promise.all = [[[6]],[[32]]]
caught: RangeError a columns must equal b rows
```

心跳演示本机一次显示 4 次心跳，结果 600×500、首元素 800，约 321 ms。仅记录观察，不要求固定次数或耗时。

生成声明包含两层 ReadonlyArray<number> 输入和 Promise<Array<Array<number>>> 返回，未退化为 Promise<unknown>。async_hooks 确认原生 Promise 对应非 PROMISE 类型的工作资源及完成回调；本机此版本资源 type 为字符串 undefined，测试不固定该名字。

## 从手册重建练习项目

在隔离临时目录 clone 既有仓库历史，将原有第二、三课教材保存为临时基线后验证第四课。新练习路径特意包含中文和空格：`含空格的实验仓库/04-ts-rust-async-matrix/practice`。

- 练习目录从不存在开始，实际执行 npm init，再从手册的 12 个完整文件块创建项目文件；没有从 reference 复制练习源码或锁文件。
- npm 与 Cargo 各自生成锁文件，12 份手写文件及两套锁文件均与成品逐字节一致。
- 手册共 26 个 bash 命令块，按顺序执行其中 22 个，覆盖版本检查、依赖获取、构建、静态检查、演示、测试、锁文件重装、清理重建、异目录启动、诊断和 Git。
- 跳过的四个条件式块分别为 sudo 安装、Rust 安装及组件添加、可选 nvm 切换、Git 身份占位配置。临时提交身份通过进程环境提供，没有修改真实仓库或全局 Git 配置。
- 四次 npm test 加一次直接 Node 测试均为 25 项通过、0 项失败。两次心跳演示的形状与首元素均正确，本次分别约 321 ms 与 315 ms，均观察到心跳；这些数值不作为固定验收条件。

## 行为、线程与所有权

25 项测试经过真实 Rust 原生库，覆盖非方阵及不同尺寸、单元素、单位矩阵、零矩阵、负数、小数误差、只读冻结输入，以及输入不被修改、提交后修改不影响结果、输出行独立、并发任务隔离。

错误测试覆盖数量、两处输入和行的类型、两处元素类型、稀疏数组、空输入、行长不一致、乘法尺寸不相容、NaN/Infinity、乘积与累加溢出，以及 getter 抛出的原异常。公开接口先确认返回 Promise，再检查拒绝分类。

原生异步资源测试用原生 Promise 对象身份区分工作资源与 Promise 自身的 async_hooks 记录，确认工作完成回调确实运行。补充诊断确认溢出拒绝也通过 AsyncTask 的原生完成资源发生。核对 compute 只操作拥有的 Rust 矩阵和纯数据错误，JS 错误对象只在主线程创建。

## 补充边界检查

- 用临时 rustc 探针直接引用纯 matrix 模块，验证 Matrix 的 Send 约束、正常元素计数、零维度、usize 乘法溢出、f64 字节容量限制、存储不匹配、计算溢出与结果行转换。探针编译开启 warnings 拒绝，没有分配巨大矩阵。
- TS 正向类型探针验证生成入口返回值精确为 number[][]、接受只读输入，公开适配层同样接受只读输入；负向探针确认错误返回值类型、字符串元素、缺少与多余参数被 tsc 拒绝。探针删除后临时工作区干净。
- 从临时仓库根目录运行相对入口，以及从 `/tmp` 运行入口绝对路径，均得到固定输出。
- 将临时项目的 `.node` 移出 build，启动退出码为 1，包含 `Cannot find native binding`；恢复文件后正常启动，确认没有 JS 乘法替代实现接管。
- file 确认产物为 x86-64 ELF 共享库，nm -D 确认 Node-API 注册入口存在。

## Git 与教材一致性

只在临时副本实际执行三个学习里程碑：

```text
chore: configure asynchronous Rust matrix project
feat: multiply matrices asynchronously with Rust AsyncTask
test: verify Rust async matrix behavior and document the lab
```

随后执行教材维护段的提交：

```text
docs: add verified asynchronous Rust matrix lesson
```

每个提交均执行手册中的状态、差异、明确路径暂存、暂存区审阅、提交和后续状态/历史检查。临时副本最终干净，两套锁文件进入历史，node_modules、target、build、dist 与 .node 均未进入历史。

交付检查核对文件块与成品一致、本地 Markdown 链接存在、围栏完整、模板占位已替换，以及全部新文件的空白检查；git diff --check 通过。前三课 43 份教材与对照成品的 SHA-256 与本次开始时一致。

工作期间观察到第二课 `practice/package.json` 有新的练习更新，本次没有修改或回退该文件。真实暂存内容保持原状，第四课 practice 未创建。

## 验证范围

仅声明本机 Ubuntu/Linux x64、Node 24、Rust 1.99.1 下的结果。未验证其他系统、架构、Node 主版本、Wasm 或发布流程，也未增加取消、进度回调和独立线程池。

使用 Result 处理预期的范围、溢出及可报告分配失败；没有进行系统级内存耗尽或底层排队失败的故障注入，不把 panic 或系统终止称为已验证可恢复错误。

正式仓库未代用户暂存、提交或推送；第四课 practice 留给用户创建。
