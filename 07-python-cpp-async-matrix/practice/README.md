# Python 异步调用 C++：矩阵乘法

本项目使用 uv、CPython 3.12.15、pybind11、scikit-build-core、CMake/Ninja 和 C++17。
asyncio.to_thread 将同步原生调用交给默认线程池；C++ 计算期间释放 GIL。
实测 Ubuntu/Linux x64，运行时只依赖 Python 标准库与本包原生扩展。

## 安装与运行

需要 uv、CMake 3.18+、支持 C++17 的编译器和 Git。在本文件所在目录执行：

```bash
uv python install 3.12.15 --no-bin
uv sync --locked
uv run --no-sync python -m cpp_matrix
uv run --no-sync python -m cpp_matrix.heartbeat
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
```

2×3 乘 3×2 的结果为 [[58.0, 64.0], [139.0, 154.0]]。
主程序还展示 gather 并发和 OverflowError。心跳次数和耗时随机器变化。
首次安装需要联网；uv 使用独立 .venv，不修改系统 Python。

## 接口与数据边界

```python
import asyncio
from cpp_matrix import multiply_async


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

pybind11 将输入复制为 C++ vector<vector<double>>，在纯 C++ 校验和
乘法期间通过 call_guard<gil_scoped_release> 释放 GIL，返回前重新持有
GIL 并生成 Python 二维列表。输入快照与 Python/C++ 转换仍需要 GIL；
大输入不能保证事件循环完全没有短暂停顿。释放 GIL 本身不会创建线程。

沿用 pybind11 默认数值转换：bool 转换为 1.0/0.0，字符串不当作数字解析。
double 存在小数舍入误差，超过 2**53 的整数可能损失精度。
非法类型抛 TypeError，空矩阵、空行、不等长行、维度不兼容及 NaN/Infinity
抛 ValueError，乘法或累加产生非有限值抛 OverflowError。
参数数量/关键字错误在调用时抛出，函数体与后台错误在 await 时传播。

asyncio.gather 保持结果的输入顺序；return_exceptions=True 可收集各项错误。
取消 Task 或超时只取消等待，已经运行的 C++ 计算仍会继续；asyncio.run
退出时会等待默认线程池清理。没有原生抢占取消或取消令牌。

## 修改、清理与打包

修改 C++、绑定或 CMake 后显式重编译：

```bash
uv sync --locked --reinstall-package py-cpp-async-matrix
uv run --no-sync pytest
```

editable 安装可直接读取 Python 修改，原生代码仍须编译。
仅在本项目目录执行下列清理命令，保留源码与锁文件：

```bash
pwd
rm -rf .venv .venv-wheel build dist .pytest_cache .ruff_cache .mypy_cache src/cpp_matrix/__pycache__ tests/__pycache__
uv sync --locked --reinstall-package py-cpp-async-matrix
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv build
uv venv --python 3.12.15 .venv-wheel
uv pip install --python .venv-wheel/bin/python --no-deps dist/*.whl
.venv-wheel/bin/python -I -m cpp_matrix
```

uv build 先生成源码包，再从源码包编译 wheel。sdist 使用显式文件清单，
即使 reference 被 Git 忽略也能完整打包。wheel 带 Python/ABI/系统架构标签，
这里只验证本机安装，未验证跨平台发布。完整独立 wheel 测试和安装后类型检查
见上一级实验手册。

## 版本控制

提交源码、配置、测试、项目说明、.python-version、uv.lock 和空 py.typed。
.venv、.venv-wheel、build、dist、缓存与原生二进制不提交。
reference 作为本地成品按根规则忽略；practice 由学习者创建。
uv.lock 锁定项目/开发依赖，直接构建依赖和 Ninja 由配置固定；隔离构建的
间接依赖、系统 CMake 和编译器并不因此完全锁定。
