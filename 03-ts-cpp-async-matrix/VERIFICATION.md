# 第三课验证记录

验证日期：2026-10-23（Asia/Singapore）。对应本课手册与 `reference/` 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x64，glibc |
| Node.js / npm | 24.21.0 / 12.2.1 |
| CMake / generator | 4.2.3 / Unix Makefiles |
| C++ / Make | G++ 15.2.0，C++17 / GNU Make 4.4.1 |
| Git / 终端 | 2.53.0 / zsh |
| TypeScript / @types/node | 7.0.2 / 24.19.2 |
| node-addon-api / cmake-js | 8.9.2 / 8.0.0 |
| node-api-headers（间接依赖） | 1.9.0 |
| Node 支持 / 插件使用的 Node-API | 10 / 8 |
| C++ 警告检查 | -Wall -Wextra -Wpedantic -Werror |
| C++ 排版检查 | clang-format 23.1.3，Google 风格 |

## 工具准备边界

使用已有 Node、CMake、编译器、Make 和 Git。未执行教程中可选的 sudo 安装、nvm 切换或 Git 身份配置。

为教材排版检查，从 PyPI 下载 clang-format wheel，解包到临时目录运行，没有安装全局工具或修改系统包。格式化与 dry-run 检查通过；学生必需验证流程不依赖该临时工具。

## 已完成的成品验证

```bash
npm install
npm run build
npm start
npm run demo:heartbeat
npm test
npm run check
npm ci
npm run clean
npm test
npm run check
npm start
npm run demo:heartbeat
```

构建开启警告视为错误，TS 类型检查通过；25 项真实跨语言测试通过。主程序输出：

```text
submitted; JavaScript continues before await
2x3 * 3x2 = [[58,64],[139,154]]
Promise.all = [[[6]],[[32]]]
caught: RangeError a columns must equal b rows
```

心跳演示本机一次输出 4 次心跳，结果为 600×500、首元素 800，约 274 ms。次数与耗时仅为观测，不作为固定阈值。

## 从手册重建练习项目

在临时目录中 clone 当前仓库历史，并将原有第二课教材作为临时基线快照保存，以独立验证第三课提交。实际项目路径包含中文与空格：`含空格的实验仓库/03-ts-cpp-async-matrix/practice`。

- 练习目录从不存在开始，按手册执行 `npm init -y`，从手册 13 个文件块创建配置、源码、测试和项目说明。没有从成品复制练习源码或锁文件。
- 13 份手写文件与 npm 自动生成的 `package-lock.json`，全部与成品逐字节一致。
- 手册共 24 个 bash 命令块，按顺序执行其中 21 个，包括工具检查、安装、构建、演示、类型检查、测试、清理、重装、异目录启动、诊断与 Git 流程。
- 跳过的三个条件式块为 sudo 安装、可选 nvm 切换和 Git 身份占位配置。临时 Git 身份由进程环境传入，不改真实仓库或全局配置。
- 四次 `npm test` 加一次直接 Node 测试均为 25 项通过、0 项失败。锁文件重装和清理后重建均成功。
- 两次心跳演示均输出正确形状与首元素，并在计算期间观察到心跳；测试不检查固定次数或耗时。

## 数学、异步和数据所有权

25 项集成测试经过实际 `.node`，覆盖不同非方阵尺寸、单元素、单位矩阵、零矩阵、负数和小数容限；小规模 TS 实现只作为预期结果的对照。

错误测试覆盖数量、两处参数及行的类型、两处元素类型、稀疏数组、空输入、行长不一致、乘法维度不相容、NaN/Infinity、乘积与累加溢出，以及输入 getter 抛出异常。普通校验错误均先确认返回 Promise，再断言拒绝；后台溢出拒绝为 RangeError。

所有权测试覆盖只读冻结输入、输入不被修改、提交后修改原数组不影响结果、输出行独立、Promise.all 任务隔离，以及某任务失败不影响另一任务。

`async_hooks` 实测创建并执行了 `ffi-lab:matrix-multiply` 的完成回调。补充诊断还确认后台溢出通过同名原生异步资源完成拒绝；并核对 Execute 只调用 C++ 算法与安全的 SetError，不访问 JS 数据。

## 补充边界与加载检查

- 单独编译临时 C++ 探针，确认正常元素计数、零维度、`size_t` 乘法溢出、vector 容量上限和存储不匹配检查按预期工作，没有实际分配巨大数组。
- 从临时仓库根目录运行相对入口，以及从 `/tmp` 运行绝对入口，均得到主程序的固定输出。
- 将临时项目的 `.node` 移出 build 后，启动以退出码 1 和 `MODULE_NOT_FOUND` 失败；恢复原文件后启动成功，没有 JS 计算降级实现。
- `file` 确认产物为 x86-64 ELF 共享库；`nm -D` 确认 `napi_register_module_v1` 与 `node_api_module_get_api_version_v1` 导出。
- CMake 构建参数包含 `-Wall -Wextra -Wpedantic -Werror`；C++ 文件通过临时 clang-format 的 Google 风格 dry-run 检查。

## Git 与文档交付

只在隔离副本中实际执行手册的三个学习提交：

```text
chore: configure asynchronous matrix addon project
feat: multiply matrices asynchronously through Node-API
test: verify async matrix behavior and document the lab
```

另外执行教材维护段的提交：

```text
docs: add verified asynchronous C++ matrix lesson
```

每次均包含手册中的状态、差异、明确路径暂存、暂存区检查、提交与后续状态/历史检查。临时副本最终干净，锁文件纳入历史，依赖目录与产物未被提交。

交付检查核对所有文件块与成品一致、文档本地链接目标存在、围栏完整、无未替换模板占位、无多余行尾空白；`git diff --check` 通过。前两课 38 份已有源码与教材文件的 SHA-256 均与本次开始时一致。真实暂存区保持为空，第三课 `practice/` 未创建。

## 验证范围

仅声明本机 Ubuntu/Linux x64、Node 24 的结果。没有验证其他系统、CPU 架构、Node 主版本、跨平台发布、取消或进度通知；没有修改线程池大小。

排队失败和 JS 结果转换异常具有捕获与释放路径，尚未通过故障注入强迫底层 API 失败。系统级内存耗尽不属于本课保证的恢复范围。

正式仓库未代用户暂存、提交或推送；第三课 practice 留给用户创建。
