# 第八课验证记录

验证日期：2026-11-01（Asia/Singapore）。对应本课 [README.md](README.md) 和本地 [reference/](reference/) 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x86-64，glibc |
| 终端 / Git | zsh；手册自动复走使用 bash / Git 2.53.0 |
| uv | 0.13.6 |
| Python | uv 托管 CPython 3.12.15，Python.h 存在 |
| 系统 Python | 3.14.4，未用于本课扩展 |
| Rust / Cargo | 1.99.1，stable-x86_64-unknown-linux-gnu |
| Rust edition / 声明最低版本 | 2024 / 1.85；未以旧工具链复测 |
| rustfmt / Clippy | 1.10.0-stable / 0.1.99 |
| 系统链接工具 | GCC 15.2.0 |
| PyO3 / Maturin | 0.30.1 / 1.15.0 |
| pytest / Ruff / mypy | 9.1.1 / 0.17.2 / 2.4.0 |
| crate-type / 构建 profile | cdylib / release |
| 调度与 GIL | asyncio.to_thread，默认 ThreadPoolExecutor；Python::detach |
| 模块 / wheel 标签 | .cpython-312-x86_64-linux-gnu.so / cp312-cp312-linux_x86_64 |

直接依赖见成品的 pyproject.toml 与 Cargo.toml，间接依赖分别由 uv.lock 和 Cargo.lock 固定。未启用 abi3、Tokio、pyo3-async-runtimes、Rayon、NumPy、BLAS 或多进程。

## 工具准备与执行边界

使用已有 uv、Rust、rustfmt、Clippy、系统链接工具、Git 和托管 Python。实际执行 `uv python install 3.12.15 --no-bin`，提示已经安装；解释器路径、版本、SOABI 与 Python.h 断言通过。

没有执行 sudo、Rust/uv 安装器、工具链更新或 Git 身份占位配置；首次下载整个 CPython 运行时未验证。依赖获取实际联网访问 PyPI 与 crates.io，验证进程将 UV_CACHE_DIR、CARGO_HOME 指向 /tmp，并使用 UV_LINK_MODE=copy，没有修改用户全局 uv、Cargo 或 Git 配置。

受限执行环境无法解析依赖源，且纯标准库 asyncio.to_thread 对照在默认线程池关闭阶段也无法正常退出。正式实验的依赖获取、构建、异步演示、测试和手册复走均在沙箱外的本地执行环境完成，进程正常结束。课程程序不依赖 Agent 的执行隔离配置。

## 成品构建与真实调用

实际执行 Cargo/Python 锁文件生成、依赖安装、Maturin 编译、演示、pytest、Python/Rust 静态检查与源码包构建，也执行根首页完整的第八课成品命令。

关键输出：

```text
2x3 @ 3x2 = [[58.0, 64.0], [139.0, 154.0]]
gather = [[[11.0]], [[30.0, 35.0]]]
OverflowError: matrix multiplication produced a non-finite value
success: [[21.0]]
49 passed
All checks passed!
6 files already formatted
Success: no issues found in 5 source files
```

rustfmt 无差异。Clippy 使用 `PYO3_PYTHON="$PWD/.venv/bin/python"` 选择项目解释器，`--locked --all-targets -- -D warnings` 通过。

原生扩展位于 src/rust_matrix/_core.cpython-312-x86_64-linux-gnu.so；函数说明为 `Multiply two finite rectangular matrices using Rust f64 arithmetic.`，文本签名为 `(a, b)`，没有要求 Python 额外传入解释器令牌。

一次成品心跳实测：

```text
awaiting 600x800 @ 800x500
heartbeat 1
...
heartbeat 11
result: 600x500; first = 800.0
heartbeats: 11; elapsed: 0.616 s
```

上面的省略号只省去相同形式的心跳日志，不是源码省略。次数和耗时是这一次观察，不作为性能指标或加速承诺；测试要求心跳发生在真实原生函数进入后、返回前。

## 从手册代码块重建项目

在 /tmp 隔离目录 clone 正式仓库现有历史，预置当前未提交的教材；第八课 practice 从不存在开始。路径包含中文和空格：`含空格的实验仓库/ffi-lab/08-python-rust-async-matrix/practice`。

- 依次执行 uv init，从手册的 12 个完整文件块创建根忽略规则及 11 份项目文件；没有从 reference 复制练习源码。
- touch 创建 0 字节 py.typed，uv/Cargo 分别生成锁文件。最终 14 份项目文件与成品逐字节一致，包含双锁文件。
- 手册共 29 个标注的 bash 命令块，实际执行 25 个，包括随后单独执行的教材提交。跳过四块仅为 sudo、Rust 安装器、uv 安装器与 Git 身份占位配置；临时提交身份由进程环境提供。
- 配置阶段先使用 --no-install-project 安装开发工具，无需尚未创建的 Rust/Python 源码。生成 Cargo.lock 后才执行锁定构建。
- 实际完成普通演示、心跳、完整测试和检查、显式重编译安装、清理重建、异目录运行、打包、wheel 测试与类型检查、最终验收和诊断。
- 清理同时删除 src 中的 editable 原生扩展与 Cargo target，再从保留的双锁文件重建。手册中的五轮完整 pytest（含 wheel）均为 49 项通过。
- 从仓库根目录及 /tmp 使用项目解释器运行均成功，没有设置 PYTHONPATH 或手动修改 sys.path。

最终诊断输出：

```text
[[6.0]]
ValueError
a columns must equal b rows
```

## 行为、所有权和异步边界

49 项集成测试覆盖动态矩形、单元素、单位矩阵、零、负数、小数、元组/关键字参数、bool 默认转换、f64 整数精度、输入不变及独立输出行；还覆盖非法外层/行/元素类型、空矩阵/空行、不等长行、维度不兼容、NaN/Infinity、乘积和累加溢出、错误时机、协程启动、输入快照、并发结果顺序、失败隔离、工作线程、GIL 心跳、取消及原生扩展身份。

Python 只实现快照与调度，PyO3 将输入转换为自有 `Vec<Vec<f64>>`；move 闭包在 detach 期间只做纯 Rust 校验、分配和乘法，返回后映射 Python 异常并转换结果。没有 Python 矩阵算法、假原生结果或测试专用原生接口。

快照测试使用单线程池和 Event，让任务排队后修改原输入，结果仍为快照值。另一个测试只创建协程再修改输入，结果反映修改，区分协程创建与执行时机。类型错误使用 PyO3 0.30.1 的参数 notes 检查 a/b 上下文。

观察器仅临时转发真实 _core.multiply，用 profiler 记录 c_call/c_return/c_exception 和线程 ID，并在结束时恢复原函数、profiler 与线程切换时间片。心跳期间原生调用确实处于活动区间，且运行在线程池而非事件循环线程。取消测试先等真实调用开始，取消等待得到 CancelledError，再等原生工作正常结束，并确认后续计算仍成功。

## 故障对照与恢复

以下改动只发生在临时练习副本，结束后恢复源码及原生库：

1. file 确认为 x86-64 ELF 共享库，nm -D 确认导出 PyInit__core。
2. 暂时移走 editable 扩展，在新进程以 `-I -m rust_matrix` 启动，以状态码 1 和涉及 _core 的 ImportError 失败；恢复后正常输出矩阵结果，确认没有 Python 算法接管。
3. 临时将绑定中的 detach 调用替换为直接 Rust 调用并重新安装，单项心跳测试得到 `1 failed, 48 deselected`，消息为 `no heartbeat while the native call was active`，计数为 0。恢复 detach 并重编译后测试通过。
4. 将 Rust 输出临时改为每项加 1：未重新安装时新进程仍得到 `[[6.0]]`；显式重新编译安装后得到 `[[7.0]]`。恢复源码并重新安装后回到 `[[6.0]]`。
5. 恢复后完整 49 项测试、Ruff、严格 mypy、rustfmt 与 Clippy 均通过，临时练习源码相对其提交历史无差异。

## 源码包、wheel 与类型信息

uv build 实际先创建源码包，再从源码包编译 wheel：

```text
py_rust_async_matrix-0.1.0.tar.gz
py_rust_async_matrix-0.1.0-cp312-cp312-linux_x86_64.whl
```

源码包包含 14 份完整项目文件和 PKG-INFO，共 15 份文件；逐份与项目内容比较通过，包括双锁文件、Rust/Python 源码、测试、说明与类型信息，没有环境、target、缓存或 editable 原生扩展。Cargo 提示缺少对外发布元数据，但命令成功；该提示不是 Clippy 代码警告。

wheel 共 10 份文件：三个 Python 源文件、_core.pyi、空 py.typed、原生扩展、METADATA/WHEEL/RECORD 和 Maturin 自动生成的依赖 SBOM。Python 和类型文件与源码逐字节一致。

独立 `.venv-wheel` 验收：

- --no-deps 安装后，以 -I 运行普通演示和真实原生调用成功。扩展路径位于独立环境的 site-packages/rust_matrix，运行时无需安装 Maturin/PyO3 Python 包。
- 从 uv.lock 导出 dev 组，以 --require-hashes 安装测试工具；wheel 环境的全部 49 项集成测试通过。
- 从 /tmp 使用独立环境的 mypy 严格检查正确调用，通过；错误的结果赋值、字符串元素、缺少参数和多余参数产生四处预期错误，分类为 assignment、list-item、call-arg、call-arg，退出码为 1。
- 没有缺少包或类型声明错误，确认 wheel 内的 Python 标注、原生 stub 和 py.typed 实际生效。

## Git 流程与交付一致性

只在临时 clone 实际执行三个学习提交：

```text
chore: configure Python Rust async matrix project
feat: call Rust matrix multiplication asynchronously from Python
test: verify Python Rust async matrix behavior
```

随后执行当前第七、八课教材的合并维护提交：

```text
docs: add verified Python async matrix lessons
```

每个里程碑都执行对应验证、状态/差异检查、明确路径暂存、暂存区审阅、提交及状态/历史检查。14 份练习受控文件含双锁文件和空标记，没有产物进入历史；教材提交包含共享根索引与第七、八课手册/验证记录，临时仓库最后干净。

本地 Markdown 链接、围栏、手册文件块、成品内容、命令目录、Git 忽略规则与空白检查通过。开始时记录的既有教材、成品与练习文件除本次更新的根 README 外保持一致；根 .gitignore 和正式暂存区保留原样。第七课尚未提交的教材保留，第八课 practice 未创建。

## 验证范围

只声明本机 Ubuntu/Linux x64、CPython 3.12.15、Rust 1.99.1 与指定依赖版本下的结果。未测试最低 Rust 版本、其他 Python 小版本、PyPy、自由线程 Python、其他系统/架构、manylinux 修复、abi3 或远端发布。

未实际触发超大结果维度或分配失败；源码中的 checked_mul/try_reserve_exact 防护只检查了实现与编译，不称为行为实测。没有原生抢占取消、取消令牌、并发限流或单次矩阵内部并行。每次调用会复制输入与结果，不是零复制；快照与转换阶段仍需要 GIL。

双锁文件固定各自依赖树，构建后端版本由 pyproject.toml 固定；系统编译器、隔离构建的其他间接依赖和平台 ABI 不因此完全锁定，不宣称跨机器二进制可复现。
