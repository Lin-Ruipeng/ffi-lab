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