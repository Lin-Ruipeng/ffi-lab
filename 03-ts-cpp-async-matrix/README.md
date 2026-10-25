# 第三课：TypeScript 异步调用 C++ 矩阵乘法

这一课从同步加法走向后台计算：TS 提交两个二维矩阵，由 C++ 在 libuv 工作线程上完成乘法，再通过 Promise 把结果交还 TS。矩阵行列数由输入决定，支持 `m×n` 乘 `n×p`，不要求方阵。

本课面向 Ubuntu/Linux x64，使用 Node.js 24、TypeScript ESM、C++17、CMake、cmake-js 和 node-addon-api。对照成品在 [reference/](reference/)，实测与验证边界见 [VERIFICATION.md](VERIFICATION.md)。按下面顺序在 `practice/` 亲手写；前两课不需要重建。

## 0. 先理解数学、目录和线程边界

### 0.1 本课做哪种矩阵计算

这里的乘法是行与列做点积，不是对应位置相乘。左矩阵列数必须等于右矩阵行数：

```text
A = [[1, 2, 3],       B = [[ 7,  8],
     [4, 5, 6]]           [ 9, 10],
                          [11, 12]]

A 的形状 2×3，B 的形状 3×2，结果形状 2×2：

C = [[ 58,  64],
     [139, 154]]

C[0][0] = 1×7 + 2×9 + 3×11 = 58
C[row][col] = 对所有 k 累加 A[row][k] × B[k][col]
```

一般形式是 `m×n` 乘 `n×p`，输出 `m×p`。例如 `1×4` 乘 `4×1` 输出 `1×1`，`3×1` 乘 `1×4` 输出 `3×4`，无需修改接口或重新编译。

每个矩阵至少一行一列，每行等长。`[[1, 2], [3]]` 是不规则数组，不是本课接受的矩阵。元素用 JS `number` 与 C++ `double`，要求是有限值，拒绝 NaN/Infinity；正常小数仍遵循浮点误差规则。

### 0.2 最终目录

```text
03-ts-cpp-async-matrix/
├── README.md
├── VERIFICATION.md
├── reference/                    # 已验证的对照成品
└── practice/                     # 由你创建
    ├── .nvmrc
    ├── .clang-format
    ├── package.json
    ├── package-lock.json         # npm 自动生成
    ├── tsconfig.json
    ├── CMakeLists.txt
    ├── native/
    │   ├── matrix.hpp
    │   ├── matrix.cpp
    │   └── addon.cpp
    ├── src/
    │   ├── native.ts
    │   ├── index.ts
    │   └── heartbeat.ts
    ├── test/matrix.test.ts
    ├── README.md                 # 你手写的项目说明
    ├── node_modules/             # npm 生成
    ├── build/Release/addon.node   # CMake 构建
    └── dist/                     # tsc 输出
```

### 0.3 一次异步调用的生命周期

```text
JS 主线程                         libuv 工作线程

TS 编译后的 JS 调用 multiplyAsync(a, b)
    │
    ├─ 创建 Deferred Promise
    ├─ 检查参数，复制成独立 C++ vector
    ├─ 创建 MatrixWorker，Queue() ───────► 等待空闲线程
    └─ 返回 Promise，JS 继续执行              │
                                            ▼
                                      Execute()
                                      三重循环计算
                                            │
主线程处理定时器、其他回调                    │
                                            │ 完成或失败
    ◄───────────────────────────────────────┘
OnOK() / OnError()
    ├─ C++ 数据转回 JS 二维数组
    ├─ resolve / reject Promise
    └─ 框架销毁 worker，释放 vector

await 后面的代码在 Promise 完成后继续
```

`async` 和 Promise 描述调用与结果的关系；真正把 CPU 计算移出主线程的是 `AsyncWorker`。仅在同步函数外加 `async` 或 `Promise.resolve()`，内部乘法仍会占用主线程。

官方线程约定要求在 `Execute()` 中避免访问 JS 值或执行 JS；JS 交互放在主线程的完成回调。本课只在后台使用 C++ 数据和工作对象的 `SetError()` 状态接口。[AsyncWorker 官方说明](https://github.com/nodejs/node-addon-api/blob/v8.9.2/doc/async_worker.md)

## 1. 检查工具链

**工作目录：任意目录。** 先检查机器已有工具：

```bash
node --version
npm --version
cmake --version
c++ --version
make --version
git --version
node -p 'JSON.stringify({platform: process.platform, arch: process.arch, napi: process.versions.napi})'
```

实测 Node `24.21.0`、npm `12.2.1`、CMake `4.2.3`、G++ `15.2.0`、Make `4.4.1`。最后一条本机输出：

```text
{"platform":"linux","arch":"x64","napi":"10"}
```

CMake 至少 3.23，本课使用 Unix Makefiles；运行时支持 Node-API 10，而插件声明只用版本 8。这与 Node 主版本 24、node-addon-api 包版本 8.9.2 是不同概念。

**只有缺少工具时，才在任意目录运行 Ubuntu 安装命令：**

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git
```

当前机器已有所需工具，本次未执行 sudo 安装。如果使用已安装的 nvm，可选执行：

```bash
nvm install 24.21.0
nvm use 24.21.0
```

未使用 nvm 时不必为本课额外安装它，确保 Node 为 24.x。完成准备后重新执行第一组检查。C++ 格式沿用 Google 风格；本课的必需检查通过编译警告和 TS 类型检查完成，无需额外安装格式化器。

## 2. 检查现有 Git 仓库

**工作目录：仓库根目录。** 第一行是路径占位符，替换为你的 clone 的实际绝对路径：

```bash
cd "/请替换为你的实际路径/ffi-lab"
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
cat .gitignore
```

前两条路径检查应指向同一个 `ffi-lab`。课程子目录共享根仓库，不运行 `git init`。保留已有练习与未提交教材，后面的练习提交只列本课 `practice/` 路径；已有其他暂存内容时，先自行安排，确认每次提交只含对应里程碑。

根忽略规则已有 `node_modules/`、`build/`、`dist/`、`*.node`，覆盖所有课程。本课无需改根忽略文件，`package-lock.json` 要提交。

检查 Git 身份：

```bash
git var GIT_AUTHOR_IDENT
```

只有身份未配置时才执行下方命令，把占位文字替换为你自己的信息：

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

## 3. 初始化独立项目

**先在仓库根目录执行：**

```bash
mkdir -p 03-ts-cpp-async-matrix/practice
cd 03-ts-cpp-async-matrix/practice
pwd
npm init -y
mkdir -p native src test
```

`pwd` 应以 `ffi-lab/03-ts-cpp-async-matrix/practice` 结尾。已有练习文件时从已有进度继续，不要覆盖。

**从这里到第 13 节结束，除非另有说明，文件路径和命令均以 `practice/` 为基准。** 每个文件块都是完整内容，使用编辑器输入，不把 Markdown 围栏写入文件。

### 3.1 创建 `.nvmrc` 与 `.clang-format`

<!-- file: .nvmrc -->
```text
24.21.0
```

<!-- file: .clang-format -->
```yaml
BasedOnStyle: Google
```

`.nvmrc` 供 nvm 选择推荐版本；`.clang-format` 记录本项目的 C++ 风格，独立打开成品也能找到配置。编辑器或自己安装的 clang-format 可读取它；Google 风格的 C++ 缩进为两个空格。

### 3.2 编辑 `package.json`

将 `npm init -y` 生成的文件完整替换为：

<!-- file: package.json -->
```json
{
  "name": "ts-cpp-async-matrix",
  "version": "1.0.0",
  "private": true,
  "description": "Learn asynchronous C++ matrix multiplication from TypeScript with Node-API",
  "type": "module",
  "engines": {
    "node": ">=24 <25"
  },
  "scripts": {
    "build:native": "cmake-js build --config Release --generator \"Unix Makefiles\"",
    "build:ts": "tsc -p tsconfig.json",
    "build": "npm run build:native && npm run build:ts",
    "typecheck": "tsc -p tsconfig.json --noEmit",
    "check": "npm run build:native && npm run typecheck",
    "start": "node dist/src/index.js",
    "demo:heartbeat": "node dist/src/heartbeat.js",
    "test": "npm run build && node --test dist/test/matrix.test.js",
    "clean": "cmake -E rm -rf build dist"
  },
  "binary": {
    "napi_versions": [8]
  },
  "dependencies": {
    "node-addon-api": "8.9.2"
  },
  "devDependencies": {
    "@types/node": "24.19.2",
    "cmake-js": "8.0.0",
    "typescript": "7.0.2"
  }
}
```

关键配置与命令：

- `private` 防止误发布；`type: "module"` 使输出 `.js` 采用 ESM。
- 直接依赖版本沿用第一课，使用精确版本；TS 编译器、Node 类型和 cmake-js 都在项目内安装，无需全局命令。
- `binary.napi_versions: [8]` 让 cmake-js 使用 Node-API 构建路线，CMake 仍会明确声明 `NAPI_VERSION=8`。
- `build` 先构建 C++，再编译 TS；`test` 先构建再运行测试；`check` 检查原生构建和 TS 类型。
- `start` 与 `demo:heartbeat` 只运行已有 JS。更改源码后先重新构建；`clean` 只删除当前项目 `build/`、`dist/`。

### 3.3 创建 `tsconfig.json`

<!-- file: tsconfig.json -->
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "rootDir": ".",
    "outDir": "dist",
    "strict": true,
    "types": ["node"],
    "verbatimModuleSyntax": true,
    "noEmitOnError": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src/**/*.ts", "test/**/*.ts"]
}
```

`NodeNext` 配合 ESM 使用 Node 的导入规则，`strict` 开启严格检查。`rootDir: "."`、`outDir: "dist"` 使 `src/` 和 `test/` 分别输出为 `dist/src/`、`dist/test/`。`noEmitOnError` 防止出现类型错误时生成新 JS。

安装依赖，自动生成锁文件：

```bash
npm install
npm ls --depth=0
```

应列出 `node-addon-api@8.9.2`、`cmake-js@8.0.0`、`typescript@7.0.2`、`@types/node@24.19.2`。锁文件由 npm 生成，不手写；以后有锁文件时使用 `npm ci`。

### 3.4 第一个里程碑：配置

本阶段验收是安装成功、四个直接依赖没有缺失。尚未编写 C++，暂不运行完整构建。

```bash
git -C ../.. status --short
git -C ../.. diff -- 03-ts-cpp-async-matrix/practice
git -C ../.. add 03-ts-cpp-async-matrix/practice/.nvmrc 03-ts-cpp-async-matrix/practice/.clang-format 03-ts-cpp-async-matrix/practice/package.json 03-ts-cpp-async-matrix/practice/package-lock.json 03-ts-cpp-async-matrix/practice/tsconfig.json
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure asynchronous matrix addon project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

## 4. 编写独立于 Node 的矩阵算法

### 4.1 创建 `native/matrix.hpp`

<!-- file: native/matrix.hpp -->
```cpp
#pragma once

#include <cstddef>
#include <vector>

namespace ffi_lab {

struct Matrix {
  std::size_t rows;
  std::size_t cols;
  std::vector<double> data;
};

std::size_t CheckedElementCount(std::size_t rows, std::size_t cols);
Matrix Multiply(const Matrix& a, const Matrix& b);

}  // namespace ffi_lab
```

`Matrix` 用行数、列数和一个连续的 `vector<double>` 表示矩阵。采用按行存储：二维坐标 `(row, col)` 对应 `data[row * cols + col]`。相比保存 JS 数组引用，vector 拥有自己的数据，可安全移动到后台任务。

### 4.2 创建 `native/matrix.cpp`

<!-- file: native/matrix.cpp -->
```cpp
#include "matrix.hpp"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace ffi_lab {

std::size_t CheckedElementCount(std::size_t rows, std::size_t cols) {
  if (rows == 0 || cols == 0) {
    throw std::invalid_argument("matrix dimensions must be positive");
  }
  if (rows > std::numeric_limits<std::size_t>::max() / cols ||
      rows * cols > std::vector<double>().max_size()) {
    throw std::length_error("matrix dimensions exceed supported size");
  }
  return rows * cols;
}

Matrix Multiply(const Matrix& a, const Matrix& b) {
  if (a.cols != b.rows) {
    throw std::invalid_argument("a columns must equal b rows");
  }
  if (a.data.size() != CheckedElementCount(a.rows, a.cols) ||
      b.data.size() != CheckedElementCount(b.rows, b.cols)) {
    throw std::invalid_argument("matrix storage does not match its shape");
  }

  Matrix result{a.rows, b.cols,
                std::vector<double>(CheckedElementCount(a.rows, b.cols))};
  for (std::size_t row = 0; row < a.rows; ++row) {
    for (std::size_t col = 0; col < b.cols; ++col) {
      double sum = 0;
      for (std::size_t k = 0; k < a.cols; ++k) {
        sum += a.data[row * a.cols + k] * b.data[k * b.cols + col];
        if (!std::isfinite(sum)) {
          throw std::overflow_error(
              "matrix multiplication produced a non-finite value");
        }
      }
      result.data[row * result.cols + col] = sum;
    }
  }
  return result;
}

}  // namespace ffi_lab
```

`CheckedElementCount` 在分配前检查正维度、`size_t` 乘法溢出和 vector 的元素数上限。先比较 `rows > max / cols`，避免已经溢出后才判断。它保护尺寸计算，不保证任意巨大矩阵都有足够内存。

`Multiply` 再次检查形状与内部存储，然后使用 `row → col → k` 三重循环。计算复杂度约为 `O(m×n×p)`，结果空间为 `O(m×p)`。检查每步累加是否仍有限，溢出时抛出 `std::overflow_error`，下一节将它转换为 Promise rejection。

这两份文件不包含 `<napi.h>`，不知道 JS 或 Promise；Node 适配和数学计算由不同文件负责。

## 5. 编写 Node-API 异步绑定

创建 `native/addon.cpp`：

<!-- file: native/addon.cpp -->
```cpp
#include <napi.h>

#include <cmath>
#include <cstdint>
#include <exception>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include "matrix.hpp"

namespace {

ffi_lab::Matrix ReadMatrix(Napi::Env env, Napi::Value value,
                           const std::string& name) {
  if (!value.IsArray()) {
    throw Napi::TypeError::New(env, name + " must be an array of rows");
  }
  const auto array = value.As<Napi::Array>();
  const std::uint32_t rows = array.Length();
  if (rows == 0) {
    throw Napi::RangeError::New(env, name + " must not be empty");
  }

  ffi_lab::Matrix matrix{rows, 0, {}};
  for (std::uint32_t row = 0; row < rows; ++row) {
    Napi::HandleScope scope(env);
    if (!array.HasOwnProperty(std::to_string(row))) {
      throw Napi::TypeError::New(env, name + " must not contain sparse rows");
    }
    const Napi::Value row_value = array.Get(row);
    if (!row_value.IsArray()) {
      throw Napi::TypeError::New(env, name + " rows must be arrays");
    }
    const auto cells = row_value.As<Napi::Array>();
    if (row == 0) {
      matrix.cols = cells.Length();
      if (matrix.cols == 0) {
        throw Napi::RangeError::New(env, name + " rows must not be empty");
      }
      matrix.data.resize(
          ffi_lab::CheckedElementCount(matrix.rows, matrix.cols));
    } else if (cells.Length() != matrix.cols) {
      throw Napi::RangeError::New(env, name + " rows must have equal lengths");
    }

    for (std::uint32_t col = 0; col < matrix.cols; ++col) {
      if (!cells.HasOwnProperty(std::to_string(col))) {
        throw Napi::TypeError::New(env,
                                   name + " must not contain sparse elements");
      }
      const Napi::Value cell = cells.Get(col);
      if (!cell.IsNumber()) {
        throw Napi::TypeError::New(env, name + " elements must be numbers");
      }
      const double number = cell.As<Napi::Number>().DoubleValue();
      if (!std::isfinite(number)) {
        throw Napi::RangeError::New(env, name + " elements must be finite");
      }
      matrix.data[row * matrix.cols + col] = number;
    }
  }
  return matrix;
}

Napi::Array WriteMatrix(Napi::Env env, const ffi_lab::Matrix& matrix) {
  auto array = Napi::Array::New(env, matrix.rows);
  for (std::uint32_t row = 0; row < matrix.rows; ++row) {
    Napi::HandleScope scope(env);
    auto cells = Napi::Array::New(env, matrix.cols);
    for (std::uint32_t col = 0; col < matrix.cols; ++col) {
      cells.Set(col,
                Napi::Number::New(env, matrix.data[row * matrix.cols + col]));
    }
    array.Set(row, cells);
  }
  return array;
}

class MatrixWorker final : public Napi::AsyncWorker {
 public:
  MatrixWorker(Napi::Env env, Napi::Promise::Deferred deferred,
               ffi_lab::Matrix a, ffi_lab::Matrix b)
      : Napi::AsyncWorker(env, "ffi-lab:matrix-multiply"),
        deferred_(deferred),
        a_(std::move(a)),
        b_(std::move(b)) {}

  void Execute() override {
    try {
      result_ = ffi_lab::Multiply(a_, b_);
    } catch (const std::overflow_error& error) {
      range_error_ = true;
      SetError(error.what());
    }
  }

  void OnOK() override {
    try {
      deferred_.Resolve(WriteMatrix(Env(), result_));
    } catch (const Napi::Error& error) {
      deferred_.Reject(error.Value());
    } catch (const std::exception& error) {
      deferred_.Reject(Napi::Error::New(Env(), error.what()).Value());
    }
  }

  void OnError(const Napi::Error& error) override {
    if (range_error_) {
      deferred_.Reject(Napi::RangeError::New(Env(), error.Message()).Value());
    } else {
      deferred_.Reject(error.Value());
    }
  }

 private:
  Napi::Promise::Deferred deferred_;
  ffi_lab::Matrix a_;
  ffi_lab::Matrix b_;
  ffi_lab::Matrix result_{};
  bool range_error_ = false;
};

Napi::Value MultiplyAsync(const Napi::CallbackInfo& info) {
  const Napi::Env env = info.Env();
  const auto deferred = Napi::Promise::Deferred::New(env);
  try {
    if (info.Length() != 2) {
      throw Napi::TypeError::New(env,
                                 "multiplyAsync expects exactly 2 arguments");
    }
    auto a = ReadMatrix(env, info[0], "a");
    auto b = ReadMatrix(env, info[1], "b");
    if (a.cols != b.rows) {
      throw Napi::RangeError::New(env, "a columns must equal b rows");
    }
    ffi_lab::CheckedElementCount(a.rows, b.cols);
    auto worker = std::make_unique<MatrixWorker>(env, deferred, std::move(a),
                                                 std::move(b));
    worker->Queue();
    worker.release();
  } catch (const Napi::Error& error) {
    deferred.Reject(error.Value());
  } catch (const std::length_error& error) {
    deferred.Reject(Napi::RangeError::New(env, error.what()).Value());
  } catch (const std::exception& error) {
    deferred.Reject(Napi::Error::New(env, error.what()).Value());
  }
  return deferred.Promise();
}

Napi::Object Init(Napi::Env env, Napi::Object exports) {
  exports.Set("multiplyAsync", Napi::Function::New(env, MultiplyAsync));
  return exports;
}

}  // namespace

NODE_API_MODULE(addon, Init)
```

这份文件比较长，按下面四个阶段阅读。每个阶段属于哪个线程，比记住具体类名更重要。

### 5.1 主线程：读取并复制二维数组

`ReadMatrix` 检查两层都是普通 JS Array、每个位置都有自身属性、元素为有限 number，并检查非空与行长一致。稀疏数组的空洞会被拒绝，不会默默变成 0，也不接受 Float64Array 代替行。

`HasOwnProperty` 与 `Get` 访问的是真实运行时值；TS 的 `number[][]` 标注不会在运行时提供这些保护。每读到一个数字，复制到 vector 中。每行的 `HandleScope` 在该行结束时释放临时 JS 句柄，避免为整张矩阵保留所有临时句柄；存入 vector 的 double 不依赖这些句柄。

错误对应关系：

| 情况 | Promise 拒绝原因 |
| --- | --- |
| 参数数量不是两个、不是数组、行不是数组、元素类型错误、稀疏数组 | `TypeError` |
| 空矩阵、空行、行长不一致、乘法维度不相容、尺寸超出表示范围 | `RangeError` |
| 输入 NaN/Infinity，或后台浮点计算产生非有限结果 | `RangeError` |
| 其他标准 C++ 计算异常，如可捕获的分配失败 | `Error` |

读取用户 getter 本身可能触发 JS 异常，该异常会保留为拒绝原因；测试也覆盖这个路径。

### 5.2 主线程：Promise、排队与所有权

`MultiplyAsync` 先创建 `Promise::Deferred`，再在 `try` 内校验与排队。这样普通参数错误也会进入 `deferred.Reject(...)`，最终返回 Promise；TS 调用方统一使用 `await` 与 `try/catch`。

创建任务时通过 `std::move` 转交两个 vector，任务独立拥有数据。`make_unique` 暂时管理新对象；`Queue()` 失败抛出异常时自动释放对象，成功后 `release()` 才将生命周期交给 AsyncWorker。调用返回后修改原 JS 数组，不会改到 worker 的副本。

Deferred 负责创建、resolve 和 reject Promise，自身不会调度计算线程。[Promise 官方接口](https://github.com/nodejs/node-addon-api/blob/v8.9.2/doc/promises.md)

### 5.3 后台线程：只计算 C++ 数据

`Execute()` 调用纯 C++ `Multiply`。这里不能调用 `Env()` 创建 JS 值，也不能使用 `Napi::Array` 读取输入或调用 JS 回调。

浮点溢出被显式捕获，通过 `range_error_` 和 `SetError()` 记录；这些属于任务自身的 C++ 状态。其他 `std::exception` 由启用 C++ 异常的 AsyncWorker 包装捕获，并转向 `OnError()`。本课不给每个任务再创建额外线程，实际调度由 libuv 的共享线程池完成。

### 5.4 主线程：结果、错误与释放

`OnOK()` 将 vector 转成新的二维数组并 resolve。每行单独创建，结果行之间没有别名；JS 转换异常也会被捕获并 reject。

`OnError()` 根据后台记录的分类，以 RangeError 或普通 Error 拒绝 Promise。回调完成后框架自动销毁 worker，vector 随对象释放；不要在完成回调中再手动 `delete this`，也不要把已排队任务放在函数局部栈上。

## 6. 编写 CMake 配置并构建

创建项目顶层 `CMakeLists.txt`：

<!-- file: CMakeLists.txt -->
```cmake
cmake_minimum_required(VERSION 3.23)
project(ts_cpp_async_matrix LANGUAGES CXX)

add_library(addon SHARED
    native/matrix.cpp
    native/addon.cpp
    ${CMAKE_JS_SRC}
)

target_compile_features(addon PRIVATE cxx_std_17)
target_compile_definitions(addon PRIVATE
    NAPI_VERSION=8
    NODE_ADDON_API_CPP_EXCEPTIONS
)
target_include_directories(addon PRIVATE ${CMAKE_JS_INC})
target_link_libraries(addon PRIVATE ${CMAKE_JS_LIB})

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(addon PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

set_target_properties(addon PROPERTIES
    PREFIX ""
    SUFFIX ".node"
    CXX_EXTENSIONS OFF
)
```

此处沿用第一课的构建路线：

- CMake 显式列出两个 `.cpp`，头文件由 include 使用，不单独编译。
- `CMAKE_JS_INC`、`CMAKE_JS_LIB`、`CMAKE_JS_SRC` 由 cmake-js 准备，避免硬编码机器路径。
- `NODE_ADDON_API_CPP_EXCEPTIONS` 与编译器异常支持配合，使 JS 异常与标准 C++ 异常能走上述捕获流程。
- GCC/Clang 启用 `-Wall -Wextra -Wpedantic -Werror`，把编译警告作为失败。配置属于 addon 目标，不改仓库全局编译参数。
- 去掉默认库前缀并使用 `.node` 后缀，输出供 Node 加载的原生模块。

**当前目录：`practice/`。** 构建并检查产物：

```bash
npm run build:native
ls -l build/Release/addon.node
```

应出现类似的关键成功日志：

```text
[100%] Linking CXX shared library Release/addon.node
[100%] Built target addon
```

首次不要直接裸跑 `cmake -S . -B build`，本配置依赖 cmake-js 注入的宿主参数。配置完成后，单独增量构建可以使用：

```bash
cmake --build build --config Release
```

本课选择 CMake 而不是手写 g++ 链接命令，使用方式见 [node-addon-api CMake 指南](https://github.com/nodejs/node-addon-api/blob/v8.9.2/doc/cmake-js.md)与 [cmake-js 官方说明](https://github.com/cmake-js/cmake-js/blob/v8.0.0/README.md)。

## 7. 在 TypeScript 中加载和等待结果

### 7.1 创建 `src/native.ts`

<!-- file: src/native.ts -->
```ts
import { createRequire } from "node:module";

export type Matrix = readonly (readonly number[])[];

interface NativeAddon {
  multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]>;
}

const require = createRequire(import.meta.url);
const addon = require("../../build/Release/addon.node") as NativeAddon;

export const multiplyAsync: NativeAddon["multiplyAsync"] = addon.multiplyAsync;
```

`Matrix` 的两层 readonly 表示调用方可以传入只读矩阵；并不强制运行时冻结数组。结果是新的可修改 `number[][]`。

`NativeAddon` 手写描述原生导出；`as` 不验证二进制，所以后面的测试必须经过真实插件。直接导出原生函数保留它收到的真实参数数量，所有校验由 C++ 边界处理。

`createRequire(import.meta.url)` 从编译后的 `dist/src/native.js` 出发定位 `../../build/Release/addon.node`，不依赖终端当前目录。ESM 的普通 import 不直接加载 `.node`，此处沿用第一课的 require 桥接。[Node ESM 原生模块说明](https://nodejs.org/download/release/v24.21.0/docs/api/esm.html#no-addon-loading)

### 7.2 创建 `src/index.ts`

<!-- file: src/index.ts -->
```ts
import { multiplyAsync } from "./native.js";

const a = [[1, 2, 3], [4, 5, 6]];
const b = [[7, 8], [9, 10], [11, 12]];

const pending = multiplyAsync(a, b);
console.log("submitted; JavaScript continues before await");
console.log("2x3 * 3x2 =", JSON.stringify(await pending));

const products = await Promise.all([
  multiplyAsync([[2]], [[3]]),
  multiplyAsync([[1, 2, 3]], [[4], [5], [6]]),
]);
console.log("Promise.all =", JSON.stringify(products));

try {
  await multiplyAsync([[1, 2]], [[3, 4]]);
} catch (error) {
  if (!(error instanceof Error)) throw error;
  console.log("caught:", error.name, error.message);
}
```

这里有三种关键用法：

1. 调用后先保存 Promise，继续执行当前 JS，再 `await` 结果。`await` 暂停的是当前异步流程，事件循环可以处理其他工作。
2. `Promise.all` 一次等待多个已提交任务，结果数组仍按提交顺序排列；任务完成顺序不作保证，也不保证所有任务同时获得线程。
3. `try/catch` 捕获 `await` 遇到的拒绝，参数错误和后台计算错误都走这个调用方式。

源码里的相对导入写 `.js`，让 TS NodeNext 对应源码 `.ts`，并为 Node 保留可运行的输出路径。

### 7.3 编译并运行

```bash
npm run build:ts
npm start
npm run check
```

程序固定输出：

```text
submitted; JavaScript continues before await
2x3 * 3x2 = [[58,64],[139,154]]
Promise.all = [[[6]],[[32]]]
caught: RangeError a columns must equal b rows
```

`check` 在原生构建没有警告且 TS 检查没有错误时成功。之后可以统一用 `npm run build` 构建两端；不要直接 `node src/index.ts`，加载路径按编译后位置设计。

### 7.4 第二个里程碑：提交可运行实现

验收是矩阵结果与错误演示符合上面输出，`npm run check` 通过：

```bash
git -C ../.. status --short
git -C ../.. diff -- 03-ts-cpp-async-matrix/practice
git -C ../.. add 03-ts-cpp-async-matrix/practice/CMakeLists.txt 03-ts-cpp-async-matrix/practice/native/matrix.hpp 03-ts-cpp-async-matrix/practice/native/matrix.cpp 03-ts-cpp-async-matrix/practice/native/addon.cpp 03-ts-cpp-async-matrix/practice/src/native.ts 03-ts-cpp-async-matrix/practice/src/index.ts
git -C ../.. diff --cached
git -C ../.. commit -m "feat: multiply matrices asynchronously through Node-API"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

## 8. 观察后台计算时的心跳

创建 `src/heartbeat.ts`：

<!-- file: src/heartbeat.ts -->
```ts
import { performance } from "node:perf_hooks";

import { multiplyAsync } from "./native.js";

const rows = 600;
const shared = 800;
const cols = 500;
const a = Array.from({ length: rows }, () => Array<number>(shared).fill(1));
const b = Array.from({ length: shared }, () => Array<number>(cols).fill(1));

let beats = 0;
const timer = setInterval(() => {
  console.log(`heartbeat ${++beats}`);
}, 50);

try {
  const started = performance.now();
  const pending = multiplyAsync(a, b);
  console.log(`queued ${rows}x${shared} * ${shared}x${cols}; waiting with await`);
  const result = await pending;
  console.log(`result: ${result.length}x${result[0].length}; first = ${result[0][0]}`);
  console.log(`heartbeats: ${beats}; elapsed: ${(performance.now() - started).toFixed(1)} ms`);
} finally {
  clearInterval(timer);
}
```

执行：

```bash
npm run build:ts
npm run demo:heartbeat
```

它构造 `600×800` 和 `800×500` 的全 1 矩阵，结果形状应为 `600×500`，每个元素为 `800`。可能看到如下输出；心跳次数与耗时只是一次示意，不是固定结果：

```text
queued 600x800 * 800x500; waiting with await
heartbeat 1
heartbeat 2
...
result: 600x500; first = 800
heartbeats: 4; elapsed: 269.4 ms
```

真实次数可能更少或更多，极快机器上也可能为 0；需要更长的观察窗口时，增大文件中的三个维度，重新编译再运行。`finally` 保证成功或失败都会清除定时器。

**不是整个调用都不占主线程。** 构造 JS 数组、校验、复制输入，以及最终把结果转回 JS，仍会短暂占用主线程；只有三重循环计算被移到后台。`await` 也不等于另起一个 JS Worker。

libuv 的池还可能被文件系统、部分密码学等原生任务使用。并发请求过多时会排队；本课不修改线程池大小，也不承诺异步比同步更快。[Node 线程池说明](https://nodejs.org/download/release/v24.21.0/docs/api/cli.html#uv_threadpool_sizesize)

## 9. 为真实跨语言调用写测试

创建 `test/matrix.test.ts`：

<!-- file: test/matrix.test.ts -->
```ts
import assert from "node:assert/strict";
import { createHook } from "node:async_hooks";
import { test } from "node:test";

import { multiplyAsync, type Matrix } from "../src/native.js";

function referenceMultiply(a: Matrix, b: Matrix): number[][] {
  return a.map((row) => b[0].map((_, col) =>
    row.reduce((sum, value, k) => sum + value * b[k][col], 0),
  ));
}

async function rejectsArguments(
  args: unknown[],
  name: string,
  message?: string,
): Promise<void> {
  const pending: unknown = Reflect.apply(multiplyAsync, undefined, args);
  assert.ok(pending instanceof Promise);
  await assert.rejects(pending, message === undefined ? { name } : { name, message });
}

test("returns a Promise and settles after the caller continues", async () => {
  const events: string[] = [];
  const pending = multiplyAsync([[2]], [[3]]).then((result) => {
    events.push("resolved");
    return result;
  });
  assert.ok(pending instanceof Promise);
  events.push("returned");
  assert.deepEqual(events, ["returned"]);
  assert.deepEqual(await pending, [[6]]);
  assert.deepEqual(events, ["returned", "resolved"]);
});

test("multiplies a 2x3 matrix by a 3x2 matrix", async () => {
  assert.deepEqual(
    await multiplyAsync([[1, 2, 3], [4, 5, 6]], [[7, 8], [9, 10], [11, 12]]),
    [[58, 64], [139, 154]],
  );
});

test("supports different rectangular shapes and single elements", async () => {
  const cases: [Matrix, Matrix][] = [
    [[[3]], [[4]]],
    [[[1, 2, 3, 4]], [[2], [3], [4], [5]]],
    [[[2], [3], [4]], [[5, 6, 7, 8]]],
    [[[1, 2], [3, 4], [5, 6]], [[7, 8, 9], [10, 11, 12]]],
  ];
  for (const [a, b] of cases) {
    assert.deepEqual(await multiplyAsync(a, b), referenceMultiply(a, b));
  }
});

test("multiplies by identity matrices on either side", async () => {
  const matrix = [[1, 2, 3], [4, 5, 6]];
  assert.deepEqual(await multiplyAsync([[1, 0], [0, 1]], matrix), matrix);
  assert.deepEqual(
    await multiplyAsync(matrix, [[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
    matrix,
  );
});

test("handles zero matrices", async () => {
  assert.deepEqual(await multiplyAsync([[0, 0], [0, 0]], [[1], [2]]), [[0], [0]]);
  assert.deepEqual(await multiplyAsync([[1, 2]], [[0, 0], [0, 0]]), [[0, 0]]);
});

test("handles negative numbers", async () => {
  const a = [[-1, 2], [3, -4]];
  const b = [[5, -6], [-7, 8]];
  assert.deepEqual(await multiplyAsync(a, b), referenceMultiply(a, b));
});

test("handles decimals with a floating-point tolerance", async () => {
  const a = [[0.1, 0.2], [1.5, -2.25]];
  const b = [[0.3, 2.5], [0.4, -1.5]];
  const actual = await multiplyAsync(a, b);
  const expected = referenceMultiply(a, b);
  actual.forEach((row, i) => row.forEach((value, j) => {
    assert.ok(Math.abs(value - expected[i][j]) < 1e-12);
  }));
});

test("accepts readonly frozen matrices", async () => {
  const a = Object.freeze([Object.freeze([1, 2])]);
  const b = Object.freeze([Object.freeze([3]), Object.freeze([4])]);
  assert.deepEqual(await multiplyAsync(a, b), [[11]]);
});

test("does not modify input matrices", async () => {
  const a = [[1, 2], [3, 4]];
  const b = [[5], [6]];
  const before = structuredClone([a, b]);
  await multiplyAsync(a, b);
  assert.deepEqual([a, b], before);
});

test("uses input snapshots taken before returning the Promise", async () => {
  const a = [[1, 2], [3, 4]];
  const b = [[5], [6]];
  const pending = multiplyAsync(a, b);
  a[0][0] = 999;
  a.push([999, 999]);
  b[0][0] = -999;
  b[1] = [999];
  assert.deepEqual(await pending, [[17], [39]]);
});

test("returns independent output rows", async () => {
  const result = await multiplyAsync([[1], [2]], [[3, 4]]);
  assert.notEqual(result[0], result[1]);
  result[0][0] = 999;
  assert.deepEqual(result[1], [6, 8]);
});

test("keeps Promise.all jobs independent and preserves input ordering", async () => {
  const jobs: [Matrix, Matrix][] = [
    [[[1, 2]], [[3], [4]]],
    [[[5]], [[6, 7, 8]]],
    [[[1], [2], [3]], [[4, 5]]],
  ];
  const results = await Promise.all(jobs.map(([a, b]) => multiplyAsync(a, b)));
  assert.deepEqual(results, jobs.map(([a, b]) => referenceMultiply(a, b)));
});

test("rejects missing or extra arguments through a Promise", async () => {
  for (const args of [[], [[[1]]], [[[1]], [[2]], [[3]]]]) {
    await rejectsArguments(args, "TypeError", "multiplyAsync expects exactly 2 arguments");
  }
});

test("rejects non-array matrices in either position", async () => {
  const invalid: unknown[] = [undefined, null, 1, "1", true, {}, 1n, new Float64Array([1])];
  for (const value of invalid) {
    await rejectsArguments([value, [[1]]], "TypeError");
    await rejectsArguments([[[1]], value], "TypeError");
  }
});

test("rejects non-array rows in either position", async () => {
  for (const value of [1, "1", null, {}, new Float64Array([1])]) {
    await rejectsArguments([[value], [[1]]], "TypeError");
    await rejectsArguments([[[1]], [value]], "TypeError");
  }
});

test("rejects non-number elements in either position", async () => {
  const invalid: unknown[] = ["1", undefined, null, true, {}, 1n];
  for (const value of invalid) {
    await rejectsArguments([[[value]], [[1]]], "TypeError");
    await rejectsArguments([[[1]], [[value]]], "TypeError");
  }
});

test("rejects sparse outer arrays and sparse rows", async () => {
  const sparseOuter = new Array<unknown>(1);
  const sparseCells = [new Array<unknown>(1)];
  for (const value of [sparseOuter, sparseCells]) {
    await rejectsArguments([value, [[1]]], "TypeError");
    await rejectsArguments([[[1]], value], "TypeError");
  }
});

test("rejects empty matrices and empty rows", async () => {
  for (const value of [[], [[]], [[], []]]) {
    await rejectsArguments([value, [[1]]], "RangeError");
    await rejectsArguments([[[1]], value], "RangeError");
  }
});

test("rejects ragged matrices", async () => {
  for (const value of [[[1, 2], [3]], [[1], []]]) {
    await rejectsArguments([value, [[1]]], "RangeError");
    await rejectsArguments([[[1]], value], "RangeError");
  }
});

test("rejects incompatible multiplication dimensions", async () => {
  await rejectsArguments([[[1, 2]], [[3, 4]]], "RangeError", "a columns must equal b rows");
});

test("rejects NaN and Infinity inputs", async () => {
  for (const value of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    await rejectsArguments([[[value]], [[1]]], "RangeError");
    await rejectsArguments([[[1]], [[value]]], "RangeError");
  }
});

test("rejects overflow detected in background computation", async () => {
  await assert.rejects(multiplyAsync([[Number.MAX_VALUE]], [[2]]), {
    name: "RangeError",
    message: "matrix multiplication produced a non-finite value",
  });
  await assert.rejects(multiplyAsync([[Number.MAX_VALUE, Number.MAX_VALUE]], [[1], [1]]), {
    name: "RangeError",
  });
});

test("creates and completes the named native async resource", async () => {
  const ids = new Set<number>();
  const callbacks = new Set<number>();
  const hook = createHook({
    init(id, type) {
      if (type === "ffi-lab:matrix-multiply") ids.add(id);
    },
    before(id) {
      if (ids.has(id)) callbacks.add(id);
    },
  });
  hook.enable();
  try {
    assert.deepEqual(await multiplyAsync([[2]], [[4]]), [[8]]);
    assert.equal(ids.size, 1);
    assert.deepEqual(callbacks, ids);
  } finally {
    hook.disable();
  }
});

test("rejects an input getter exception without throwing synchronously", async () => {
  const failure = new Error("input getter failed");
  const a = [[1]];
  Object.defineProperty(a[0], "0", { get() { throw failure; } });
  const pending = multiplyAsync(a, [[1]]);
  assert.ok(pending instanceof Promise);
  await assert.rejects(pending, (error) => error === failure);
});

test("a failing job does not corrupt another queued job", async () => {
  const results = await Promise.allSettled([
    multiplyAsync([[Number.MAX_VALUE]], [[2]]),
    multiplyAsync([[3]], [[7]]),
  ]);
  assert.equal(results[0].status, "rejected");
  assert.deepEqual(results[1], { status: "fulfilled", value: [[21]] });
});
```

运行：

```bash
npm test
```

关键统计应为：

```text
ℹ tests 25
ℹ pass 25
ℹ fail 0
```

这些测试按以下目的组织：

- 小规模 TS 对照算法只用于测试预期值；被测函数始终调用 `.node`，不 mock、不用 JS 替代原生计算。
- 非方阵、不同尺寸、单位矩阵、零矩阵、负数和小数验证数学行为；浮点结果用容限比较。
- 只读输入、不修改输入、调用后的输入变更、独立结果行与多个并发任务验证数据所有权。
- `Reflect.apply` 故意绕过 TS 的正常调用约束，模拟动态 JS 错误参数；辅助函数先确认返回 Promise，再检查 rejection。
- `Number.MAX_VALUE × 2` 和两个大数累加触发后台溢出，验证 `Execute → SetError → OnError → reject`。
- `async_hooks` 只在诊断测试中观察 `ffi-lab:matrix-multiply`，确认创建了原生异步资源并运行完成回调。它与心跳演示及 Execute 的代码边界一起验证异步路径，不依赖某个毫秒阈值，也不把 Promise 本身当成后台计算的证明。

hook 中只记录数字与类型，不执行 console.log，避免日志产生新异步资源干扰观察。[Node async_hooks 文档](https://nodejs.org/download/release/v24.21.0/docs/api/async_hooks.html)

确认产物最新时，可单独重跑已编译测试：

```bash
node --test dist/test/matrix.test.js
```

源码改动后仍用 `npm test`，它会先构建两端。

## 10. 验证锁文件、清理重建和加载路径

### 10.1 从锁文件重装

```bash
npm ci
npm test
npm start
```

`npm ci` 按已有锁文件替换 node_modules，不负责更新锁文件。首次手抄项目的 `npm install` 会按当时解析间接依赖；需要严格使用交付成品依赖树时，在 `reference/` 使用其已有的锁文件。

### 10.2 清除构建目录后重建

```bash
npm run clean
npm test
npm run check
npm start
npm run demo:heartbeat
```

清理只删除本项目的 `build/`、`dist/`，保留源码、锁文件和 node_modules。重新生成产物后应仍有 25 项测试通过，矩阵输出与主程序固定输出一致。

### 10.3 从仓库根目录启动

以下子 shell 不改变外层终端仍在 `practice/` 的状态：

```bash
(
  cd ../..
  node 03-ts-cpp-async-matrix/practice/dist/src/index.js
)
```

应得到第 7 节相同输出，确认路径基于当前模块而非工作目录。

| 修改内容 | 下一步 |
| --- | --- |
| C++ 算法或绑定 | `npm test`、`npm run check`，然后启动演示 |
| TS 或测试 | `npm test`；只改演示时可 `npm run build:ts` 后启动 |
| CMake | `npm run build:native`，再运行测试 |
| 构建器或编译器改变 | `npm run clean`，再 `npm test` |
| 有意改变 npm 依赖 | `npm install` 更新锁文件，再检查与测试 |

## 11. 编写项目说明

创建当前 `practice/` 目录下的 `README.md`，完整写为：

<!-- file: README.md -->
````markdown
# TypeScript 异步调用 C++：矩阵乘法

在本目录独立安装依赖和构建。使用 Ubuntu/Linux x64、Node.js 24、npm、
C++17、CMake（至少 3.23）、Make 和系统 C++ 编译器。

## 安装与运行

```bash
npm ci
npm test
npm run check
npm start
npm run demo:heartbeat
```

预期 25 项集成测试通过，演示输出 `[[58,64],[139,154]]`。
`test` 先构建 C++ 和 TS，`check` 检查 C++ 构建与 TS 类型；
`start` 和 `demo:heartbeat` 只运行已有产物。

## 接口

`multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]>`，其中
`Matrix = readonly (readonly number[])[]`。

输入必须是非空、每行等长、元素有限的普通二维数值数组。
`m×n` 乘 `n×p` 返回 `m×p`，不要求方阵。
参数数量或类型错误拒绝为 TypeError，形状、非有限输入和计算溢出拒绝为
RangeError，其他原生计算异常拒绝为 Error。

## 异步与数据所有权

主线程校验并复制输入，创建 Promise，向 libuv 队列提交 AsyncWorker。
Execute 在后台只使用任务持有的 C++ 矩阵；OnOK/OnError 回主线程转换结果、
resolve/reject，随后框架销毁任务。

调用返回后修改输入不影响已经提交的计算；结果行之间、不同任务之间不共享缓存。
输入复制和结果转回 JS 仍占用主线程。Promise.all 可以提交多个任务，但线程池
容量有限，任务可能排队；异步不保证更快。

心跳演示使用 600×800 乘 800×500，结果首元素为 800。
心跳次数和耗时依机器而变化，不作为测试阈值。

## 清理重建与版本控制

```bash
npm run clean
npm test
npm run check
npm start
```

提交源码、配置、测试、本说明与 package-lock.json；
不提交 node_modules/、build/、dist/ 或 .node。
本项目用 Google 风格排版 C++，GCC/Clang 构建开启
-Wall -Wextra -Wpedantic -Werror。
````

说明文件记录项目的入口、接口和边界，方便以后直接进入练习目录时回顾；外层手册负责从零教学。

## 12. 第三个里程碑：提交测试与演示文档

先做最终检查：

```bash
npm test
npm run check
npm start
git -C ../.. check-ignore 03-ts-cpp-async-matrix/practice/node_modules/ 03-ts-cpp-async-matrix/practice/build/ 03-ts-cpp-async-matrix/practice/dist/
git -C ../.. status --short --untracked-files=all
```

测试与检查应成功，check-ignore 应列出三个目录。确认未跟踪列表没有依赖或构建产物，然后提交：

```bash
git -C ../.. diff -- 03-ts-cpp-async-matrix/practice
git -C ../.. add 03-ts-cpp-async-matrix/practice/src/heartbeat.ts 03-ts-cpp-async-matrix/practice/test/matrix.test.ts 03-ts-cpp-async-matrix/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify async matrix behavior and document the lab"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

最后三条新提交应分别对应配置、异步实现、测试与文档。原有工作或未提交教材可能仍显示在状态中，保留它们。本课只要求本地提交，不需要配置新远端或推送。

## 13. 常见故障与检查方式

**当前目录仍是 `practice/`。** 先检查实际工具、依赖和模块产物：

```bash
npm ls --depth=0
node -p 'process.versions.napi'
ls -l build/Release/addon.node
cmake --build build --config Release --verbose
```

| 现象 | 检查与处理 |
| --- | --- |
| CMake、Make 或 C++ 编译器不存在 | 按第 1 节安装工具，检查对应版本与 PATH |
| 找不到 napi.h / node_api.h | `npm ls node-addon-api node-api-headers`；有锁文件时 `npm ci`，再用 cmake-js 构建 |
| 提示 C++ 异常未启用 | 保留 `NODE_ADDON_API_CPP_EXCEPTIONS`，不要自行添加 `-fno-exceptions` |
| C++ 警告导致构建失败 | 根据文件和行号修复；`-Werror` 的目的就是阻止带警告的教材代码继续构建 |
| 找不到 dist/src/index.js | 先 `npm run build`；核对 tsconfig 的 rootDir/outDir |
| 找不到 addon.node | 检查 build/Release，先构建原生模块；不要直接运行 TS 源码 |
| ERR_DLOPEN_FAILED 或二进制架构不符 | 核对 Node 平台和架构，在当前机器清理重建，不复制其他平台产物 |
| Promise 没有正确被等待 | 使用 await，并在外层 try/catch 中处理；不要直接打印 Promise 当成矩阵 |
| 计算溢出变成拒绝 | 本课要求有限输出；缩小数值或检查输入，不能把 Infinity 当作有效结果 |
| 每行长度不一致或维度不相容 | 检查每行长度与 A 列数/B 行数；第三维或不规则数组不属于本课输入 |
| 修改 C++ 后结果仍旧 | 确认当前目录，执行 npm test；必要时清理后重建 |
| 心跳次数少或为 0 | 先核对异步资源测试；增大心跳演示矩阵并重新编译，不能仅凭次数判断代码是否异步 |
| 并发任务没有同时完成 | 线程池调度和任务大小会影响完成顺序，Promise.all 只保证结果按输入顺序返回 |
| npm ci 提示锁文件不匹配 | 有意修改依赖时用 npm install 更新锁文件，审阅并提交两份文件 |

可单独验证 Promise 错误处理：

```bash
node --input-type=module -e 'import { multiplyAsync } from "./dist/src/native.js"; try { await multiplyAsync([[1, 2]], [[3, 4]]); } catch (error) { console.log(error.name, error.message); }'
```

应输出：

```text
RangeError a columns must equal b rows
```

## 14. 最终验收清单

- [ ] 能按 `m×n` 与 `n×p` 规则解释结果尺寸，运行不同尺寸无需修改接口。
- [ ] 能区分 Promise、await 和后台线程，指出哪段代码在哪个线程执行。
- [ ] 知道 JS 句柄不能带进 Execute；任务拥有自己的 vector。
- [ ] 参数错误、尺寸错误和后台溢出均可用 await/try-catch 捕获。
- [ ] npm test 的 25 项真实集成测试全部通过，异步资源测试通过。
- [ ] npm run check 通过，C++ 构建启用警告视为错误。
- [ ] 运行心跳演示并理解次数不是固定验收阈值。
- [ ] npm ci 与清理重建后依然通过测试，异目录启动正常。
- [ ] 完成三个学习提交，提交了锁文件与说明，依赖和产物被忽略。
- [ ] 保留前两课与自己的原有工作，没有在课程内初始化嵌套 Git 仓库。

## 教材维护者的提交命令

下面用于本次新教材尚未提交的情况；从已包含教材的 clone 练习时无需重复。若仍在 `practice/`，先用第一行回到根目录，已在根目录时跳过第一行。

先安排原有未提交教材。本次开始时第二课教材和根索引仍有未提交改动；下方 `git add README.md` 会暂存根索引的全部改动，需自行审阅并安排前后课程的提交。目录路径只列第三课教材，不会暂存前两课成品或用户练习。

```bash
cd ../..
git status --short
git diff --check
git diff -- README.md
git add README.md 03-ts-cpp-async-matrix/README.md 03-ts-cpp-async-matrix/VERIFICATION.md 03-ts-cpp-async-matrix/reference
git diff --cached
git commit -m "docs: add verified asynchronous C++ matrix lesson"
git status --short
git log -1 --oneline
```

Agent 仅在隔离临时仓库验证这些提交命令，正式仓库的暂存、提交和推送由你执行。
