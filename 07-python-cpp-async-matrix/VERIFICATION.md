# 第七课验证记录

验证日期：2026-11-01（Asia/Singapore）。对应本课 [README.md](README.md) 和本地 [reference/](reference/) 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x86-64，glibc |
| 终端 / Git | zsh；手册自动复走使用 bash / Git 2.53.0 |
| uv | 0.13.6 |
| 项目 Python | uv 托管 CPython 3.12.15，配套 Python.h 存在 |
| 系统 Python | 3.14.4，未用于本课原生扩展 |
| CMake | 4.2.3 |
| 原生编译器 / 标准 | G++ 15.2.0 / C++17，无编译器语言扩展 |
| 编译模式 / 警告 | Release；-Wall -Wextra -Wpedantic -Werror |
| CMake generator / Ninja | Ninja / 1.13.2，由后端按项目配置提供 |
| pybind11 / scikit-build-core | 3.1.0 / 1.1.1 |
| pytest / Ruff / mypy | 9.1.1 / 0.17.2 / 2.4.0 |
| 线程调度 | asyncio.to_thread，事件循环默认 ThreadPoolExecutor |
| 模块 / wheel 标签 | .cpython-312-x86_64-linux-gnu.so / cp312-cp312-linux_x86_64 |

依赖声明和 uv 自动生成的锁文件位于本地成品；所有手写文件在手册中完整提供。

## 环境准备与执行边界

使用已有的 uv、CMake、G++、Git 和 uv 托管 Python。实际执行 `uv python install 3.12.15 --no-bin`，报告该版本已经安装；解释器路径、版本及 Python.h 断言通过。未执行 sudo、uv 安装器和 Git 身份占位配置，首次下载完整 CPython 运行时的过程未验证。

依赖获取实际联网访问 PyPI，构建并安装锁定的开发依赖和隔离构建依赖。验证进程设置 `UV_CACHE_DIR` 指向 `/tmp`，并使用 `UV_LINK_MODE=copy`；没有修改全局 uv 配置。正式仓库没有执行暂存、提交或推送。

最初的受限执行环境中，纯标准库 `asyncio.to_thread` 对照也在默认线程池关闭阶段出现等待不结束。最终异步测试、演示和手册重建均在沙箱外的本地执行环境完成，进程正常退出；手册中的程序不依赖 Agent 的执行隔离配置。

## 成品构建与真实调用

实际执行根首页的第七课成品命令：Python 版本准备、`uv sync --locked`、普通演示、心跳、pytest、Ruff 检查/格式与严格 mypy，全部通过。

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

一次成品心跳实测为：

```text
awaiting 600x800 @ 800x500
heartbeat 1
heartbeat 2
heartbeat 3
result: 600x500; first = 800.0
heartbeats: 3; elapsed: 0.196 s
```

次数与耗时只是本次观察，不作为性能承诺。测试的通过条件为真实原生调用期间存在心跳，不比较固定耗时或并行加速比。

49 项集成测试覆盖动态矩形、单元素、单位矩阵、零、负数、小数、元组和关键字输入、bool 默认转换、double 整数精度、输入不变与独立输出行；另覆盖非法外层/行/元素类型、空矩阵/空行、不等长行、维度不匹配、NaN/Infinity、乘积和累加溢出、参数错误时机、协程启动与快照时机、并发顺序、失败隔离、原生调用线程、GIL 心跳、取消后原生任务结束及实际扩展路径。

## 从手册重建与清理重编译

在隔离临时目录 clone 当前正式仓库历史，预置教材，让新课 practice 从不存在开始。最终复走路径含中文和空格：`含空格的最终实验仓库/ffi-lab/07-python-cpp-async-matrix/practice`。

- 依次执行 `uv init --bare --vcs none --no-workspace`，从手册的 13 个完整文件块建立根忽略规则和 12 份项目文件；没有从 reference 复制练习源码。
- 通过 `touch` 创建 0 字节 py.typed，uv 生成锁文件、环境与产物。最终 14 份项目文件（包含锁文件和空标记）与成品逐字节一致。
- 手册共 27 个标注的 bash 命令块，实际执行 24 个，包括稍后单独执行的教材提交。跳过的三块仅为 sudo 安装、uv 安装器和 Git 身份占位配置；临时提交通过进程环境使用验证专用身份。
- 配置阶段只安装开发工具，不提前要求尚未写出的源码；随后构建、演示与静态检查均通过。
- 实际执行显式重新安装、删除本课环境/构建/缓存后的重建、锁文件检查，以及从仓库根目录和 /tmp 运行。各轮完整测试均为 49 项通过。
- 构建日志确认 scikit-build-core 1.1.1 调用 CMake 4.2.3，找到 CPython 3.12.15 与 pybind11 3.1.0，由 Ninja 编译并链接；实际编译参数包含 C++17、Release 优化和全部警告检查，没有启用 fast-math。

## GIL、原生加载与重编译故障对照

以下操作只发生在临时练习副本，所有源码与原生文件均已恢复：

1. 临时移除绑定中的 `call_guard<gil_scoped_release>`，显式重新构建，再运行单项原生心跳测试。得到 `1 failed, 48 deselected`，失败消息为 `no heartbeat while the native call was active`，实际计数为 0。
2. 恢复 GIL 释放并重建，全部 49 项测试通过。观察辅助代码只转发真实原生调用，使用 profiler 标记其进入/退出；测试期间临时延长 Python 切换时间片，防止调用边界前的调度被误计为心跳，结束后恢复原函数、profiler 与时间片。
3. file 确认扩展是 x86-64 ELF 共享库，nm -D 确认导出 PyInit__core。临时移走已安装 .so，在新进程以 `-I -m cpp_matrix` 启动，退出码为 1，报告原生文件缺失的 ImportError；恢复后得到正常矩阵结果，确认没有 Python 算法接管。
4. 将纯 C++ 输出临时改为每项加 1：未重编译时，新进程仍得到 `[[6.0]]`；执行 `uv sync --locked --reinstall-package py-cpp-async-matrix` 后得到 `[[7.0]]`。恢复源码并重新构建后，完整 49 项测试、Ruff 与 mypy 再次通过。
5. 恢复后的原生源码相对临时提交没有差异，随后重新构建源码包和 wheel 并检查内容。

## 源码包、独立 wheel 和类型信息

实际执行 `uv build`，先创建源码包，再从源码包编译 wheel：

```text
py_cpp_async_matrix-0.1.0.tar.gz
py_cpp_async_matrix-0.1.0-cp312-cp312-linux_x86_64.whl
```

源码包包含 14 份完整项目文件和生成的 PKG-INFO，共 15 份文件。逐份与项目内容比较通过，包括 C++、CMake、Python 包、测试、README、uv.lock 和 py.typed；没有环境或缓存。

wheel 共 9 份文件：三个 Python 源码、_core.pyi、空 py.typed、原生 .so，以及 METADATA/WHEEL/RECORD。Python/类型文件与源码逐字节一致，未包含环境或构建目录。

独立 `.venv-wheel` 验收结果：

- `--no-deps` 安装 wheel 后，使用 `-I` 运行完整普通演示和真实原生调用成功；扩展路径位于该环境的 site-packages/cpp_matrix，运行时无需安装 pybind11/scikit-build-core。
- 从 uv.lock 导出 dev 组，用 `--require-hashes` 安装测试工具；在 wheel 环境运行同样 49 项集成测试，全部通过。
- 从 /tmp 使用 wheel 环境的 mypy 检查安装后的包，正确调用返回 list[list[float]]，严格类型检查通过。
- 故意把结果赋给 str、传字符串元素、少传参数、多传参数，分别报告 assignment、list-item、call-arg、call-arg，共四处预期错误，退出码为 1。没有缺失包或类型信息的错误。

## Git 流程与教材一致性

仅在临时 clone 实际执行三个学习提交：

```text
chore: configure Python C++ async matrix project
feat: call C++ matrix multiplication asynchronously from Python
test: verify Python C++ async matrix behavior
```

随后执行教材维护提交：

```text
docs: add verified Python C++ async matrix lesson
```

每个提交均执行对应验证、状态和差异检查、明确路径暂存、暂存区审阅、提交和后续状态/历史检查。临时练习的 14 份受控文件包含源码、配置、测试、项目说明、版本文件、锁文件和空类型标记；最终临时工作区干净，环境、缓存、构建、分发和原生二进制未进入历史。

交付检查包括手册文件块/成品一致性、本地 Markdown 链接、围栏、命令工作目录、忽略规则以及新增文本空白。前六课和番外的 168 份既有教材、成品与练习文件 SHA-256 与开始时一致；根 .gitignore 保持原内容，正式暂存区保持原状。

正式仓库只更新根课程索引和新增本课教材；本课 practice 未创建。reference 按现有规则作为被忽略的本地成品保留。

## 验证范围

只声明本机 Ubuntu/Linux x64、常规 CPython 3.12.15 和上表工具链下的结果。未验证其他系统、CPU 架构、其他 Python 小版本、PyPy、自由线程解释器、最低编译器版本、manylinux 修复、跨平台 wheel 或 PyPI 发布。

使用标准库线程池和 asyncio 取消语义，没有原生抢占取消。输入快照复制容器，不深拷贝自定义数值对象的状态；其他线程并发修改正在复制的输入不属于支持范围。输入/输出转换仍需要 GIL，不保证巨大输入没有事件循环暂停。

极大内存分配与尺寸溢出分支没有用实际超大矩阵触发。uv.lock 固定项目/开发依赖，直接构建依赖与 Ninja 由配置固定；构建的间接依赖、CMake 和系统编译器不因此完全锁定，不声明跨机器二进制可复现。
