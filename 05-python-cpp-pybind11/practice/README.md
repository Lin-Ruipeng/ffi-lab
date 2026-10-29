# Python 调用 C++：加法

本项目使用 uv、pybind11、scikit-build-core、CMake 和 C++17，
在同一个 Python 进程中调用 C++ 的 double 加法。
实测 Ubuntu/Linux x64、uv 0.13.5、CPython 3.12.15。

## 安装与运行

需要支持 C++17 的编译器、CMake 3.18+ 和 uv。
在本文件所在目录执行：

```bash
uv python install 3.12.15 --no-bin
uv sync --locked
uv run --no-sync python -m cpp_add
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
```

演示输出 add(2, 3) = 5.0；测试应为 20 项通过。
首次获取 Python 与依赖需要联网。uv 创建本项目的 .venv，
无需激活，也不改系统 Python。构建依赖安装在临时隔离环境，
运行时无需单独安装 pybind11。

## 公开接口与调用链

```python
from cpp_add import add

result: float = add(2, 3)
assert result == 5.0
```

cpp_add 导出 _core.add；pybind11 将 Python 数值转换为 C++ double，
调用 native/add.cpp 中的加法，再将结果转成 Python float。
支持位置参数与 a、b 关键字，无默认值；错误类型或参数不匹配抛 TypeError。

采用 pybind11 默认数值转换：bool 可以转换为 1.0/0.0；字符串不会
作为数值解析。double 不是 Python 任意精度整数，超过 2**53 的整数
可能损失精度，小数存在二进制舍入误差。NaN/Infinity 按浮点规则传播，
浮点溢出可得到 Infinity。本课不额外限制有限值，也不释放 GIL。

_core.pyi 与 py.typed 为静态工具提供类型，不替代原生实现或运行时检查。
uv.lock 固定项目及开发依赖；build-system.requires 单独固定直接构建依赖，
其间接依赖与系统编译器不由 uv.lock 完整锁定。

## 修改、清理与打包

修改 C++ 或绑定后显式重编译，再运行测试：

```bash
uv sync --locked --reinstall-package py-cpp-pybind11-add
uv run --no-sync pytest
uv run --no-sync python -m cpp_add
```

editable 安装可直接读取 Python 源文件；C++ 改动仍需要编译。
清理当前项目的环境、编译和工具缓存后重新安装：

```bash
rm -rf .venv .venv-wheel build dist .pytest_cache .ruff_cache .mypy_cache src/cpp_add/__pycache__ tests/__pycache__
uv sync --locked --reinstall-package py-cpp-pybind11-add
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync python -m cpp_add
uv build
```

uv build 在 dist 中生成源码包，再由源码包编译 wheel；这里只在本地打包。
sdist 使用显式文件清单，使被根仓库忽略的 reference 也能完整打包。
wheel 带有 Python/系统/架构标签，不能像第一课的 Node-API 那样推断跨
Python 小版本 ABI 稳定性，也不能跨操作系统或架构直接复制使用。

## 版本控制

练习项目提交源码、配置、测试、README.md、.python-version 和 uv.lock。
.venv、缓存、build、dist、.so 不提交。reference 是本地对照成品，
遵循根仓库 reference/ 忽略规则，不强制加入版本控制。