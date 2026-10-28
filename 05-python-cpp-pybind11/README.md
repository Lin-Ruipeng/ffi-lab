# 第五课：从零用 Python 调用 C++

这一课只做一个同步加法函数：Python 调用 `add(2, 3)`，C++ 执行加法，Python 收到 `5.0`。你会亲手完成 uv 项目配置、C++ 实现、pybind11 绑定、编译安装、测试、静态检查、项目说明和 Git 提交。

本课实测 Ubuntu/Linux x64、uv 0.13.5、CPython 3.12.15、C++17 和 CMake。已有成品在本地 [reference/](reference/)，实测过程见 [VERIFICATION.md](VERIFICATION.md)。根仓库忽略 `reference/`，成品不会随 Git clone 分发；成品不存在时，照下面的完整内容创建 `practice/` 即可，不需要从成品复制任何文件。

## 0. 先理解技术路线、接口和目录

### 0.1 为什么选 pybind11

对于把现有 C++ 函数、类等 API 暴露给 Python，pybind11 是成熟的主流选择之一。其原作者介绍了它在 PyTorch、TensorFlow 等项目中的使用；这说明应用广泛，但不是所有 Python/C++ 调用方式的统一排名。[原作者的应用情况说明](https://nanobind.readthedocs.io/en/latest/why.html)

pybind11 用 C++ 模板和少量绑定代码处理 Python 对象与 C++ 类型之间的转换，适合本课。其[官方入门](https://pybind11.readthedocs.io/en/stable/basics.html)也以加法为例；本课采用官方支持的 [CMake + scikit-build-core 构建方式](https://pybind11.readthedocs.io/en/stable/compiling.html)。

简单区分其他路线：`ctypes` 适合调用 C ABI 的共享库，C++ API 通常需要另写 C 接口；Cython 适合编写或扩展带类型的 Python 风格代码；nanobind 也是 C++ 绑定方案。本课只实现 pybind11，不引入多套方案和性能比较。

### 0.2 公开接口与调用链

```python
from cpp_add import add

result: float = add(2, 3)
assert result == 5.0
```

公开接口是 `add(a: float, b: float) -> float`，接受整数、小数以及 `a`、`b` 关键字参数，没有默认值。Python 类型检查器允许在 `float` 参数位置传 `int`。C++ 函数为 `double add(double a, double b)`，返回值在 Python 中始终是 `float`。

```text
python -m cpp_add
    │ 执行 cpp_add/__main__.py
    ▼
cpp_add/__init__.py：导出 _core.add
    │ import 已编译、已安装的共享库
    ▼
cpp_add/_core.cpython-312-x86_64-linux-gnu.so
    │ PYBIND11_MODULE(_core, m) 注册 add
    ▼
native/bindings.cpp：pybind11 将 Python 数值转换为 double
    ▼
native/add.cpp：纯 C++ 计算 a + b
    │ double 转换为 Python float
    ▼
Python 得到 5.0
```

这是同一个 Python 进程里的同步调用。`.pyi` 类型声明不会执行，Python 也不会直接解释 `.cpp` 文件。调用时不启动 C++ 子进程，不经过 HTTP，也不读取 `.pyi` 来计算结果。

| 工具 | 本课职责 |
| --- | --- |
| uv | 选择项目 Python、创建 `.venv`、锁定依赖、调用构建后端并运行命令 |
| CPython | 执行 Python 代码并加载原生扩展；本课用 uv 托管版本 |
| pybind11 | 生成 Python/C++ 之间的绑定与类型转换代码，是头文件库 |
| scikit-build-core | Python 构建后端，将安装/打包请求交给 CMake |
| CMake / Ninja / G++ | 配置目标、调度编译、编译和链接 C++ 扩展 |
| pytest | 测试真实的跨语言调用 |
| Ruff / mypy | Python 格式、静态检查及基于类型声明的类型检查 |

与第一课的 Node-API 对照：本课普通 pybind11 扩展面向当前 Python ABI。wheel 标签标明 Python、ABI 和系统架构，不能直接假定一个 `.so` 能跨 Python 小版本、系统或架构使用。[Python 二进制分发标签](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)

### 0.3 最终目录

```text
05-python-cpp-pybind11/
├── README.md                         # 本实验手册
├── VERIFICATION.md                   # 实测记录
├── reference/                        # 本地对照成品，不提交
└── practice/                         # 由你从零创建
    ├── .python-version
    ├── pyproject.toml
    ├── uv.lock                       # uv 自动生成，需要提交
    ├── CMakeLists.txt
    ├── README.md                     # 你编写的项目说明
    ├── native/
    │   ├── add.hpp
    │   ├── add.cpp
    │   └── bindings.cpp
    ├── src/cpp_add/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── _core.pyi
    │   └── py.typed                  # 空文件
    ├── tests/test_add.py
    ├── .venv/                        # 项目环境，包含已安装的 .so
    ├── .venv-wheel/                  # 独立 wheel 验收环境
    ├── build/                        # CMake/Ninja 编译产物
    └── dist/                         # 源码包和 wheel
```

## 1. 检查并准备工具链

**工作目录：任意目录。** 先检查已有工具：

<!-- verify: tools -->
```bash
uv --version
cmake --version
c++ --version
git --version
file --version
nm --version
```

实测 uv `0.13.5`、CMake `4.2.3`、G++ `15.2.0`、Git `2.53.0`。CMake 至少 3.18，编译器需要支持 C++17。Ninja 会作为项目构建依赖安装，不需要全局安装。

只有缺少相应工具时，才在任意目录执行 Ubuntu 准备命令；这些命令需要自己的 sudo 权限：

<!-- verify: skip-sudo -->
```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git file binutils curl
```

只有缺少 uv 时，按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)安装本课实测版本：

<!-- verify: skip-uv-install -->
```bash
curl -LsSf https://astral.sh/uv/0.13.5/install.sh | sh
. "$HOME/.local/bin/env"
uv --version
```

上面的环境文件适用于使用官方脚本的默认安装位置；已经可以运行 uv 时跳过该块。不要为了本课切换系统 `/usr/bin/python3`。

准备 uv 托管的 Python，只安装版本化运行时，不向 PATH 增加 Python 命令：

<!-- verify: python-install -->
```bash
uv python install 3.12.15 --no-bin
uv python find 3.12.15
uv run --no-project --python 3.12.15 python -c 'import pathlib, sys, sysconfig; header = pathlib.Path(sysconfig.get_path("include")) / "Python.h"; print(sys.version); print(sys.executable); print(header); assert header.is_file()'
```

已有该版本时，安装命令报告已安装即可。本机系统 Python 是 3.14.4，但本课选用已具备开发头文件的 uv 托管 CPython 3.12.15；`.python-version` 会固定项目选择，`.venv` 与系统 Python 是不同环境。上面的断言应通过，输出路径随安装位置变化。

本课安装 uv 托管的 Python 来提供配套的 `Python.h`，不依赖 `python3 -m venv`、系统 pip 或系统 `python3-dev`。Python 和依赖首次下载需要联网。[uv 的 Python 管理说明](https://docs.astral.sh/uv/concepts/python-versions/)

## 2. 检查现有仓库和忽略规则

**工作目录：仓库根目录。** 第一行是占位路径，替换成你已有 clone 的实际绝对路径：

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

确认当前目录与 Git 根路径一致，沿用已有历史和分支，不再 `git init`。若有自己的未提交或暂存内容，先保留并安排好已有工作；本课只暂存列出的路径。`git commit` 会提交整个暂存区，只有确认没有无关暂存内容时才执行下面的学习提交，不要用 reset/stash 自动搬动原有进度。

根 `.gitignore` 的完整内容应为下方所示。已有内容完整时保持不动；缺少 Python 段时只补齐该段，保留原有规则：

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

`uv.lock`、`.python-version`、`.pyi` 和空的 `py.typed` 都要提交；`.venv`、缓存及编译产物不提交。`reference/` 的忽略规则是仓库现有约定，不要用 `git add -f` 把成品加入历史。

检查 Git 身份：

<!-- verify: git-identity -->
```bash
git var GIT_AUTHOR_IDENT
```

只有身份缺失时才设置仓库局部身份，替换下方占位内容：

<!-- verify: skip-git-identity -->
```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

## 3. 初始化独立的 Python 项目

**先从仓库根目录执行：**

<!-- verify: init -->
```bash
mkdir -p 05-python-cpp-pybind11/practice
cd 05-python-cpp-pybind11/practice
pwd
uv init --bare --vcs none --no-workspace --python 3.12.15 --name py-cpp-pybind11-add
mkdir -p native src/cpp_add tests
```

`pwd` 应以 `ffi-lab/05-python-cpp-pybind11/practice` 结尾。`--bare` 只生成基础配置，`--vcs none` 不创建嵌套 Git 仓库，`--no-workspace` 保证这一课独立管理依赖。若你已经有练习文件，从原进度继续，不要重新初始化和覆盖。

**从这里到第 11 节结束，除非另有说明，命令与文件路径都以 `practice/` 为基准。** 用编辑器亲手输入每份完整文件，围栏符号不要写入文件。

### 3.1 创建 `.python-version`

<!-- file: .python-version -->
```text
3.12.15
```

这记录项目解释器版本，uv 会读取它；直接在终端运行 `python3` 不会自动因此切换。

### 3.2 完整替换 `pyproject.toml`

<!-- file: pyproject.toml -->
```toml
[build-system]
requires = ["scikit-build-core==1.1.1", "pybind11==3.1.0"]
build-backend = "scikit_build_core.build"

[project]
name = "py-cpp-pybind11-add"
version = "0.1.0"
description = "Learn to call a C++ add function from Python with pybind11"
readme = "README.md"
requires-python = ">=3.12,<3.13"

[dependency-groups]
dev = ["pytest==9.1.1", "ruff==0.17.2", "mypy==2.4.0"]

[tool.scikit-build]
minimum-version = "1.1"
cmake.build-type = "Release"
ninja.version = "==1.13.2"
build-dir = "build/{wheel_tag}"
wheel.packages = ["src/cpp_add"]
sdist.inclusion-mode = "explicit"
sdist.include = [
  "pyproject.toml",
  ".python-version",
  "uv.lock",
  "README.md",
  "CMakeLists.txt",
  "native/*.hpp",
  "native/*.cpp",
  "src/cpp_add/*.py",
  "src/cpp_add/*.pyi",
  "src/cpp_add/py.typed",
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

配置的分工：

- `[project]` 描述可安装项目；分发包名是 `py-cpp-pybind11-add`，导入包名是 `cpp_add`，CMake 目标和原生模块名是 `_core`，三者用途不同。
- `requires-python` 将本课限定在 Python 3.12 系列，精确实测版本由 `.python-version` 记录。
- `[build-system]` 固定两个直接构建依赖：scikit-build-core 是后端，pybind11 提供头文件；`ninja.version` 固定后端按需安装的 Ninja 版本。它们只用于编译，不是运行时依赖，不需要塞进 `[project].dependencies`。
- `dev` 组是 pytest、Ruff、mypy；`uv sync` 默认安装该组。安装构建依赖时，uv 使用临时隔离环境，所以在 `.venv` 内 `import pybind11` 失败不代表构建未安装它。
- `build-dir` 保留本项目的 CMake 构建缓存；`wheel.packages` 把 Python 源码、类型声明和 `py.typed` 放进 wheel。稍后的 CMake `install` 把原生库放入同一个 `cpp_add` 包。
- `sdist.inclusion-mode = "explicit"` 只收集 `sdist.include` 匹配的文件，并独立于 Git 忽略规则。这样本地 `reference/` 虽被根仓库忽略，仍能完整打包，同时不收集环境、缓存和构建产物。注意 `include` 单独使用并不是白名单，`manual` 模式也不会自动排除所有环境目录；本课固定的 scikit-build-core 支持 `explicit` 模式。[源码包配置参考](https://scikit-build-core.readthedocs.io/en/stable/reference/configs.html#confval-sdist.inclusion-mode)
- Ruff 负责格式、常见错误、导入顺序与部分现代写法；mypy 使用严格模式检查源码和测试。C++ 警告稍后由编译器检查。

### 3.3 编写项目说明 `README.md`

先记录最终接口和命令，方便以后单独进入项目时回顾。下面是完整文件；其中的运行命令将在后续步骤逐一执行，现在先写文件。

<!-- file: README.md -->
````markdown
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

此时还没有 C++ 和 Python 包源码，所以先用 `--no-install-project` 安装开发依赖，不编译当前项目。`.venv` 与 `uv.lock` 由 uv 生成，不手写锁文件，也无需激活虚拟环境。

后续 `--locked` 检查声明与锁文件一致，不允许偷偷更新锁文件；`uv run --no-sync` 只运行已安装环境，不在演示或排错时隐式安装、重编译。[uv 锁定与同步说明](https://docs.astral.sh/uv/concepts/projects/sync/)

`uv.lock` 固定项目及开发依赖的解析结果；构建隔离环境的直接依赖由 `[build-system].requires` 固定，构建的间接依赖以及系统 CMake、编译器并不因此被完整锁定。后续验证记录会写明实际版本。第一次手抄项目的 `uv lock` 也可能解析到不同的间接依赖；若要重现本地成品的依赖树，在成品中使用已有的 `uv.lock`。

### 3.5 第一个里程碑：提交项目配置

确认上面的版本检查成功，再检查本里程碑的差异：

<!-- verify: commit-config -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- .gitignore 05-python-cpp-pybind11/practice
git -C ../.. add .gitignore 05-python-cpp-pybind11/practice/.python-version 05-python-cpp-pybind11/practice/pyproject.toml 05-python-cpp-pybind11/practice/uv.lock 05-python-cpp-pybind11/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure Python C++ addition project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

若根忽略规则早已提交，`git add .gitignore` 不会制造额外变更。`git diff` 不显示未跟踪文件内容，暂存后的 `git diff --cached` 才是检查这些新文件内容的关键步骤。

## 4. 编写纯 C++ 加法、绑定和构建配置

### 4.1 `native/add.hpp`

<!-- file: native/add.hpp -->
```cpp
#pragma once

namespace ffi_lab {

double add(double a, double b);

}  // namespace ffi_lab
```

这里只声明普通 C++ 函数，命名空间避免与其他库的同名函数冲突，不依赖 Python。

### 4.2 `native/add.cpp`

<!-- file: native/add.cpp -->
```cpp
#include "add.hpp"

namespace ffi_lab {

double add(double a, double b) {
  return a + b;
}

}  // namespace ffi_lab
```

计算只发生在这里。选择 `double` 可同时演示整数与小数输入，也避免用固定宽度有符号整数做加法时引入溢出未定义行为；它不保留 Python 任意精度整数的语义。

### 4.3 `native/bindings.cpp`

<!-- file: native/bindings.cpp -->
```cpp
#include <pybind11/pybind11.h>

#include "add.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_core, m) {
  m.doc() = "A C++ addition function exposed with pybind11";
  m.def("add", &ffi_lab::add, py::arg("a"), py::arg("b"),
        "Add two numbers using C++ double arithmetic.");
}
```

`pybind11/pybind11.h` 间接包含 `Python.h`，按官方约定放在首个 include。`PYBIND11_MODULE(_core, m)` 注册模块初始化入口；名字必须和构建目标 `_core` 一致。`m.def` 绑定函数指针，pybind11 根据 C++ 签名生成参数与返回值转换代码。`py::arg` 为两个参数命名，允许 Python 用 `a=`、`b=` 调用，不会添加默认值。

绑定采用 pybind11 默认数值转换，不加自定义验证层。参数类型或数量不匹配会在调用 C++ 加法之前抛 Python `TypeError`。本课没有业务异常；参数转换产生的 Python 错误由 pybind11 传播。[pybind11 函数参数](https://pybind11.readthedocs.io/en/stable/advanced/functions.html)、[异常转换](https://pybind11.readthedocs.io/en/stable/advanced/exceptions.html)

### 4.4 `CMakeLists.txt`

<!-- file: CMakeLists.txt -->
```cmake
cmake_minimum_required(VERSION 3.18...4.2)
project(py_cpp_pybind11_add LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_core native/add.cpp native/bindings.cpp)
target_compile_features(_core PRIVATE cxx_std_17)
set_target_properties(_core PROPERTIES CXX_EXTENSIONS OFF)

if(MSVC)
  target_compile_options(_core PRIVATE /W4 /WX)
else()
  target_compile_options(_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

install(TARGETS _core LIBRARY DESTINATION cpp_add RUNTIME DESTINATION cpp_add)
```

`find_package(Python ... Development.Module)` 查找正在构建的解释器及扩展开发头文件，先执行它使 pybind11 使用现代 FindPython 模式。`pybind11_add_module` 创建可导入的扩展，并处理平台后缀等细节。

`target_compile_features` 要求 C++17，关闭编译器语言扩展；G++/Clang 打开 `-Wall -Wextra -Wpedantic -Werror`，将警告作为错误。MSVC 分支保留通行写法，但本课未在 Windows 验证。

`install(TARGETS ...)` 的目标目录相对 wheel 的安装根，让 `_core` 最终位于 `cpp_add/` 内。单纯编译出共享库，不等于 Python 已经能 import；构建后端还需要安装布局和包内容。这里使用 `Development.Module`，不额外要求用于嵌入解释器的完整开发组件。[pybind11 的 CMake 支持](https://pybind11.readthedocs.io/en/stable/cmake/index.html)

## 5. 编写 Python 包与类型声明

### 5.1 `src/cpp_add/__init__.py`

<!-- file: src/cpp_add/__init__.py -->
```python
"""Expose the C++ addition function."""

from ._core import add as add

__all__ = ["add"]
```

这里重新导出原生函数，没有 Python 加法实现。显式 `add as add` 同时告知静态工具：这个导入就是公开接口。

### 5.2 `src/cpp_add/__main__.py`

<!-- file: src/cpp_add/__main__.py -->
```python
"""Run the addition demo with python -m cpp_add."""

from . import add


def main() -> None:
    print(f"add(2, 3) = {add(2, 3)}")


if __name__ == "__main__":
    main()
```

`python -m cpp_add` 执行该入口；普通 `import cpp_add` 不会打印演示。

### 5.3 `src/cpp_add/_core.pyi`

<!-- file: src/cpp_add/_core.pyi -->
```python
def add(a: float, b: float) -> float: ...
```

这是手写的静态接口声明，文件里的 `...` 是 stub 的正常语法，不是省略待实现代码。类型检查器可以据此拒绝字符串参数，并知道返回值是 `float`；真正的运行时仍然加载 `.so`。

本声明描述本课面向调用者的整数/浮点接口。底层 pybind11 还可能接受实现数值转换协议的对象；本课不对所有协议类型扩展声明，也不把它视为运行时白名单。

### 5.4 创建空的 `src/cpp_add/py.typed`

<!-- verify: typed-marker -->
```bash
touch src/cpp_add/py.typed
```

这必须是 **0 字节空文件**，不用写解释文字。它标记分发包提供类型信息，让安装后的包也能被 mypy 等工具识别。[Python 类型信息分发规范](https://typing.python.org/en/latest/spec/distributing.html)

## 6. 编译安装并运行真实调用

<!-- verify: build-demo -->
```bash
uv sync --locked
uv run --no-sync python -m cpp_add
uv run --no-sync python -c 'import cpp_add._core as native; print(native.__file__); print(native.add.__doc__)'
uv run --no-sync ruff check src
uv run --no-sync ruff format --check src
uv run --no-sync mypy src
```

`uv sync` 安装当前项目，会调用 scikit-build-core → CMake → Ninja → G++。默认采用 editable 安装：Python 源码保留在 `src` 中，原生 `.so` 安装进 `.venv`；不要把 editable 理解为“运行时编译 C++”。

固定演示输出：

```text
add(2, 3) = 5.0
```

原生文件路径应位于本项目 `.venv` 的 `site-packages/cpp_add/`，类似 `_core.cpython-312-x86_64-linux-gnu.so`；绝对前缀与平台后缀可能变化。函数 docstring 显示参数名和返回类型；pybind11 3.1.0 在本机显示 `SupportsFloat | SupportsIndex` 输入，而手写 stub 聚焦本课的 `float` 接口。编译和三项静态检查应退出成功，构建日志顺序与耗时不固定。

### 6.1 第二个里程碑：提交可运行的调用链

以上编译、演示、静态检查成功后执行：

<!-- verify: commit-implementation -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 05-python-cpp-pybind11/practice
git -C ../.. add 05-python-cpp-pybind11/practice/CMakeLists.txt 05-python-cpp-pybind11/practice/native/add.hpp 05-python-cpp-pybind11/practice/native/add.cpp 05-python-cpp-pybind11/practice/native/bindings.cpp 05-python-cpp-pybind11/practice/src/cpp_add/__init__.py 05-python-cpp-pybind11/practice/src/cpp_add/__main__.py 05-python-cpp-pybind11/practice/src/cpp_add/_core.pyi 05-python-cpp-pybind11/practice/src/cpp_add/py.typed
git -C ../.. diff --cached
git -C ../.. commit -m "feat: call C++ addition from Python with pybind11"
git -C ../.. status --short
git -C ../.. log -2 --oneline
```

## 7. 编写集成测试并理解数值边界

创建 `tests/test_add.py`：

<!-- file: tests/test_add.py -->
```python
import importlib.machinery
import math
import sys
from pathlib import Path

import pytest

from cpp_add import _core, add


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


def test_integer_precision_is_double_precision() -> None:
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
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(bad, 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(1, bad)  # type: ignore[arg-type]


def test_missing_argument() -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(1)  # type: ignore[call-arg]


def test_extra_argument() -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(1, 2, 3)  # type: ignore[call-arg]


def test_unknown_keyword() -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(a=1, c=2)  # type: ignore[call-arg]


def test_real_native_extension() -> None:
    assert add is _core.add
    assert add.__module__ == "cpp_add._core"
    native_path = _core.__file__
    assert native_path is not None
    assert Path(native_path).is_file()
    assert any(
        native_path.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
```

执行：

<!-- verify: tests -->
```bash
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
```

应为 **20 项测试通过**，Ruff 与 mypy 通过。参数化的正负数和错误类型各自展开为多个测试。测试直接导入编译后的 `_core`，没有 mock、Python 加法替代或复制算法作为实现。

这些行为是本课接口的一部分：

- C++ `double` 在本机是通常的 64 位二进制浮点，返回 Python `float`；`0.1 + 0.2` 使用 `pytest.approx` 判断，不断言十进制绝对精确。
- `add(2**53, 1)` 不能得到精确整数 `2**53 + 1`，本机舍入为 `float(2**53)`；不要把此接口用于任意精度整数运算。
- pybind11 默认接受 `bool` 的数值转换，所以 `add(True, False)` 为 `1.0`。本课不增加“拒绝 bool”的额外规则。
- NaN/Infinity 按浮点规则传播，两个最大有限值相加得到 Infinity；没有沿用第三、四课矩阵中“必须有限”的业务限制。
- 字符串不会被当数字解析；字符串、None、容器、普通对象，以及缺少、多余、未知关键字参数会触发 `TypeError`。测试只匹配稳定的错误片段，不绑定整个随版本变化的签名和参数 repr。
- 故意传错类型或参数数量的行，用具体的 `type: ignore[...]` 让测试能检查运行时错误；其他源码和测试仍经过严格类型检查。
- 原生路径存在且后缀属于当前解释器支持的扩展后缀，公开函数就是 `_core.add`。editable 安装可能包装加载器，因此不按加载器实现类名判断是否为原生模块。

## 8. 修改代码、清理重建与异目录运行

### 8.1 C++ 修改后显式重编译

<!-- verify: rebuild -->
```bash
uv sync --locked --reinstall-package py-cpp-pybind11-add
uv run --no-sync pytest
uv run --no-sync python -m cpp_add
```

这个命令要求重新构建并安装当前分发包。修改 C++、绑定或 CMake 后都运行它，再执行测试。只修改 Python 源码时，editable 安装可直接读取修改；仍要运行相应测试和静态检查。这里不启用导入时自动构建，避免把编译隐藏在 import 中。[uv 本地项目缓存](https://docs.astral.sh/uv/concepts/cache/)

| 修改内容 | 后续操作 |
| --- | --- |
| C++、绑定、CMake | 显式重编译，再运行测试、演示和检查 |
| Python、stub、测试 | 运行 pytest、Ruff 和 mypy；改变分发内容时也重新安装 |
| 依赖版本 | 有意编辑 pyproject，运行 uv lock，再 uv sync --locked 并完整检查 |
| 需要排除旧原生产物 | 按下节清理，再显式重编译 |

### 8.2 清理后从源码重建

**仍在本课 `practice/`。** 先用 `pwd` 确认目录；下方删除项全部是本项目的环境或产物，不删除源码、锁文件和 Git 历史：

<!-- verify: clean-rebuild -->
```bash
pwd
rm -rf .venv .venv-wheel build dist .pytest_cache .ruff_cache .mypy_cache src/cpp_add/__pycache__ tests/__pycache__
uv sync --locked --reinstall-package py-cpp-pybind11-add
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync python -m cpp_add
```

预期重新生成 `.venv`、构建目录和 `.so`，仍为 20 项通过、演示 `5.0`，检查通过。不需要删除 uv 全局缓存，也不重新初始化项目。

### 8.3 从仓库根目录和 `/tmp` 启动

用子 shell 切换目录，结束后外层仍处于 practice：

<!-- verify: other-directories -->
```bash
(
  cd ../..
  05-python-cpp-pybind11/practice/.venv/bin/python -m cpp_add
)
(
  project_python="$PWD/.venv/bin/python"
  cd /tmp
  "$project_python" -m cpp_add
)
```

两次均应输出 `add(2, 3) = 5.0`。使用本项目解释器和已安装包，加载不依赖当前工作目录，也不设置 `PYTHONPATH` 或 `sys.path`。

## 9. 构建源码包与 wheel，并独立安装验收

这一步是本地打包，不发布到 PyPI：

<!-- verify: build-wheel -->
```bash
uv build
ls -1 dist
uv venv --python 3.12.15 .venv-wheel
uv pip install --python .venv-wheel/bin/python --no-deps dist/*.whl
.venv-wheel/bin/python -I -m cpp_add
.venv-wheel/bin/python -I -c 'import cpp_add._core as native; from cpp_add import add; print(native.__file__); assert add(2, 3) == 5.0'
```

默认 `uv build` 先生成 `.tar.gz` 源码包，再用该源码包编译 `.whl`，能检查源码是否打包完整；不是仅从当前源码目录直接编译 wheel。[uv 构建说明](https://docs.astral.sh/uv/guides/package/)

本机文件名为：

```text
py_cpp_pybind11_add-0.1.0-cp312-cp312-linux_x86_64.whl
py_cpp_pybind11_add-0.1.0.tar.gz
```

wheel 名中的 `cp312-cp312-linux_x86_64` 表示本次 CPython、ABI 和平台。它没有经过 manylinux 修复或跨平台发布验证。

`.venv-wheel` 是第二个虚拟环境，`--no-deps` 确认这个加法包运行时不需要 pybind11 等第三方依赖。`-I` 使用 Python 隔离模式，避免当前目录或 `PYTHONPATH` 干扰；原生模块路径应位于 `.venv-wheel` 内，演示应得到 `5.0`。这是独立 wheel 的冒烟验收；完整 20 项集成测试已在项目环境执行。

查看两种分发包的内容：

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

源码包应包含完整 C++ 源码、头文件、CMake、Python 包、测试、说明和锁文件；wheel 应包含 `cpp_add` 的 Python 文件、`_core.pyi`、空 `py.typed`、原生 `.so` 和分发元数据。两者均不应包含 `.venv`、构建缓存或其他课程。

## 10. 第三个里程碑：提交测试并做最终检查

先检查行为、工具和忽略规则：

<!-- verify: acceptance -->
```bash
uv lock --check
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync python -m cpp_add
git -C ../.. check-ignore 05-python-cpp-pybind11/practice/.venv/ 05-python-cpp-pybind11/practice/.venv-wheel/ 05-python-cpp-pybind11/practice/build/ 05-python-cpp-pybind11/practice/dist/ 05-python-cpp-pybind11/practice/.pytest_cache/ 05-python-cpp-pybind11/practice/.ruff_cache/ 05-python-cpp-pybind11/practice/.mypy_cache/
git -C ../.. status --short --untracked-files=all
```

预期锁文件匹配、20 项通过、静态检查通过、演示 `5.0`，check-ignore 列出全部七类产物目录，状态中没有依赖或二进制。项目说明在第 3 节已经写全，此时核对其命令和接口与最终实现一致。

然后提交本里程碑：

<!-- verify: commit-tests -->
```bash
git -C ../.. status --short
git -C ../.. diff --check
git -C ../.. diff -- 05-python-cpp-pybind11/practice
git -C ../.. add 05-python-cpp-pybind11/practice/tests/test_add.py
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify Python to C++ addition"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

三个学习提交分别对应初始化配置、可运行调用链、集成测试。当前项目没有新的改动时不要重复创建相同提交；再次练习从自己的现有进度继续。

## 11. 常见故障与定位

| 现象 | 检查命令或位置 | 处理步骤 |
| --- | --- | --- |
| 找不到 uv | `command -v uv` | 按第 1 节安装，并加载安装器提示的 PATH |
| 下载失败 | uv 日志中的 URL、代理或证书错误 | 确认网络及本机代理/证书配置，再重试原命令；不要关闭 TLS 校验 |
| Python 版本不对 | `uv run --no-sync python --version`、`.python-version` | 用 uv 安装 3.12.15；旧环境指向其他版本时按第 8 节清理重建 |
| `Python.h` 不存在 | 第 1 节的头文件断言、`uv python find 3.12.15` | 确认使用 uv 托管运行时；不要混用系统解释器和另一个版本的头文件 |
| 找不到 CMake 或 C++ 编译器 | `cmake --version`、`c++ --version` | 补齐第 1 节工具链，重新编译 |
| `No module named cpp_add` | `uv run --no-sync python -c 'import sys; print(sys.executable)'` | 确认处于 practice，执行 uv sync --locked，使用项目解释器 |
| `_core` 导入失败 | `uv run --no-sync python -c 'import cpp_add._core as m; print(m.__file__)'` | 对照 CMake 目标、宏名字、安装目录；清理并重编译，避免复制其他 Python 的 .so |
| 项目环境无法 import pybind11 | `[build-system]` 和构建日志 | 这是构建隔离的正常结果，运行时不需要 import 它 |
| 改了 C++ 结果没变 | 原生路径、源码是否保存 | 运行 uv sync --locked --reinstall-package py-cpp-pybind11-add，再测试 |
| mypy 找不到 `_core` 类型 | `_core.pyi`、`py.typed` 和重新导出写法 | 补齐第 5 节的声明与空标记，重新安装后检查 |
| Ruff 格式检查失败 | `uv run --no-sync ruff format --check .` | 按差异手动修改，或主动运行 uv run --no-sync ruff format . 后审阅 diff |
| C++ 警告导致构建失败 | 编译日志中第一个源码位置 | 修正警告后重新编译；不直接删除 Werror 掩盖问题 |
| 锁文件被拒绝 | `uv lock --check`、pyproject 与 uv.lock 的差异 | 有意改依赖时运行 uv lock，再安装、验证并提交两份文件 |
| 小数不精确或大整数结果变化 | `uv run --no-sync python -c 'from cpp_add import add; print(add(0.1, 0.2)); print(add(2**53, 1))'` | 按 double 精度理解接口；近似测试用 pytest.approx，不把该接口用于任意精度运算 |
| 字符串被拒绝 | TypeError 中的函数签名 | 调用者传数值；本课不会自动把字符串解析为数字 |
| `git add reference` 提示忽略 | `git check-ignore 05-python-cpp-pybind11/reference/` | 遵循现有约定，只提交教材和练习，不强行加入成品 |

可直接观察正常调用和错误传播：

<!-- verify: diagnose -->
```bash
uv run --no-sync python - <<'PYCODE'
from cpp_add import add

print(add(a=2, b=3))
try:
    add("2", 3)
except TypeError as error:
    print(type(error).__name__)
    print(str(error).splitlines()[0])
PYCODE
```

固定部分：

```text
5.0
TypeError
add(): incompatible function arguments. The following argument types are supported:
```

## 12. 最终验收清单

- [ ] 能指出 Python 入口、导出层、pybind11 绑定和纯 C++ 加法分别在哪里。
- [ ] `from cpp_add import add` 可运行，`add(2, 3)` 得到 `float` 类型的 `5.0`。
- [ ] 知道整数会转换为 double，理解小数误差、2**53 精度、bool 和 NaN/Infinity 行为。
- [ ] 原生文件位于本项目环境，20 项真实调用测试通过。
- [ ] Ruff 检查、格式检查、mypy 与 C++ 警告检查均通过。
- [ ] 修改 C++ 后会显式重编译，清理后可以从锁文件重新安装和构建。
- [ ] 从根目录和 /tmp 运行成功，没有手动调整模块搜索路径。
- [ ] 源码包包含所需源码，独立环境可以安装并执行 wheel。
- [ ] 三个学习提交包含源码、配置、测试、文档、版本文件与锁文件，不含环境或产物。
- [ ] 保留其他课程与个人工作，没有在课程子目录初始化 Git 或发布到远端。

## 教材维护者的提交命令

只适用于本次新教材尚未提交的工作副本。先回到仓库根目录；如果还在 practice，用 `cd ../..`，已经在根目录则不用切换。确认本次检查完成、暂存区没有其他工作的内容，再执行：

<!-- verify: commit-material -->
```bash
cd ../..
git status --short
git diff --check
git diff -- .gitignore README.md
git add .gitignore README.md 05-python-cpp-pybind11/README.md 05-python-cpp-pybind11/VERIFICATION.md
git diff --cached
git commit -m "docs: add verified Python to C++ pybind11 lesson"
git status --short
git log -1 --oneline
```

如果已经在根目录，跳过该命令块第一行。暂存范围只包含根索引、忽略规则、本课手册与验证记录；`reference/` 继续保留本地，`practice/` 的三个学习提交单独完成。Agent 只在隔离临时仓库验证这些 Git 命令，正式仓库由你执行暂存、提交和推送。
