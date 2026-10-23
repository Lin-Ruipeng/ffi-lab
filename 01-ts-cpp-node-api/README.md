# 第一课：从零用 TypeScript 调用 C++

这一课实现一个很小但完整的项目：在 TS 中调用 `add(2, 3)`，计算发生在 C++ 中，最终打印 `add(2, 3) = 5`。你会亲手完成项目初始化、原生模块编译、TS 类型声明、测试和 Git 提交。

本文面向当前 Ubuntu/Linux，使用 Node.js 24、npm、TypeScript ESM、C++17、CMake 和 `cmake-js`。完整成品在 [reference/](reference/)，实际验证记录在 [VERIFICATION.md](VERIFICATION.md)。

## 0. 先理解目录和调用链

这一课有两条阅读路线：想先看效果，可以运行仓库首页的成品命令；想学习，就按下面步骤在 `practice/` 中从零写。下面每份代码都是完整文件，不需要从成品中复制额外文件。

```text
01-ts-cpp-node-api/
├── README.md
├── VERIFICATION.md
├── reference/              # 对照成品
└── practice/               # 下面由你创建
    ├── .nvmrc
    ├── package.json
    ├── package-lock.json   # npm 自动生成
    ├── tsconfig.json
    ├── CMakeLists.txt
    ├── native/
    │   ├── add.hpp
    │   ├── add.cpp
    │   └── addon.cpp
    ├── src/
    │   ├── native.ts
    │   └── index.ts
    └── test/
        └── add.test.ts
```

调用关系如下：

```text
src/index.ts
    │ tsc 编译，类型标注被移除
    ▼
dist/src/index.js
    │ 调用 dist/src/native.js 导出的 add
    ▼
createRequire 加载 build/Release/addon.node
    │ Node 初始化插件，找到它导出的 add
    ▼
native/addon.cpp：Napi::Value → double
    │ 通过 node-addon-api 封装的 Node-API 接口与 JS 交互
    ▼
native/add.cpp：执行 a + b
    │ double → Napi::Number
    ▼
JavaScript 收到 number 结果
```

**TS 不会直接执行 C++ 源文件。** C++ 要先编译成 Node 能加载的共享库，通常使用 `.node` 后缀。这个同步调用发生在同一个 Node 进程中，不需要 HTTP 或启动另一个 C++ 进程。

几个工具的分工：

| 工具/概念 | 在本课中的作用 |
| --- | --- |
| Node-API，旧称 N-API | Node 提供的稳定 C 接口，用于原生插件与 JS 交互 |
| `node-addon-api` | Node 项目维护的 C++ 头文件封装，提供 `Napi::Number` 等 C++ 类型 |
| CMake | 根据 `CMakeLists.txt` 配置编译目标，生成 Makefile |
| Make / G++ | Make 调度编译，G++ 编译和链接 C++ |
| `cmake-js` | 将 Node 插件需要的头文件路径、构建参数等交给 CMake |
| TypeScript / `tsc` | 检查 TS 类型，生成实际运行的 JS |
| `node:test` | Node 内置测试运行器 |

Node-API 的 ABI 稳定性有前提：运行时支持目标 Node-API 版本，并且依赖的接口、系统和架构兼容。它不意味着同一个 `.node` 文件可以跨 Linux、Windows 或 CPU 架构通用。[Node-API 官方文档](https://nodejs.org/download/release/v24.21.0/docs/api/n-api.html)

## 1. 准备 Ubuntu 工具链

**工作目录：任意目录。**

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git
```

`build-essential` 提供 G++ 和 Make 等工具。CMake 至少需要 3.23；本课明确使用 Unix Makefiles，不必额外安装 Ninja。

检查工具：

```bash
node --version
npm --version
cmake --version
c++ --version
make --version
git --version
node -p 'JSON.stringify({platform: process.platform, arch: process.arch, napi: process.versions.napi})'
```

本课实测 Node `v24.21.0`、npm `12.2.1`、CMake `4.2.3`、G++ `15.2.0`。最后一条在当前机器输出：

```text
{"platform":"linux","arch":"x64","napi":"10"}
```

`napi: "10"` 是运行时支持的 Node-API 版本，本课插件只要求版本 8。**Node 主版本 24、Node-API 版本 8、node-addon-api 包版本 8.9.2 是三个不同概念。**

当前机器已经有 Node 24。如果你使用了已安装的 nvm，可以按已验证版本切换：

```bash
nvm install 24.21.0
nvm use 24.21.0
```

没有 nvm 时不必为本课额外安装它，只要确保 `node --version` 为 `v24.x`。上面的 apt 安装和 nvm 切换是环境准备指引；本次实际使用临时解压的 Ubuntu CMake 工具完成构建，没有执行需要密码的系统安装。详见验证记录。

## 2. 在仓库根目录准备 Git

**工作目录：仓库根目录。**

```bash
cd /home/folin/文档/Code/ffi-lab
git init -b main
git branch --show-current
git status --short
```

这里已经初始化过 Git，重复 `git init` 可能提示重新初始化以及忽略 `-b`，属于正常情况。`git branch --show-current` 应显示 `main`。不要在 `practice/` 或 `reference/` 内再建嵌套仓库。

检查根目录 `.gitignore`，内容如下。如果从一个全新的仓库复现，就创建这份文件：

<!-- file: root/.gitignore -->
```gitignore
# 每一课独立安装依赖、编译源码。
node_modules/
build/
dist/
*.node
*.tsbuildinfo
npm-debug.log*

# 编辑器和系统临时文件。
.DS_Store
*~
```

这些没有开头 `/` 的目录规则会覆盖各级子目录。`package-lock.json` 和 CMake、TS 源文件需要提交，不要忽略。`.gitignore` 中的 `build/` 指构建输出目录，**并不是忽略 `CMakeLists.txt`**。

可以做第一个学习提交。先检查 Git 身份：

```bash
git var GIT_AUTHOR_IDENT
```

如果报身份未配置，再执行下面两行，并替换成你自己的信息；这是仓库局部设置：

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

提交忽略规则：

```bash
git add .gitignore
git diff --cached
git commit -m "chore: initialize ffi learning repository"
```

`git add` 将指定内容放入暂存区，`git diff --cached` 检查即将提交的内容，`git commit` 创建本地历史。提交应成功；其他教材文件仍可能显示为未跟踪，后面会一起提交。

## 3. 在子文件夹初始化 TS 项目

**先在仓库根目录执行：**

```bash
mkdir -p 01-ts-cpp-node-api/practice
cd 01-ts-cpp-node-api/practice
pwd
npm init -y
mkdir -p native src test
```

`pwd` 应以 `ffi-lab/01-ts-cpp-node-api/practice` 结尾。`npm init -y` 生成基础 `package.json`，随后我们把它编辑成适合本课的完整配置。若 `practice/` 已经有你写过的文件，请从已有进度继续，不要重新覆盖。

**从这里到第 10 节，除非另有说明，命令都在 `practice/` 执行。** 文件内容用你习惯的编辑器输入即可，Markdown 的围栏符号不要写进文件。

### 3.1 创建 `.nvmrc`

<!-- file: .nvmrc -->
```text
24.21.0
```

这份文件记录推荐的 Node 版本。使用 nvm 时，在项目内执行 `nvm use` 可读取它；Node 自己不会自动读取 `.nvmrc`。

### 3.2 编辑 `package.json`

将初始化生成的内容完整替换为：

<!-- file: package.json -->
```json
{
  "name": "ts-cpp-node-api-add",
  "version": "1.0.0",
  "private": true,
  "description": "Learn to call a C++ add function from TypeScript with Node-API and CMake",
  "type": "module",
  "engines": {
    "node": ">=24 <25"
  },
  "scripts": {
    "build:native": "cmake-js build --config Release --generator \"Unix Makefiles\"",
    "build:ts": "tsc -p tsconfig.json",
    "build": "npm run build:native && npm run build:ts",
    "typecheck": "tsc -p tsconfig.json --noEmit",
    "start": "node dist/src/index.js",
    "test": "npm run build && node --test dist/test/add.test.js",
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

解释关键字段：

- `private: true`：避免误将学习项目发布到 npm。
- `type: "module"`：让 Node 将生成的 `.js` 文件当作 ESM，使用 `import/export`。
- `engines`：声明本课以 Node 24 为目标；npm 默认可能只给版本警告，所以仍需自己检查版本。
- `dependencies`：`node-addon-api` 提供 C++ 头文件，本课遵循其官方接入方式放在这里。头文件代码会编译进插件，运行时不会再解释这些头文件。
- `devDependencies`：TS 编译器、Node 类型定义、原生构建工具；这里的 `@types/node` 不是 Node 程序本身。
- `binary.napi_versions: [8]`：供 `cmake-js` 识别 Node-API 项目，在本路线使用 `node-api-headers` 提供头文件。CMake 中仍会显式定义同样的 `NAPI_VERSION=8`。
- npm scripts 会自动找到本项目 `node_modules/.bin/` 中的命令，所以无需全局安装 `tsc` 或 `cmake-js`。

现在安装上面声明的精确版本：

```bash
npm install
npm ls --depth=0
```

应安装四个直接依赖：`node-addon-api@8.9.2`、`cmake-js@8.0.0`、`typescript@7.0.2`、`@types/node@24.19.2`。项目中会生成 `node_modules/` 和 `package-lock.json`。安装需要联网，耗时和 npm 提示可能不同。

版本号不带 `^`，固定直接依赖；锁文件进一步记录间接依赖和校验信息。**锁文件由 npm 生成，无需手抄。** 以后安装已经有锁文件的成品项目使用 `npm ci`，后面会练习。

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

`NodeNext` 让 TS 按 Node 的模块规则检查代码；结合 `type: "module"`，这里输出 ESM。`strict` 开启严格类型检查；`types: ["node"]` 加载 Node 类型；`noEmitOnError` 避免类型错误时生成新的 JS。

`rootDir: "."` 是后续路径计算的关键：`src/index.ts` 输出到 `dist/src/index.js`，`test/add.test.ts` 输出到 `dist/test/add.test.js`。TS 编译不会复制或编译 `native/` 中的 C++。

`verbatimModuleSyntax` 保留值导入的 ESM 写法；`forceConsistentCasingInFileNames` 帮助避免文件名大小写不一致的问题。

### 3.4 提交项目配置

仍在 `practice/`，用 `git -C ../..` 表示从仓库根目录执行 Git：

```bash
git -C ../.. status --short
git -C ../.. add 01-ts-cpp-node-api/practice/.nvmrc 01-ts-cpp-node-api/practice/package.json 01-ts-cpp-node-api/practice/package-lock.json 01-ts-cpp-node-api/practice/tsconfig.json
git -C ../.. diff --cached --stat
git -C ../.. commit -m "chore: initialize TypeScript native addon project"
```

空的 `native/`、`src/` 和 `test/` 不会出现在 Git 中，因为 Git 跟踪文件，不单独跟踪空目录。

## 4. 编写真正执行计算的 C++ 函数

### 4.1 创建 `native/add.hpp`

<!-- file: native/add.hpp -->
```cpp
#pragma once

namespace ffi_lab {
double add(double a, double b);
}
```

这是函数声明，告诉其他 C++ 文件函数名、参数和返回类型。`#pragma once` 防止头文件重复包含；命名空间避免与其他库的 `add` 混淆。

### 4.2 创建 `native/add.cpp`

<!-- file: native/add.cpp -->
```cpp
#include "add.hpp"

namespace ffi_lab {
double add(double a, double b) {
    return a + b;
}
}
```

这是函数实现。使用 `double` 对应 JS 的双精度 `number`，避免先转成 32 位整数导致小数丢失。这份代码完全不依赖 Node，之后也可以用于其他 C++ 程序。

## 5. 用 Node-API 将函数暴露给 JS

创建 `native/addon.cpp`：

<!-- file: native/addon.cpp -->
```cpp
#include <napi.h>

#include "add.hpp"

namespace {
Napi::Value Add(const Napi::CallbackInfo& info) {
    const Napi::Env env = info.Env();

    if (info.Length() != 2) {
        throw Napi::TypeError::New(env, "add expects exactly 2 arguments");
    }

    if (!info[0].IsNumber() || !info[1].IsNumber()) {
        throw Napi::TypeError::New(env, "add expects two numbers");
    }

    const double a = info[0].As<Napi::Number>().DoubleValue();
    const double b = info[1].As<Napi::Number>().DoubleValue();
    const double result = ffi_lab::add(a, b);

    return Napi::Number::New(env, result);
}

Napi::Object Init(Napi::Env env, Napi::Object exports) {
    exports.Set("add", Napi::Function::New(env, Add));
    return exports;
}
}

NODE_API_MODULE(addon, Init)
```

按执行过程阅读：

1. `<napi.h>` 来自 npm 的 `node-addon-api` 包；它内部调用 Node-API C 接口。`"add.hpp"` 是自己的业务头文件。
2. `info` 是 JS 调用信息，包含参数；`env` 表示当前 Node 执行环境。`info[0]`、`info[1]` 是传入的 JS 值。
3. 先检查参数数量，再检查值是不是 `number`。这里不把字符串 `"2"` 自动转换为数字，也不接受 `bigint`。
4. `As<Napi::Number>().DoubleValue()` 把 JS 数值取成 C++ `double`。随后 `ffi_lab::add` 完成计算。
5. `Napi::Number::New` 将结果包装成 JS 数值，并作为 `Napi::Value` 返回。
6. `Init` 在插件加载时运行，将回调注册为导出对象的 `add` 属性。
7. `NODE_API_MODULE(addon, Init)` 生成 Node 所需的注册入口。回调在匿名命名空间中只供本文件使用；通过注册入口暴露给 Node。

这里的 `throw Napi::TypeError` 使用 C++ 异常。下一节会显式启用对应支持；`node-addon-api` 的回调包装会将这些 `Napi::Error` 转为 JS 异常，使 JS 的 `try/catch` 和测试的 `assert.throws` 能接住。

为什么有 TS 类型还需要这里的检查？TS 类型在编译后会被移除，而且 JS 调用者可以传入任意值。跨语言边界必须自己检查收到的真实参数。

## 6. 写完整的 CMake 配置并编译

### 6.1 创建 `CMakeLists.txt`

文件放在 `practice/` 顶层，与 `package.json` 同级。文件名注意大小写：

<!-- file: CMakeLists.txt -->
```cmake
cmake_minimum_required(VERSION 3.23)
project(ts_cpp_node_api LANGUAGES CXX)

add_library(addon SHARED
    native/add.cpp
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

set_target_properties(addon PROPERTIES
    PREFIX ""
    SUFFIX ".node"
    CXX_EXTENSIONS OFF
)
```

逐项解释：

| 配置 | 意义 |
| --- | --- |
| `cmake_minimum_required` | 声明最低 CMake 版本并设置相关策略基准 |
| `project(... LANGUAGES CXX)` | 声明工程，只启用 C++ 语言，检测编译器 |
| `add_library(addon SHARED ...)` | 创建名为 `addon` 的共享库目标，明确列出两个 `.cpp` 文件 |
| `${CMAKE_JS_SRC}` | `cmake-js` 提供的额外源码列表；本课 Linux 构建时为空 |
| `target_compile_features(... cxx_std_17)` | 要求编译器至少支持 C++17；不要手写全局 `-std` 参数 |
| `NAPI_VERSION=8` | 声明插件使用的 Node-API 版本，与 npm 配置保持一致 |
| `NODE_ADDON_API_CPP_EXCEPTIONS` | 选择 `node-addon-api` 的 C++ 异常模式；本课 G++ 默认支持异常 |
| `${CMAKE_JS_INC}` | `cmake-js` 计算的 Node-API 以及 C++ 封装头文件路径 |
| `${CMAKE_JS_LIB}` | `cmake-js` 提供的链接库参数；本课 Linux 配置为空，运行时由 Node 提供 Node-API 符号 |
| `PRIVATE` | 配置只作用于 `addon`，不把这些要求传播给其他目标 |
| `PREFIX ""` / `SUFFIX ".node"` | 将 Linux 默认的 `libaddon.so` 命名改成 Node 加载的 `addon.node` |
| `CXX_EXTENSIONS OFF` | 使用标准 C++ 模式，不要求 GNU 方言扩展 |

头文件通过 `#include` 使用，不单独编译。本课没有使用全局 `include_directories` 或扫描源码的 `file(GLOB ...)`，每个目标的输入和配置都能直接看清。

### 6.2 编译原生插件

**工作目录：`practice/`。**

```bash
npm run build:native
ls -l build/Release/addon.node
```

第一条执行：

```text
cmake-js build --config Release --generator "Unix Makefiles"
```

`cmake-js` 先计算参数并调用 CMake 进行配置、生成，再通过 `cmake --build` 编译。所有 CMake 缓存和目标文件放到 `build/`，不会混入源码目录。`Release` 表示发布构建配置。

本课版本的 `cmake-js` 会自动把 `node-addon-api` 加入包含路径，因此不需要在 CMake 中硬编码 `/home/.../node_modules`。构建输出中可以看到 `CMAKE_JS_INC` 和实际执行的 CMake 命令。[CMake.js 官方说明](https://github.com/cmake-js/cmake-js/blob/v8.0.0/README.md)

关键成功输出类似：

```text
[100%] Linking CXX shared library Release/addon.node
[100%] Built target addon
```

第一次配置成功后，也可以直接用 CMake 做增量编译：

```bash
cmake --build build --config Release
```

第一次不要直接执行 `cmake -S . -B build`：本文配置依赖 `cmake-js` 注入的变量，缺少这些参数时编译器找不到 `napi.h` 等头文件。我们仍完整编写并使用 CMake，只是由专门的 Node 构建工具负责传递宿主参数。[node-addon-api 官方 CMake 指南](https://github.com/nodejs/node-addon-api/blob/v8.9.2/doc/cmake-js.md)

## 7. 在 TypeScript 中加载和调用

### 7.1 创建 `src/native.ts`

<!-- file: src/native.ts -->
```ts
import { createRequire } from "node:module";

interface NativeAddon {
  add(a: number, b: number): number;
}

const require = createRequire(import.meta.url);
const addon = require("../../build/Release/addon.node") as NativeAddon;

export const add: NativeAddon["add"] = addon.add;
```

ESM 中不能直接用普通 `import` 加载 `.node` 插件，也没有自带的 CommonJS `require`。`createRequire(import.meta.url)` 创建一个以当前模块为基准的 `require`，用它加载原生模块。[Node.js 官方规则](https://nodejs.org/download/release/v24.21.0/docs/api/esm.html#no-addon-loading)

`NativeAddon` 描述插件提供的接口。`as NativeAddon` 告诉 TS 如何理解动态加载的结果，**不会在运行时验证插件导出的形状**。这里的接口需要与 C++ 导出保持一致，我们用后面的集成测试来验证两端能正确协作。

`NativeAddon["add"]` 取出接口中 `add` 的函数类型，让导出的 TS 函数也具有 `(a: number, b: number) => number` 签名。

路径为什么是两个 `..`？执行的是编译后的文件：

```text
practice/dist/src/native.js
             └─ .. → dist/
                .. → practice/
                     └─ build/Release/addon.node
```

路径相对于 `dist/src/native.js`，不相对于终端当前目录。因此从其他目录启动编译后的入口也能找到插件。本文通过 `tsc` 生成 JS 后再运行；不要直接 `node src/index.ts`，那会绕过这条编译路线并改变路径基准。

### 7.2 创建 `src/index.ts`

<!-- file: src/index.ts -->
```ts
import { add } from "./native.js";

console.log(`add(2, 3) = ${add(2, 3)}`);
```

虽然源文件是 `native.ts`，相对导入却写 `./native.js`。Node ESM 运行时需要文件扩展名；TS 的 `NodeNext` 会在检查源码时将它对应到 `native.ts`，并让输出保留可运行的 `.js` 路径。

### 7.3 编译并运行

```bash
npm run build:ts
npm start
```

应看到：

```text
add(2, 3) = 5
```

现在也可以一条命令构建全部内容：

```bash
npm run build
npm run typecheck
```

`build` 先构建 C++，再编译 TS；`typecheck` 只检查 TS，不输出文件。`npm start` 本身只运行已生成的 JS，修改源码后要先重新构建。

## 8. 为真实跨语言调用编写测试

创建 `test/add.test.ts`：

<!-- file: test/add.test.ts -->
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { add } from "../src/native.js";

test("adds positive numbers", () => {
  assert.equal(add(2, 3), 5);
});

test("adds negative numbers", () => {
  assert.equal(add(-2, -3), -5);
  assert.equal(add(-2, 3), 1);
});

test("adds zero", () => {
  assert.equal(add(0, 0), 0);
  assert.equal(add(0, 7), 7);
});

test("adds decimals using floating-point arithmetic", () => {
  assert.equal(add(1.5, 2.25), 3.75);
  assert.ok(Math.abs(add(0.1, 0.2) - 0.3) < 1e-12);
});

test("preserves JavaScript number semantics for NaN and Infinity", () => {
  assert.ok(Number.isNaN(add(Number.NaN, 1)));
  assert.equal(add(Number.POSITIVE_INFINITY, 1), Number.POSITIVE_INFINITY);
});

test("rejects non-number arguments in either position", () => {
  const invalidValues: unknown[] = ["2", undefined, null, true, {}, 2n];

  for (const value of invalidValues) {
    assert.throws(() => Reflect.apply(add, undefined, [value, 3]), {
      name: "TypeError",
      message: "add expects two numbers",
    });
    assert.throws(() => Reflect.apply(add, undefined, [2, value]), {
      name: "TypeError",
      message: "add expects two numbers",
    });
  }
});

test("rejects missing arguments", () => {
  for (const args of [[], [2]]) {
    assert.throws(() => Reflect.apply(add, undefined, args), {
      name: "TypeError",
      message: "add expects exactly 2 arguments",
    });
  }
});

test("rejects extra arguments", () => {
  assert.throws(() => Reflect.apply(add, undefined, [2, 3, 4]), {
    name: "TypeError",
    message: "add expects exactly 2 arguments",
  });
});
```

运行：

```bash
npm test
```

成功时关键统计为：

```text
ℹ tests 8
ℹ pass 8
ℹ fail 0
```

输出样式、耗时和构建进度可能不同。`npm test` 每次都先增量构建原生模块和 TS，避免修改 C++ 后仍测试旧二进制。没有 mock 或 JS 加法替代实现，测试直接经过真实 `.node` 插件。

理解几个测试细节：

- `assert.equal` 来自 `node:assert/strict`，执行严格断言。测试或原生加载失败会使进程以非零状态退出。
- `double` 和 JS `number` 都使用浮点数表示；`0.1 + 0.2` 存在表示误差，所以该项用误差容限比较。`NaN` 和 `Infinity` 仍是 `number`，本课保留其运算语义。
- `Reflect.apply(add, undefined, args)` 在这里用于模拟动态 JS 调用，故意传入 TS 正常调用不允许的参数，验证 C++ 边界检查。`undefined` 是本次调用的 `this` 值，`args` 是参数数组。
- 两类错误的先后顺序已经固定：先检查数量，再检查类型。因此 `add()` 会报告数量错误。

如果只想重跑已经构建好的测试，可以执行：

```bash
node --test dist/test/add.test.js
```

只有确认构建产物是最新时才这样做。Node 内置运行器无需再安装测试框架。[测试运行器文档](https://nodejs.org/download/release/v24.21.0/docs/api/test.html)

## 9. 验证安装、路径和重新构建

### 9.1 用锁文件重新安装

```bash
npm ci
npm test
npm start
```

`npm ci` 按已有锁文件安装，自动替换现有 `node_modules/`；若锁文件与 `package.json` 不一致会报错。它不会替你修改锁文件。首次创建练习项目用 `npm install`，拿到已有项目用 `npm ci`。

### 9.2 清理构建产物后重建

```bash
npm run clean
npm test
npm start
```

`clean` 使用 CMake 的文件工具，只删除当前项目的 `build/` 和 `dist/`。源码、依赖和锁文件保留。随后测试应该重新生成插件和 JS，仍然 8 项通过。

### 9.3 从其他工作目录启动

下面用子 shell 临时切到仓库根目录，不改变外层终端的 `practice/` 工作目录：

```bash
(
  cd ../..
  node 01-ts-cpp-node-api/practice/dist/src/index.js
)
```

仍应得到 `add(2, 3) = 5`。这是验证插件加载基于模块位置，而不是 `process.cwd()`。

### 9.4 修改源码后用什么命令

| 修改内容 | 需要执行 |
| --- | --- |
| 修改 C++ 或绑定代码 | `npm run build:native`，之后再运行程序；用 `npm test` 可同时重建并测试 |
| 修改 TS | `npm run build:ts`，之后 `npm start` |
| 修改 CMake | `npm run build:native`，CMake 会检测配置变化 |
| 切换编译器或构建器 | `npm run clean`，再 `npm test` |

练习时也可以统一执行 `npm test` 和 `npm start`，先确保行为正确，再关心增量构建优化。同步原生调用会占用当前 JS 执行线程；加法很短，但后续耗时计算需要另学异步任务或工作线程。

## 10. 提交完整练习和教材

**当前仍在 `practice/`。**

检查哪些文件会被忽略：

```bash
git -C ../.. check-ignore 01-ts-cpp-node-api/practice/node_modules/ 01-ts-cpp-node-api/practice/build/ 01-ts-cpp-node-api/practice/dist/
git -C ../.. status --short --untracked-files=all
```

第一条应列出这三个目录。第二条应列出你的新源码，而不是成千上万条依赖文件。

提交实现和测试：

```bash
git -C ../.. add 01-ts-cpp-node-api/practice/CMakeLists.txt 01-ts-cpp-node-api/practice/native 01-ts-cpp-node-api/practice/src 01-ts-cpp-node-api/practice/test
git -C ../.. diff --cached
git -C ../.. commit -m "feat: call C++ add from TypeScript through Node-API"
```

回到仓库根目录，将教程和成品也放入版本历史：

```bash
cd ../..
git add README.md 01-ts-cpp-node-api/README.md 01-ts-cpp-node-api/VERIFICATION.md 01-ts-cpp-node-api/reference
git diff --cached --stat
git commit -m "docs: add verified TypeScript to C++ lesson and reference"
git log --oneline -4
git status --short
```

按本文从空历史操作，应得到四条提交，最后一条 `git status --short` 没有输出。如果你在一个已有提交的副本中练习，教材可能已经被跟踪，最后这次教材提交会提示没有新内容，此时跳过它即可。

这里的提交保存在本地。等你自己创建远程仓库后，再单独配置 remote 和 push，不需要为了本课先有 GitHub 仓库。

## 11. 常见错误怎么查

以下排错命令在 `practice/` 执行。若刚做完第 10 节，先回到项目：

```bash
cd /home/folin/文档/Code/ffi-lab/01-ts-cpp-node-api/practice
```

| 现象 | 先检查什么 | 处理方法 |
| --- | --- | --- |
| `cmake` 找不到 | `cmake --version` | 完成第 1 节安装，确认 CMake 在 `PATH` 中 |
| 没有 C++ 编译器或 Make | `c++ --version`、`make --version` | 安装 `build-essential` |
| `napi.h: No such file or directory` | `npm ls node-addon-api` | 执行 `npm ci`，使用 `npm run build:native`，检查 `CMAKE_JS_INC` 是否接入 |
| `node_api.h` 找不到 | `npm ls node-api-headers` | 确认依赖完整且使用本文 `cmake-js` 构建，不要单独裸跑配置命令 |
| 异常相关宏或编译报错 | CMake 中的宏和编译器异常设置 | 保留 `NODE_ADDON_API_CPP_EXCEPTIONS`，不要自行加入 `-fno-exceptions` |
| 找不到 `dist/src/index.js` | `ls dist/src` | 先执行 `npm run build:ts`，确认 `rootDir`、`outDir` 未改变 |
| 找不到 `addon.node` | `ls build/Release/addon.node` | 先构建原生模块；检查相对路径从 `dist/src/native.js` 出发 |
| `ERR_UNKNOWN_FILE_EXTENSION` 指向 `.node` | 加载插件的写法 | 用 `createRequire`，不要直接 `import` 原生文件 |
| `add is not a function` | `Init` 的导出名称与 TS 接口 | 两边必须都叫 `add`；类型断言不会修复导出错误 |
| 修改 C++ 后结果没变化 | 是否重新构建、是否运行了另一个目录的项目 | 执行 `npm test`，确认操作的是 `practice/` |
| CMake generator 不匹配 | 是否复用了其他构建器的缓存 | `npm run clean`，然后 `npm test` |
| `npm ci` 提示锁文件不一致 | 是否手动改过依赖版本 | 若是有意修改，用 `npm install` 更新锁文件，再提交两份文件 |
| 原生插件架构不匹配或 `ERR_DLOPEN_FAILED` | Node 架构、系统和二进制来源 | 在当前机器执行 `npm run clean`、`npm test`，不要复制其他系统的 `.node` |

查看底层依赖和 Node-API 版本：

```bash
npm ls node-addon-api cmake-js node-api-headers
node -p 'process.versions.napi'
```

若还是不清楚编译器实际收到了哪些参数，可以在首次配置成功后查看详细构建过程：

```bash
cmake --build build --config Release --verbose
```

本课学到的核心是：声明 TS 接口、校验真实 JS 参数、转换为 C++ 值、执行业务函数、将结果交还 JS。后续换成 Rust 或其他跨语言方式时，仍可以沿着这些问题理解接口边界。

## 下一步：把学习仓库发布到 GitHub

完成本课及本地提交后，可以继续阅读[番外：使用 GitHub CLI 发布本地仓库](../extras/01-publish-to-github/README.md)。从尚未创建远端仓库开始，学习登录 GitHub、创建公开仓库、首次推送和后续更新；所有发布命令都在 `ffi-lab` 根目录执行。
