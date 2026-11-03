# 第八课：Python 异步调用 Rust 矩阵乘法

这一课把第六课的 Rust 加法扩展成动态二维矩阵乘法，保持第七课的 Python 异步接口：协程复制输入，默认线程池调用 Rust，Rust 在计算期间释放 GIL，结果或异常再回到 `await`。你会亲手完成配置、实现、类型声明、演示、真实集成测试、双锁文件、独立 wheel 验收和分阶段 Git 提交。

沿用 uv 0.13.6、CPython 3.12.15、Rust 2024 edition、PyO3 0.30.1、Maturin 1.15.0、pytest、Ruff 和严格 mypy。实测 Ubuntu/Linux x64、Rust/Cargo 1.99.1。本地成品在 [reference/](reference/)，完整验证与限制见 [VERIFICATION.md](VERIFICATION.md)。`reference/` 继续按根规则忽略，不随 clone 分发；本手册完整提供需要手写的文件，成品不存在时也能从零学习。

## 0. 先理解数学、异步和所有权边界

### 0.1 动态矩阵与公开接口

矩阵乘法是左边一行与右边一列做点积，不是逐个位置相乘。`m×n` 乘 `n×p` 得到 `m×p`：

```text
A = [[1, 2, 3],       B = [[ 7,  8],
     [4, 5, 6]]           [ 9, 10],
                          [11, 12]]

C = [[58, 64],
     [139, 154]]

C[0][0] = 1×7 + 2×9 + 3×11 = 58
C[row][col] = 对所有 k 累加 A[row][k] × B[k][col]
```

公开接口如下；这里只先看签名，稍后创建完整文件：

```python
async def multiply_async(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]: ...
```

允许列表、元组等非文本二维序列，支持位置参数和 `a=`、`b=` 关键字，无默认值。至少一行一列，各行等长，左列数等于右行数；不接受字符串、字节序列或生成器作为矩阵或行。`float` 类型标注允许传 `int`，返回二维 list，元素始终是 Python float。

沿用 PyO3 的默认数值转换：bool 可转为 1.0/0.0，字符串不会按数字解析。Rust f64 是二进制浮点，小数有舍入误差，Python 大整数转换后可能失去精度。输入必须有限，乘法或中间累加一旦出现非有限值就失败；这与第七课的行为对应。

| 情况 | Python 侧结果 |
| --- | --- |
| 合法矩形矩阵 | await 得到 list[list[float]] |
| 非法容器、行或元素类型 | TypeError |
| 空矩阵、空行、不等长行、维度不符、NaN/Infinity | ValueError |
| 乘积或中间累加出现非有限值 | OverflowError |
| Rust 输出 try_reserve_exact 返回分配失败 | MemoryError；不承诺处理进程的一切内存耗尽 |

### 0.2 协程、工作线程与 detach

```text
Python 事件循环线程                         默认线程池的某个工作线程

multiply_async(a, b) → 协程对象
await / create_task / gather 启动协程
    ├─ 两层容器复制为 tuple
    └─ await asyncio.to_thread(...) ────────► PyO3 持有 GIL
          │                                   将输入转换为自有 Vec<Vec<f64>>
          │                                   move 到 detach 闭包
          │                                   ▼ Python::detach 释放 GIL
其他协程、定时器继续运行                      纯 Rust 形状/有限值校验和三重循环
          │                                   返回 Result<Matrix, MatrixError>
          │                                   ▼ detach 结束，重新持有 GIL
          │                                   map_err 映射错误；PyO3 转换结果
          ◄──────────────────────────────── Future 完成，唤醒等待的协程
await 得到结果，或在等待处抛出异常
```

普通调用 `async def` 创建协程，函数体通常尚未执行。`await` 进入它，`create_task/gather` 将它交给事件循环调度。仅把同步原生调用包在 async def 中仍会阻塞事件循环；本课用 `asyncio.to_thread` 让工作线程执行它。官方说明释放 GIL 的扩展也适合用 to_thread 承载 CPU 计算。[Python 协程、任务与线程](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.to_thread)

`Python::detach` 在**当前工作线程**临时释放 GIL，闭包返回后重新持有 GIL；它本身不创建线程，也不会把 Rust 函数变成 Future。脱离解释器期间只操作 Rust 自有数据，不访问 Python 对象或回调。[PyO3 并行说明](https://pyo3.rs/v0.30.1/parallelism)、[固定版本 detach API](https://docs.rs/pyo3/0.30.1/pyo3/marker/struct.Python.html#method.detach)

快照在**协程开始执行时**建立，不是在创建协程对象时。复制的是两层容器，面向不可变的 int/float；自定义数值对象的内部状态不会深拷贝。其他线程不应在快照过程中修改输入。完成快照后修改原列表不会影响任务。快照、参数转换和结果转换仍持有 GIL，大输入可能让事件循环短暂停顿。

### 0.3 与前几课的对应关系

| 已学内容 | 本课保留或替换 |
| --- | --- |
| 第六课 uv + Maturin + Cargo + PyO3 | 保留工具链、混合包、双锁文件与严格检查 |
| 第七课 asyncio.to_thread + Python 快照 | 保留异步接口、gather、取消语义与验证方法 |
| 第七课 `vector<vector<double>>` | 替换为 Rust 自有 `Vec<Vec<f64>>` |
| 第七课 `call_guard<gil_scoped_release>` | 替换为 `Python::detach` 的闭包 |
| 第四课 Node AsyncTask | 本课由 Python 默认线程池调度；Rust 函数仍同步 |

本课不增加 Tokio、pyo3-async-runtimes、Rayon、NumPy、BLAS 或多进程；先把同一异步模型下的绑定、所有权和错误边界学清楚。每个任务是一个工作线程上的顺序点积算法，并发请求不等于单次乘法内部并行，也不承诺固定加速比。

### 0.4 最终目录

```text
08-python-rust-async-matrix/
├── README.md                         # 本手册
├── VERIFICATION.md                   # 实测记录
├── reference/                        # 本地成品，不提交
└── practice/                         # 由你从零创建
    ├── .python-version
    ├── pyproject.toml
    ├── uv.lock                       # uv 生成，提交
    ├── Cargo.toml
    ├── Cargo.lock                    # Cargo 生成，提交
    ├── README.md                     # 你手写的项目说明
    ├── native/
    │   ├── matrix.rs                 # 纯 Rust 校验、乘法和错误
    │   └── lib.rs                    # PyO3 绑定、detach 与异常映射
    ├── src/rust_matrix/
    │   ├── __init__.py                # 快照和异步公开接口
    │   ├── __main__.py                # 结果、并发与错误演示
    │   ├── heartbeat.py
    │   ├── _core.pyi                 # 同步原生函数的声明
    │   ├── py.typed                  # 0 字节文件
    │   └── _core.*.so                # editable 安装生成
    ├── tests/test_matrix.py
    ├── .venv/                        # 本课环境
    ├── .venv-wheel/                  # 独立 wheel 验收环境
    ├── target/                       # Cargo 构建缓存
    ├── build/                        # 临时导出的验收依赖
    └── dist/                         # 源码包、wheel
```

uv 管理解释器、环境和 Python 依赖；Maturin 组织混合包并调用 Cargo；Cargo/rustc 管理 Rust 依赖、编译和链接；PyO3 做绑定、转换和 GIL 管理。运行时加载同一 Python 进程内的共享库，不启动 Rust 子进程，也不解释 .rs 源码。

## 1. 检查并准备工具链

**工作目录：任意目录。** 先检查已有工具：

<!-- verify: tools -->
```bash
uv --version
rustup show active-toolchain
rustc --version
cargo --version
rustfmt --version
cargo clippy --version
cc --version
git --version
file --version
nm --version
```

实测 Rust/Cargo `1.99.1`、rustfmt `1.10.0-stable`、Clippy `0.1.99`、uv `0.13.6`。PyO3 0.30.1 的最低 Rust 要求为 1.85；本课只声明实际使用的工具链结果。Rust edition 与编译器版本是不同概念。

只有缺少链接工具、Git 或 curl 等系统工具时，才在任意目录执行 Ubuntu 准备命令：

<!-- verify: skip-sudo -->
```bash
sudo apt-get update
sudo apt-get install -y build-essential git curl file binutils
```

只有缺少 Rust 时，按 [Rust 官方安装说明](https://rust-lang.org/tools/install/)执行：

<!-- verify: skip-rust-install -->
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
. "$HOME/.cargo/env"
rustup component add rustfmt clippy
```

已有 Rust 但缺少组件时，只执行最后一行；工具链过旧且依赖报最低版本错误时，有意运行 `rustup update stable` 后再检查版本。本次使用现有工具链，未执行安装或更新。

只有缺少 uv 时，按 [uv 官方说明](https://docs.astral.sh/uv/getting-started/installation/)安装实测版本：

<!-- verify: skip-uv-install -->
```bash
curl -LsSf https://astral.sh/uv/0.13.6/install.sh | sh
. "$HOME/.local/bin/env"
uv --version
```

环境文件适用于官方脚本的默认安装位置。已有 uv 时跳过，不覆盖系统 Python。

准备并检查 uv 托管的 Python：

<!-- verify: python-install -->
```bash
uv python install 3.12.15 --no-bin
uv python find 3.12.15
uv run --no-project --python 3.12.15 python -c 'import pathlib, sys, sysconfig; header = pathlib.Path(sysconfig.get_path("include")) / "Python.h"; print(sys.version); print(sys.executable); print(sysconfig.get_config_var("SOABI")); print(header); assert header.is_file()'
```

已有该版本时，安装命令报告已安装即可。`--no-bin` 不向 PATH 增加 Python 命令。输出应为 3.12.15，SOABI 类似 `cpython-312-x86_64-linux-gnu`，绝对安装路径因机器而异，Python.h 断言应成功。

系统 Python 3.14 与本课的 uv 托管 Python 3.12 是不同解释器；本课不会修改 `/usr/bin/python3`。本次没有验证首次下载整个 Python 运行时的过程。初次获取 Python、Cargo crate 和 Python 依赖需要联网。[uv Python 管理](https://docs.astral.sh/uv/concepts/python-versions/)

## 2. 检查现有仓库和 Git 状态

**工作目录：仓库根目录。** 替换下面唯一的 clone 路径占位符：

<!-- verify: root -->
```bash
cd "/请替换为你的实际路径/ffi-lab"
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
git diff --cached --name-only
cat .gitignore
```

保留现有分支和历史，不重新 `git init`。若暂存区包含其他工作，先按自己的安排处理；`git commit` 会提交整个暂存区，只有没有无关暂存内容时才执行本课提交。不要自动 reset、stash 或覆盖旧练习。

根 `.gitignore` 已覆盖本课产物，通常无需修改。若在另一个工作副本缺少规则，按下方完整内容核对并补齐缺失部分，保留原有额外规则：

<!-- file: root/.gitignore -->
```gitignore
# 每一课独立安装依赖、编译源码。
node_modules/
build/
dist/
target/
*.node
*.tsbuildinfo
npm-debug.log*
reference/

# Python 虚拟环境、缓存和原生扩展产物。
.venv/
.venv-wheel/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/
*.so
*.pyd

# 编辑器和系统临时文件。
.vscode/
.DS_Store
*~
```

`Cargo.lock`、`uv.lock`、`.python-version`、`.pyi` 和空 `py.typed` 要提交。`reference/` 按原规则忽略，不使用 `git add -f`。若你补了忽略规则，在第一个里程碑检查后，将 `.gitignore` 单独加入该次暂存。

本次交付时第七课教材也尚未提交，共享根索引包含第七、八课。下面的学习提交仅涉及第八课 practice；末尾给出当前两课教材合并提交命令。已有 clone 的学习者无需重新提交教材。

检查身份：

<!-- verify: git-identity -->
```bash
git var GIT_AUTHOR_IDENT
```

只有身份未配置时才执行，替换自己的信息：

<!-- verify: skip-git-identity -->
```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

## 3. 初始化独立的 uv 项目

**从仓库根目录开始：**

<!-- verify: init -->
```bash
mkdir -p 08-python-rust-async-matrix/practice
cd 08-python-rust-async-matrix/practice
pwd
uv init --bare --vcs none --no-workspace --python 3.12.15 --name py-rust-async-matrix
mkdir -p native src/rust_matrix tests
```

`pwd` 应以 `ffi-lab/08-python-rust-async-matrix/practice` 结尾。`--bare` 只初始化基础配置；`--vcs none` 不创建嵌套 Git 仓库；`--no-workspace` 让每课独立管理 Python 依赖。若已有练习文件，从原进度继续，不重新覆盖。

**从这里到第 13 节结束，除非另有说明，所有路径和命令以 practice 为基准。** 每份文件内容完整提供，用编辑器亲手输入，不把 Markdown 围栏写入文件。

### 3.1 创建 `.python-version`

<!-- file: .python-version -->
```text
3.12.15
```

uv 根据它选择解释器；直接运行系统 `python3` 不会自动切换。

### 3.2 完整替换 `pyproject.toml`

<!-- file: pyproject.toml -->
```toml
[build-system]
requires = ["maturin==1.15.0"]
build-backend = "maturin"

[project]
name = "py-rust-async-matrix"
version = "0.1.0"
description = "Learn asynchronous Python to Rust matrix multiplication"
readme = "README.md"
requires-python = ">=3.12,<3.13"

[dependency-groups]
dev = ["pytest==9.1.1", "ruff==0.17.2", "mypy==2.4.0"]

[tool.maturin]
bindings = "pyo3"
python-source = "src"
module-name = "rust_matrix._core"
profile = "release"
locked = true
compatibility = "linux"
strip = true
include = [
  { path = ".python-version", format = "sdist" },
  { path = "uv.lock", format = "sdist" },
  { path = "Cargo.lock", format = "sdist" },
  { path = "tests/*.py", format = "sdist" },
]
exclude = [
  "src/rust_matrix/*.so",
  "src/rust_matrix/*.pyd",
  "**/__pycache__/**",
  "**/*.pyc",
  ".venv/**",
  ".venv-wheel/**",
  "target/**",
  "build/**",
  "dist/**",
  ".pytest_cache/**",
  ".ruff_cache/**",
  ".mypy_cache/**",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
target-version = "py312"
line-length = 88
extend-exclude = [".venv-wheel"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]
```

配置解释：

- 本课的 Python 分发包名为 `py-rust-async-matrix`，import 的包是 `rust_matrix`，内部扩展为 `rust_matrix._core`；名字各有用途，不要求所有字符串完全一样。
- `[build-system]` 固定 Maturin 后端；它在 uv 的隔离构建环境中运行，不需要全局安装，也不是本项目的运行时依赖。PyO3 是 Cargo crate，稍后写入 Cargo.toml。
- Python 限定为 3.12 系列，具体实测版本由 `.python-version` 指定；dev 组固定与前课一致的 pytest、Ruff、mypy；测试用 asyncio.run，不增加 pytest-asyncio。
- `python-source` 与 `module-name` 配置混合项目布局：Python 包在 src/rust_matrix，Rust 扩展作为包内 `_core`。[Maturin 混合项目布局](https://www.maturin.rs/project_layout)
- `profile = "release"` 选择 Rust 优化构建；`locked = true` 要求使用已经生成且匹配的 Cargo.lock。第 5 节生成 Cargo 锁文件后再编译当前项目。
- `compatibility = "linux"` 只构建本机 Linux wheel，不进行 manylinux 发布处理；`strip` 去掉二进制中的非必要符号信息。未开启 abi3，不宣称跨 Python 小版本 ABI 稳定。
- 源码包默认由 Cargo 提供文件集合；Cargo.toml 会给出明确的源码清单。Maturin 的 include 补充说明、锁文件和测试，exclude 排除 editable 二进制和缓存，不把 include 单独误当白名单。[Maturin 配置](https://www.maturin.rs/config)
- Ruff 检查 Python 风格和常见问题，mypy 使用严格模式；`.venv-wheel` 明确排除在 Ruff 目录扫描外。

### 3.3 编写项目说明 `README.md`

先记录最终项目的接口与操作方式，供以后单独进入项目时回顾。现在只创建文件，说明中的命令会在后续各节实际执行。

<!-- file: README.md -->
````markdown
# Python 异步调用 Rust：矩阵乘法

本项目使用 uv 0.13.6、CPython 3.12.15、PyO3 0.30.1、Maturin 1.15.0，
以及 Rust 2024 edition（实测 Rust/Cargo 1.99.1）。目标为 Ubuntu/Linux x64。
asyncio.to_thread 将同步原生调用交给默认线程池；Rust 计算期间释放 GIL。
运行时只依赖 Python 标准库与本包原生扩展。

## 安装与运行

需要 uv、Rust/Cargo、rustfmt、Clippy、系统 C 链接工具和 Git。
在本文件所在目录执行：

```bash
uv python install 3.12.15 --no-bin
cargo fetch --locked
uv sync --locked
uv run --no-sync python -m rust_matrix
uv run --no-sync python -m rust_matrix.heartbeat
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
```

2×3 乘 3×2 的结果为 [[58.0, 64.0], [139.0, 154.0]]，测试应为 49 项通过。
主程序还展示 gather 并发和 OverflowError。心跳次数和耗时随机器变化。
首次安装需要联网；uv 使用独立 .venv，不修改系统 Python。

## 接口与数据边界

```python
import asyncio
from rust_matrix import multiply_async


async def main() -> None:
    result = await multiply_async([[1, 2]], [[3], [4]])
    assert result == [[11.0]]


asyncio.run(main())
```

multiply_async(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]])
返回协程，await 后得到 list[list[float]]。支持位置参数和 a、b 关键字。
输入可用列表、元组等非文本序列；生成器和字符串不属于矩阵接口。
m×n 乘 n×p 得到 m×p，至少一行一列，各行等长。

创建协程不会执行函数体，也不会拍快照。协程开始执行时，先将两层
序列复制成 tuple，再交给线程池。快照完成后，修改原列表不会改变
任务的输入；调用者应避免其他线程在快照期间同时修改输入。
数值接口面向不可变的 int/float；不会深拷贝自定义数值对象的内部状态。
函数不修改输入，输出行相互独立。

PyO3 在持有 GIL 时将输入转换为 Rust 自有的 `Vec<Vec<f64>>`。
绑定把两份 Vec move 到 Python::detach 的闭包，在当前工作线程执行纯 Rust
校验和乘法。闭包不访问 Python 对象，返回后重新持有 GIL，映射错误并转换结果。
detach 不创建线程；异步调度来自 Python 线程池，不使用 Tokio 或 Rust async。
快照和 Python/Rust 转换仍需要 GIL，大输入可能让事件循环短暂停顿。

采用 PyO3 默认数值转换：bool 转为 1.0/0.0，字符串不按数字解析。
f64 存在小数舍入误差，2**53 附近的整数可能损失精度。
非法类型抛 TypeError，空矩阵、空行、不等长行、维度不兼容及 NaN/Infinity
抛 ValueError，乘法或中间累加产生非有限值抛 OverflowError。
Rust 输出分配通过 try_reserve_exact 检查，其返回的分配错误映射为 MemoryError；
这不是对整个进程内存耗尽的保障。参数数量/关键字错误在调用时抛出，
函数体与后台错误在 await 时传播。

asyncio.gather 保持结果的输入顺序；return_exceptions=True 可收集各项错误。
取消 Task 或超时只取消等待，已经运行的 Rust 计算仍会继续；asyncio.run
退出时会等待默认线程池清理。没有原生抢占取消或取消令牌。

## 修改、清理与打包

修改 Rust、绑定或 Cargo 配置后显式重编译：

```bash
uv sync --locked --reinstall-package py-rust-async-matrix
uv run --no-sync pytest
```

editable 安装从 src/rust_matrix 读取 Python 包和编译出的扩展。
cargo clean 不删除包目录里的扩展；只在本项目目录执行下列清理，保留源码和锁文件：

```bash
pwd
uv run --no-project --python 3.12.15 python - <<'PYCODE'
from pathlib import Path

for pattern in ("_core*.so", "_core*.pyd"):
    for path in Path("src/rust_matrix").glob(pattern):
        path.unlink()
PYCODE
cargo clean
rm -rf .venv .venv-wheel build dist .pytest_cache .ruff_cache .mypy_cache src/rust_matrix/__pycache__ tests/__pycache__
cargo fetch --locked
uv sync --locked --reinstall-package py-rust-async-matrix
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
uv build
uv venv --python 3.12.15 .venv-wheel
uv pip install --python .venv-wheel/bin/python --no-deps dist/*.whl
.venv-wheel/bin/python -I -m rust_matrix
```

uv build 先生成源码包，再从源码包编译 wheel。Cargo 的 include 与 Maturin
配置收集源码，即使 reference 被 Git 忽略也能打包。完整的独立 wheel 测试
和安装后类型检查见上一级实验手册。这里只验证本机 Linux wheel，
未启用 abi3、manylinux 修复、跨平台构建或上传。

## 版本控制

提交源码、配置、测试、说明、.python-version、uv.lock、Cargo.lock 和空 py.typed。
.venv、.venv-wheel、target、build、dist、缓存与原生二进制不提交。
reference 作为本地成品按根规则忽略；practice 由学习者创建。
uv.lock 锁定 Python 项目/开发依赖，Cargo.lock 锁定 Rust 依赖，构建后端版本
在 pyproject.toml 中固定；系统工具链不由这些锁文件固定。
````

### 3.4 生成 Python 锁文件并安装开发工具

<!-- verify: lock-dev -->
```bash
uv lock
uv sync --locked --no-install-project
uv run --no-sync python --version
uv run --no-sync pytest --version
uv run --no-sync ruff --version
uv run --no-sync mypy --version
```

此时尚未写 Rust 项目，先用 `--no-install-project` 只安装开发依赖。uv 自动生成 `.venv` 和 `uv.lock`，不要手写锁文件。配置中的 Python 项目信息是静态的，生成这个锁文件不需要编译 Rust。

以后用 `uv sync --locked` 检查并按锁文件安装；`uv run --no-sync` 只运行已安装环境，避免演示或排错时隐式重编译。[uv 锁定与同步说明](https://docs.astral.sh/uv/concepts/projects/sync/)

### 3.5 第一个里程碑：提交 Python 项目配置

上面的版本检查应成功，再提交配置与项目说明：

<!-- verify: commit-config -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 08-python-rust-async-matrix/practice
git -C ../.. add 08-python-rust-async-matrix/practice/.python-version 08-python-rust-async-matrix/practice/pyproject.toml 08-python-rust-async-matrix/practice/uv.lock 08-python-rust-async-matrix/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure Python Rust async matrix project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

普通 `git diff` 不显示未跟踪文件内容，所以暂存后的 `git diff --cached` 是检查这些新文件的关键一步。其他教材仍可能显示未提交，但不应出现在本次暂存区中。

## 4. 编写 Rust 配置与纯矩阵算法

### 4.1 `Cargo.toml`

<!-- file: Cargo.toml -->
```toml
[package]
name = "py-rust-async-matrix"
version = "0.1.0"
edition = "2024"
rust-version = "1.85"
publish = false
readme = "README.md"
include = [
  "Cargo.toml",
  "Cargo.lock",
  "pyproject.toml",
  ".python-version",
  "uv.lock",
  "README.md",
  "native/*.rs",
  "src/rust_matrix/*.py",
  "src/rust_matrix/*.pyi",
  "src/rust_matrix/py.typed",
  "tests/*.py",
]

[lib]
name = "_core"
path = "native/lib.rs"
crate-type = ["cdylib"]

[dependencies]
pyo3 = "=0.30.1"
```

包名 `py-rust-async-matrix` 用于 Cargo/分发，库名 `_core` 对应 Python 扩展，源码入口为 native/lib.rs。`crate-type = ["cdylib"]` 生成供 Python 加载的动态库；模块名还要与第 5 节的 #[pymodule] 和 Maturin 的 rust_matrix._core 对齐。

edition 2024 是语言规则版本；rust-version 声明最低 1.85，本课只在 1.99.1 实测。PyO3 使用精确版本 `=0.30.1`，Rust 间接依赖由稍后生成的 Cargo.lock 固定。沿用第六课的当前 PyO3/Maturin 配合方式，不额外启用旧教程中的 extension-module 特性。

`include` 明确列出源码包中的配置、双锁文件、Rust/Python 源码、类型信息、测试和说明；`publish = false` 表示不向 crates.io 发布。Maturin 会使用 Cargo 的文件集合构建源码包，再收集 Python 包。[Maturin 项目布局](https://www.maturin.rs/project_layout)

### 4.2 `native/matrix.rs`

<!-- file: native/matrix.rs -->
```rust
use std::mem::size_of;

pub type Matrix = Vec<Vec<f64>>;

#[derive(Debug)]
pub enum MatrixError {
    Invalid(String),
    Overflow,
    Allocation(String),
}

fn validate(matrix: &[Vec<f64>], name: &str) -> Result<(), MatrixError> {
    if matrix.is_empty() {
        return Err(MatrixError::Invalid(format!("{name} must not be empty")));
    }
    let cols = matrix[0].len();
    if cols == 0 {
        return Err(MatrixError::Invalid(format!(
            "{name} rows must not be empty"
        )));
    }
    for row in matrix {
        if row.len() != cols {
            return Err(MatrixError::Invalid(format!(
                "{name} rows must have equal lengths"
            )));
        }
        if row.iter().any(|value| !value.is_finite()) {
            return Err(MatrixError::Invalid(format!(
                "{name} elements must be finite"
            )));
        }
    }
    Ok(())
}

pub fn multiply(a: &[Vec<f64>], b: &[Vec<f64>]) -> Result<Matrix, MatrixError> {
    validate(a, "a")?;
    validate(b, "b")?;
    let rows = a.len();
    let shared = a[0].len();
    let cols = b[0].len();
    if shared != b.len() {
        return Err(MatrixError::Invalid("a columns must equal b rows".into()));
    }
    rows.checked_mul(cols)
        .filter(|count| *count <= (isize::MAX as usize) / size_of::<f64>())
        .ok_or_else(|| MatrixError::Invalid("result dimensions exceed supported size".into()))?;

    let allocation_error =
        |error| MatrixError::Allocation(format!("result allocation failed: {error}"));
    let mut result = Vec::new();
    result.try_reserve_exact(rows).map_err(allocation_error)?;
    for a_row in a {
        let mut output_row = Vec::new();
        output_row
            .try_reserve_exact(cols)
            .map_err(allocation_error)?;
        for col in 0..cols {
            let mut sum = 0.0;
            for (left, b_row) in a_row.iter().zip(b) {
                sum += left * b_row[col];
                if !sum.is_finite() {
                    return Err(MatrixError::Overflow);
                }
            }
            output_row.push(sum);
        }
        result.push(output_row);
    }
    Ok(result)
}
```

这个模块不依赖 PyO3。`Matrix` 只是 `Vec<Vec<f64>>` 的别名，没有引入类或外部数值库。`&[Vec<f64>]` 只借用行集合，算法不取得调用者输入的可变引用；每次创建新的结果和新的输出行，互不共享。

先检查非空、行宽和有限值，保证索引安全，再检查共享维度。外层遍历左矩阵行，中层遍历结果列，内层通过 `a_row.iter().zip(b)` 将左行元素与右矩阵各行配对，累加 left × b_row[col]。维度先被校验，所以 zip 不会悄悄丢弃合法点积项。时间复杂度 O(mnp)，结果占 O(mp)；嵌套 Vec 的每一行单独分配。

每次累加后检查 is_finite，乘积或中间和溢出就返回 MatrixError::Overflow，即使后续项可能抵消也不继续。没有 fast-math、自定义乘加或任意精度保障。

`checked_mul` 与 isize/f64 大小限制对结果总元素数做保守检查，超出支持范围返回 Invalid。输出外层 Vec 和每行使用 try_reserve_exact，返回的分配错误变成 Allocation；后面的 push 不需要扩容。这只覆盖这些显式申请返回的错误，不能保证输入转换、Python 输出构造或操作系统内存耗尽都能被恢复；本课也不实际申请超大内存做测试。[Rust Vec 分配 API](https://doc.rust-lang.org/stable/std/vec/struct.Vec.html#method.try_reserve_exact)

## 5. 编写 PyO3 绑定并生成 Cargo 锁文件

### 5.1 `native/lib.rs`

<!-- file: native/lib.rs -->
```rust
mod matrix;

use matrix::{Matrix, MatrixError};
use pyo3::exceptions::{PyMemoryError, PyOverflowError, PyValueError};
use pyo3::prelude::*;

fn matrix_error(error: MatrixError) -> PyErr {
    match error {
        MatrixError::Invalid(message) => PyValueError::new_err(message),
        MatrixError::Overflow => {
            PyOverflowError::new_err("matrix multiplication produced a non-finite value")
        }
        MatrixError::Allocation(message) => PyMemoryError::new_err(message),
    }
}

/// Multiply two finite rectangular matrices using Rust f64 arithmetic.
#[pyfunction]
#[pyo3(signature = (a, b))]
fn multiply(py: Python<'_>, a: Matrix, b: Matrix) -> PyResult<Matrix> {
    py.detach(move || matrix::multiply(&a, &b))
        .map_err(matrix_error)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(multiply, m)?)?;
    Ok(())
}
```

PyO3 在进入 multiply 的函数体前，把 Python 输入转换为两个 Rust 自有 Matrix；类型不匹配会直接产生 Python 异常。`py: Python<'_>` 是 PyO3 注入的解释器令牌，不是 Python 调用者要传的第三个参数；`#[pyo3(signature = (a, b))]` 固定公开参数名。

`move` 把两个 Vec 的所有权移入闭包，不再持有原 Python 列表的引用。detach 的闭包和返回值必须满足 Ungil 约束；这里仅包含普通 Rust Vec、f64、String 和 Result。闭包里不使用 py、不构造 Python 异常、不读写 Python 对象。`&a`、`&b` 是闭包内部对自有数据的只读借用。闭包返回后重新持有 GIL，随后 map_err 把三类业务错误翻译为 ValueError、OverflowError 或 MemoryError；成功时 PyO3 把结果转换为 Python 二维列表。

`Result<Matrix, MatrixError>` 负责纯 Rust 失败传播，`PyResult<Matrix>` 负责绑定边界；`?` 提前返回错误，正常业务失败不使用 panic/unwrap。模块注册同样使用 PyResult 与 ?。`_core.multiply` 仍是同步原生函数，Python 公开接口在下一节负责异步等待。[PyO3 错误处理](https://pyo3.rs/v0.30.1/function/error-handling)

### 5.2 生成并获取 Rust 锁定依赖

<!-- verify: cargo-lock -->
```bash
cargo generate-lockfile
cargo fetch --locked
cargo fmt --all -- --check
```

Cargo 自动生成 Cargo.lock，不手写。当前阶段只获取依赖、检查 Rust 格式，不要求扩展已经安装；正式构建在第 7 节。`locked = true` 防止构建时悄悄改锁文件，但不是离线模式。

首次按手册生成的间接依赖可能随时间变化；本地成品保留实测双锁文件。需要完全采用成品依赖树时，在成品中运行 uv sync --locked / cargo fetch --locked，不从旧文章拼凑锁文件。

## 6. 编写 Python 异步包与类型信息

### 6.1 `src/rust_matrix/__init__.py`

<!-- file: src/rust_matrix/__init__.py -->
```python
"""Run Rust matrix multiplication through asyncio's thread pool."""

import asyncio
from collections.abc import Sequence

from . import _core

__all__ = ["multiply_async"]


def _snapshot(
    matrix: Sequence[Sequence[float]], name: str
) -> tuple[tuple[float, ...], ...]:
    if isinstance(matrix, (str, bytes, bytearray)) or not isinstance(matrix, Sequence):
        raise TypeError(f"{name} must be a sequence of rows")
    rows: list[tuple[float, ...]] = []
    for row in matrix:
        if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
            raise TypeError(f"{name} rows must be sequences")
        rows.append(tuple(row))
    return tuple(rows)


async def multiply_async(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]:
    """Snapshot the inputs when this coroutine starts, then await native work."""
    a_snapshot = _snapshot(a, "a")
    b_snapshot = _snapshot(b, "b")
    return await asyncio.to_thread(_core.multiply, a_snapshot, b_snapshot)
```

`_snapshot` 限定为非文本序列，把外层和每行复制成不可变 tuple；具体数值仍由 PyO3 转换，Python 层没有乘法算法。协程执行到第一个 `await` 之前，两个快照已经建立；`to_thread` 随后将原生调用交给事件循环默认线程池。每个调用拥有独立输入和结果，没有共享计算缓存。

只创建协程后立即修改列表，协程启动时看到的是修改后的值；启动并完成快照后再修改，原生任务使用快照。不要照搬 JS Promise 返回前就拍快照的假设。

Python 在调用时检查参数数量与关键字，所以这些错误立即抛出。类型、形状与计算检查发生在函数体或后台，错误随 `await` 传播。取消 Task 或 `asyncio.timeout` 超时不会杀死已经运行的 Rust；未开始的排队工作可能被取消。默认线程池由事件循环管理，`asyncio.run` 退出时会等待其关闭，不要把“停止等待”理解为“计算已经停止”。[线程任务取消](https://docs.python.org/3.12/library/concurrent.futures.html#concurrent.futures.Future.cancel)、[asyncio.run 生命周期](https://docs.python.org/3.12/library/asyncio-runner.html#asyncio.run)

### 6.2 `src/rust_matrix/__main__.py`

<!-- file: src/rust_matrix/__main__.py -->
```python
"""Run the result, concurrency and error demos with python -m rust_matrix."""

import asyncio
import sys

from . import multiply_async


async def main() -> None:
    result = await multiply_async([[1, 2, 3], [4, 5, 6]], [[7, 8], [9, 10], [11, 12]])
    print(f"2x3 @ 3x2 = {result}")
    results = await asyncio.gather(
        multiply_async([[1, 2]], [[3], [4]]),
        multiply_async([[5]], [[6, 7]]),
    )
    print(f"gather = {results}")
    outcomes = await asyncio.gather(
        multiply_async([[sys.float_info.max]], [[2]]),
        multiply_async([[3]], [[7]]),
        return_exceptions=True,
    )
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            print(f"{type(outcome).__name__}: {outcome}")
        else:
            print(f"success: {outcome}")


if __name__ == "__main__":
    asyncio.run(main())
```

`asyncio.run` 创建并关闭顶层事件循环。`gather` 按输入顺序收集结果；`return_exceptions=True` 将错误作为单项结果收集，其他任务可正常完成。不要用连续两次 `await` 误认为同时提交了两个任务。普通 import 不运行演示。

### 6.3 `src/rust_matrix/_core.pyi`

<!-- file: src/rust_matrix/_core.pyi -->
```python
from collections.abc import Sequence

def multiply(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]: ...
```

这是同步原生内部接口的类型声明；公开异步函数的类型由 Python 源码提供。stub 中的 `...` 是合法声明语法，不是待补齐的算法。声明面向 int/float 调用者；PyO3 默认还可能接受实现数值转换协议的对象，不把 stub 当运行时白名单。

### 6.4 空的 `src/rust_matrix/py.typed`

<!-- verify: typed-marker -->
```bash
touch src/rust_matrix/py.typed
```

必须为 0 字节。它使安装后的包也携带可供 mypy 读取的类型信息。[类型分发规范](https://typing.python.org/en/latest/spec/distributing.html)

## 7. 编译、运行与第二个里程碑

<!-- verify: build-demo -->
```bash
uv sync --locked
uv run --no-sync python -m rust_matrix
uv run --no-sync python -c 'from rust_matrix import _core; print(_core.__file__); print(_core.multiply.__doc__); print(_core.multiply.__text_signature__)'
uv run --no-sync ruff check src
uv run --no-sync ruff format --check src
uv run --no-sync mypy src
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
```

uv 调用隔离环境中的 Maturin，Maturin 调用 Cargo/rustc，以 release 配置编译并 editable 安装本项目。固定演示输出：

```text
2x3 @ 3x2 = [[58.0, 64.0], [139.0, 154.0]]
gather = [[[11.0]], [[30.0, 35.0]]]
OverflowError: matrix multiplication produced a non-finite value
success: [[21.0]]
```

原生扩展通常位于 src/rust_matrix/_core.cpython-312-x86_64-linux-gnu.so，Python 源码通过 editable 安装从 src 读取；Cargo 的 target 是编译缓存，不是导入路径。函数说明为 `Multiply two finite rectangular matrices using Rust f64 arithmetic.`，文本签名为 `(a, b)`。绝对路径、耗时和构建日志会变化。[Maturin 本地开发](https://www.maturin.rs/local_development)

Ruff、mypy、rustfmt、Clippy 都应成功。Clippy 的 `-D warnings` 把警告当错误；`--all-targets` 检查本 crate 各目标。命令前的 `PYO3_PYTHON` 只对本次 Cargo 检查生效，避免误用系统 Python 3.14；它不重新安装 Python 正在使用的扩展。Rust 修改后需要第 10 节的显式重编译。

确认可运行后，只提交本里程碑的配置、Rust 绑定、实现、Python 包与类型信息：

<!-- verify: commit-implementation -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 08-python-rust-async-matrix/practice
git -C ../.. add 08-python-rust-async-matrix/practice/Cargo.toml 08-python-rust-async-matrix/practice/Cargo.lock 08-python-rust-async-matrix/practice/native/matrix.rs 08-python-rust-async-matrix/practice/native/lib.rs 08-python-rust-async-matrix/practice/src/rust_matrix/__init__.py 08-python-rust-async-matrix/practice/src/rust_matrix/__main__.py 08-python-rust-async-matrix/practice/src/rust_matrix/_core.pyi 08-python-rust-async-matrix/practice/src/rust_matrix/py.typed
git -C ../.. diff --cached
git -C ../.. commit -m "feat: call Rust matrix multiplication asynchronously from Python"
git -C ../.. status --short
git -C ../.. log -2 --oneline
```

## 8. 观察计算期间的心跳

编写完整的 `src/rust_matrix/heartbeat.py`：

<!-- file: src/rust_matrix/heartbeat.py -->
```python
"""Observe asyncio while a real Rust multiplication is running."""

import asyncio
from contextlib import suppress
from time import perf_counter

from . import multiply_async


async def main() -> None:
    rows, shared, cols = 600, 800, 500
    a = [[1.0] * shared for _ in range(rows)]
    b = [[1.0] * cols for _ in range(shared)]
    beats = 0

    async def heartbeat() -> None:
        nonlocal beats
        while True:
            await asyncio.sleep(0.05)
            beats += 1
            print(f"heartbeat {beats}")

    timer = asyncio.create_task(heartbeat())
    started = perf_counter()
    try:
        print(f"awaiting {rows}x{shared} @ {shared}x{cols}")
        result = await multiply_async(a, b)
        print(f"result: {len(result)}x{len(result[0])}; first = {result[0][0]}")
        print(f"heartbeats: {beats}; elapsed: {perf_counter() - started:.3f} s")
    finally:
        timer.cancel()
        with suppress(asyncio.CancelledError):
            await timer


if __name__ == "__main__":
    asyncio.run(main())
```

<!-- verify: heartbeat -->
```bash
uv run --no-sync python -m rust_matrix.heartbeat
```

固定部分为等待 `600x800 @ 800x500`，结果 `600x500; first = 800.0`；中间的心跳数和耗时随机器变化。`finally` 取消并等待心跳协程，避免残留后台 Task；取消的是计时演示，不是矩阵计算。

小矩阵可能在首个定时器前就完成。如果更快的机器没有心跳，可手动增加本文件的三个尺寸后重试；不要用固定次数或耗时作性能结论。下一节的测试会在真实原生调用开始与结束之间计数，并通过负对照检验是否真的发现 GIL 阻塞。

## 9. 编写真实集成测试

创建完整的 `tests/test_matrix.py`：

<!-- file: tests/test_matrix.py -->
```python
import asyncio
import importlib.machinery
import inspect
import math
import sys
import threading
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

import pytest

from rust_matrix import _core, multiply_async


@dataclass
class NativeCall:
    started: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    thread_ids: set[int] = field(default_factory=set)


@contextmanager
def observe_native_call() -> Iterator[NativeCall]:
    state = NativeCall()
    native = _core.multiply

    def profile(_frame: FrameType, event: str, arg: object) -> None:
        if arg is native:
            if event == "c_call":
                state.thread_ids.add(threading.get_ident())
                state.started.set()
            elif event in ("c_return", "c_exception"):
                state.finished.set()

    def observed(
        a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
    ) -> list[list[float]]:
        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            return native(a, b)
        finally:
            sys.setprofile(previous)

    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1.0)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(_core, "multiply", observed)
            yield state
    finally:
        sys.setswitchinterval(previous_interval)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ([[1, 2, 3], [4, 5, 6]], [[7, 8], [9, 10], [11, 12]], [[58, 64], [139, 154]]),
        ([[3]], [[4]], [[12]]),
        ([[1, 2, 3, 4]], [[2], [3], [4], [5]], [[40]]),
        ([[2], [3], [4]], [[5, 6]], [[10, 12], [15, 18], [20, 24]]),
        ([[-1, 2], [3, -4]], [[5, -6], [-7, 8]], [[-19, 22], [43, -50]]),
        ([[0, 0], [0, 0]], [[1], [2]], [[0], [0]]),
        ([[1, 2]], [[0, 0], [0, 0]], [[0, 0]]),
    ],
)
def test_products(
    a: Sequence[Sequence[float]],
    b: Sequence[Sequence[float]],
    expected: list[list[float]],
) -> None:
    result = asyncio.run(multiply_async(a, b))
    assert result == expected
    assert all(isinstance(value, float) for row in result for value in row)


def test_identity_on_either_side() -> None:
    matrix = [[1, 2, 3], [4, 5, 6]]
    assert asyncio.run(multiply_async([[1, 0], [0, 1]], matrix)) == matrix
    assert (
        asyncio.run(multiply_async(matrix, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])) == matrix
    )


def test_decimal() -> None:
    result = asyncio.run(multiply_async([[0.1, 0.2]], [[0.3], [0.4]]))
    assert result[0][0] == pytest.approx(0.11)


def test_tuple_and_keyword_inputs() -> None:
    assert asyncio.run(multiply_async(b=((3,), (4,)), a=((1, 2),))) == [[11.0]]


def test_bool_and_f64_precision() -> None:
    assert asyncio.run(multiply_async([[True, False]], [[3], [4]])) == [[3.0]]
    assert asyncio.run(multiply_async([[2**53, 1]], [[1], [1]])) == [[float(2**53)]]


def test_input_unchanged_and_output_rows_independent() -> None:
    a = [[1], [2]]
    b = [[3, 4]]
    result = asyncio.run(multiply_async(a, b))
    assert a == [[1], [2]]
    assert b == [[3, 4]]
    assert result[0] is not result[1]
    result[0][0] = 999
    assert result[1] == [6, 8]


def test_creating_a_coroutine_does_not_take_a_snapshot() -> None:
    a = [[2]]
    pending = multiply_async(a, [[3]])
    assert inspect.iscoroutine(pending)
    a[0][0] = 4
    assert asyncio.run(pending) == [[12.0]]


def test_started_coroutine_snapshots_before_waiting_for_a_worker() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        release = threading.Event()
        blocker = loop.run_in_executor(None, release.wait, 10.0)
        a = [[1, 2], [3, 4]]
        b = [[5], [6]]
        pending = asyncio.create_task(multiply_async(a, b))
        try:
            await asyncio.sleep(0)
            assert not pending.done()
            a[0][0] = 999
            a.append([999, 999])
            b[0][0] = -999
            b[1] = [999]
        finally:
            release.set()
            await blocker
        assert await pending == [[17.0], [39.0]]

    asyncio.run(scenario())


def test_concurrent_jobs_preserve_order() -> None:
    async def scenario() -> None:
        results = await asyncio.gather(
            multiply_async([[1, 2]], [[3], [4]]),
            multiply_async([[5]], [[6, 7]]),
            multiply_async([[1], [2]], [[3, 4]]),
        )
        assert list(results) == [[[11.0]], [[30.0, 35.0]], [[3.0, 4.0], [6.0, 8.0]]]

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [None, 1, True, "1", b"1", {}, object()])
def test_invalid_outer_types(bad: object) -> None:
    with pytest.raises(TypeError, match="a must be a sequence of rows"):
        asyncio.run(multiply_async(bad, [[1]]))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="b must be a sequence of rows"):
        asyncio.run(multiply_async([[1]], bad))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, 1, "1", b"1", {}])
def test_invalid_row_types(bad: object) -> None:
    with pytest.raises(TypeError, match="a rows must be sequences"):
        asyncio.run(multiply_async([bad], [[1]]))  # type: ignore[list-item]
    with pytest.raises(TypeError, match="b rows must be sequences"):
        asyncio.run(multiply_async([[1]], [bad]))  # type: ignore[list-item]


@pytest.mark.parametrize("bad", ["1", None, [], {}, object()])
def test_invalid_element_types(bad: object) -> None:
    with pytest.raises(TypeError, match="while processing 'a'"):
        asyncio.run(multiply_async([[bad]], [[1]]))  # type: ignore[list-item]
    with pytest.raises(TypeError, match="while processing 'b'"):
        asyncio.run(multiply_async([[1]], [[bad]]))  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ([], "must not be empty"),
        ([[]], "rows must not be empty"),
        ([[], []], "rows must not be empty"),
        ([[1, 2], [3]], "rows must have equal lengths"),
        ([[1], []], "rows must have equal lengths"),
    ],
)
def test_invalid_shapes(bad: list[list[float]], message: str) -> None:
    with pytest.raises(ValueError, match=f"a {message}"):
        asyncio.run(multiply_async(bad, [[1]]))
    with pytest.raises(ValueError, match=f"b {message}"):
        asyncio.run(multiply_async([[1]], bad))


def test_incompatible_dimensions() -> None:
    with pytest.raises(ValueError, match="a columns must equal b rows"):
        asyncio.run(multiply_async([[1, 2]], [[3, 4]]))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_inputs(value: float) -> None:
    with pytest.raises(ValueError, match="a elements must be finite"):
        asyncio.run(multiply_async([[value]], [[1]]))
    with pytest.raises(ValueError, match="b elements must be finite"):
        asyncio.run(multiply_async([[1]], [[value]]))


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ([[sys.float_info.max]], [[2]]),
        ([[sys.float_info.max, sys.float_info.max]], [[1], [1]]),
    ],
)
def test_overflow(a: list[list[float]], b: list[list[float]]) -> None:
    with pytest.raises(OverflowError, match="produced a non-finite value"):
        asyncio.run(multiply_async(a, b))


def test_argument_errors_are_immediate() -> None:
    with pytest.raises(TypeError):
        _ = multiply_async([[1]])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        _ = multiply_async([[1]], [[1]], [[1]])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        _ = multiply_async(a=[[1]], c=[[1]])  # type: ignore[call-arg]


def test_content_errors_are_reported_when_awaited() -> None:
    pending = multiply_async([], [[1]])
    assert inspect.iscoroutine(pending)
    with pytest.raises(ValueError, match="a must not be empty"):
        asyncio.run(pending)


def test_failure_does_not_corrupt_another_job() -> None:
    async def scenario() -> None:
        results = await asyncio.gather(
            multiply_async([[sys.float_info.max]], [[2]]),
            multiply_async([[3]], [[7]]),
            return_exceptions=True,
        )
        assert isinstance(results[0], OverflowError)
        assert results[1] == [[21.0]]

    asyncio.run(scenario())


def test_native_work_runs_off_thread_and_releases_the_gil() -> None:
    async def scenario(state: NativeCall) -> int:
        a = [[1.0] * 800 for _ in range(600)]
        b = [[1.0] * 500 for _ in range(800)]
        pending = asyncio.create_task(multiply_async(a, b))
        beats = 0
        while not pending.done():
            await asyncio.sleep(0.001)
            if state.started.is_set() and not state.finished.is_set():
                beats += 1
        result = await pending
        assert (len(result), len(result[0]), result[0][0]) == (600, 500, 800.0)
        return beats

    with observe_native_call() as state:
        beats = asyncio.run(scenario(state))
    assert state.started.is_set() and state.finished.is_set()
    assert state.thread_ids and threading.get_ident() not in state.thread_ids
    assert beats > 0, "no heartbeat while the native call was active"


def test_cancellation_does_not_stop_running_native_work() -> None:
    async def scenario(state: NativeCall) -> None:
        a = [[1.0] * 800 for _ in range(600)]
        b = [[1.0] * 500 for _ in range(800)]
        pending = asyncio.create_task(multiply_async(a, b))
        assert await asyncio.to_thread(state.started.wait, 10.0)
        assert not state.finished.is_set(), (
            "native workload completed before cancellation"
        )
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert await asyncio.to_thread(state.finished.wait, 10.0)
        assert await multiply_async([[3]], [[7]]) == [[21.0]]

    with observe_native_call() as state:
        asyncio.run(scenario(state))


def test_real_native_extension() -> None:
    assert _core.multiply.__module__ == "rust_matrix._core"
    native_path = _core.__file__
    assert native_path is not None
    assert Path(native_path).is_file()
    assert any(
        native_path.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
```

<!-- verify: tests -->
```bash
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
```

预期 **49 项通过**，Ruff 检查/格式、严格 mypy、rustfmt 和 Clippy 通过。参数化展开计入测试总数，耗时不固定。

几个关键检查：

- 正常结果包括不同矩形、单元素、正负数、零、单位矩阵、小数和元组输入。所有输出元素为 float，输出行互相独立，输入保持原值。
- 对非法类型在左右两处分别验证，形状和非有限值精确验证业务错误片段；PyO3 0.30.1 在 Python 3.12 的异常 notes 中附加 `while processing 'a'` / `'b'`，pytest 的 match 会包含 notes；元素类型测试验证该参数上下文，不固定完整错误文本。
- 先创建协程再修改输入，结果反映修改。快照测试用单线程池中的 Event 阻塞第一项工作，让矩阵任务排队；`sleep(0)` 只让协程开始并提交，不靠固定毫秒猜测计算时机。解除阻塞后必须得到原快照结果。
- `observe_native_call` 只在测试中临时加一个 Python 转发层，仍调用保存的真实 `_core.multiply`。`sys.setprofile` 观察该原生调用的 `c_call/c_return/c_exception`，记录线程和调用区间；它不替换算法。测试临时延长 Python 线程切换时间片，防止原生调用边界前的偶然调度被算成心跳；显式释放 GIL 仍允许事件循环运行。退出时恢复原函数、profiler 与原时间片。转发层让经 `Context.run` 调用的原生函数产生可观察的 Python 调用事件。
- 心跳必须发生在原生函数进入后、返回前。取消测试先等原生调用开始，再取消等待，随后等原生调用结束并检查另一项计算仍成功；Event 等待放在线程中，避免阻塞事件循环。10 秒只是失效保护，不是加速验收值。
- 这两项使用较大真实矩阵以留出观察窗口。极快机器若计算早于取消完成，可增加对应测试尺寸；不增加产品的睡眠或测试专用原生接口。
- `type: ignore[...]` 只出现在故意传错类型或参数的行，其他代码继续严格检查。原生文件路径与扩展后缀验证确保加载了实际共享库。

维护者会在隔离副本移除 GIL 释放，确认心跳测试失败；该故障实验不需要在你的正式练习里执行，记录见 VERIFICATION。

## 10. 修改、清理重建与异目录运行

### 10.1 修改 Rust 源码后显式重编译

<!-- verify: rebuild -->
```bash
uv sync --locked --reinstall-package py-rust-async-matrix
uv run --no-sync pytest
uv run --no-sync python -m rust_matrix
```

Rust、绑定或 Cargo 配置修改后都执行上述步骤。cargo build / clippy 不能替代安装：它们不会更新 src/rust_matrix 中供 Python import 的扩展。Python、stub 或测试修改后运行测试与检查，分发内容改变时也重新安装。[uv 本地项目缓存](https://docs.astral.sh/uv/concepts/cache/)

| 修改内容 | 后续操作 |
| --- | --- |
| Rust 实现、绑定、Cargo 配置 | 重新编译安装，运行测试与 Python/Rust 检查 |
| Python、stub、测试 | 测试、Ruff、mypy；分发变化时重新安装 |
| 有意更新 Python 依赖 | uv lock，审阅后 uv sync --locked，再验证 |
| 有意更新 Rust 依赖 | 重新生成并审阅 Cargo.lock，再构建与验证 |
| 怀疑加载了旧二进制 | 查 _core.__file__，按下节清理后重建 |

### 10.2 清理本课产物后从锁文件重建

**仍在本课 practice。** 先确认 pwd；只删除列出的本课产物，保留源码、双锁文件和 Git 历史：

<!-- verify: clean-rebuild -->
```bash
pwd
uv run --no-project --python 3.12.15 python - <<'PYCODE'
from pathlib import Path

for pattern in ("_core*.so", "_core*.pyd"):
    for path in Path("src/rust_matrix").glob(pattern):
        path.unlink()
PYCODE
cargo clean
rm -rf .venv .venv-wheel build dist .pytest_cache .ruff_cache .mypy_cache src/rust_matrix/__pycache__ tests/__pycache__
cargo fetch --locked
uv sync --locked --reinstall-package py-rust-async-matrix
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
uv run --no-sync python -m rust_matrix
```

`cargo clean` 只清理 target，不删除 editable 安装放在 src/rust_matrix 中的扩展，所以两处都要清理。Python 小段仅删除生成库，--no-project 使它不依赖项目环境是否完好。应重新生成环境、target 和扩展，仍为 49 项通过、全部检查通过、演示正确。不删除全局 Cargo/uv 缓存。

### 10.3 从仓库根目录和 /tmp 运行

两个子 shell 不改变外层当前目录：

<!-- verify: other-directories -->
```bash
(
  cd ../..
  08-python-rust-async-matrix/practice/.venv/bin/python -m rust_matrix
)
(
  project_python="$PWD/.venv/bin/python"
  cd /tmp
  "$project_python" -m rust_matrix
)
```

两次都应得到第 7 节固定输出。不设置 PYTHONPATH，不修改 sys.path，也不复制共享库到当前工作目录。

## 11. 源码包、wheel 与安装后验收

### 11.1 从源码包构建 wheel 并独立安装

<!-- verify: build-wheel -->
```bash
uv build
ls -1 dist
uv venv --python 3.12.15 .venv-wheel
uv pip install --python .venv-wheel/bin/python --no-deps dist/*.whl
.venv-wheel/bin/python -I -m rust_matrix
.venv-wheel/bin/python -I -c 'import asyncio; import rust_matrix._core as native; from rust_matrix import multiply_async; print(native.__file__); assert asyncio.run(multiply_async([[2]], [[3]])) == [[6.0]]'
```

`uv build` 默认先生成源码包，再从源码包构建 wheel，检查分发所需源码是否齐全。[uv 构建说明](https://docs.astral.sh/uv/guides/package/)

Cargo package 可能提示未填写对外发布元数据；本课是私有教学项目，命令成功即可，该提示不属于 Clippy 代码警告。

本机文件名：

```text
py_rust_async_matrix-0.1.0.tar.gz
py_rust_async_matrix-0.1.0-cp312-cp312-linux_x86_64.whl
```

`--no-deps` 安装后可以运行，说明本包运行时不需要单独安装 PyO3/Maturin。`-I` 采用 Python 隔离模式，排除当前目录和 PYTHONPATH 干扰；原生路径应位于 `.venv-wheel`。这里只在本地打包，不发布 PyPI，也没有 manylinux 修复或跨平台验收。

查看包内文件：

<!-- verify: inspect-distributions -->
```bash
uv run --no-sync python - <<'PYCODE'
from pathlib import Path
import tarfile
import zipfile

sdist = next(Path("dist").glob("*.tar.gz"))
wheel = next(Path("dist").glob("*.whl"))
with tarfile.open(sdist) as archive:
    print("source files:")
    print("\n".join(archive.getnames()))
with zipfile.ZipFile(wheel) as archive:
    print("wheel files:")
    print("\n".join(archive.namelist()))
PYCODE
```

源码包应包含 Rust/Python 源码、Cargo.toml、pyproject.toml、测试、README、.python-version、双锁文件和空 py.typed；不应包含虚拟环境、target、缓存或 editable 原生扩展。wheel 应包含 Python 文件、stub、空 py.typed、最终原生扩展和分发元数据；Maturin 自动生成的 SBOM 可以存在。

### 11.2 在 wheel 环境运行完整测试

把锁定的开发依赖导出到构建目录，再安装进独立环境：

<!-- verify: wheel-tests -->
```bash
mkdir -p build
uv export --locked --only-group dev --no-emit-project --format requirements-txt --output-file build/dev-requirements.txt
uv pip install --python .venv-wheel/bin/python --require-hashes -r build/dev-requirements.txt
.venv-wheel/bin/python -I -m pytest tests
```

应为同样 49 项通过。此时运行的原生包来自 wheel，不是 editable 包；导出的依赖文件属于临时验收产物，不新增另一份需要维护的依赖清单。

### 11.3 检查安装后的类型信息

先从 `/tmp` 检查有效调用，避免误用项目源码目录的 stub；子 shell 退出后仍在 practice：

<!-- verify: wheel-type-valid -->
```bash
(
  wheel_python="$PWD/.venv-wheel/bin/python"
  cd /tmp
  "$wheel_python" -I -m mypy --strict --no-incremental -c 'from rust_matrix import multiply_async
async def check() -> list[list[float]]:
    return await multiply_async([[1, 2]], [[3], [4]])'
)
```

应报告没有类型问题。再故意检查四处错误：

<!-- verify: wheel-type-invalid -->
```bash
(
  wheel_python="$PWD/.venv-wheel/bin/python"
  cd /tmp
  "$wheel_python" -I -m mypy --strict --no-incremental -c 'from rust_matrix import multiply_async
async def check() -> None:
    result: str = await multiply_async([[1]], [[2]])
    await multiply_async([["1"]], [[2]])
    await multiply_async([[1]])
    await multiply_async([[1]], [[2]], [[3]])'
)
```

**这一块预期以状态码 1 退出**，报告四处 assignment、list-item、call-arg 类型错误；这是成功的负向检查，不要把这些错误写进正式源码。不应出现找不到包或缺少类型声明的错误。

## 12. 第三个里程碑与最终检查

<!-- verify: acceptance -->
```bash
uv lock --check
cargo fetch --locked
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
uv run --no-sync python -m rust_matrix
uv run --no-sync python -m rust_matrix.heartbeat
git -C ../.. check-ignore 08-python-rust-async-matrix/practice/.venv/ 08-python-rust-async-matrix/practice/.venv-wheel/ 08-python-rust-async-matrix/practice/target/ 08-python-rust-async-matrix/practice/build/ 08-python-rust-async-matrix/practice/dist/ 08-python-rust-async-matrix/practice/.pytest_cache/ 08-python-rust-async-matrix/practice/.ruff_cache/ 08-python-rust-async-matrix/practice/.mypy_cache/ 08-python-rust-async-matrix/practice/src/rust_matrix/_core.example.so
git -C ../.. status --short --untracked-files=all
```

锁文件匹配、49 项通过、全部检查通过、演示正确。check-ignore 列出八类目录和一个模拟 .so 路径（不创建文件），状态中没有依赖或二进制。核对项目说明与当前接口、命令一致后提交：

<!-- verify: commit-tests -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 08-python-rust-async-matrix/practice
git -C ../.. add 08-python-rust-async-matrix/practice/src/rust_matrix/heartbeat.py 08-python-rust-async-matrix/practice/tests/test_matrix.py
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify Python Rust async matrix behavior"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

三个学习提交依次为配置、可运行实现、心跳与测试。无需重复提交已有内容，课程子目录共享根仓库。

## 13. 常见故障与定位

以下检查均在本课 practice 执行：

| 现象 | 检查命令或位置 | 处理步骤 |
| --- | --- | --- |
| 找不到 Rust、Cargo 或链接器 | rustc --version、cargo --version、cc --version | 按第 1 节补齐工具，再构建 |
| rustfmt/Clippy 缺失或 Rust 过旧 | rustup show active-toolchain、工具版本 | 安装所缺组件；依赖明确要求更新时再有意更新 stable |
| Python 版本或 Python.h 不对 | uv run --no-sync python --version、第 1 节断言 | 安装托管 3.12.15，旧环境不匹配则清理重建 |
| 下载失败 | uv/Cargo 日志中的 URL、代理、证书错误 | 修正网络或证书配置后重试，不关闭 TLS 校验 |
| Cargo.lock 缺失或 --locked 拒绝构建 | Cargo.toml、Cargo.lock | 首次按第 5 节生成；改依赖后重新生成并审阅 |
| Clippy 误用系统 Python | PYO3_PYTHON 的命令前缀 | 指向当前项目 .venv/bin/python，不全局切换解释器 |
| No module named rust_matrix | uv run --no-sync python -c 'import sys; print(sys.executable)' | 确认在本课目录并执行 uv sync --locked |
| _core 导入失败或架构不匹配 | uv run --no-sync python -c 'import rust_matrix._core as m; print(m.__file__)' | 对齐模块名，清理重建；不复制其他 Python 的 .so |
| RuntimeWarning: coroutine was never awaited | 是否只创建协程没有运行 | async 函数内 await，终端入口用 asyncio.run，并发用 create_task/gather |
| asyncio.run cannot be called from a running event loop | Notebook 或已有异步程序入口 | 已有事件循环内直接 await，不再嵌套 asyncio.run |
| await 时出现 TypeError/ValueError | 输入层级、元素、形状与错误消息 | 传非文本二维序列和有限数值，左列数等于右行数 |
| OverflowError | 数值范围和中间部分和 | 缩小数值；有限输入不保证点积始终有限 |
| 创建了线程却没有心跳 | native/lib.rs 是否调用 py.detach | 按第 5、6 节核对；同步原生函数仍需 to_thread 调度 |
| 小矩阵没有打印心跳 | 尺寸和执行耗时 | 增大演示尺寸观察，不把心跳次数当性能承诺 |
| 快照结果与预期不同 | 协程是否已开始执行 | 创建协程时未复制；不要在其他线程同时修改正在复制的输入 |
| cancel 后仍计算或退出等待 | 原生工作是否已开始 | 取消只停止等待，允许工作正常结束，理解线程池关闭 |
| Rust 改动后结果没变 | _core.__file__、是否显式重编译 | uv sync --locked --reinstall-package py-rust-async-matrix，再用新进程运行 |
| cargo clean 后仍能 import | src/rust_matrix 中的旧 .so | 按第 10 节同时清理 editable 扩展 |
| 找不到全局 maturin 或 import pyo3 失败 | pyproject.toml、Cargo.toml | uv 调用隔离后端；PyO3 是 Rust crate，无需 Python import |
| detach 闭包编译失败 | 错误中的 Ungil/Send 约束、闭包捕获 | 仅传 Rust 自有数据，不捕获 Python 令牌、Bound 对象或 Python 借用 |
| Ruff/mypy/rustfmt/Clippy 失败 | 输出的首个文件位置 | 修复问题；可运行 ruff format . / cargo fmt --all 后审阅差异，保留严格配置 |
| wheel 类型检查找不到包或类型 | wheel 中的 .py、_core.pyi、py.typed | 检查文件清单，重新构建安装，再从 /tmp 检查 |
| reference 无法 git add | git check-ignore 08-python-rust-async-matrix/reference/ | 沿用仓库约定，不强制暂存 |

直接观察正常调用与错误传播，不保存为项目文件：

<!-- verify: diagnose -->
```bash
uv run --no-sync python - <<'PYCODE'
import asyncio
from rust_matrix import multiply_async

async def main():
    print(await multiply_async(a=[[2]], b=[[3]]))
    try:
        await multiply_async([[1, 2]], [[3, 4]])
    except ValueError as error:
        print(type(error).__name__)
        print(error)

asyncio.run(main())
PYCODE
```

固定输出：

```text
[[6.0]]
ValueError
a columns must equal b rows
```

## 14. 最终验收清单

- [ ] 能指出 Python 异步层、PyO3 绑定与纯 Rust 算法各自的位置。
- [ ] 能解释协程启动、tuple 快照、线程池、Vec 所有权、detach 与结果转换的顺序。
- [ ] 明白 Python 线程池承担异步调度，detach 本身不创建线程，Rust 函数仍同步。
- [ ] 动态矩阵得到正确形状和 float 数值，理解 f64 精度与中间和溢出策略。
- [ ] 49 项真实调用测试、Ruff、严格 mypy、rustfmt 与 Clippy 全部通过。
- [ ] 原生计算期间存在心跳，理解 gather 顺序、失败隔离和取消等待的边界。
- [ ] 修改 Rust 后会显式重新安装，能同时清理 editable 扩展和 target 后重建。
- [ ] uv.lock 与 Cargo.lock 匹配声明，从仓库根目录及 /tmp 启动都成功。
- [ ] 源码包完整、无缓存，独立 wheel 环境运行 49 项测试，安装后正负类型检查符合预期。
- [ ] 三个有意义的学习提交包含配置、源码、测试、说明、双锁文件和空 py.typed，不含产物。
- [ ] 保留其他课程与已有练习，正式仓库的暂存、提交和推送由自己执行。

## 教材维护者的提交命令

这一段只适用于本次新增教材尚未提交的工作副本，已有教材的 clone 学习者不需要执行。

当前第七课教材也尚未提交，共享根索引同时包含第七、八课入口。因此本次维护提交明确包含两课的手册和验证记录，说明也覆盖两课；不包含 practice 或 reference。采用下面的合并教材提交后，不再重复第七课末尾只列一课的维护提交。若你已经单独提交了第七课，相关路径不会产生额外差异，仍需审阅暂存区。

**从仓库根目录开始**；若仍在 practice，先执行 cd ../..。确认暂存区没有无关内容，并完成本课验收后执行：

<!-- verify: commit-material -->
```bash
git status --short
git diff --check
git diff -- README.md 07-python-cpp-async-matrix/README.md 07-python-cpp-async-matrix/VERIFICATION.md 08-python-rust-async-matrix/README.md 08-python-rust-async-matrix/VERIFICATION.md
git add README.md 07-python-cpp-async-matrix/README.md 07-python-cpp-async-matrix/VERIFICATION.md 08-python-rust-async-matrix/README.md 08-python-rust-async-matrix/VERIFICATION.md
git diff --cached
git commit -m "docs: add verified Python async matrix lessons"
git status --short
git log -1 --oneline
```

Agent 只在隔离临时 clone 验证学习提交和教材提交。正式仓库的暂存、提交和推送仍由你执行；第八课 practice 在教材交付时不创建。
