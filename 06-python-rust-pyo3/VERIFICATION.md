# 第六课验证记录

验证日期：2026-10-25（Asia/Singapore）。对应本课 [README.md](README.md) 与本地 [reference/](reference/) 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x86-64，glibc |
| 终端 / Git | zsh；手册自动复走使用 bash / Git 2.53.0 |
| uv | 0.13.5 |
| Python | uv 托管 CPython 3.12.15 |
| Rust / Cargo | 1.99.1，stable-x86_64-unknown-linux-gnu |
| Rust edition / 声明最低版本 | 2024 / 1.85；未以旧工具链复测 |
| rustfmt / Clippy | 1.10.0-stable / 0.1.99 |
| 系统链接工具 | GCC 15.2.0 |
| PyO3 / Maturin | 0.30.1 / 1.15.0 |
| pytest / Ruff / mypy | 9.1.1 / 0.17.2 / 2.4.0 |
| crate-type / 构建 profile | cdylib / release |
| 模块后缀 | .cpython-312-x86_64-linux-gnu.so |
| wheel 标签 | cp312-cp312-linux_x86_64 |

直接依赖版本见成品的 pyproject.toml 与 Cargo.toml，间接依赖分别由 uv.lock 和 Cargo.lock 固定。未启用 abi3、Tokio、NumPy 或第三方数值计算库。

## 工具准备边界

使用已有 Rust、rustfmt、Clippy、uv、系统链接工具和托管 Python。实际执行 `uv python install 3.12.15 --no-bin`，报告该版本已经安装；解释器路径和 SOABI 检查通过。

没有执行 sudo、Rust 安装器或更新、uv 安装器、Git 身份占位配置，也没有切换系统 Python 3.14。首次获取整个 CPython 运行时未验证，已有运行时下的编译和加载已经验证。

实际联网获取 PyPI 开发工具、Maturin 和 crates.io 的 PyO3 依赖。验证进程使用 `/tmp` 下的 UV_CACHE_DIR、CARGO_HOME，并以 UV_LINK_MODE=copy 安装 Python 依赖；没有修改用户全局 uv、Cargo 或 Git 配置。

## 成品安装、编译与运行

实际执行 Cargo 锁文件生成、Python 锁文件生成、安装和编译、测试及静态检查；还执行根首页新增的第六课成品命令，以及源码包到 wheel 的构建。

关键输出：

```text
add(2, 3) = 5.0
collected 20 items
20 passed
All checks passed!
5 files already formatted
Success: no issues found in 4 source files
Finished `dev` profile [unoptimized + debuginfo]
```

rustfmt 检查没有差异；Clippy 使用 `PYO3_PYTHON="$PWD/.venv/bin/python"` 选择项目解释器，`--locked --all-targets -- -D warnings` 通过。

原生扩展实际位于 `src/rust_add/_core.cpython-312-x86_64-linux-gnu.so`。Python 包通过 editable 安装读取源码目录；这与第五课的安装布局不同。函数说明为 `Add two numbers using Rust f64 arithmetic.`，文本签名为 `(a, b)`。

## 从手册代码块重建项目

在隔离临时目录 clone 正式仓库现有历史，保留第五课尚未提交教材的临时副本，令第六课 practice 从不存在开始。练习路径包含中文和空格：`含空格的实验仓库/06-python-rust-pyo3/practice`。

- 实际执行 uv init，再从手册 11 个完整文件块写入根忽略规则和 10 份项目文件；练习源码没有从 reference 复制。
- 使用 touch 创建 0 字节 py.typed，uv 与 Cargo 各自生成锁文件。11 份项目手写文件及两份生成锁文件与成品逐字节一致，共 13 份项目文件。
- 手册共 25 个 bash 命令块，验证其中 21 个，包括最后单独执行的教材维护提交。跳过的四块仅为 sudo、Rust 安装器、uv 安装器及 Git 身份占位配置；临时提交身份通过进程环境提供。
- 确认先生成静态 Python 项目锁文件、以 `--no-install-project` 安装开发工具的流程可行；随后写 Rust 项目，生成 Cargo.lock，再进行锁定构建，无隐含的 Rust 初始化或占位源码步骤。
- 安装、构建、演示、Python/Rust 静态检查、测试、显式重新编译安装、清理重建、异目录运行、打包和诊断均实际执行。
- 清理同时移除 src 中的 editable 扩展、Cargo target、Python 环境与缓存；从保留的两套锁文件重新安装和编译后，测试与检查仍通过。
- 手册流程中的四次 pytest 均为 20 项通过。从仓库根目录和 `/tmp` 使用项目解释器启动，均得到 5.0，未设置 PYTHONPATH。
- 根据实测补充了异常 notes 说明，并按最终手册单独复验诊断代码块，输出与文档逐行一致。

## 数值与错误行为

20 项集成测试实际经过 Rust：正数、负数、正负混合、零、小数、关键字参数、bool、2**53 附近整数精度、NaN、正负 Infinity 和浮点溢出；还覆盖五类非法值在两处参数中的使用，以及缺少参数、多余参数、未知关键字与原生模块身份。

返回值为 Python float，计算在 native/arithmetic.rs 中完成。没有 Python 加法实现或 mock。默认转换接受 bool，非有限浮点按 f64 规则传播，不增加有限值或任意精度整数保障。

PyO3 0.30.1 在本机为 TypeError 添加参数 notes，例如 `while processing 'a'`；这不在 `str(error)` 中，pytest 的 match 会包含它。最终诊断显式读取 notes，输出：

```text
5.0
TypeError
must be real number, not str
while processing 'a'
```

数量和关键字错误只断言 TypeError，非法类型另外确认出错参数上下文，没有照搬 pybind11 的整段错误文本。

## 原生加载与重编译检查

以下故障注入只发生在临时练习项目：

- file 确认为 x86-64 ELF 共享库，nm -D 确认导出 PyInit__core，公开函数与 `_core.add` 是同一对象。
- 暂时移走 src/rust_add 中的扩展，在新 Python 进程以 `-I -m rust_add` 启动，退出码为 1，抛 `ModuleNotFoundError: No module named 'rust_add._core'`。恢复文件后正常输出 5.0，证明没有 Python 备用实现接管。
- 临时将纯 Rust 计算改为 `a + b + 1.0`：未重新安装时新进程仍得到 5.0；执行 `uv sync --locked --reinstall-package py-rust-pyo3-add` 后得到 6.0；恢复源码并再次安装后回到 5.0。
- 恢复后重新执行 20 项测试、Ruff、mypy、rustfmt 和 Clippy，全部通过，练习源码相对其提交历史没有残留差异。

## 源码包、wheel 和安装后的类型信息

uv build 实际调用 Maturin 创建源码包，再从源码包编译 wheel：

```text
py_rust_pyo3_add-0.1.0.tar.gz
py_rust_pyo3_add-0.1.0-cp312-cp312-linux_x86_64.whl
```

源码包包含 13 份完整项目文件与生成的 PKG-INFO，共 14 项；逐份与原项目文件比较字节内容通过，包括 Cargo.toml 和两套锁文件。没有环境、target、dist、检查缓存、pycache 或 editable 原生扩展。

Cargo package 报告缺少发布元数据，这是私有教学项目未填写发布信息的提示；命令退出成功，源码包到 wheel 的编译通过，不把它混同于 Clippy 代码警告。

wheel 包含 Python 源码、_core.pyi、空 py.typed、原生扩展、常规分发元数据和 Maturin 自动生成的依赖 SBOM；用户不需要手写这些生成文件。

先在独立 `.venv-wheel` 中以 `--no-deps` 安装 wheel，使用 `-I` 成功运行演示；模块路径位于该环境的 site-packages/rust_add，运行时不需要 PyO3/Maturin Python 包。随后从 uv.lock 导出 dev 组，用 `--require-hashes` 安装工具，在这个 wheel 环境中运行全部 20 项测试，全部通过。

从项目外目录使用 wheel 环境的 mypy 进行严格类型检查：

- `result: float = add(2, 3)` 通过。
- 返回值赋给 str、字符串参数、缺少参数、多余参数产生四处预期错误，包含 assignment、arg-type、call-arg 分类。

这验证了 wheel 中的 stub、公开导出和 py.typed 生效，而不是仅检查项目源目录中的类型文件。

## Git 与交付一致性

只在临时 clone 实际执行三个学习提交：

```text
chore: configure Python Rust addition project
feat: call Rust addition from Python with PyO3
test: verify Python to Rust addition
```

由于正式工作副本第五课也尚未提交，教材维护命令明确包含第五、六课和共享根文件，并在临时 clone 验证这一教材提交：

```text
docs: add verified Python native addition lessons
```

每个提交都按手册执行对应验证、状态与差异检查、明确路径暂存、暂存区审阅、提交及后续状态/历史检查。临时练习的 13 份受控文件包含两套锁文件和空类型标记；环境、target、dist、缓存和生成扩展均未进入历史，临时仓库最后干净。

检查通过本地 Markdown 链接、围栏、手册文件块与成品一致性、命令目录、忽略规则及新增文本空白检查。前五课和番外共 113 份原有教材、成品与练习文件的 SHA-256 与开始时一致；根 .gitignore 内容未变化，正式暂存区保留原样。

真实仓库没有代用户暂存、提交或推送，第六课 practice 未创建；第五课尚未提交的教材保留，reference 继续按既有规则作为本地成品保存。

## 验证范围

仅声明本机 Ubuntu/Linux x64、CPython 3.12.15、Rust 1.99.1、指定版本的 uv/PyO3/Maturin 下的结果。未测试最低 Rust 版本、其他 Python 小版本、其他系统和架构、自由线程解释器、PyPy、跨平台 wheel、manylinux 修复、abi3 或远端发布。

未添加类、矩阵、异步、主动释放 GIL、自定义数值校验或实验性自动 stub 生成。Python 开发依赖、Rust 依赖和 Maturin 构建后端由各自声明约束，但系统工具链不由这些锁文件固定，不宣称跨机器二进制可复现。
