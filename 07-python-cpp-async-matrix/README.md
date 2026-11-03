# 第七课：Python 异步调用 C++ 矩阵乘法

这一课把第五课的同步加法扩展为异步矩阵乘法：Python 协程提交动态二维矩阵，默认线程池调用 C++，C++ 计算期间释放 GIL，结果或异常再回到等待它的协程。你会亲手完成配置、实现、类型声明、演示、真实集成测试、打包和分阶段 Git 提交。

沿用 uv、CPython 3.12.15、C++17、pybind11、scikit-build-core、CMake/Ninja、pytest、Ruff 和严格 mypy。实测平台为 Ubuntu/Linux x64；本地成品在 [reference/](reference/)，完整实测与边界见 [VERIFICATION.md](VERIFICATION.md)。`reference/` 继续被根仓库忽略，不随 clone 分发；成品不存在时，本手册足够从零创建 `practice/`。

## 0. 先理解数学、协程和线程边界

### 0.1 动态矩阵与公开接口

矩阵乘法是左边一行与右边一列做点积，不是逐个位置相乘。`m×n` 乘 `n×p` 得到 `m×p`，可以是矩形或单元素：

```text
A = [[1, 2, 3],       B = [[ 7,  8],
     [4, 5, 6]]           [ 9, 10],
                          [11, 12]]

C = [[58, 64],
     [139, 154]]

C[0][0] = 1×7 + 2×9 + 3×11 = 58
C[row][col] = 对所有 k 累加 A[row][k] × B[k][col]
```

公开接口如下；这里仅先看用法，稍后再创建文件：

```python
async def multiply_async(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]: ...
```

调用 `multiply_async(a, b)` 得到协程，`await` 后得到二维 `list`，每个元素为 Python `float`。接受位置参数及 `a=`、`b=` 关键字，无默认值。输入可用列表、元组等非文本 `Sequence`；字符串、字节序列、生成器不属于本课矩阵接口。类型标注中的 `float` 允许调用者传 `int`。

至少一行一列，各行等长，左列数等于右行数。形状和有限值错误抛 `ValueError`，非法类型抛 `TypeError`，乘法或中间累加产生非有限值抛 `OverflowError`。C++ 使用 `double`，小数有舍入误差，大整数可能损失精度；沿用第五课的数值转换，`bool` 可转成 `1.0/0.0`。

### 0.2 为什么既要线程池，也要释放 GIL

```text
Python 事件循环线程                    默认线程池的某个工作线程

multiply_async(a, b) → 协程对象
await / create_task / gather 使它开始执行
    ├─ 复制两层输入为 tuple
    └─ await asyncio.to_thread(...) ──────► pybind11 读取数值，复制为 C++ vector
          │                                  │ 持有 GIL
          │                                  ▼ call_guard 释放 GIL
其他协程、定时器继续运行                  纯 C++ 校验形状、有限值和三重循环
          │                                  │ 不访问 Python 对象
          │                                  ▼ 正常返回或异常展开后重新持有 GIL
          │                              生成 Python 二维列表或翻译异常
          ◄────────────────────────────── Future 完成，唤醒事件循环
await 得到结果，或在等待处抛出错误
```

与第三课的 Promise 不同，Python 调用 `async def` 通常只创建协程，不会立即排队执行。`asyncio.create_task` 安排它尽快运行；直接 `await` 会进入它的执行。仅在同步乘法外加 `async def`，仍然会阻塞事件循环。[Python 协程与任务](https://docs.python.org/3.12/library/asyncio-task.html#coroutines)

`to_thread` 负责把调用交给另一个线程；GIL 的释放允许这个线程计算时，其他线程继续执行 Python。只把持有 GIL 的长计算放进线程，仍可能让事件循环无法运行；只释放 GIL、却在事件循环线程同步调用 C++，那个线程仍要等函数返回。官方明确说明，释放 GIL 的扩展也适合用 `to_thread` 承载 CPU 计算。[asyncio.to_thread](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.to_thread)、[pybind11 的 GIL 约定](https://pybind11.readthedocs.io/en/stable/advanced/misc.html#global-interpreter-lock-gil)

快照在**协程开始执行时**建立，不是在创建协程对象时。复制的是两层容器，面向本课不可变的 int/float 数值；自定义数值对象的内部状态不会深拷贝。其他线程不应在快照过程中修改输入。快照完成后，原列表的修改不会影响任务。快照、参数转换与结果转换仍需要 GIL，因此本课不保证巨大输入完全没有暂停，也不承诺固定并行加速比。

### 0.3 最终目录与工具分工

```text
07-python-cpp-async-matrix/
├── README.md                         # 本手册
├── VERIFICATION.md                   # 实测记录
├── reference/                        # 本地成品，不提交
└── practice/                         # 下面由你创建
    ├── .python-version
    ├── pyproject.toml
    ├── uv.lock                       # uv 生成，提交
    ├── README.md                     # 你手写的项目说明
    ├── CMakeLists.txt
    ├── native/
    │   ├── matrix.hpp
    │   ├── matrix.cpp
    │   └── bindings.cpp
    ├── src/cpp_matrix/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── heartbeat.py
    │   ├── _core.pyi
    │   └── py.typed                  # 0 字节文件
    ├── tests/test_matrix.py
    ├── .venv/                        # 独立项目环境
    ├── .venv-wheel/                  # 独立 wheel 验收环境
    ├── build/                        # CMake/Ninja 与临时验收文件
    └── dist/                         # 源码包、wheel
```

uv 管理解释器、环境与依赖并调用构建后端；scikit-build-core 接入 CMake，Ninja 调度 G++ 编译；pybind11 完成绑定、转换和 GIL 管理；asyncio 使用进程内线程池；pytest 验证实际调用，Ruff/mypy 检查 Python。普通 pybind11 扩展面向当前 Python ABI，不假定跨 Python 小版本、系统或 CPU 架构通用。本课不引入 NumPy、BLAS、多进程或 C++ 自建线程池。

## 1. 检查并准备工具链

**工作目录：任意目录。**

<!-- verify: tools -->
```bash
uv --version
cmake --version
c++ --version
git --version
file --version
nm --version
```

本机 uv 为 `0.13.6`，CMake `4.2.3`，G++ `15.2.0`，Git `2.53.0`。需要 CMake 3.18+ 和 C++17 编译器；Ninja 由构建后端按版本配置提供，无需全局安装。

只有工具缺失时，才在任意目录执行下面的 Ubuntu 环境准备，需要自己的 sudo 权限：

<!-- verify: skip-sudo -->
```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git file binutils curl
```

只有找不到 uv 时，按[官方安装方法](https://docs.astral.sh/uv/getting-started/installation/)安装本课实测版本：

<!-- verify: skip-uv-install -->
```bash
curl -LsSf https://astral.sh/uv/0.13.6/install.sh | sh
. "$HOME/.local/bin/env"
uv --version
```

已有 uv 时跳过安装块；上面的环境文件对应官方脚本默认安装位置。准备独立的 Python 及开发头文件，不切换系统 Python：

<!-- verify: python-install -->
```bash
uv python install 3.12.15 --no-bin
uv python find 3.12.15
uv run --no-project --python 3.12.15 python -c 'import pathlib, sys, sysconfig; header = pathlib.Path(sysconfig.get_path("include")) / "Python.h"; print(sys.version); print(sys.executable); print(header); assert header.is_file()'
```

已有版本时提示已安装即可；断言应成功。系统 `/usr/bin/python3` 在本机是 3.14.4，本课使用 uv 托管 CPython 3.12.15，不混用系统头文件。首次获取解释器和依赖需要联网，本次使用已有运行时，没有重新下载整个 Python。[uv Python 管理](https://docs.astral.sh/uv/concepts/python-versions/)

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

`uv.lock`、`.python-version`、`.pyi` 和空 `py.typed` 要提交。`reference/` 按原规则忽略，不使用 `git add -f`。若你补了忽略规则，在第一个里程碑检查后，将 `.gitignore` 单独加入该次暂存。

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

## 3. 初始化独立 uv 项目

**先从仓库根目录执行：**

<!-- verify: init -->
```bash
mkdir -p 07-python-cpp-async-matrix/practice
cd 07-python-cpp-async-matrix/practice
pwd
uv init --bare --vcs none --no-workspace --python 3.12.15 --name py-cpp-async-matrix
mkdir -p native src/cpp_matrix tests
```

若 `practice/` 已经有你的文件，从已有进度继续，不重做初始化。`--bare` 生成基础配置，`--vcs none` 不创建嵌套 Git，`--no-workspace` 保持课程独立。

**从这里到第 13 节结束，除非另有说明，命令和文件路径都以本课 `practice/` 为基准。** 用编辑器手敲下面每个完整文件，不把围栏写入文件。

### 3.1 `.python-version`

<!-- file: .python-version -->
```text
3.12.15
```

精确选择项目解释器；`.venv` 由 uv 创建，无需激活。

### 3.2 完整替换 `pyproject.toml`

<!-- file: pyproject.toml -->
```toml
[build-system]
requires = ["scikit-build-core==1.1.1", "pybind11==3.1.0"]
build-backend = "scikit_build_core.build"

[project]
name = "py-cpp-async-matrix"
version = "0.1.0"
description = "Learn asynchronous Python to C++ matrix multiplication"
readme = "README.md"
requires-python = ">=3.12,<3.13"

[dependency-groups]
dev = ["pytest==9.1.1", "ruff==0.17.2", "mypy==2.4.0"]

[tool.scikit-build]
minimum-version = "1.1"
cmake.build-type = "Release"
ninja.version = "==1.13.2"
build-dir = "build/{wheel_tag}"
wheel.packages = ["src/cpp_matrix"]
sdist.inclusion-mode = "explicit"
sdist.include = [
  "pyproject.toml",
  ".python-version",
  "uv.lock",
  "README.md",
  "CMakeLists.txt",
  "native/*.hpp",
  "native/*.cpp",
  "src/cpp_matrix/*.py",
  "src/cpp_matrix/*.pyi",
  "src/cpp_matrix/py.typed",
  "tests/*.py",
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

分发包名 `py-cpp-async-matrix`、Python 导入包名 `cpp_matrix`、原生模块名 `_core` 分别服务于安装、import 和绑定注册。

`build-system` 固定第五课相同的 scikit-build-core/pybind11；Ninja 版本也固定。这些是隔离构建依赖，不是运行时依赖。`dev` 组保留 pytest、Ruff、mypy，不需要 pytest-asyncio；测试自己使用 `asyncio.run`。

`wheel.packages` 收集 Python 包及类型文件，CMake 稍后安装 `.so`。`sdist.inclusion-mode = "explicit"` 配合完整清单，确保被 Git 忽略的 reference 也能构建源码包，并排除环境和产物。[scikit-build-core 配置](https://scikit-build-core.readthedocs.io/en/stable/configuration/index.html)

Ruff 检查导入、常见错误和格式；mypy 对源码与测试使用严格模式；C++ 警告检查在编译阶段进行。

### 3.3 手写项目说明 `README.md`

先写完整的项目说明，之后逐项验证其中的接口和命令：

<!-- file: README.md -->
````markdown
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
````

### 3.4 生成锁文件并安装开发工具

<!-- verify: lock-dev -->
```bash
uv lock
uv sync --locked --no-install-project
uv run --no-sync python --version
uv run --no-sync pytest --version
uv run --no-sync ruff --version
uv run --no-sync mypy --version
```

此时还没有源码，先用 `--no-install-project` 安装开发依赖。`uv.lock` 由 uv 生成，不手写。`--locked` 要求声明和锁文件匹配；`uv run --no-sync` 只运行已安装环境，避免演示命令隐式触发安装。[uv 锁定与同步](https://docs.astral.sh/uv/concepts/projects/sync/)

锁文件固定项目和开发依赖；隔离构建的直接依赖由配置固定，构建的间接依赖及系统编译器不由该锁文件完全固定。首次手抄项目的解析结果可能不同；本地成品使用自己的锁文件。

### 3.5 第一个里程碑：提交配置

版本检查通过后执行：

<!-- verify: commit-config -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 07-python-cpp-async-matrix/practice
git -C ../.. add 07-python-cpp-async-matrix/practice/.python-version 07-python-cpp-async-matrix/practice/pyproject.toml 07-python-cpp-async-matrix/practice/uv.lock 07-python-cpp-async-matrix/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure Python C++ async matrix project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

未跟踪文件不显示在普通 `git diff` 中，暂存后的 `git diff --cached` 用来检查完整新增内容。

## 4. 编写纯 C++ 矩阵算法

### 4.1 `native/matrix.hpp`

<!-- file: native/matrix.hpp -->
```cpp
#pragma once

#include <vector>

namespace ffi_lab {

using Matrix = std::vector<std::vector<double>>;

Matrix multiply(const Matrix& a, const Matrix& b);

}  // namespace ffi_lab
```

每一行是一份 `vector<double>`，整张矩阵是嵌套 vector。不假定方阵，也不依赖 Python。与第三课的连续行主序数组相比，这里使用 pybind11 可自动转换的嵌套 STL 容器，行与行不保证连续。

### 4.2 `native/matrix.cpp`

<!-- file: native/matrix.cpp -->
```cpp
#include "matrix.hpp"

#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <string>

namespace ffi_lab {
namespace {

void validate(const Matrix& matrix, const std::string& name) {
  if (matrix.empty()) {
    throw std::invalid_argument(name + " must not be empty");
  }
  const auto cols = matrix.front().size();
  if (cols == 0) {
    throw std::invalid_argument(name + " rows must not be empty");
  }
  for (const auto& row : matrix) {
    if (row.size() != cols) {
      throw std::invalid_argument(name + " rows must have equal lengths");
    }
    for (const double value : row) {
      if (!std::isfinite(value)) {
        throw std::invalid_argument(name + " elements must be finite");
      }
    }
  }
}

}  // namespace

Matrix multiply(const Matrix& a, const Matrix& b) {
  validate(a, "a");
  validate(b, "b");
  const auto rows = a.size();
  const auto shared = a.front().size();
  const auto cols = b.front().size();
  if (shared != b.size()) {
    throw std::invalid_argument("a columns must equal b rows");
  }
  if (rows > std::numeric_limits<std::size_t>::max() / cols) {
    throw std::length_error("result dimensions exceed supported size");
  }

  Matrix result(rows, std::vector<double>(cols));
  for (std::size_t row = 0; row < rows; ++row) {
    for (std::size_t col = 0; col < cols; ++col) {
      double sum = 0;
      for (std::size_t k = 0; k < shared; ++k) {
        sum += a[row][k] * b[k][col];
        if (!std::isfinite(sum)) {
          throw std::overflow_error(
              "matrix multiplication produced a non-finite value");
        }
      }
      result[row][col] = sum;
    }
  }
  return result;
}

}  // namespace ffi_lab
```

先检查两个矩阵的形状和输入有限值，再检查相乘维度。结果元素数的整数乘法做溢出保护，分配失败由 pybind11 翻译为 `MemoryError`。极大内存分配不在本课实测范围。

三重循环逐项点积；每一步累加检查 `isfinite`，乘积或部分和溢出都失败，即使之后的项可能抵消也不会继续。这与第三课的有限值策略一致。小数舍入仍正常存在，检查不等于任意精度数学。

## 5. 编写绑定和构建配置

### 5.1 `native/bindings.cpp`

<!-- file: native/bindings.cpp -->
```cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "matrix.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_core, m) {
  m.doc() = "C++ matrix multiplication with the GIL released";
  m.def("multiply", &ffi_lab::multiply, py::arg("a"), py::arg("b"),
        py::call_guard<py::gil_scoped_release>(),
        "Multiply two finite rectangular matrices using C++ double arithmetic.");
}
```

`pybind11.h` 放在首个 include。`stl.h` 开启 Python 序列与嵌套 vector 的转换，每次跨边界会复制；原生函数获得的是自己拥有的数据，不是原列表视图。[STL 容器转换](https://pybind11.readthedocs.io/en/stable/advanced/cast/stl.html)

`call_guard<gil_scoped_release>` 只包住实际 C++ 函数调用：参数转换先在持有 GIL 时完成，返回后重新持有 GIL，再转换结果。异常展开也会恢复 GIL，再把 `invalid_argument/length_error` 翻译为 `ValueError`、`overflow_error` 翻译为 `OverflowError`。不能在这段纯 C++ 函数里访问 Python 对象、打印 Python 日志或调用 Python 回调。[调用策略](https://pybind11.readthedocs.io/en/stable/advanced/functions.html#additional-call-policies)、[异常翻译](https://pybind11.readthedocs.io/en/stable/advanced/exceptions.html)

GIL 管理不负责排队或创建线程；`_core.multiply` 本身仍是同步函数，异步调度在 Python 包里实现。

### 5.2 `CMakeLists.txt`

<!-- file: CMakeLists.txt -->
```cmake
cmake_minimum_required(VERSION 3.18...4.2)
project(py_cpp_async_matrix LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_core native/matrix.cpp native/bindings.cpp)
target_compile_features(_core PRIVATE cxx_std_17)
set_target_properties(_core PROPERTIES CXX_EXTENSIONS OFF)

if(MSVC)
  target_compile_options(_core PRIVATE /W4 /WX)
else()
  target_compile_options(_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

install(TARGETS _core LIBRARY DESTINATION cpp_matrix RUNTIME DESTINATION cpp_matrix)
```

先用 `FindPython` 查找当前解释器及 `Development.Module`，再找 pybind11。目标 `_core` 必须与 `PYBIND11_MODULE` 一致，安装到 `cpp_matrix/`。要求 C++17、关闭语言扩展，并把警告当错误；本课只实测 Linux/G++ 分支。[pybind11 CMake 支持](https://pybind11.readthedocs.io/en/stable/cmake/index.html)

## 6. 编写 Python 异步包与类型信息

### 6.1 `src/cpp_matrix/__init__.py`

<!-- file: src/cpp_matrix/__init__.py -->
```python
"""Run C++ matrix multiplication through asyncio's thread pool."""

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

`_snapshot` 限定为非文本序列，把外层和每行复制成不可变 tuple；具体数值仍由 pybind11 转换，Python 层没有乘法算法。协程执行到第一个 `await` 之前，两个快照已经建立；`to_thread` 随后将原生调用交给事件循环默认线程池。每个调用拥有独立输入和结果，没有共享计算缓存。

只创建协程后立即修改列表，协程启动时看到的是修改后的值；启动并完成快照后再修改，原生任务使用快照。不要照搬 JS Promise 返回前就拍快照的假设。

Python 在调用时检查参数数量与关键字，所以这些错误立即抛出。类型、形状与计算检查发生在函数体或后台，错误随 `await` 传播。取消 Task 或 `asyncio.timeout` 超时不会杀死已经运行的 C++；未开始的排队工作可能被取消。默认线程池由事件循环管理，`asyncio.run` 退出时会等待其关闭，不要把“停止等待”理解为“计算已经停止”。[线程任务取消](https://docs.python.org/3.12/library/concurrent.futures.html#concurrent.futures.Future.cancel)、[asyncio.run 生命周期](https://docs.python.org/3.12/library/asyncio-runner.html#asyncio.run)

### 6.2 `src/cpp_matrix/__main__.py`

<!-- file: src/cpp_matrix/__main__.py -->
```python
"""Run the result, concurrency and error demos with python -m cpp_matrix."""

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

### 6.3 `src/cpp_matrix/_core.pyi`

<!-- file: src/cpp_matrix/_core.pyi -->
```python
from collections.abc import Sequence

def multiply(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]: ...
```

这是同步原生内部接口的类型声明；公开异步函数的类型由 Python 源码提供。stub 中的 `...` 是合法声明语法，不是待补齐的算法。声明面向 int/float 调用者；pybind11 默认还可能接受实现数值转换协议的对象，不把 stub 当运行时白名单。

### 6.4 空的 `src/cpp_matrix/py.typed`

<!-- verify: typed-marker -->
```bash
touch src/cpp_matrix/py.typed
```

必须为 0 字节。它使安装后的包也携带可供 mypy 读取的类型信息。[类型分发规范](https://typing.python.org/en/latest/spec/distributing.html)

## 7. 编译、运行与第二个里程碑

<!-- verify: build-demo -->
```bash
uv sync --locked
uv run --no-sync python -m cpp_matrix
uv run --no-sync python -c 'import cpp_matrix._core as native; print(native.__file__); print(native.multiply.__doc__)'
uv run --no-sync ruff check src
uv run --no-sync ruff format --check src
uv run --no-sync mypy src
```

构建链为 uv → scikit-build-core → CMake → Ninja → G++。默认 editable 安装使 Python 源码仍从 `src` 读取，原生库安装进本项目 `.venv`，不是运行时解释 C++。隔离构建依赖不必出现在 `.venv` 的可导入包中。

固定演示输出：

```text
2x3 @ 3x2 = [[58.0, 64.0], [139.0, 154.0]]
gather = [[[11.0]], [[30.0, 35.0]]]
OverflowError: matrix multiplication produced a non-finite value
success: [[21.0]]
```

原生路径应指向本项目环境里的 `cpp_matrix/_core...so`；绝对前缀、扩展后缀、构建进度和 docstring 格式可能变化。三项检查应退出成功。

确认上面通过后提交实现：

<!-- verify: commit-implementation -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 07-python-cpp-async-matrix/practice
git -C ../.. add 07-python-cpp-async-matrix/practice/CMakeLists.txt 07-python-cpp-async-matrix/practice/native/matrix.hpp 07-python-cpp-async-matrix/practice/native/matrix.cpp 07-python-cpp-async-matrix/practice/native/bindings.cpp 07-python-cpp-async-matrix/practice/src/cpp_matrix/__init__.py 07-python-cpp-async-matrix/practice/src/cpp_matrix/__main__.py 07-python-cpp-async-matrix/practice/src/cpp_matrix/_core.pyi 07-python-cpp-async-matrix/practice/src/cpp_matrix/py.typed
git -C ../.. diff --cached
git -C ../.. commit -m "feat: call C++ matrix multiplication asynchronously from Python"
git -C ../.. status --short
git -C ../.. log -2 --oneline
```

## 8. 观察计算期间的心跳

编写完整的 `src/cpp_matrix/heartbeat.py`：

<!-- file: src/cpp_matrix/heartbeat.py -->
```python
"""Observe asyncio while a real C++ multiplication is running."""

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
uv run --no-sync python -m cpp_matrix.heartbeat
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

from cpp_matrix import _core, multiply_async


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


def test_bool_and_double_precision() -> None:
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
    with pytest.raises(TypeError, match="incompatible function arguments"):
        asyncio.run(multiply_async([[bad]], [[1]]))  # type: ignore[list-item]
    with pytest.raises(TypeError, match="incompatible function arguments"):
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
    assert _core.multiply.__module__ == "cpp_matrix._core"
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
```

预期 **49 项通过**，Ruff 检查/格式和严格 mypy 通过。参数化展开计入测试总数，耗时不固定。

几个关键检查：

- 正常结果包括不同矩形、单元素、正负数、零、单位矩阵、小数和元组输入。所有输出元素为 float，输出行互相独立，输入保持原值。
- 对非法类型在左右两处分别验证，形状和非有限值精确验证业务错误片段；不绑定 pybind11 整段随版本变化的签名文本。
- 先创建协程再修改输入，结果反映修改。快照测试用单线程池中的 Event 阻塞第一项工作，让矩阵任务排队；`sleep(0)` 只让协程开始并提交，不靠固定毫秒猜测计算时机。解除阻塞后必须得到原快照结果。
- `observe_native_call` 只在测试中临时加一个 Python 转发层，仍调用保存的真实 `_core.multiply`。`sys.setprofile` 观察该原生调用的 `c_call/c_return/c_exception`，记录线程和调用区间；它不替换算法。测试临时延长 Python 线程切换时间片，防止原生调用边界前的偶然调度被算成心跳；显式释放 GIL 仍允许事件循环运行。退出时恢复原函数、profiler 与原时间片。转发层让经 `Context.run` 调用的原生函数产生可观察的 Python 调用事件。
- 心跳必须发生在原生函数进入后、返回前。取消测试先等原生调用开始，再取消等待，随后等原生调用结束并检查另一项计算仍成功；Event 等待放在线程中，避免阻塞事件循环。10 秒只是失效保护，不是加速验收值。
- 这两项使用较大真实矩阵以留出观察窗口。极快机器若计算早于取消完成，可增加对应测试尺寸；不增加产品的睡眠或测试专用原生接口。
- `type: ignore[...]` 只出现在故意传错类型或参数的行，其他代码继续严格检查。原生文件路径与扩展后缀验证确保加载了实际共享库。

维护者会在隔离副本移除 GIL 释放，确认心跳测试失败；该故障实验不需要在你的正式练习里执行，记录见 VERIFICATION。

## 10. 修改、清理重建与异目录运行

### 10.1 修改原生源码后显式重编译

<!-- verify: rebuild -->
```bash
uv sync --locked --reinstall-package py-cpp-async-matrix
uv run --no-sync pytest
uv run --no-sync python -m cpp_matrix
```

C++、绑定或 CMake 修改后都执行上述步骤。Python、stub 或测试修改后运行测试/检查，分发内容改变时也重新安装。不依赖 import 自动触发编译。[uv 本地项目缓存](https://docs.astral.sh/uv/concepts/cache/)

### 10.2 清理本课产物后从锁文件重建

**仍在本课 `practice/`。** `pwd` 确认后再删除列出的环境、构建和缓存，不删除源码、锁文件或 Git 历史：

<!-- verify: clean-rebuild -->
```bash
pwd
rm -rf .venv .venv-wheel build dist .pytest_cache .ruff_cache .mypy_cache src/cpp_matrix/__pycache__ tests/__pycache__
uv sync --locked --reinstall-package py-cpp-async-matrix
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync python -m cpp_matrix
```

应重新生成 `.venv`、构建目录与 `.so`，49 项仍通过；不删除全局 uv 缓存。

### 10.3 从根目录和 `/tmp` 运行

两个子 shell 不改变外层当前目录：

<!-- verify: other-directories -->
```bash
(
  cd ../..
  07-python-cpp-async-matrix/practice/.venv/bin/python -m cpp_matrix
)
(
  project_python="$PWD/.venv/bin/python"
  cd /tmp
  "$project_python" -m cpp_matrix
)
```

两次均应得到第 7 节固定输出。通过已安装包加载，不手动设置 PYTHONPATH/sys.path，也不依赖当前工作目录。

## 11. 源码包、wheel 与安装后验收

### 11.1 从源码包构建 wheel 并独立安装

<!-- verify: build-wheel -->
```bash
uv build
ls -1 dist
uv venv --python 3.12.15 .venv-wheel
uv pip install --python .venv-wheel/bin/python --no-deps dist/*.whl
.venv-wheel/bin/python -I -m cpp_matrix
.venv-wheel/bin/python -I -c 'import asyncio; import cpp_matrix._core as native; from cpp_matrix import multiply_async; print(native.__file__); assert asyncio.run(multiply_async([[2]], [[3]])) == [[6.0]]'
```

`uv build` 默认先生成源码包，再从源码包构建 wheel，检查分发所需源码是否齐全。[uv 构建说明](https://docs.astral.sh/uv/guides/package/)

本机文件名：

```text
py_cpp_async_matrix-0.1.0.tar.gz
py_cpp_async_matrix-0.1.0-cp312-cp312-linux_x86_64.whl
```

`--no-deps` 安装后可以运行，说明本包运行时不需要单独安装 pybind11/scikit-build-core。`-I` 采用 Python 隔离模式，排除当前目录和 PYTHONPATH 干扰；原生路径应位于 `.venv-wheel`。这里只在本地打包，不发布 PyPI，也没有 manylinux 修复或跨平台验收。

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

源码包应包含 C++ 源码、头文件、CMake、Python 包、测试、说明和锁文件；wheel 应包含 Python 文件、stub、空 py.typed、原生扩展和分发元数据。不得包含虚拟环境、构建缓存或其他课程。

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
  "$wheel_python" -I -m mypy --strict --no-incremental -c 'from cpp_matrix import multiply_async
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
  "$wheel_python" -I -m mypy --strict --no-incremental -c 'from cpp_matrix import multiply_async
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
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync python -m cpp_matrix
uv run --no-sync python -m cpp_matrix.heartbeat
git -C ../.. check-ignore 07-python-cpp-async-matrix/practice/.venv/ 07-python-cpp-async-matrix/practice/.venv-wheel/ 07-python-cpp-async-matrix/practice/build/ 07-python-cpp-async-matrix/practice/dist/ 07-python-cpp-async-matrix/practice/.pytest_cache/ 07-python-cpp-async-matrix/practice/.ruff_cache/ 07-python-cpp-async-matrix/practice/.mypy_cache/
git -C ../.. status --short --untracked-files=all
```

锁文件匹配、49 项通过、全部检查通过、演示正确。check-ignore 列出七类目录，状态中没有依赖或二进制。核对项目说明与当前接口、命令一致后提交：

<!-- verify: commit-tests -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 07-python-cpp-async-matrix/practice
git -C ../.. add 07-python-cpp-async-matrix/practice/src/cpp_matrix/heartbeat.py 07-python-cpp-async-matrix/practice/tests/test_matrix.py
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify Python C++ async matrix behavior"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

三个学习提交依次为配置、可运行实现、心跳与测试。无需重复提交已有内容，课程子目录共享根仓库。

## 13. 常见故障与定位

以下检查均在本课 practice 执行：

| 现象 | 检查命令或位置 | 处理步骤 |
| --- | --- | --- |
| uv、CMake、编译器缺失 | `command -v uv`、`cmake --version`、`c++ --version` | 完成第 1 节环境准备后重试 |
| Python 版本不对或找不到 Python.h | `uv run --no-sync python --version`、第 1 节头文件断言 | 使用 uv 托管 3.12.15，旧环境按第 10 节清理重建 |
| 下载失败 | uv 日志中的 URL、代理、证书错误 | 修正网络或证书配置后重试原命令，不关闭 TLS 校验 |
| `No module named cpp_matrix` | `uv run --no-sync python -c 'import sys; print(sys.executable)'` | 确认在本课目录并执行 `uv sync --locked` |
| `_core` 导入失败或架构不匹配 | `uv run --no-sync python -c 'import cpp_matrix._core as m; print(m.__file__)'` | 核对模块名和 CMake 安装目录，清理重编译，不复制其他 Python 的 .so |
| RuntimeWarning: coroutine was never awaited | 是否只调用了 multiply_async | 在 async 函数内 await，顶层用 asyncio.run；并发用 create_task/gather |
| `asyncio.run() cannot be called from a running event loop` | 是否在 Notebook 或已有异步程序里再次 asyncio.run | 已有循环中直接 await，仅终端入口和同步 pytest 测试调用 asyncio.run |
| await 时出现 TypeError/ValueError | 参数容器、元素、形状与错误消息 | 传非文本二维序列和有限数值，核对左列数等于右行数 |
| OverflowError | 输入是否过大，是否中间和溢出 | 调整数值范围；有限输入不保证乘积/部分和有限 |
| 只有 async 却没有心跳 | 是否实际用了 to_thread，绑定是否释放 GIL | 对照第 5、6 节；直接在事件循环调用同步原生函数仍阻塞 |
| 小矩阵没有心跳 | 当前尺寸与运行耗时 | 增大演示尺寸，再观察；不把心跳次数当基准测试 |
| 快照结果与想象不同 | 是否只创建了协程对象还未运行 | 按协程启动时机理解；不要在其他线程并发修改正在复制的输入 |
| cancel 后进程仍在计算/退出等待 | 是否已有原生工作开始 | 取消只停止等待；让 C++ 正常结束，默认线程池随后关闭 |
| 修改 C++ 后结果没变化 | 原生路径与是否重新编译 | 执行 `uv sync --locked --reinstall-package py-cpp-async-matrix` 再测试 |
| Ruff/mypy 或编译警告失败 | 工具输出中的首个文件位置 | 修正具体问题；需格式化时运行 `uv run --no-sync ruff format .` 并审阅 diff，不删除严格检查配置 |
| 安装后的类型检查找不到类型 | wheel 的 _core.pyi、py.typed 和包源码 | 检查打包清单，重新构建、安装，再从 /tmp 检查 |
| `git add reference` 提示忽略 | `git check-ignore 07-python-cpp-async-matrix/reference/` | 遵循仓库约定，不强制暂存本地成品 |

观察绑定与错误传播：

<!-- verify: diagnose -->
```bash
uv run --no-sync python - <<'PYCODE'
import asyncio
from cpp_matrix import multiply_async

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

预期输出 `[[6.0]]`、`ValueError` 和 `a columns must equal b rows`。诊断片段不保存为项目文件。

## 14. 最终验收清单

- [ ] 能说清创建协程、启动协程、复制输入、线程池、GIL 释放与结果回传的先后关系。
- [ ] 动态矩阵得到正确形状和 float 数值，理解 double 舍入与有限值校验。
- [ ] 理解数量/关键字错误与后台业务错误的不同发生时机。
- [ ] 49 项真实调用测试、Ruff、严格 mypy 和 C++ 警告检查通过。
- [ ] 原生计算期间可观察到心跳，理解释放 GIL 和创建线程各自的作用。
- [ ] 理解 gather 的结果顺序与错误收集，取消等待后原生计算仍可能继续。
- [ ] 会显式重编译，能清理后从锁文件重建，并从根目录及 /tmp 启动。
- [ ] 源码包完整，独立 wheel 环境运行 49 项测试，安装后的正确/错误类型检查符合预期。
- [ ] 完成三个有意义的学习提交，包含源码、配置、测试、说明、版本文件与锁文件，不含产物。
- [ ] 保留其他课程与现有练习，没有在课程内初始化 Git 或发布到远端。

## 教材维护者的提交命令

适用于本次教材尚未提交的工作副本。**从仓库根目录开始**；若仍在 practice，先执行 `cd ../..`，已经在根目录就不切换。确认暂存区没有无关内容，再执行：

<!-- verify: commit-material -->
```bash
git status --short
git diff --check
git diff -- README.md 07-python-cpp-async-matrix/README.md 07-python-cpp-async-matrix/VERIFICATION.md
git add README.md 07-python-cpp-async-matrix/README.md 07-python-cpp-async-matrix/VERIFICATION.md
git diff --cached
git commit -m "docs: add verified Python C++ async matrix lesson"
git status --short
git log -1 --oneline
```

只暂存根索引、手册与验证记录。reference 保留本地，practice 的学习提交分开执行。Agent 只在隔离临时仓库验证 Git 命令，正式仓库的暂存、提交和推送由你完成。
