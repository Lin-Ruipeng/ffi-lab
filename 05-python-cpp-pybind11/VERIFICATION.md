# 第五课验证记录

验证日期：2026-10-25（Asia/Singapore）。对应本课 [README.md](README.md) 与本地 [reference/](reference/) 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x86-64，glibc |
| 终端 / Git | zsh；手册自动复走使用 bash / Git 2.53.0 |
| uv | 0.13.5 |
| 项目 Python | uv 托管 CPython 3.12.15，具备配套 Python.h |
| 系统 Python | 3.14.4，未用于编译、运行本课项目 |
| CMake | 4.2.3 |
| 原生编译器 / 标准 | G++ 15.2.0 / C++17，无编译器语言扩展 |
| C++ 警告检查 | -Wall -Wextra -Wpedantic -Werror |
| CMake generator / Ninja | Ninja / 1.13.2，由后端按版本配置提供 |
| pybind11 | 3.1.0 |
| scikit-build-core | 1.1.1 |
| pytest / Ruff / mypy | 9.1.1 / 0.17.2 / 2.4.0 |
| 模块后缀 | .cpython-312-x86_64-linux-gnu.so |
| wheel 标签 | cp312-cp312-linux_x86_64 |

依赖声明与生成的 `uv.lock` 位于本地成品中；手册完整提供所有手写文件，锁文件通过 uv 生成。

## 工具准备与环境边界

使用已有 uv、CMake、G++、Git 和 uv 托管的 Python。实际执行 `uv python install 3.12.15 --no-bin`，返回 `Python 3.12.15 is already installed`；解释器路径与 Python.h 断言通过。没有执行 sudo、uv 安装器或 Git 身份占位配置，也没有切换系统 Python。

实际联网读取 PyPI 官方元数据、下载 Python 开发/构建依赖并编译项目。验证进程将 `UV_CACHE_DIR` 指向 `/tmp`，以 `UV_LINK_MODE=copy` 使用临时缓存；这些是验证进程设置，没有写入用户全局 uv 配置。首次下载整个 CPython 运行时的过程未验证，现有运行时的使用、构建和加载已经验证。

## 成品安装、构建和运行

实际执行根首页的第五课成品命令，以及最终配置下的显式重新安装、测试、静态检查和 `uv build`。

关键结果：

```text
add(2, 3) = 5.0
collected 20 items
20 passed
All checks passed!
5 files already formatted
Success: no issues found in 4 source files
```

构建日志确认 scikit-build-core 1.1.1 使用 CMake 4.2.3，找到 Python 3.12.15 的 Interpreter 与 Development.Module、pybind11 3.1.0，由 Ninja 编译两个 C++ 源文件并链接原生库。C++ 编译的警告检查通过。

安装后的模块位于项目 `.venv/lib/python3.12/site-packages/cpp_add/`；Python 源码通过 editable 安装从 `src` 读取。函数 docstring 为：

```text
add(a: typing.SupportsFloat | typing.SupportsIndex, b: typing.SupportsFloat | typing.SupportsIndex) -> float
```

运行时接受的数值转换协议比手写 stub 中面向本课调用者的 `float` 接口更广。类型声明没有被当作原生实现，也没有在 Python 层添加加法替代。

## 从手册代码块重建项目

在隔离临时目录 clone 当前正式仓库历史，预置教材文件，让第五课 `practice/` 从不存在开始。验证路径包含中文与空格：`含空格的实验仓库/05-python-cpp-pybind11/practice`。

- 按文档顺序实际执行 `uv init --bare --vcs none --no-workspace`，再从手册的 12 个完整文件块写入根忽略规则和 11 份项目文件；没有从 reference 复制练习源码。
- `touch` 创建 0 字节的 `py.typed`，uv 自动创建锁文件、虚拟环境及编译产物。12 份项目手写文件和生成的锁文件均与最终成品逐字节一致。
- 手册有 23 个 bash 命令块，实际验证 20 个，包括最后单独执行的教材维护提交。跳过的三块仅为 sudo 安装、uv 安装器和 Git 身份占位配置；临时 Git 身份通过进程环境提供。
- 实际验证先只安装开发工具、再编译当前项目的流程，不依赖尚未创建的源码。版本选择、依赖锁定、构建、演示、检查、测试、显式重编译、清理重建、打包和诊断均成功。
- 清理移除了项目 `.venv`、构建目录、分发包和检查缓存，然后从锁文件重新安装并重新编译；测试、检查与演示仍通过。
- 手册流程中的四次 pytest 均为 20 项通过；从仓库根目录和 `/tmp` 使用项目解释器运行均输出 `add(2, 3) = 5.0`，未设置 PYTHONPATH。

## 行为、原生加载与重编译

20 项测试覆盖正数、负数、正负混合、零、小数、关键字参数、bool 数值转换、2**53 附近整数精度、NaN、正负 Infinity、浮点溢出；错误测试覆盖五类非法值在两处参数中的使用、缺少参数、多余参数、未知关键字。错误均为 TypeError，测试只匹配稳定的错误片段。

原生加载的补充检查均只在临时项目执行：

- `file` 确认为 x86-64 ELF 共享库，`nm -D` 确认导出 `PyInit__core`。公开函数对象与 `_core.add` 相同，模块路径确实指向 `.so`。
- 暂时移走已安装的 `.so`，使用独立 Python 进程以 `-I -m cpp_add` 启动，退出码为 1，错误为 `ImportError: ... cannot open shared object file`；恢复文件后重新得到 5.0。没有 Python 备用实现接管。
- 暂时将纯 C++ 返回式改为 `a + b + 1`：未重编译时新进程仍得到 5.0；执行 `uv sync --locked --reinstall-package py-cpp-pybind11-add` 后得到 6.0；恢复源码并再次编译后回到 5.0，20 项测试与静态检查重新通过。

editable 安装会包装加载器，因此测试不要求 loader 的具体实现类；采用实际文件、导出身份与移走原生库的故障检查验证调用链。

## 源码包、wheel 与安装后的类型信息

`uv build` 实际先生成源码包，再从源码包编译 wheel：

```text
py_cpp_pybind11_add-0.1.0.tar.gz
py_cpp_pybind11_add-0.1.0-cp312-cp312-linux_x86_64.whl
```

源码包包含 13 份完整项目文件及生成的 PKG-INFO，共 14 项；逐份比对项目文件的字节内容通过。最终使用 `sdist.inclusion-mode = "explicit"`，没有包含 `.venv`、`.venv-wheel`、build、dist 或检查缓存。验证中发现单独使用 include 与 manual 模式会收集不需要的环境文件，因此已修正配置、手册并从头复验最终版本。

wheel 包含三个 Python/类型源码文件、空 `py.typed`、原生 `.so` 及 METADATA、WHEEL、RECORD；与成品对应文件核对通过。

在独立 `.venv-wheel` 中，以 `--no-deps` 安装 wheel，使用 `-I` 成功运行演示；原生路径位于 `.venv-wheel`，运行时不需要 pybind11、scikit-build-core 等 Python 包。随后从 uv.lock 导出 dev 组并以 `--require-hashes` 安装测试工具，在该 wheel 环境中独立运行全部 20 项测试，全部通过。

从项目外的目录，使用 wheel 环境中的 mypy 检查安装后的包：

- `result: float = add(2, 3)` 通过严格类型检查。
- 把返回值赋给 str、传字符串、缺少参数、多传参数得到四处预期错误，包含 assignment、arg-type、call-arg 分类。这确认随 wheel 安装的 stub、重新导出及 py.typed 均可工作。

## Git 流程与教材一致性

仅在临时 clone 实际执行三个学习提交：

```text
chore: configure Python C++ addition project
feat: call C++ addition from Python with pybind11
test: verify Python to C++ addition
```

随后实际执行教材维护提交：

```text
docs: add verified Python to C++ pybind11 lesson
```

每个提交均包含对应的验证、状态检查、差异检查、明确路径暂存、暂存区审阅、提交和提交后状态/历史检查。临时项目有 13 份受控文件，包含源码、配置、测试、项目说明、版本文件、锁文件与空类型标记；虚拟环境、缓存、原生二进制与打包产物没有进入历史，最终临时工作区干净。

交付检查通过本地 Markdown 链接、围栏、文件块与成品一致性、命令目录和忽略规则检查；根 diff 与新教材文件空白检查通过。前四课和番外共 98 份原有教材、成品与练习文件的 SHA-256 与工作开始时一致。

正式仓库的暂存区保持原状，没有代用户暂存、提交或推送；第五课 practice 未创建。reference 继续作为被忽略的本地成品保留，根索引已说明 clone 后应按手册重建练习。

## 验证范围

只声明 Ubuntu/Linux x64、uv 0.13.5、CPython 3.12.15、当前编译器与依赖下的结果。没有验证其他 Python 小版本、系统、架构、PyPy、自由线程解释器、跨平台 wheel、manylinux 修复或 PyPI 发布。

未加入类、矩阵、异步、NumPy、自定义数值校验或释放 GIL 的逻辑。普通 pybind11 扩展未声明跨 Python 小版本 ABI 稳定。

uv.lock 覆盖项目及开发依赖；直接构建依赖与 Ninja 由各自配置固定版本，隔离构建的间接依赖、系统 CMake 和编译器不由该锁文件完整固定。这里不宣称跨机器、跨时间的二进制可复现构建。
