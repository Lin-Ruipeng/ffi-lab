# 第六课：从零用 Python 调用 Rust

这一课继续使用第五课的同步加法接口：Python 调用 `add(2, 3)`，Rust 执行 `f64` 加法，Python 得到 `5.0`。你会亲手完成 uv 配置、Rust 实现、PyO3 绑定、编译安装、测试、静态检查、项目说明和 Git 提交。

本课面向 Ubuntu/Linux x64，沿用 uv 0.13.5、CPython 3.12.15，使用 Rust 2024 edition、PyO3 0.30.1 和 Maturin 1.15.0。本地成品在 [reference/](reference/)，实际验证过程见 [VERIFICATION.md](VERIFICATION.md)。`reference/` 按根仓库规则忽略，不随 Git clone 分发；缺少成品时，按本文在 `practice/` 中手写即可，不依赖从其他课程复制文件。

## 0. 理解 PyO3、接口和目录

### 0.1 技术路线与第五课对照

PyO3 是为 Python 编写 Rust 扩展的主流路线，也支持反向嵌入解释器；本课只学习 Python 调用 Rust。PyO3 官方推荐使用 Maturin 构建扩展包，本课让 uv 调用这个后端，不安装全局 Maturin。[PyO3 官方入门](https://pyo3.rs/main/getting-started)、[固定版本 API 文档](https://docs.rs/pyo3/0.30.1/pyo3/)

| 第五课 | 本课 | 职责 |
| --- | --- | --- |
| pybind11 | PyO3 | 注册原生函数，转换参数与返回值，传播 Python 错误 |
| CMake + scikit-build-core | Cargo + Maturin | 构建扩展，组织 Python 包和分发文件 |
| C++ double | Rust f64 | 本课加法使用的浮点类型 |
| native/add.cpp | native/arithmetic.rs | 只做普通语言内部的加法 |
| uv.lock | uv.lock + Cargo.lock | 分别管理 Python 和 Rust 依赖 |

Rust 代码由 rustc 编译为共享库，Python import 时加载它；不会解释 `.rs`，也不会启动另一个 Rust 进程。运行时无需 Cargo、Maturin 或 Python 中的“pyo3 包”，但本机从源码编译需要完整工具链。

### 0.2 公开接口与调用链

```python
from rust_add import add

result: float = add(2, 3)
assert result == 5.0
```

接口是 `add(a: float, b: float) -> float`，允许整数、小数和 `a`、`b` 关键字，没有默认值。Rust 的对应输入与输出都是 `f64`，返回 Python 后始终是 `float`。接口与第五课保持可对照，错误消息使用当前 PyO3 的实际形式。

```text
python -m rust_add
    │ 执行 src/rust_add/__main__.py
    ▼
rust_add/__init__.py：重新导出 _core.add
    │ import 编译出的 _core 扩展
    ▼
rust_add._core：PyInit__core / #[pymodule]
    │ #[pyfunction] 生成的包装进行 Python 数值 → f64 转换
    ▼
native/lib.rs：调用 arithmetic::add(a, b)
    ▼
native/arithmetic.rs：执行 a + b
    │ f64 转为 Python float
    ▼
Python 得到 5.0
```

这是同步调用。只传两个数值，没有复杂对象的所有权交接、线程任务或异步运行时。普通 CPython 3.12 下本课不主动释放 GIL。

### 0.3 最终目录

```text
06-python-rust-pyo3/
├── README.md                         # 本手册
├── VERIFICATION.md                   # 实测记录
├── reference/                        # 本地对照成品，不提交
└── practice/                         # 由你从零创建
    ├── .python-version
    ├── pyproject.toml
    ├── uv.lock                       # uv 生成并提交
    ├── Cargo.toml
    ├── Cargo.lock                    # Cargo 生成并提交
    ├── README.md                     # 你编写的项目说明
    ├── native/
    │   ├── arithmetic.rs             # 纯 Rust 加法
    │   └── lib.rs                    # PyO3 绑定与模块入口
    ├── src/rust_add/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── _core.pyi
    │   ├── py.typed                  # 0 字节空文件
    │   └── _core.*.so                # editable 安装生成，不提交
    ├── tests/test_add.py
    ├── .venv/                        # 项目环境
    ├── .venv-wheel/                  # 独立 wheel 验收环境
    ├── target/                       # Cargo 构建产物
    └── dist/                         # 源码包和 wheel
```

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

实测 Rust/Cargo `1.99.1`、rustfmt `1.10.0-stable`、Clippy `0.1.99`、uv `0.13.5`。PyO3 0.30.1 的最低 Rust 要求为 1.85；本课只声明实际使用的工具链结果。Rust edition 与编译器版本是不同概念。

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
curl -LsSf https://astral.sh/uv/0.13.5/install.sh | sh
. "$HOME/.local/bin/env"
uv --version
```

环境文件适用于官方脚本的默认安装位置。已有 uv 时跳过，不覆盖系统 Python。

准备并检查 uv 托管的 Python：

<!-- verify: python-install -->
```bash
uv python install 3.12.15 --no-bin
uv python find 3.12.15
uv run --no-project --python 3.12.15 python -c 'import sys, sysconfig; print(sys.version); print(sys.executable); print(sysconfig.get_config_var("SOABI"))'
```

已有该版本时，安装命令报告已安装即可。`--no-bin` 不向 PATH 增加 Python 命令。输出应为 3.12.15，SOABI 类似 `cpython-312-x86_64-linux-gnu`，绝对安装路径因机器而异。

系统 Python 3.14 与本课的 uv 托管 Python 3.12 是不同解释器；本课不会修改 `/usr/bin/python3`。本次没有验证首次下载整个 Python 运行时的过程。初次获取 Python、Cargo crate 和 Python 依赖需要联网。

## 2. 检查现有仓库

**工作目录：仓库根目录。** 第一行路径是占位符，替换为你的 clone 的实际绝对路径：

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

沿用当前分支和历史，不再 `git init`。已有未提交工作继续保留；学习提交只暂存列出的练习路径。每次 `git commit` 会提交整个暂存区，先确认没有其他工作的暂存内容；不要用 reset 或 stash 自动搬动既有进度。

根忽略规则已经覆盖本课所需产物，内容如下。已有时不改，缺少时仅补齐对应规则，不覆盖个人规则：

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

`Cargo.lock`、`uv.lock`、`.python-version`、`.pyi` 和空 `py.typed` 都需要提交。Rust 的 `target/`、Python 环境、缓存与 `.so` 不提交。`reference/` 继续忽略，不使用 `git add -f`。

本次编写第六课时，第五课教材和共享根索引尚未提交。下面的三个学习提交只包含本课练习；教程末尾另给出当前工作副本的两课教材合并提交命令。已有 clone 的学习者不需要重复提交已存在的教材。

检查 Git 身份：

<!-- verify: git-identity -->
```bash
git var GIT_AUTHOR_IDENT
```

只有身份缺失时，设置仓库局部身份，并替换占位内容：

<!-- verify: skip-git-identity -->
```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

## 3. 初始化独立的 uv 项目

**从仓库根目录开始：**

<!-- verify: init -->
```bash
mkdir -p 06-python-rust-pyo3/practice
cd 06-python-rust-pyo3/practice
pwd
uv init --bare --vcs none --no-workspace --python 3.12.15 --name py-rust-pyo3-add
mkdir -p native src/rust_add tests
```

`pwd` 应以 `ffi-lab/06-python-rust-pyo3/practice` 结尾。`--bare` 只初始化基础配置；`--vcs none` 不创建嵌套 Git 仓库；`--no-workspace` 让每课独立管理 Python 依赖。若已有练习文件，从原进度继续，不重新覆盖。

**从这里到第 11 节结束，除非另有说明，所有路径和命令以 practice 为基准。** 每份文件内容完整提供，用编辑器亲手输入，不把 Markdown 围栏写入文件。

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
name = "py-rust-pyo3-add"
version = "0.1.0"
description = "Learn to call a Rust add function from Python with PyO3"
readme = "README.md"
requires-python = ">=3.12,<3.13"

[dependency-groups]
dev = ["pytest==9.1.1", "ruff==0.17.2", "mypy==2.4.0"]

[tool.maturin]
bindings = "pyo3"
python-source = "src"
module-name = "rust_add._core"
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
  "src/rust_add/*.so",
  "src/rust_add/*.pyd",
  "**/__pycache__/**",
  "**/*.pyc",
  ".venv/**",
  ".venv-wheel/**",
  "target/**",
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

- Python 分发包名为 `py-rust-pyo3-add`，import 的包是 `rust_add`，内部扩展为 `rust_add._core`；名字各有用途，不要求所有字符串完全一样。
- `[build-system]` 固定 Maturin 后端；它在 uv 的隔离构建环境中运行，不需要全局安装，也不是本项目的运行时依赖。PyO3 是 Cargo crate，稍后写入 Cargo.toml。
- Python 限定为 3.12 系列，具体实测版本由 `.python-version` 指定；dev 组固定与第五课一致的 pytest、Ruff、mypy。
- `python-source` 与 `module-name` 配置混合项目布局：Python 包在 src/rust_add，Rust 扩展作为包内 `_core`。[Maturin 混合项目布局](https://www.maturin.rs/project_layout)
- `profile = "release"` 选择 Rust 优化构建；`locked = true` 要求使用已经生成且匹配的 Cargo.lock。第 4 节生成 Cargo 锁文件后再编译当前项目。
- `compatibility = "linux"` 只构建本机 Linux wheel，不进行 manylinux 发布处理；`strip` 去掉二进制中的非必要符号信息。未开启 abi3，不宣称跨 Python 小版本 ABI 稳定。
- 源码包默认由 Cargo 提供文件集合；Cargo.toml 会给出明确的源码清单。Maturin 的 include 补充说明、锁文件和测试，exclude 排除 editable 二进制和缓存，不把 include 单独误当白名单。[Maturin 配置](https://www.maturin.rs/config)
- Ruff 检查 Python 风格和常见问题，mypy 使用严格模式；`.venv-wheel` 明确排除在 Ruff 目录扫描外。

### 3.3 编写项目说明 `README.md`

先记录最终项目的接口与操作方式，供以后单独进入项目时回顾。现在只创建文件，说明中的命令会在后续各节实际执行。

<!-- file: README.md -->
````markdown
# Python 调用 Rust：加法

本项目使用 uv、PyO3 0.30.1、Maturin 1.15.0 和 Rust 2024 edition，
在同一个 Python 进程中调用 Rust 的 f64 加法。
目标环境为 Ubuntu/Linux x64、uv 0.13.5、CPython 3.12.15、Rust 1.99.1。

## 安装与运行

需要 uv、Rust/Cargo、rustfmt、Clippy 和系统 C 链接工具。
在本文件所在目录执行：

```bash
uv python install 3.12.15 --no-bin
cargo fetch --locked
uv sync --locked
uv run --no-sync python -m rust_add
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
```

演示输出 add(2, 3) = 5.0；测试应为 20 项通过。
Python、Cargo 与构建依赖首次下载需要联网。uv 创建本项目 .venv，
无需激活。Maturin 位于隔离构建环境，运行时无需安装 Maturin 或 PyO3。

## 接口与调用链

```python
from rust_add import add

result: float = add(2, 3)
assert result == 5.0
```

rust_add 导出 _core.add；PyO3 把 Python 数值转为 f64，
绑定调用 native/arithmetic.rs 中的纯 Rust 加法，再返回 Python float。
支持位置参数与 a、b 关键字，无默认值；类型和参数不匹配抛 TypeError。
纯加法返回 f64；模块注册使用 PyResult 和 ? 传播 Python 错误。

采用 PyO3 默认数值转换：bool 可转为 1.0/0.0，字符串不会按数字解析。
f64 不是 Python 任意精度整数，2**53 附近会有精度损失；小数近似比较。
NaN/Infinity 按浮点规则传播，浮点溢出可得到 Infinity。
接口不增加有限值限制，不引入异步或主动释放 GIL。

_core.pyi 与空 py.typed 提供静态类型；它们不参与运行时计算。
uv.lock 固定 Python 项目和开发依赖；Cargo.lock 固定 Rust 依赖，
Maturin 的构建后端版本由 build-system.requires 单独固定。

## 修改与清理

修改 Rust 或绑定后显式重编译，再测试：

```bash
uv sync --locked --reinstall-package py-rust-pyo3-add
uv run --no-sync pytest
uv run --no-sync python -m rust_add
```

editable 安装从 src 读取 Python 包，原生扩展也放在 src/rust_add。
cargo clean 不会删除包目录里的已安装扩展；清理时先移除这些产物：

```bash
uv run --no-project --python 3.12.15 python - <<'PYCODE'
from pathlib import Path

for pattern in ("_core*.so", "_core*.pyd"):
    for path in Path("src/rust_add").glob(pattern):
        path.unlink()
PYCODE
cargo clean
rm -rf .venv .venv-wheel dist .pytest_cache .ruff_cache .mypy_cache src/rust_add/__pycache__ tests/__pycache__
cargo fetch --locked
uv sync --locked --reinstall-package py-rust-pyo3-add
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
uv run --no-sync python -m rust_add
uv build
```

只在本项目目录执行清理。源码、两套锁文件和 Git 历史保留。
uv build 先创建源码包，再由源码包编译 wheel；只做本机 Linux 打包，
未启用 abi3、跨平台构建、manylinux 修复或上传。

## 版本控制

练习提交源码、配置、测试、README.md、.python-version、uv.lock、Cargo.lock
和空 py.typed；不提交环境、target、dist、缓存或生成的原生扩展。
reference 是按根仓库规则忽略的本地成品，不强制加入版本控制。
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
git -C ../.. diff -- 06-python-rust-pyo3/practice
git -C ../.. add 06-python-rust-pyo3/practice/.python-version 06-python-rust-pyo3/practice/pyproject.toml 06-python-rust-pyo3/practice/uv.lock 06-python-rust-pyo3/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure Python Rust addition project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

普通 `git diff` 不显示未跟踪文件内容，所以暂存后的 `git diff --cached` 是检查这些新文件的关键一步。其他教材仍可能显示未提交，但不应出现在本次暂存区中。

## 4. 编写 Rust 配置、纯加法和 PyO3 绑定

### 4.1 `Cargo.toml`

<!-- file: Cargo.toml -->
```toml
[package]
name = "py-rust-pyo3-add"
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
  "src/rust_add/*.py",
  "src/rust_add/*.pyi",
  "src/rust_add/py.typed",
  "tests/*.py",
]

[lib]
name = "_core"
path = "native/lib.rs"
crate-type = ["cdylib"]

[dependencies]
pyo3 = "=0.30.1"
```

`edition = "2024"` 选择语言规则；`rust-version` 声明最低工具链要求，但本课实测使用 1.99.1。`publish = false` 防止误发到 crates.io，本课也不会调用 PyPI 发布命令。

`[lib]` 指定 Rust 入口在 native/lib.rs，`cdylib` 生成供外部语言加载的动态库。库名 `_core`、下一节的模块函数名 `_core` 与 Maturin 的模块名末段保持一致。`pyo3 = "=0.30.1"` 精确固定直接依赖，Cargo.lock 还会固定间接依赖。

`include` 明确列出源码包需要的文件，使根仓库忽略的 reference 也可打包。它不把 `.venv`、target、dist 或源目录中的生成 `.so` 纳入 Cargo 文件集合；稍后 Maturin 还会处理 Python 包文件。Cargo 自动生成的分发元数据不需要手写。[Cargo 文件选择说明](https://doc.rust-lang.org/cargo/reference/manifest.html#the-exclude-and-include-fields)

当前 PyO3/Maturin 组合会处理扩展模块构建参数；不照搬旧版教程中的 `extension-module` feature，也不需要本课手写 build.rs。[Maturin 与 PyO3 版本说明](https://www.maturin.rs/tutorial)

### 4.2 `native/arithmetic.rs`

<!-- file: native/arithmetic.rs -->
```rust
pub fn add(a: f64, b: f64) -> f64 {
    a + b
}
```

这里只有普通 Rust `f64` 加法，不依赖 Python。输入是数值拷贝，没有借用 Python 对象；浮点溢出可能得到 Infinity，不会像有符号整数溢出那样引入另一套错误处理问题。

### 4.3 `native/lib.rs`

<!-- file: native/lib.rs -->
```rust
mod arithmetic;

use pyo3::prelude::*;

/// Add two numbers using Rust f64 arithmetic.
#[pyfunction]
#[pyo3(signature = (a, b))]
fn add(a: f64, b: f64) -> f64 {
    arithmetic::add(a, b)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(add, m)?)?;
    Ok(())
}
```

逐层看这份很短的绑定：

- `mod arithmetic` 引入纯 Rust 模块；绑定函数只负责调用它，计算不在 Python 包中重复实现。
- `#[pyfunction]` 生成 Python 可调用包装，按 `f64` 签名提取两个 Python 参数，并转换返回值。`#[pyo3(signature = (a, b))]` 明确两个参数的名字，支持位置和关键字调用，不添加默认值。
- `#[pymodule]` 导出扩展初始化入口。`Bound<'_, PyModule>` 是当前解释器上下文中的模块引用，`'_` 表示由编译器推断相关生命周期；本课不跨线程保存它。
- `wrap_pyfunction!` 把函数包装交给模块，`add_function` 完成注册。
- `PyResult<()>` 是 `Result<(), PyErr>` 的别名；这里用 `?` 传播注册失败。纯加法本身返回 `f64`，参数转换错误由 PyO3 生成的包装报告为 Python 异常，不用 panic 或 unwrap 处理预期失败。

只需要标量传值，不必在本课引入智能指针、复杂所有权模型或异步运行时。[PyO3 原生模块示例](https://docs.rs/pyo3/0.30.1/pyo3/#example-building-a-native-python-module)、[错误处理](https://pyo3.rs/v0.30.1/function/error-handling)

### 4.4 生成并获取 Rust 锁定依赖

<!-- verify: cargo-lock -->
```bash
cargo generate-lockfile
cargo fetch --locked
cargo fmt --all -- --check
```

Cargo.lock 由标准工具生成；本课不要手写，也不要等到 locked 构建失败后才补。成功标志是命令退出码为 0，格式检查没有差异；初次会显示锁定和下载日志，依赖条目及耗时不作为固定结果。

现在有两套锁文件：`uv.lock` 管理 Python 项目与开发依赖；`Cargo.lock` 管理 PyO3 及其 Rust 依赖；Maturin 版本单独由 `[build-system].requires` 固定。它们不锁定操作系统、系统链接器或 Rust 工具链二进制。[Cargo 锁文件说明](https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html)

首次手抄生成锁文件可能解析到后来更新的间接依赖；在已有成品中使用两份已生成的锁文件，才能重现本次依赖解析结果。

## 5. 编写 Python 包与类型信息

### 5.1 `src/rust_add/__init__.py`

<!-- file: src/rust_add/__init__.py -->
```python
"""Expose the Rust addition function."""

from ._core import add as add

__all__ = ["add"]
```

重新导出原生函数，方便调用者使用 `from rust_add import add`；没有 Python 加法备用实现。`add as add` 明确向类型工具公开这个导出。

### 5.2 `src/rust_add/__main__.py`

<!-- file: src/rust_add/__main__.py -->
```python
"""Run the addition demo with python -m rust_add."""

from . import add


def main() -> None:
    print(f"add(2, 3) = {add(2, 3)}")


if __name__ == "__main__":
    main()
```

`python -m rust_add` 执行这个文件，普通 import 不会打印演示。

### 5.3 `src/rust_add/_core.pyi`

<!-- file: src/rust_add/_core.pyi -->
```python
def add(a: float, b: float) -> float: ...
```

`...` 是类型声明文件的正常语法，不是漏写 Rust 代码。静态工具允许 `float` 参数传入 `int`，并知道返回值是 float；运行时由编译后的扩展提供函数。

声明面向本课的整数/浮点调用方式；PyO3 默认转换还可能接受实现数值协议的对象，本课不扩展到所有协议类型，也不把 stub 当作运行时白名单。

### 5.4 创建空的 `src/rust_add/py.typed`

<!-- verify: typed-marker -->
```bash
touch src/rust_add/py.typed
```

这是 **0 字节空文件**，不要写入说明文字。它标记包包含类型信息，供安装后的 mypy 等工具使用。[类型信息分发规范](https://typing.python.org/en/latest/spec/distributing.html)

## 6. 编译安装、运行并检查

<!-- verify: build-demo -->
```bash
uv sync --locked
uv run --no-sync python -m rust_add
uv run --no-sync python -c 'import rust_add._core as native; print(native.__file__); print(native.add.__doc__); print(native.add.__text_signature__)'
uv run --no-sync ruff check src
uv run --no-sync ruff format --check src
uv run --no-sync mypy src
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
```

uv 在隔离环境中使用 Maturin，Maturin 调用 Cargo/rustc，编译并安装当前扩展。演示固定输出：

```text
add(2, 3) = 5.0
```

默认 editable 安装读取 src/rust_add，扩展通常也位于这个包目录，类似 `_core.cpython-312-x86_64-linux-gnu.so`；这与第五课将共享库安装在 .venv 中的布局不同。Rust 编译缓存位于 target，不要把缓存路径当作 Python 的导入路径。[Maturin 本地开发说明](https://www.maturin.rs/local_development)

函数说明应为 `Add two numbers using Rust f64 arithmetic.`，文本签名应为 `(a, b)`；绝对路径、日志顺序和耗时可能变化。静态检查退出成功。Clippy 的 `-D warnings` 将警告作为错误；`--all-targets` 检查当前 crate 各目标。

`PYO3_PYTHON` 只对紧随其后的 Cargo 命令生效，确保 PyO3 检测项目的 Python 3.12，而不是系统 3.14；不需要全局 export。这个检查不会替你重新安装改动后的扩展，运行行为仍需要下一节所示的显式重编译。

### 6.1 第二个里程碑：提交可运行的调用链

编译、演示和上述检查成功后执行：

<!-- verify: commit-implementation -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 06-python-rust-pyo3/practice
git -C ../.. add 06-python-rust-pyo3/practice/Cargo.toml 06-python-rust-pyo3/practice/Cargo.lock 06-python-rust-pyo3/practice/native/arithmetic.rs 06-python-rust-pyo3/practice/native/lib.rs 06-python-rust-pyo3/practice/src/rust_add/__init__.py 06-python-rust-pyo3/practice/src/rust_add/__main__.py 06-python-rust-pyo3/practice/src/rust_add/_core.pyi 06-python-rust-pyo3/practice/src/rust_add/py.typed
git -C ../.. diff --cached
git -C ../.. commit -m "feat: call Rust addition from Python with PyO3"
git -C ../.. status --short
git -C ../.. log -2 --oneline
```

## 7. 编写真实调用集成测试

创建 `tests/test_add.py`：

<!-- file: tests/test_add.py -->
```python
import importlib.machinery
import math
import sys
from pathlib import Path

import pytest

from rust_add import _core, add


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(2, 3, 5.0), (-2, -3, -5.0), (-2, 3, 1.0), (0, 0, 0.0)],
)
def test_numbers(a: float, b: float, expected: float) -> None:
    result = add(a, b)
    assert result == expected
    assert isinstance(result, float)


def test_decimal() -> None:
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_keywords() -> None:
    assert add(b=3, a=2) == 5.0


def test_bool_uses_default_numeric_conversion() -> None:
    assert add(True, False) == 1.0


def test_integer_precision_is_f64_precision() -> None:
    assert add(2**53, 1) == float(2**53)


def test_nan() -> None:
    assert math.isnan(add(math.nan, 1))


def test_infinity() -> None:
    assert add(math.inf, 1) == math.inf
    assert add(-math.inf, 1) == -math.inf
    assert math.isnan(add(math.inf, -math.inf))


def test_floating_point_overflow() -> None:
    assert add(sys.float_info.max, sys.float_info.max) == math.inf


@pytest.mark.parametrize("bad", ["3", None, [], {}, object()])
def test_invalid_types(bad: object) -> None:
    with pytest.raises(TypeError, match="while processing 'a'"):
        add(bad, 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="while processing 'b'"):
        add(1, bad)  # type: ignore[arg-type]


def test_missing_argument() -> None:
    with pytest.raises(TypeError):
        add(1)  # type: ignore[call-arg]


def test_extra_argument() -> None:
    with pytest.raises(TypeError):
        add(1, 2, 3)  # type: ignore[call-arg]


def test_unknown_keyword() -> None:
    with pytest.raises(TypeError):
        add(a=1, c=2)  # type: ignore[call-arg]


def test_real_native_extension() -> None:
    assert add is _core.add
    native_path = _core.__file__
    assert native_path is not None
    assert Path(native_path).is_file()
    assert any(
        native_path.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
```

运行完整测试和检查：

<!-- verify: tests -->
```bash
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
```

预期 **20 项通过**，全部检查通过。参数化正负数和非法类型会展开为多个测试；每项都经过真实 PyO3 扩展，没有 mock 或 Python 加法实现。

本课的行为与边界：

- f64 是 64 位二进制浮点；小数计算存在舍入误差，用 `pytest.approx` 比较 0.1 + 0.2。
- Python 的 int 可以是任意精度，但该接口转换为 f64；`add(2**53, 1)` 舍入为 `float(2**53)`，不能保留任意精度整数语义。
- 默认数值转换接受 bool，因此 `add(True, False)` 得到 1.0，不增加拒绝 bool 的业务规则。
- NaN 和 Infinity 按浮点规则传播，两个最大有限浮点数相加得到 Infinity；没有加入有限值限制。
- 字符串、None、容器与普通对象触发 TypeError。PyO3 0.30.1 在 Python 3.12 中通过异常的 `__notes__` 附带 `while processing 'a'` 或 `'b'` 上下文；参数个数或未知关键字同样触发 TypeError。
- 不照搬第五课的错误消息。pytest 的 `raises(..., match=...)` 会检查异常文本及 notes，所以类型测试可以匹配参数上下文；数量错误只断言异常类型，不固定整段版本相关文本。普通 `print(error)` 不会自动打印 notes，第 11 节展示如何单独读取。
- 故意违反静态签名的测试行使用具体 `type: ignore[...]`，让测试能验证运行时错误；其余文件仍严格检查。
- 公开函数就是 `_core.add`，原生路径必须存在且后缀属于当前解释器支持的扩展后缀；类型文件不能替代缺失的共享库。

## 8. 修改、清理重建与异目录运行

### 8.1 Rust 修改后重新编译安装

<!-- verify: rebuild -->
```bash
uv sync --locked --reinstall-package py-rust-pyo3-add
uv run --no-sync pytest
uv run --no-sync python -m rust_add
```

修改 Rust、PyO3 绑定或 Cargo 配置后执行该命令。`cargo clippy` 只检查，`cargo build` 只编译，不能据此假定 editable 包中的扩展已更新。这里让 Maturin 重新安装实际供 Python 使用的扩展。

| 修改内容 | 后续操作 |
| --- | --- |
| Rust 实现、绑定、Cargo 配置 | 显式重新编译安装，再测试与检查 |
| Python 或测试 | pytest、Ruff、mypy；分发内容改变时也重新安装 |
| 类型声明、包布局 | 重新安装并检查类型和导入 |
| 有意更新 Python 依赖 | uv lock，再 uv sync --locked 并完整检查 |
| 有意更新 Rust 依赖 | 重新生成并审阅 Cargo.lock，再编译、检查与测试 |
| 需要排除旧二进制 | 按下节同时清理 Cargo 缓存和包中的扩展 |

### 8.2 清理后重建

**仍在本课 practice。** 先确认 pwd；下面只删除已生成的扩展、环境与产物，保留源码、类型声明、两份锁文件和 Git 历史：

<!-- verify: clean-rebuild -->
```bash
pwd
uv run --no-project --python 3.12.15 python - <<'PYCODE'
from pathlib import Path

for pattern in ("_core*.so", "_core*.pyd"):
    for path in Path("src/rust_add").glob(pattern):
        path.unlink()
PYCODE
cargo clean
rm -rf .venv .venv-wheel dist .pytest_cache .ruff_cache .mypy_cache src/rust_add/__pycache__ tests/__pycache__
cargo fetch --locked
uv sync --locked --reinstall-package py-rust-pyo3-add
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
cargo fmt --all -- --check
PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --locked --all-targets -- -D warnings
uv run --no-sync python -m rust_add
```

Python 小段只遍历并删除生成扩展，不写源码；`--no-project` 使用托管解释器，即使项目环境损坏也能完成这项清理。单独 `cargo clean` 不会移除 src/rust_add 中先前安装的扩展，这就是要分开清理的原因。

应重新生成环境、target 与原生库，依然 20 项通过、所有检查通过、输出 5.0。不需要清空全局 Cargo 或 uv 缓存。

### 8.3 从其他目录运行

使用子 shell 改变目录，结束后仍回到外层 practice：

<!-- verify: other-directories -->
```bash
(
  cd ../..
  06-python-rust-pyo3/practice/.venv/bin/python -m rust_add
)
(
  project_python="$PWD/.venv/bin/python"
  cd /tmp
  "$project_python" -m rust_add
)
```

两次都应打印 `add(2, 3) = 5.0`，没有设置 PYTHONPATH、修改 sys.path 或复制共享库到当前工作目录。

## 9. 从源码包构建 wheel 并独立安装

只执行本地打包，不上传：

<!-- verify: build-wheel -->
```bash
uv build
ls -1 dist
uv venv --python 3.12.15 .venv-wheel
uv pip install --python .venv-wheel/bin/python --no-deps dist/*.whl
.venv-wheel/bin/python -I -m rust_add
.venv-wheel/bin/python -I -c 'import rust_add._core as native; from rust_add import add; print(native.__file__); assert add(2, 3) == 5.0'
```

`uv build` 默认先创建源码包，再从这个源码包编译 wheel，因此缺源码、锁文件或绑定配置会在这里暴露。[uv 构建说明](https://docs.astral.sh/uv/guides/package/)

本次 Cargo package 提示未填写发布元数据；本课没有配置对外发布信息，该提示不影响本地打包成功，也不属于 Clippy 的代码警告。

本机文件名为：

```text
py_rust_pyo3_add-0.1.0-cp312-cp312-linux_x86_64.whl
py_rust_pyo3_add-0.1.0.tar.gz
```

独立 `.venv-wheel` 没有 editable 安装，原生库应位于其 site-packages/rust_add 中。`--no-deps` 确认包不依赖第三方 Python 运行时包；`-I` 使用隔离模式，避免当前目录和 PYTHONPATH 干扰。演示仍得到 5.0。

查看分发包内容：

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

源码包应包含 Rust 源码、Cargo 配置和锁文件、pyproject、Python 源码与类型信息、测试、README、Python 版本文件及 uv.lock。Cargo/Maturin 自动生成的清单或分发元数据可以存在；源码包不能混入环境、target、dist、缓存或 editable `.so`。

wheel 应包含 rust_add 的 Python 文件、stub、空 py.typed、最终原生扩展和分发元数据；不能漏掉扩展。wheel 标签限定本次 CPython、ABI、系统与架构，不能直接推断可跨平台使用。

## 10. 第三个里程碑：提交测试并最终检查

先验证锁文件、行为、静态检查和忽略规则：

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
uv run --no-sync python -m rust_add
git -C ../.. check-ignore 06-python-rust-pyo3/practice/.venv/ 06-python-rust-pyo3/practice/.venv-wheel/ 06-python-rust-pyo3/practice/target/ 06-python-rust-pyo3/practice/dist/ 06-python-rust-pyo3/practice/.pytest_cache/ 06-python-rust-pyo3/practice/.ruff_cache/ 06-python-rust-pyo3/practice/.mypy_cache/ 06-python-rust-pyo3/practice/src/rust_add/_core.example.so
git -C ../.. status --short --untracked-files=all
```

预期 20 项通过，Ruff、mypy、rustfmt、Clippy 均通过，演示得到 5.0；check-ignore 输出全部八个路径，最后的模拟文件路径用于检查 `.so` 规则，不会创建文件。项目说明应与最终命令及接口一致。

提交测试：

<!-- verify: commit-tests -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 06-python-rust-pyo3/practice
git -C ../.. add 06-python-rust-pyo3/practice/tests/test_add.py
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify Python to Rust addition"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

三个学习提交分别记录 Python 项目配置、Rust 调用链与 Cargo 锁文件、真实集成测试。再次进入已有练习时，从已有进度继续，不重复初始化和创建相同提交。

## 11. 常见故障与定位

| 现象 | 检查命令或位置 | 处理步骤 |
| --- | --- | --- |
| 找不到 Rust、Cargo 或链接器 | `rustc --version`、`cargo --version`、`cc --version` | 按第 1 节补齐工具链，重新编译 |
| 缺少 rustfmt/Clippy | `rustfmt --version`、`cargo clippy --version` | 执行 rustup component add rustfmt clippy |
| Cargo 报最低 Rust 版本不满足 | 报错中的版本与 rustc --version | 有意更新 stable 后重新检查；本课实测 1.99.1 |
| 下载失败 | uv/Cargo 日志中的 URL、代理或证书错误 | 检查网络和本机代理/证书配置后重试，不关闭 TLS 校验 |
| 构建找不到 Cargo.lock 或拒绝修改锁文件 | Cargo.toml 与 Cargo.lock | 首次按第 4 节生成；有意改依赖后重新生成并审阅 |
| Python 版本不对 | `.python-version`、`uv run --no-sync python --version` | 安装指定托管版本；旧环境不匹配时清理重建 |
| Clippy 使用了系统 Python | Cargo 命令前的 PYO3_PYTHON | 指向当前项目 .venv/bin/python，不设置为其他课程的路径 |
| `No module named rust_add` | 项目解释器路径、当前工作目录 | 在 practice 执行 uv sync --locked，使用项目 Python 运行 |
| `_core` 导入失败 | 模块名、Cargo 库名、src/rust_add 中的扩展 | 三处命名对齐，清理后重新安装，不复制其他版本 .so |
| 改了 Rust 输出没变 | 源码是否保存、扩展的实际路径 | uv sync --locked --reinstall-package py-rust-pyo3-add，再运行新 Python 进程 |
| cargo clean 后仍能 import | src/rust_add 中原来的 .so | 按第 8 节清理 editable 产物，再重建 |
| 找不到全局 maturin 或 import pyo3 失败 | pyproject 的构建系统、Cargo.toml | 本课用 uv 调用隔离后端，PyO3 是 Rust crate，不需要这两个全局 Python 命令 |
| mypy 找不到原生函数类型 | `_core.pyi`、空 py.typed、重新导出写法 | 按第 5 节补齐并重新安装；声明不能替代原生实现 |
| Ruff 格式检查失败 | uv run --no-sync ruff format --check . | 按差异手动改，或主动运行 ruff format . 后审阅 diff |
| Rust 格式检查失败 | cargo fmt --all -- --check | 手动修正，或主动运行 cargo fmt --all 后审阅差异 |
| Clippy 警告导致失败 | 第一个报告的源码位置 | 修复后重查，不直接去掉 -D warnings |
| 锁文件与声明不匹配 | uv lock --check、Cargo 错误 | 有意更新对应锁文件，完整验证并一起提交 |
| 字符串被拒绝或整数精度变化 | 输入值与接口中的 f64 | 传入数值，按二进制浮点理解精度，不能用此接口保持任意精度整数 |
| reference 无法 git add | git check-ignore 06-python-rust-pyo3/reference/ | 沿用本地成品忽略约定，不强制暂存 |

直接观察正常调用和错误传播：

<!-- verify: diagnose -->
```bash
uv run --no-sync python - <<'PYCODE'
from rust_add import add

print(add(a=2, b=3))
try:
    add("2", 3)
except TypeError as error:
    print(type(error).__name__)
    print(error)
    for note in getattr(error, "__notes__", ()):
        print(note)
PYCODE
```

PyO3 0.30.1 在本机输出：

```text
5.0
TypeError
must be real number, not str
while processing 'a'
```

## 12. 最终验收清单

- [ ] 能区分 uv、Maturin、Cargo、PyO3 与 rustc 的职责。
- [ ] 能指出 Python 导出层、PyO3 绑定和纯 Rust 加法的位置。
- [ ] add(2, 3) 返回 float 类型的 5.0，关键字参数可用。
- [ ] 理解 f64 的整数精度、小数误差、bool、NaN/Infinity 行为。
- [ ] 20 项测试经过真实 Rust 扩展，错误类型与参数位置检查通过。
- [ ] Ruff、mypy、rustfmt 与 Clippy 均通过。
- [ ] 两套锁文件匹配声明，修改 Rust 后会重新编译安装。
- [ ] 能清理包中的 editable 扩展与 target，从源码重建成功。
- [ ] 从仓库根目录和 /tmp 启动成功，没有手动调整模块搜索路径。
- [ ] 源码包文件完整且没有缓存，独立环境安装 wheel 后可运行。
- [ ] 三个学习提交包含源码、配置、文档、测试、空标记和两套锁文件。
- [ ] 其他课程与个人进度保留，正式仓库的提交由自己执行。

## 教材维护者的提交命令

这一段只适用于本次新增教材仍未提交的工作副本，已有教材的 clone 学习者无需执行。

当前第五课也尚未提交，共享根索引包含第五、六课入口，Python 忽略规则来自第五课。为让根索引对应的两课文件一起进入历史，下列维护提交**明确包含第五、六课教材**，提交说明也覆盖两课；不包含任何 practice 或 reference。若第五课已经单独提交，相关路径再次 git add 不会产生新变更，仍需审阅暂存区。

使用本段命令处理当前两课新增教材时，不再重复第五课末尾只列一课的维护提交。若你希望拆分教材提交，先自行安排共享根索引的差异，再调整暂存范围；不要在存在无关暂存内容时执行 commit。

仍在 practice 时用第一行回到根目录；已在根目录则跳过第一行。完成本课验证后执行：

<!-- verify: commit-material -->
```bash
cd ../..
git status --short
git diff --check
git diff -- .gitignore README.md
git add .gitignore README.md 05-python-cpp-pybind11/README.md 05-python-cpp-pybind11/VERIFICATION.md 06-python-rust-pyo3/README.md 06-python-rust-pyo3/VERIFICATION.md
git diff --cached
git commit -m "docs: add verified Python native addition lessons"
git status --short
git log -1 --oneline
```

Agent 仅在隔离临时 clone 验证学习提交和上述教材提交，不代用户操作正式仓库的暂存、提交或推送。
