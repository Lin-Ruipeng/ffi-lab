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
