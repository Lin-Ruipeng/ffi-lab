# 第二课：从零用 TypeScript 调用 Rust

这一课仍然只做加法：在 TS 中写 `add(2, 3)`，由 Rust 计算，最终打印 `add(2, 3) = 5`。沿用第一课的 Node.js 原生插件路线，重点理解 Cargo、napi-rs 导出宏、自动生成的类型声明与跨语言边界。

本文面向 Ubuntu/Linux x64，使用 Node.js 24、npm、TypeScript ESM 和 Rust。完整成品在 [reference/](reference/)，实测环境与复走结果见 [VERIFICATION.md](VERIFICATION.md)。本课独立安装依赖，无需重新构建第一课。

## 0. 先理解目录与调用链

按顺序阅读并在 `practice/` 亲手创建项目。文件块都是完整内容；标注为自动生成的文件交给工具，不要手抄。

```text
02-ts-rust-node-api/
├── README.md                    # 本手册
├── VERIFICATION.md
├── reference/                    # 对照成品
└── practice/                     # 由你创建
    ├── .nvmrc
    ├── package.json
    ├── package-lock.json         # npm 生成
    ├── tsconfig.json
    ├── Cargo.toml
    ├── Cargo.lock                # Cargo 生成
    ├── build.rs
    ├── native/lib.rs
    ├── src/native.ts
    ├── src/index.ts
    ├── test/add.test.ts
    ├── README.md                 # 你编写的项目说明
    ├── build/                    # CLI 生成：加载器、声明、.node
    ├── target/                   # Cargo 生成：缓存与编译产物
    └── dist/                     # tsc 生成：可执行 JS
```

```text
src/index.ts --tsc--> dist/src/index.js
                          │ 导入 dist/src/native.js
                          ▼
                     build/index.js       napi-rs 生成的 ESM 加载器
                          │ 内部使用 createRequire 加载原生库
                          ▼
              build/addon.linux-x64-gnu.node
                          │ Node-API / napi-rs 生成的参数检查与转换
                          ▼
                  native/lib.rs：a + b
                          │ f64 转成 JS number
                          ▼
                    TypeScript 调用方收到结果

编译时：Rust 函数签名 → build/index.d.ts → TS 获取 add 的类型
```

TS 不会直接运行 `.rs`。Cargo 将 Rust 编译成共享库，napi-rs CLI 将库复制为 Node 能加载的 `.node`，并生成 JS 加载器与 TS 声明。运行时加载的是本机二进制；同一进程内调用，不需要 HTTP 或另开 Rust 服务。

| 工具 | 本课职责 |
| --- | --- |
| `rustup` | 管理 Rust 工具链和组件 |
| `rustc` / Cargo | 编译 Rust / 管理 crate、依赖和构建 |
| `napi` | Rust 与 Node-API 交互及类型转换 |
| `napi-derive` | 提供 `#[napi]` 宏，生成绑定代码及类型信息 |
| `napi-build` | 在 Cargo 构建阶段准备原生插件的平台配置 |
| `@napi-rs/cli` | 调用 Cargo，整理 `.node`、JS 加载器和 `.d.ts` |
| `tsc` / `node:test` | 检查并编译 TS / 测试真实插件 |
| rustfmt / Clippy | 检查 Rust 格式 / 检查常见代码问题 |

原生构建与生成文件采用 [napi-rs 官方手动配置](https://napi.rs/docs/introduction/manual-setup)和[构建命令](https://napi.rs/docs/cli/build)。本课不涉及跨平台发布、Wasm 或异步任务。

## 1. 检查并准备工具链

**工作目录：任意目录。** 先检查已有工具，不必重复安装：

```bash
node --version
npm --version
rustup show active-toolchain
rustc --version
cargo --version
rustfmt --version
cargo clippy --version
cc --version
git --version
node -p 'JSON.stringify({platform: process.platform, arch: process.arch, napi: process.versions.napi})'
```

本课实测 Node `v24.21.0`、npm `12.2.1`、Rust/Cargo `1.99.1`，最后一条输出：

```text
{"platform":"linux","arch":"x64","napi":"10"}
```

`process.versions.napi` 是运行时支持的 Node-API 版本。本课通过 Cargo feature 选择 Node-API 8，它与 Node 24、napi crate 3.15.0 的版本号含义不同。

如果缺少系统链接器、Git 或 curl，**才在任意目录执行**下面的 Ubuntu 环境准备命令：

```bash
sudo apt-get update
sudo apt-get install -y build-essential git curl
```

Rust 编译器仍需要系统链接器。当前机器已经具备这些工具；本次没有执行 sudo 安装。

如果没有 Rust，按 [Rust 官方安装页](https://rust-lang.org/tools/install/)执行下列命令，按提示安装 stable，然后让当前终端读取环境：

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
. "$HOME/.cargo/env"
rustup component add rustfmt clippy
```

已经安装 Rust 时跳过安装器；如果只有 rustfmt 或 Clippy 缺失，仅执行最后一行。已有工具链过旧而被依赖拒绝时，用 `rustup update stable` 更新后重新检查版本。本次使用已有 stable 工具链，未重新安装或更新。

本课沿用第一课的 Node 24。已安装 nvm 时可以执行下面的可选命令；否则使用已有 Node 24 即可：

```bash
nvm install 24.21.0
nvm use 24.21.0
```

安装和首次获取依赖需要网络。环境准备完成后，再运行本节第一组检查命令。

## 2. 从现有仓库开始

**工作目录：仓库根目录。** 下方第一行路径是占位符，替换成你这台机器上已有 clone 的真实绝对路径，不要原样执行：

```bash
cd "/请替换为你的实际路径/ffi-lab"
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
```

`pwd` 与 `git rev-parse` 应指向同一个 `ffi-lab`。复用当前历史和分支，不需要 `git init`。如果已有未提交或暂存内容，保留它们；后面的提交只暂存列出的本课路径。**已有其他暂存文件时，先自行处理，确认暂存区只含本次里程碑，再提交。**

检查根 `.gitignore`，保证有 `target/`。本课准备后的完整内容如下；若你另有自定义规则，在已有内容上补充，保留自己的规则：

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

# 编辑器和系统临时文件。
.vscode/
.DS_Store
*~
```

不带前导 `/` 的目录规则会覆盖各级目录，所以两课都能独立构建。提交 `package-lock.json` 和 `Cargo.lock`，不提交 `node_modules/`、`target/`、`build/`、`dist/` 或 `.node`。本课的 `build/index.d.ts` 是可重新生成的声明，因此随 `build/` 一起忽略。

先检查 Git 提交身份：

```bash
git var GIT_AUTHOR_IDENT
```

只有提示身份未配置时才执行下面的占位配置，替换为你自己的信息：

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

## 3. 初始化独立的 TS 项目

**从仓库根目录执行：**

```bash
mkdir -p 02-ts-rust-node-api/practice
cd 02-ts-rust-node-api/practice
pwd
npm init -y
mkdir -p native src test
```

`pwd` 应以 `ffi-lab/02-ts-rust-node-api/practice` 结尾。如果这个目录已经有你写的文件，请从已有进度继续，不要重新覆盖。

**从现在到第 11 节结束，除非特别说明，命令与文件路径都以 `practice/` 为基准。** 使用你习惯的编辑器创建文件；不要把 Markdown 围栏写入文件。

### 3.1 创建 `.nvmrc`

<!-- file: .nvmrc -->
```text
24.21.0
```

nvm 可以通过它选择推荐版本；Node 不会自动读取它。

### 3.2 编辑 `package.json`

将 `npm init -y` 生成的文件完整改为：

<!-- file: package.json -->
```json
{
  "name": "ts-rust-node-api-add",
  "version": "1.0.0",
  "private": true,
  "description": "Learn to call a Rust add function from TypeScript with napi-rs",
  "type": "module",
  "engines": {
    "node": ">=24 <25"
  },
  "scripts": {
    "build:native": "napi build --platform --esm --release --output-dir build --js index.js --dts index.d.ts -- --locked",
    "build:ts": "tsc -p tsconfig.json",
    "build": "npm run build:native && npm run build:ts",
    "typecheck": "npm run build:native && tsc -p tsconfig.json --noEmit",
    "fmt:check": "cargo fmt --all -- --check",
    "lint:rust": "cargo clippy --locked -- -D warnings",
    "check": "npm run fmt:check && npm run lint:rust && npm run typecheck",
    "start": "node dist/src/index.js",
    "test": "npm run build && node --test dist/test/add.test.js",
    "clean": "cargo clean && node --input-type=module -e \"import { rmSync } from 'node:fs'; for (const path of ['build', 'dist']) rmSync(path, { recursive: true, force: true });\""
  },
  "napi": {
    "binaryName": "addon"
  },
  "devDependencies": {
    "@napi-rs/cli": "3.10.9",
    "@types/node": "24.19.2",
    "typescript": "7.0.2"
  }
}
```

关键字段：

- `private: true` 防止误发布 npm 包；`type: "module"` 让本项目 `.js` 按 ESM 加载。
- CLI、TS 编译器和 Node 类型都是开发工具，放在 `devDependencies`；无需全局安装 CLI。Rust 依赖稍后由 Cargo 独立管理。
- `napi.binaryName: "addon"` 决定原生文件的基础名称；本课 Linux x64 glibc 下得到 `addon.linux-x64-gnu.node`。
- `build:native` 先生成加载器和类型；`build:ts` 再编译 TS。`typecheck` 也先构建 Rust，确保从干净目录执行时能找到生成的声明。
- `-- --locked` 中第一个 `--` 将后续参数传给 Cargo，要求使用已有 `Cargo.lock`，不在构建时悄悄更新依赖树。首次生成锁文件的命令见第 4 节。
- `check` 顺序运行 Rust 格式、Clippy 和 TS 类型检查；`test` 先构建再测试，`start` 只运行已有 JS。
- `clean` 先用 Cargo 清除 `target/`，再用 Node 文件 API 删除当前项目 `build/` 和 `dist/`。请始终通过本项目的 npm script 执行。

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

`NodeNext` 配合 `type: "module"` 使用 Node ESM 规则；`strict` 开启严格检查。`rootDir: "."` 和 `outDir: "dist"` 使源码与测试分别输出到 `dist/src/`、`dist/test/`。

TS 不编译 Rust，也不复制 `.node`。`noEmitOnError` 避免类型错误时继续产生新 JS；`types: ["node"]` 加载 Node 类型声明。

安装并检查 npm 依赖：

```bash
npm install
npm ls --depth=0
```

成功时有 `@napi-rs/cli@3.10.9`、`@types/node@24.19.2`、`typescript@7.0.2` 三个直接依赖，同时自动生成 `package-lock.json`。直接版本没有 `^`，间接依赖由锁文件记录。

### 3.4 第一个里程碑：提交项目配置

此时 Rust 文件还未创建，不运行完整构建；本阶段验收是依赖安装成功、`npm ls --depth=0` 没有缺失依赖。仍在 `practice/`：

```bash
git -C ../.. status --short
git -C ../.. diff -- .gitignore 02-ts-rust-node-api/practice
git -C ../.. add .gitignore 02-ts-rust-node-api/practice/.nvmrc 02-ts-rust-node-api/practice/package.json 02-ts-rust-node-api/practice/package-lock.json 02-ts-rust-node-api/practice/tsconfig.json
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure TypeScript Rust addon project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

如果教材已经带有 `target/` 忽略规则，`.gitignore` 没有新差异是正常的。Git 不记录空目录，源码会在后续里程碑加入。

## 4. 手动初始化 Cargo 库

本课直接手写最小 Cargo 配置，避免模板生成不相关的发布或 CI 文件，也避免嵌套 Git 仓库。不需要执行 `cargo new` 或 `cargo init`。

### 4.1 创建 `Cargo.toml`

文件放在 `practice/` 顶层，与 `package.json` 同级：

<!-- file: Cargo.toml -->
```toml
[package]
name = "ts-rust-node-api-add"
version = "1.0.0"
edition = "2024"
publish = false

[lib]
path = "native/lib.rs"
crate-type = ["cdylib"]

[dependencies]
napi = { version = "=3.15.0", default-features = false, features = ["napi8"] }
napi-derive = "=3.6.13"

[build-dependencies]
napi-build = "=2.6.0"
```

| 配置 | 意义 |
| --- | --- |
| `edition = "2024"` | 选择 Rust 2024 语言规则；edition 不是编译器版本 |
| `publish = false` | 禁止误将学习 crate 发布到 crates.io |
| `[lib].path` | 库入口显式放在 `native/lib.rs`，与 TS 的 `src/` 区分 |
| `crate-type = ["cdylib"]` | 生成可由其他语言运行时加载的共享库 |
| `napi` | 提供 Node-API 的 Rust 封装和转换能力 |
| `default-features = false` | 关闭默认 feature，本课只显式选择所需 Node-API 级别 |
| `features = ["napi8"]` | 使用 Node-API 8 能力；要求运行时至少支持它 |
| `napi-derive` | 提供导出宏；保留默认的宏检查与类型信息生成功能 |
| `[build-dependencies]` | 供构建脚本使用的依赖，不是运行时的 npm 包 |

Cargo 的 `"3.15.0"` 默认允许兼容版本更新；**`"=3.15.0"` 才是精确约束**。这与 npm 的裸版本写法不同。两端仍需要锁文件固定间接依赖。

### 4.2 创建 `build.rs`

<!-- file: build.rs -->
```rust
fn main() {
    napi_build::setup();
}
```

Cargo 会识别根目录的 `build.rs`，先编译并执行它，再构建库。这里调用 `napi_build::setup()`，按平台设置原生插件需要的构建信息。它是构建期 Rust 程序，不是 JS 入口，也不在每次加法时执行。[Cargo 构建脚本说明](https://doc.rust-lang.org/cargo/reference/build-scripts.html)

### 4.3 创建 `native/lib.rs`

<!-- file: native/lib.rs -->
```rust
use napi_derive::napi;

#[napi(strict)]
pub fn add(a: f64, b: f64) -> f64 {
    a + b
}
```

逐项理解：

1. `use napi_derive::napi` 引入属性宏；`#[napi(strict)]` 让宏为下方函数生成 Node-API 绑定，并在转换前检查 JS 值的类型。
2. `pub fn add` 定义公开 Rust 函数。JS 导出由宏生成，只有写 `pub` 并不足以让 Node 找到它。
3. `a: f64`、`b: f64` 和 `-> f64` 指定参数与结果都是 64 位浮点数，与 JS `number` 对应。这里不使用可能截断小数的整数类型。
4. 最后一行 `a + b` 没有分号，是 Rust 的尾表达式，作为返回值；计算在 Rust 中执行。
5. 错误类型在进入函数前就被绑定拒绝。声明文件中的 `number` 只供 TS 检查，运行时检查来自宏生成的绑定。[napi-rs 属性说明](https://napi.rs/docs/concepts/napi-attributes)

与第一课的手写 C++ 适配层相比，本课把转换与注册工作交给宏；仍要理解边界并验证它的行为。

### 4.4 生成 Cargo 锁文件并检查库

```bash
cargo generate-lockfile
cargo fetch --locked
cargo check --locked
```

第一次会获取 crates.io 索引和依赖，生成 `Cargo.lock`，并在 `target/` 保存检查产物。成功标志是 `cargo check` 最终出现 `Finished` 且退出状态为 0，日志耗时和依赖编译顺序可能不同。

`cargo check` 主要检查 Rust 编译，不会替你生成 `.node`、JS 加载器和类型声明。`Cargo.lock` 由 Cargo 管理，不手写；首次生成后，后续构建使用 `--locked`。[Cargo 配置与锁文件说明](https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html)

## 5. 构建原生插件，观察生成文件

```bash
npm run build:native
ls -l build
cat build/index.d.ts
```

成功构建应出现 `Finished`，`build/` 内至少有：

```text
addon.linux-x64-gnu.node
index.js
index.d.ts
```

这些文件由工具生成，不需要自己创建。CLI 参数分工如下：

| 参数 | 作用 |
| --- | --- |
| `--platform` | 文件名带平台、架构和 ABI 标识，并生成平台加载器 |
| `--esm` | 生成 ESM 格式的 JS 加载器 |
| `--release` | 请求 Cargo release 构建 |
| `--output-dir build` | 将可加载文件放在 `build/`，Cargo 缓存仍在 `target/` |
| `--js index.js` / `--dts index.d.ts` | 显式指定生成的加载器和声明文件名 |
| `-- --locked` | 向 Cargo 传递锁文件约束 |

`build/index.d.ts` 中应包含下面这一行。**这只是观察输出，不要另建文件：**

```ts
export declare function add(a: number, b: number): number
```

工具还会生成注释和 `__napiBindingTarget` 等元数据声明，不必与上面的摘录逐字相同。我们在 TS 中只暴露本课的 `add`。

`index.js` 内部会识别平台并用 `createRequire` 加载对应 `.node`。它也包含面向发布包和 WASI 的通用分支，但本课没有配置对应产物或 JS 加法替代实现。加载器和 `.node` 必须保持相邻。

可以直接经生成加载器做一次真实 Rust 调用：

```bash
node --input-type=module -e 'import { add } from "./build/index.js"; console.log(add(2, 3))'
```

应输出 `5`。`--input-type=module` 使 `-e` 中的代码按 ESM 执行。`cargo build` 单独成功还不等于 Node 插件已经整理好，日常使用 `npm run build:native`。

## 6. 在 TypeScript 中加载并调用

### 6.1 创建 `src/native.ts`

<!-- file: src/native.ts -->
```ts
type NativeAddon = typeof import("../build/index.js");

const addonUrl = new URL("../../build/index.js", import.meta.url);
const addon = (await import(addonUrl.href)) as NativeAddon;

export const add: NativeAddon["add"] = addon.add;
```

这里有两条不同阶段的路径，逐行看清：

- `typeof import("../build/index.js")` 是类型查询。TS 在源码位置 `src/native.ts` 查找 `build/index.d.ts`，获取自动生成的模块类型；这一行在编译后被移除，不会运行导入。
- `new URL("../../build/index.js", import.meta.url)` 在运行时从 **`dist/src/native.js`** 出发，退两级找到项目根下的 `build/index.js`。它使用模块 URL，因此路径里有中文或空格、启动目录改变时仍能定位。
- `await import(addonUrl.href)` 动态加载生成的 ESM 加载器。顶层 `await` 只在模块初始化时等待加载；导出的 `add` 仍然是同步函数，返回 `number`，不返回 Promise。
- `as NativeAddon` 用生成的声明描述动态导入的结果，不手写重复接口；断言不会验证二进制是否正确。集成测试负责验证实际导出与行为。
- `NativeAddon["add"]` 取出 `add` 的函数类型，并只导出这个业务函数。

为什么不在源码里直接静态导入 `../../build/index.js`？TS 会从 `src/` 而不是 `dist/src/` 解析它，导致找错目录。本课保持第一课的 `dist/src/` 输出布局，通过类型路径与运行时 URL 分别处理两个阶段。

TS 运行前要先生成声明；不要直接 `node src/index.ts`，本课明确先用 `tsc` 编译。Node ESM 的动态导入、模块 URL 和顶层 await 见 [Node.js 24 文档](https://nodejs.org/download/release/v24.21.0/docs/api/esm.html)。

### 6.2 创建 `src/index.ts`

<!-- file: src/index.ts -->
```ts
import { add } from "./native.js";

console.log(`add(2, 3) = ${add(2, 3)}`);
```

源文件是 `native.ts`，相对导入写 `.js`：Node ESM 运行实际生成的 JS；TS 的 NodeNext 模式会在源码检查时对应到 `.ts`。

### 6.3 编译、运行与检查

```bash
npm run build:ts
npm start
npm run check
```

程序固定输出：

```text
add(2, 3) = 5
```

`check` 成功时所有子命令退出状态均为 0：rustfmt 通过时通常没有输出；Clippy 没有警告；TS 没有类型错误。这里用 `-D warnings` 将 Clippy 警告作为失败处理。

`npm run build` 可以统一构建 Rust 和 TS。修改 Rust 后不能只运行 `build:ts`；修改 TS 后也不能直接依赖上一次的 `dist/`。`npm start` 不会自动重建。

### 6.4 第二个里程碑：提交可运行实现

验收是刚才的加法输出正确且 `npm run check` 通过。仍在 `practice/`：

```bash
git -C ../.. status --short
git -C ../.. diff -- 02-ts-rust-node-api/practice
git -C ../.. add 02-ts-rust-node-api/practice/Cargo.toml 02-ts-rust-node-api/practice/Cargo.lock 02-ts-rust-node-api/practice/build.rs 02-ts-rust-node-api/practice/native/lib.rs 02-ts-rust-node-api/practice/src/native.ts 02-ts-rust-node-api/practice/src/index.ts
git -C ../.. diff --cached
git -C ../.. commit -m "feat: call Rust add from TypeScript through Node-API"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

## 7. 用测试确认真实跨语言边界

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

test("preserves number semantics for NaN and Infinity", () => {
  assert.ok(Number.isNaN(add(Number.NaN, 1)));
  assert.equal(add(Number.POSITIVE_INFINITY, 1), Number.POSITIVE_INFINITY);
  assert.ok(Number.isNaN(add(Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY)));
});

test("rejects non-number arguments in either position", () => {
  const invalidValues: unknown[] = ["2", undefined, null, true, {}, 2n];

  for (const value of invalidValues) {
    assert.throws(() => Reflect.apply(add, undefined, [value, 3]), {
      code: "InvalidArg",
    });
    assert.throws(() => Reflect.apply(add, undefined, [2, value]), {
      code: "InvalidArg",
    });
  }
});

test("rejects missing arguments", () => {
  for (const args of [[], [2]]) {
    assert.throws(() => Reflect.apply(add, undefined, args), {
      code: "InvalidArg",
    });
  }
});

test("ignores extra arguments at the native boundary", () => {
  assert.equal(Reflect.apply(add, undefined, [2, 3, 4]), 5);
});
```

运行：

```bash
npm test
```

关键统计应为：

```text
ℹ tests 8
ℹ pass 8
ℹ fail 0
```

每次测试先构建 Rust 和 TS，不使用 mock。理解这些边界：

- JS `number` 与 Rust `f64` 都是双精度浮点数；`0.1 + 0.2` 存在表示误差，使用容限比较。`NaN` 和 Infinity 是有效的 number 值，允许通过类型检查。
- `Reflect.apply` 绕过 TS 的常规调用约束，用动态 JS 参数验证原生边界；不需要编造类型断言。
- 本课实测错误对象为 JS `Error`，带 `code: "InvalidArg"`。测试断言错误码，避免把第三方库的完整英文消息当作本项目接口。
- 缺少参数相当于收到 `undefined`，同样被数值检查拒绝。多余参数被绑定忽略，`Reflect.apply(add, undefined, [2, 3, 4])` 得到 `5`。
- **`strict` 检查值的类型，不保证“参数数量必须恰好为二”。** 第一课主动编写了数量检查，本课沿用 napi-rs 的默认数量语义，没有额外添加包装规则。

只想重跑已构建好的测试时可执行下面一条；源码改动后应继续使用 `npm test`：

```bash
node --test dist/test/add.test.js
```

同步加法执行期间占用当前 JS 执行线程。本课计算极短，耗时任务的异步设计留待后续课程。

## 8. 用锁文件重装，清理后重建

### 8.1 重装依赖

```bash
npm ci
cargo fetch --locked
npm test
npm start
```

`npm ci` 按已有 `package-lock.json` 安装，会替换当前 `node_modules/`；它不替你更新锁文件。`cargo fetch --locked` 获取 Cargo 锁定的依赖，不删除现有 Cargo 缓存。

本次手抄项目首次执行 `npm install` 与 `cargo generate-lockfile` 时，间接依赖按当时解析并锁定；需要严格复现交付成品的依赖树时，在 `reference/` 使用它已有的两套锁文件，不要手工拼锁文件。

### 8.2 清除编译产物

```bash
npm run clean
npm test
npm run check
npm start
```

`target/`、`build/`、`dist/` 被删除后应能重新生成，依然 8 项测试通过且输出 `5`。`clean` 保留源码、`node_modules/` 和两套锁文件，不需要重新创建项目。

### 8.3 从其他目录启动

用子 shell 暂时回仓库根目录，外层终端仍停在 `practice/`：

```bash
(
  cd ../..
  node 02-ts-rust-node-api/practice/dist/src/index.js
)
```

仍应输出 `add(2, 3) = 5`。这确认加载路径依赖当前模块位置，而不是 `process.cwd()`。

| 修改内容 | 后续命令 |
| --- | --- |
| Rust、Cargo 配置或构建脚本 | `npm test`，再 `npm run check` |
| TS 或测试 | `npm test`；只改 TS 时也可 `npm run build:ts` 后启动 |
| 依赖版本 | npm 执行 `npm install`；Cargo 执行 `cargo generate-lockfile`，再完整检查并提交两套变更 |
| 想排除旧二进制干扰 | `npm run clean`，再 `npm test` |

## 9. 编写项目说明文档

创建 `practice/README.md`，当前目录下就是 `README.md`。内容完整写为：

<!-- file: README.md -->
````markdown
# TypeScript 调用 Rust：加法实验

这个项目使用 napi-rs 将 Rust 的 `add(a: f64, b: f64) -> f64` 暴露为
TypeScript 的 `add(a: number, b: number): number`。

## 环境

本课以 Ubuntu/Linux x64、Node.js 24、npm 和 Rust stable 为目标。
实测 Node.js 24.21.0、Rust 1.99.1，需要 rustfmt、Clippy 和系统链接器。

## 安装与运行

在本文件所在目录执行：

```bash
npm ci
cargo fetch --locked
npm test
npm start
npm run check
```

预期 8 项集成测试通过，程序打印 `add(2, 3) = 5`。
`npm test` 先构建 Rust 和 TS；`npm start` 只运行已有产物。

## 调用链与边界

TS 经 `tsc` 生成 JS，`src/native.ts` 的编译产物加载 `build/index.js`，
生成的 ESM 加载器再加载 `build/addon.linux-x64-gnu.node`，由 Rust 执行加法。
`build/index.d.ts` 提供自动生成的类型声明，不需要手写 TS 接口。

两个输入和返回值都是双精度浮点数；允许小数、NaN 和 Infinity。
错误类型或缺少参数抛出带 `code: "InvalidArg"` 的 JS `Error`，多余参数被忽略。
TS 类型在运行时被移除，实际类型检查由 `#[napi(strict)]` 生成的绑定执行。

## 清理重建

```bash
npm run clean
npm test
npm run check
npm start
```

`clean` 删除当前项目的 `target/`、`build/`、`dist/`，保留源码、依赖和两套锁文件。
提交 `package-lock.json` 与 `Cargo.lock`；生成的加载器、声明、原生库和编译目录不提交。
````

这份说明描述项目本身，供以后直接进入练习目录时回顾；本课外层 README 则负责从零教学。

## 10. 第三个里程碑：提交测试与说明

**当前仍在 `practice/`。** 先运行完整验证并检查忽略规则：

```bash
npm test
npm run check
npm start
git -C ../.. check-ignore 02-ts-rust-node-api/practice/node_modules/ 02-ts-rust-node-api/practice/target/ 02-ts-rust-node-api/practice/build/ 02-ts-rust-node-api/practice/dist/
git -C ../.. status --short --untracked-files=all
```

第一组命令应通过；`check-ignore` 应列出四个目录。状态中应只有自己的源码、锁文件和文档变更，不出现大量依赖或构建产物。然后提交：

```bash
git -C ../.. diff -- 02-ts-rust-node-api/practice
git -C ../.. add 02-ts-rust-node-api/practice/test/add.test.ts 02-ts-rust-node-api/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify Rust addon behavior and document the lab"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

三条新提交应依次对应配置、实现、测试与说明。若练习开始时工作区干净且教材已提交，现在 `git status --short` 应没有输出；否则只留下你原有工作或尚未提交的教材。本课不要求创建远端或推送。

## 11. 常见故障与检查命令

以下命令都在 `practice/` 执行。查看实际工具和绑定：

```bash
npm ls --depth=0
cargo tree --locked --depth 1
node -p 'process.versions.napi'
ls -l build
cat build/index.d.ts
```

| 现象 | 检查与处理 |
| --- | --- |
| `cargo` 或 `rustc` 找不到 | 查看 `command -v cargo`；已用 rustup 安装时执行 `. "$HOME/.cargo/env"`，再检查版本 |
| 找不到链接器 `cc` | `cc --version`；按第 1 节安装 `build-essential` |
| 依赖要求更高 Rust 版本 | `rustc --version` 和报错中的最低要求；用 `rustup update stable` 后重新检查 |
| rustfmt / Clippy 不存在 | `rustup component list --installed`；执行 `rustup component add rustfmt clippy` |
| `napi` 命令找不到 | `npm ls @napi-rs/cli`，有锁文件时 `npm ci`；通过 npm script 调用本地 CLI |
| `Cargo.lock` 缺失或不匹配 | 首次创建按第 4 节生成；有意修改 Cargo 依赖时重新生成锁文件，再构建并检查差异 |
| `npm ci` 提示锁文件不匹配 | 有意修改 npm 依赖时运行 `npm install` 更新锁文件，再检查变更 |
| `build/index.d.ts` 不存在 / TS 找不到模块 | 先 `npm run build:native`；`npm run typecheck` 会自动完成这一步 |
| 找不到 `dist/src/index.js` | 先 `npm run build`，确认 TS 的 `rootDir` 与 `outDir` 未改变 |
| `Cannot find native binding` | 检查 `ls -l build`；用 `npm run build:native` 重新生成相邻的加载器和 `.node` |
| 直接导入 `.node` 出现扩展名错误 | 应加载生成的 `build/index.js`，由它内部加载原生库 |
| 从源码直接运行时路径错误 | 执行 `npm test`、`npm start`；本课路径针对 `tsc` 生成的 `dist/src/native.js` |
| 修改 Rust 后仍是旧结果 | 确认终端处于 `practice/`，执行 `npm test`；必要时清理重建 |
| 插件架构不符、`ERR_DLOPEN_FAILED` | 检查 Node 平台与架构，不复制其他机器的 `.node`；当前机器清理重建 |
| `fmt:check` 给出差异 | 根据差异手动改 Rust 排版，再运行检查；也可以主动执行 `cargo fmt --all` 自动格式化并审阅 diff |

可观察动态调用的实际异常，确认 TS 类型与运行时检查是两回事：

```bash
node --input-type=module -e 'import { add } from "./build/index.js"; try { Reflect.apply(add, undefined, ["2", 3]); } catch (error) { console.log(error.name, error.code, error.message); }'
```

本课版本实测输出为：

```text
Error InvalidArg Expect value to be Number, but received String
```

类型检查通过并不能保证当前二进制与源码一致，因此验收始终包含实际构建与集成测试。

## 12. 最终验收清单

- [ ] `practice/` 由自己创建，使用根仓库历史，没有嵌套 `.git/`。
- [ ] 能解释 Cargo、导出宏、生成加载器、`.node` 与 `.d.ts` 各自的职责。
- [ ] `npm test` 真实调用 Rust，8 项测试通过。
- [ ] `npm run check` 通过格式检查、Clippy 和 TS 类型检查。
- [ ] `npm ci` 与 `cargo fetch --locked` 后可以构建，清理后可以重新构建。
- [ ] `npm start` 及第 8.3 节异目录启动均打印 `add(2, 3) = 5`。
- [ ] 知道 `f64` 与 `number` 的浮点语义，以及错误类型、缺参和多余参数的行为。
- [ ] 提交了两套锁文件、源码、配置、测试和项目说明，忽略了四类产物目录。
- [ ] 完成三个学习里程碑，提交前审阅了实际暂存差异。

## 教材维护者的提交命令

这一段用于本次新增教材尚未提交的情况；跟随已经提交教材的 clone 练习时，前面三个里程碑就足够。当前若仍位于 `practice/`，先执行下方第一行回到仓库根目录；已经在根目录时跳过第一行。先确认验证记录对应当前教材，且没有其他暂存内容：

```bash
cd ../..
git status --short
git diff --check
git diff -- README.md .gitignore
git add README.md .gitignore 02-ts-rust-node-api/README.md 02-ts-rust-node-api/VERIFICATION.md 02-ts-rust-node-api/reference
git diff --cached
git commit -m "docs: add verified TypeScript to Rust lesson and reference"
git status --short
git log -1 --oneline
```

这里的 `reference` 路径只暂存对照成品，不包含 `practice/`。该教材提交与用户练习的三个里程碑独立；Agent 不会在正式仓库代你执行。
