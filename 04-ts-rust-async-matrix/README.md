# 第四课：TypeScript 异步调用 Rust 矩阵乘法

这一课用 Rust 实现与第三课相同的二维矩阵乘法：TS 提交 `m×n` 与 `n×p` 矩阵，Rust 在后台计算，TS 通过 Promise 和 `await` 收到 `m×p` 结果。你会亲手完成 Cargo 配置、Rust 算法、AsyncTask 绑定、TS 适配、测试、文档和 Git 提交。

本课面向 Ubuntu/Linux x64，沿用第二课的 Node.js 24、TypeScript ESM、napi-rs 和 Rust 工具链。成品在 [reference/](reference/)，实测步骤与范围见 [VERIFICATION.md](VERIFICATION.md)。每课独立安装和构建，不需要运行第三课的 C++ 项目。

## 0. 理解矩阵、目录和异步流程

### 0.1 数学与接口

矩阵乘法用左边的行与右边的列做点积；不是对应位置相乘。

```text
A = [[1, 2, 3],       B = [[ 7,  8],
     [4, 5, 6]]           [ 9, 10],
                          [11, 12]]

2×3 乘 3×2，结果 2×2：
[[58, 64], [139, 154]]

C[row][col] = 对 k 累加 A[row][k] × B[k][col]
58 = 1×7 + 2×9 + 3×11
```

行列数从输入得到，不写死在函数里。`1×4` 乘 `4×1` 得到 `1×1`，`3×1` 乘 `1×4` 得到 `3×4`，都不需要改变接口。

公开 TS 接口为 `multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]>`，其中 `Matrix = readonly (readonly number[])[]`。输入必须至少一行一列，每行等长，元素是有限 number；接受负数与小数，拒绝 NaN/Infinity。readonly 允许调用方传只读矩阵，不会自动在运行时冻结对象。

### 0.2 最终目录

```text
04-ts-rust-async-matrix/
├── README.md
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
    ├── native/
    │   ├── lib.rs                # Node 绑定与 Task
    │   └── matrix.rs             # 纯 Rust 数据和算法
    ├── src/
    │   ├── native.ts             # 公开 TS 适配层
    │   ├── index.ts
    │   └── heartbeat.ts
    ├── test/matrix.test.ts
    ├── README.md                 # 自己编写的项目说明
    ├── build/                    # CLI 生成：加载器、声明和 .node
    ├── target/                   # Cargo 缓存、编译产物
    └── dist/                     # tsc 输出
```

### 0.3 与第三课对照线程生命周期

| 阶段 | 第三课 C++ | 本课 Rust |
| --- | --- | --- |
| 主线程检查与输入快照 | ReadMatrix + vector | read_matrix + Vec |
| 提交后台工作 | AsyncWorker::Queue | 返回 AsyncTask，由生成绑定排队 |
| 工作线程计算 | Execute | Task::compute |
| 主线程处理成功 | OnOK | Task::resolve 和生成的结果转换 |
| 主线程处理失败 | OnError | Task::reject |
| 任务释放 | 框架销毁 worker | 框架结束任务，Rust 自动释放拥有的数据 |

```text
TS 源码 --tsc--> dist/src/index.js
                       │ 调用 dist/src/native.js 中的 async function
                       ▼
                 build/index.js          自动生成的 ESM 加载器
                       │ 加载本机 .node
                       ▼
JS 主线程：Rust 校验 JS 数组 → 独立 Matrix/Vec → AsyncTask
                       │ move 交出所有权，排队后返回原生 Promise
                       ▼
libuv 工作线程：compute → 纯 Rust 三重循环 → Result<Matrix>
                       │
                       ▼
JS 主线程：resolve / reject → 数组或错误 → Promise 完成
                       │
                       ▼
                  TS 的 await 继续
```

`AsyncTask` 用于 Node 共享线程池中的 CPU/阻塞任务；Tokio 的 `async fn` 适合 Rust 异步生态与 I/O。本课不增加 Tokio，也不会仅给同步乘法加一个 async 标记。真正把循环放到后台的是 Task 的 `compute`。[napi-rs 异步选型说明](https://napi.rs/docs/more/async-concurrency)

## 1. 检查并准备工具链

**工作目录：任意目录。** 先检查已有工具：

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

本课实测 Node `24.21.0`、npm `12.2.1`、Rust/Cargo `1.99.1`。最后一条输出为：

```text
{"platform":"linux","arch":"x64","napi":"10"}
```

插件选择 Node-API 8，当前 Node 支持版本 10。Node 主版本、Node-API 级别和 napi crate 版本是不同概念。

只有缺少链接器、Git 或 curl 时，**在任意目录**执行下方 Ubuntu 准备命令：

```bash
sudo apt-get update
sudo apt-get install -y build-essential git curl
```

Rust 仍需系统链接工具。缺少 Rust 时，按 [Rust 官方安装页](https://rust-lang.org/tools/install/)安装 stable：

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
. "$HOME/.cargo/env"
rustup component add rustfmt clippy
```

已有 Rust 时跳过安装器；仅缺少组件时只运行最后一行。工具链太旧而依赖报最低版本要求时，执行 `rustup update stable` 后重新检查版本。实测使用已有工具，本次未执行 sudo、安装器或更新。

已安装 nvm 时可选切换到实测 Node；不使用 nvm 时保留可用的 Node 24 即可：

```bash
nvm install 24.21.0
nvm use 24.21.0
```

环境准备完成后，重新运行本节第一组检查命令。安装与首次下载依赖需要联网。

## 2. 检查现有仓库

**工作目录：仓库根目录。** 第一行路径是占位符，替换为已有 clone 的实际绝对路径：

```bash
cd "/请替换为你的实际路径/ffi-lab"
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
cat .gitignore
```

确认 pwd 与 Git 根路径一致，复用当前历史与分支，不运行 git init。已有未提交或暂存内容需要保留；练习提交只暂存本课列出的路径，每次审阅暂存区，避免夹带其他工作。

根规则已经忽略所有课程中的 `node_modules/`、`target/`、`build/`、`dist/` 和 `.node`，本课无需修改。`package-lock.json` 与 `Cargo.lock` 要提交。

检查提交身份：

```bash
git var GIT_AUTHOR_IDENT
```

只有身份缺失时才执行下面的占位配置，替换为你自己的名字与邮箱：

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

## 3. 初始化独立的 TS 项目

**在仓库根目录执行：**

```bash
mkdir -p 04-ts-rust-async-matrix/practice
cd 04-ts-rust-async-matrix/practice
pwd
npm init -y
mkdir -p native src test
```

pwd 应以 `ffi-lab/04-ts-rust-async-matrix/practice` 结尾。如果已有练习文件，从原进度继续，不要覆盖。

**从这里到第 13 节结束，除非另有说明，命令与文件路径都以 `practice/` 为基准。** 每份文件内容都完整给出；用编辑器手写，不把 Markdown 围栏写进文件。

### 3.1 创建 `.nvmrc`

<!-- file: .nvmrc -->
```text
24.21.0
```

它供 nvm 选择推荐版本；Node 本身不会自动读取。

### 3.2 编辑 `package.json`

将 npm init 生成的内容完整替换为：

<!-- file: package.json -->
```json
{
  "name": "ts-rust-async-matrix",
  "version": "1.0.0",
  "private": true,
  "description": "Learn asynchronous Rust matrix multiplication from TypeScript with napi-rs",
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
    "demo:heartbeat": "node dist/src/heartbeat.js",
    "test": "npm run build && node --test dist/test/matrix.test.js",
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

- `private` 避免误发布 npm 包，`type: "module"` 让本项目 JS 采用 ESM。
- 三个 npm 包都是开发工具，保持第二课的精确版本；Rust 依赖由 Cargo 管理。
- `build:native` 使用本地 CLI，生成 release 原生库、ESM 加载器和类型声明；`-- --locked` 将锁文件约束传给 Cargo。首次锁文件在第 4 节生成。
- `build` 先生成 Rust 绑定和声明，再编译 TS。`typecheck` 也先构建原生模块，避免干净目录中缺少声明。
- `check` 顺序执行 rustfmt、Clippy 和 TS 检查。Clippy 的警告视为错误。
- `start` 与心跳命令只运行已有产物；`clean` 清除本项目的 Cargo 产物、加载器和编译后 JS，保留源码与锁文件。

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

NodeNext 与 ESM 按 Node 的规则解析导入。`strict` 开启严格检查；`rootDir: "."` 与 `outDir: "dist"` 使 src、test 分别输出到 dist/src、dist/test。TS 不编译 Rust，也不复制 `.node`。

安装依赖并生成 npm 锁文件：

```bash
npm install
npm ls --depth=0
```

应有 `@napi-rs/cli@3.10.9`、`@types/node@24.19.2`、`typescript@7.0.2` 三个直接依赖。`package-lock.json` 交给 npm 生成，不手写。

### 3.4 第一个里程碑：项目配置

当前阶段的验收是安装成功、没有缺失依赖；Rust 文件尚未创建，不运行完整构建。

```bash
git -C ../.. status --short
git -C ../.. diff -- 04-ts-rust-async-matrix/practice
git -C ../.. add 04-ts-rust-async-matrix/practice/.nvmrc 04-ts-rust-async-matrix/practice/package.json 04-ts-rust-async-matrix/practice/package-lock.json 04-ts-rust-async-matrix/practice/tsconfig.json
git -C ../.. diff --cached
git -C ../.. commit -m "chore: configure asynchronous Rust matrix project"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

## 4. 手写 Cargo 配置与构建脚本

本课手动初始化最小 crate，不运行 cargo new/cargo init，不创建嵌套 Git 仓库。

### 4.1 创建 `Cargo.toml`

<!-- file: Cargo.toml -->
```toml
[package]
name = "ts-rust-async-matrix"
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

`edition = "2024"` 是语言规则版本；`publish = false` 防止误发布 crate。`[lib].path` 把 Rust 入口放在 native，与 TS 的 src 区分；`cdylib` 生成可由 Node 加载的共享库。

napi 关闭默认 feature，只启用 Node-API 8 所需能力；AsyncTask 已可使用，不需要开启 Tokio 的 async feature。napi-derive 保留默认类型信息生成，napi-build 用于构建脚本。

Cargo 的 `"3.15.0"` 默认允许兼容更新，`"=3.15.0"` 才精确固定。间接版本由 Cargo.lock 记录，不能只靠固定直接版本复现全部依赖树。

### 4.2 创建 `build.rs`

<!-- file: build.rs -->
```rust
fn main() {
    napi_build::setup();
}
```

Cargo 在构建库之前执行这个程序，`napi_build::setup()` 准备平台相关构建信息；它在构建阶段运行，不会在每次矩阵调用时执行。[Cargo 构建脚本说明](https://doc.rust-lang.org/cargo/reference/build-scripts.html)

## 5. 编写纯 Rust 矩阵模型与算法

创建 `native/matrix.rs`：

<!-- file: native/matrix.rs -->
```rust
use std::fmt;
use std::mem::size_of;

#[derive(Debug)]
pub enum MatrixError {
    Range(String),
    Allocation(String),
}

impl MatrixError {
    pub fn is_range(&self) -> bool {
        matches!(self, Self::Range(_))
    }
}

impl fmt::Display for MatrixError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Range(message) | Self::Allocation(message) => formatter.write_str(message),
        }
    }
}

pub type MatrixResult<T> = Result<T, MatrixError>;

pub struct Matrix {
    pub rows: usize,
    pub cols: usize,
    pub data: Vec<f64>,
}

pub fn checked_element_count(rows: usize, cols: usize) -> MatrixResult<usize> {
    if rows == 0 || cols == 0 {
        return Err(MatrixError::Range(
            "matrix dimensions must be positive".into(),
        ));
    }
    let count = rows
        .checked_mul(cols)
        .filter(|count| *count <= (isize::MAX as usize) / size_of::<f64>())
        .ok_or_else(|| MatrixError::Range("matrix dimensions exceed supported size".into()))?;
    Ok(count)
}

impl Matrix {
    pub fn zeros(rows: usize, cols: usize) -> MatrixResult<Self> {
        let count = checked_element_count(rows, cols)?;
        let mut data = Vec::new();
        data.try_reserve_exact(count).map_err(|error| {
            MatrixError::Allocation(format!("matrix allocation failed: {error}"))
        })?;
        data.resize(count, 0.0);
        Ok(Self { rows, cols, data })
    }

    fn validate_storage(&self) -> MatrixResult<()> {
        if self.data.len() != checked_element_count(self.rows, self.cols)? {
            return Err(MatrixError::Range(
                "matrix storage does not match its shape".into(),
            ));
        }
        Ok(())
    }

    pub fn multiply(&self, other: &Self) -> MatrixResult<Self> {
        self.validate_storage()?;
        other.validate_storage()?;
        if self.cols != other.rows {
            return Err(MatrixError::Range("a columns must equal b rows".into()));
        }
        let mut result = Self::zeros(self.rows, other.cols)?;
        for row in 0..self.rows {
            for col in 0..other.cols {
                let mut sum = 0.0;
                for k in 0..self.cols {
                    sum += self.data[row * self.cols + k] * other.data[k * other.cols + col];
                    if !sum.is_finite() {
                        return Err(MatrixError::Range(
                            "matrix multiplication produced a non-finite value".into(),
                        ));
                    }
                }
                result.data[row * result.cols + col] = sum;
            }
        }
        Ok(result)
    }

    pub fn into_rows(self) -> MatrixResult<Vec<Vec<f64>>> {
        self.validate_storage()?;
        let allocation_error =
            |error| MatrixError::Allocation(format!("result allocation failed: {error}"));
        let mut rows = Vec::new();
        rows.try_reserve_exact(self.rows)
            .map_err(allocation_error)?;
        for chunk in self.data.chunks(self.cols) {
            let mut row = Vec::new();
            row.try_reserve_exact(self.cols).map_err(allocation_error)?;
            row.extend_from_slice(chunk);
            rows.push(row);
        }
        Ok(rows)
    }
}
```

按以下顺序理解：

- `Matrix` 拥有 rows、cols 和连续的 `Vec<f64>`；位置 `(row, col)` 对应 `data[row * cols + col]`。struct 中没有 JS 对象或借用。
- `MatrixError` 将范围与分配错误分开，`MatrixResult<T>` 是纯 Rust 的 Result 别名。该模块不导入 napi。
- `checked_mul` 检查 usize 乘法，再限制 f64 总字节数不超过 isize 的容量约束。分配前检查，避免溢出后再比较。
- `try_reserve_exact` 让可报告的分配失败进入 Result；reserve 成功后再填充。它不保证进程能从系统级内存耗尽中恢复。
- `multiply` 使用 row、col、k 三重循环，按乘法规则累加。每步检查有限性，乘积或累加溢出都返回 Range 错误，不用 panic 表达预期失败。
- `into_rows(self)` 消费结果矩阵并组织成 `Vec<Vec<f64>>`，每行拥有独立内存；使用结果的主线程完成这一步。

`&self`、`&Self` 是计算期间的只读借用；输入本身由任务拥有。`self` 参数则把结果的所有权交给转换函数。这些方法不依赖 Node，可单独检查算法边界。

## 6. 实现 Rust 的 Node 绑定与 AsyncTask

创建 `native/lib.rs`：

<!-- file: native/lib.rs -->
```rust
mod matrix;

use matrix::{Matrix, MatrixError, checked_element_count};
use napi::bindgen_prelude::{AsyncTask, JsObjectValue, Unknown};
use napi::{Env, Error, JsRangeError, JsTypeError, JsValue, Result, Task, ValueType};
use napi_derive::napi;

fn type_error(env: Env, message: impl Into<String>) -> Error {
    JsTypeError::from(Error::from_reason(message))
        .into_unknown(env)
        .into()
}

fn range_error(env: Env, message: impl Into<String>) -> Error {
    JsRangeError::from(Error::from_reason(message))
        .into_unknown(env)
        .into()
}

fn matrix_error(env: Env, error: MatrixError) -> Error {
    if error.is_range() {
        range_error(env, error.to_string())
    } else {
        Error::from_reason(error.to_string())
    }
}

fn read_matrix(env: Env, value: Unknown<'_>, name: &str) -> Result<Matrix> {
    if !value.is_array()? {
        return Err(type_error(env, format!("{name} must be an array of rows")));
    }
    let array = value.coerce_to_object()?;
    let rows = array.get_array_length()?;
    if rows == 0 {
        return Err(range_error(env, format!("{name} must not be empty")));
    }
    if !array.has_own_property("0")? {
        return Err(type_error(
            env,
            format!("{name} must not contain sparse rows"),
        ));
    }
    let first: Unknown = array.get_element(0)?;
    if !first.is_array()? {
        return Err(type_error(env, format!("{name} rows must be arrays")));
    }
    let cols = first.coerce_to_object()?.get_array_length()?;
    if cols == 0 {
        return Err(range_error(env, format!("{name} rows must not be empty")));
    }
    let mut matrix =
        Matrix::zeros(rows as usize, cols as usize).map_err(|error| matrix_error(env, error))?;
    for row in 0..rows {
        env.run_in_scope(|| {
            if !array.has_own_property(&row.to_string())? {
                return Err(type_error(
                    env,
                    format!("{name} must not contain sparse rows"),
                ));
            }
            let row_value: Unknown = array.get_element(row)?;
            if !row_value.is_array()? {
                return Err(type_error(env, format!("{name} rows must be arrays")));
            }
            let cells = row_value.coerce_to_object()?;
            if cells.get_array_length()? != cols {
                return Err(range_error(
                    env,
                    format!("{name} rows must have equal lengths"),
                ));
            }
            for col in 0..cols {
                if !cells.has_own_property(&col.to_string())? {
                    return Err(type_error(
                        env,
                        format!("{name} must not contain sparse elements"),
                    ));
                }
                let cell: Unknown = cells.get_element(col)?;
                if cell.get_type()? != ValueType::Number {
                    return Err(type_error(env, format!("{name} elements must be numbers")));
                }
                let number = cell.coerce_to_number()?.get_double()?;
                if !number.is_finite() {
                    return Err(range_error(env, format!("{name} elements must be finite")));
                }
                matrix.data[row as usize * matrix.cols + col as usize] = number;
            }
            Ok(())
        })?;
    }
    Ok(matrix)
}

pub struct MatrixTask {
    a: Matrix,
    b: Matrix,
    range_error: bool,
}

#[napi]
impl Task for MatrixTask {
    type Output = Matrix;
    type JsValue = Vec<Vec<f64>>;

    fn compute(&mut self) -> Result<Self::Output> {
        self.a.multiply(&self.b).map_err(|error| {
            self.range_error = error.is_range();
            Error::from_reason(error.to_string())
        })
    }

    fn resolve(&mut self, env: Env, output: Self::Output) -> Result<Self::JsValue> {
        output.into_rows().map_err(|error| matrix_error(env, error))
    }

    fn reject(&mut self, env: Env, error: Error) -> Result<Self::JsValue> {
        if self.range_error {
            Err(JsRangeError::from(error).into_unknown(env).into())
        } else {
            Err(error)
        }
    }
}

#[napi(
    ts_args_type = "a: ReadonlyArray<ReadonlyArray<number>>, b: ReadonlyArray<ReadonlyArray<number>>"
)]
pub fn multiply_async(env: Env, a: Unknown<'_>, b: Unknown<'_>) -> Result<AsyncTask<MatrixTask>> {
    let a = read_matrix(env, a, "a")?;
    let b = read_matrix(env, b, "b")?;
    if a.cols != b.rows {
        return Err(range_error(env, "a columns must equal b rows"));
    }
    checked_element_count(a.rows, b.cols).map_err(|error| matrix_error(env, error))?;
    Ok(AsyncTask::new(MatrixTask {
        a,
        b,
        range_error: false,
    }))
}
```

### 6.1 JS 主线程：类型检查与自有数据

`mod matrix` 引入刚才的算法模块。这里的 `Result` 来自 napi，区别于纯算法的 MatrixResult；`?` 在两类 Result 的边界处通过 map_err 转换错误。

`read_matrix` 用 Unknown 接收真实 JS 值，手动检查普通数组、非空、每行等长、每个下标都有自身属性、元素为有限 number。先确认 Number 再取 f64，不会把字符串自动转成数值。

`env.run_in_scope` 让每行的临时 JS 句柄只留在该行处理过程中；向量里的 f64 是独立副本，可以离开句柄作用域。遇到用户 getter 抛出的异常时，错误会沿绑定层传出，由 TS 层转成拒绝。

`type_error`、`range_error` 在 JS 线程创建正确的错误对象，保留为 napi Error。只在主线程读取或创建这些 JS 值；纯算法错误在这里按类别映射。

### 6.2 把输入 move 给任务

`multiply_async` 先完成输入读取、维度相容性与输出尺寸检查，再构造 MatrixTask。写入 `a`、`b` 字段会移动所有权，不复制整个 Vec，也不留下对 JS 数组的借用。

Task trait 要求任务可 Send；两个 Matrix 只保存自有数字数据，满足这个跨线程约束。任务在完成后由框架结束，拥有的 Vec 自动释放，不需要手写 delete 或手工释放输入。

### 6.3 compute、resolve 与 reject

- `compute` 在 libuv 工作线程上，只调用纯 Rust 矩阵算法。它可以生成只包含状态和字符串的 napi Error，但不能读取 Env、Unknown 或调用 JS。
- `resolve` 回到 JS 线程，把成功输出组织为独立行；框架随后将 `Vec<Vec<f64>>` 转成 JS 二维数组。
- `reject` 也在 JS 线程，把范围类计算错误转换为 JS RangeError，其他错误保留为 Error。后台没有保存 JS 错误对象。

Rust 的 Result 用来返回预期失败；panic 表示另一种失败机制，不应把输入校验写成 unwrap 或依赖数组越界。官方 Task/AsyncTask 的阶段划分见 [AsyncTask 文档](https://napi.rs/docs/concepts/async-task)。

### 6.4 自动声明与运行时校验分工

Task impl 上的 `#[napi]` 供声明生成器识别 `JsValue = Vec<Vec<f64>>`，生成确切的数值矩阵 Promise。缺少这层信息可能变成 Promise<unknown>。

函数的 `ts_args_type` 将 Unknown 输入的声明描述为两层只读数值数组。它只修改 `.d.ts`，不执行校验；真实值仍由 read_matrix 完整检查。[napi 属性说明](https://napi.rs/docs/concepts/napi-attributes)

### 6.5 生成 Cargo 锁文件并检查

现在 Cargo 配置与源码完整，执行：

```bash
cargo generate-lockfile
cargo fetch --locked
cargo check --locked
```

首次会获取索引、依赖并生成 Cargo.lock。成功标志是最后出现 Finished、退出状态为 0；日志顺序与耗时可变。锁文件由 Cargo 管理，不手写；后续构建带 --locked，不悄悄更新解析结果。[Cargo 锁文件说明](https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html)

## 7. 构建并观察生成文件

**当前目录：`practice/`。**

```bash
npm run build:native
ls -l build
cat build/index.d.ts
```

成功时有 release 构建的 Finished，build 内至少有：

```text
index.js
index.d.ts
addon.linux-x64-gnu.node
```

`--platform` 生成带平台标识的原生库和加载器，`--esm` 选择 ESM，`--release` 请求发布构建，`--output-dir build` 指定整理后的产物目录；Cargo 中间产物仍在 target。CLI 的调用方式见 [官方构建说明](https://napi.rs/docs/cli/build)。

声明中应包含以下函数。**这是观察输出的摘录，不要手写生成文件：**

```ts
export declare function multiplyAsync(a: ReadonlyArray<ReadonlyArray<number>>, b: ReadonlyArray<ReadonlyArray<number>>): Promise<Array<Array<number>>>
```

`ReadonlyArray<ReadonlyArray<number>>` 对应本课的 Matrix，`Array<Array<number>>` 等价于 number[][]。文件还包含工具注释、绑定目标等元数据，不需要逐字匹配整份文件。

加载器识别系统、架构和 libc，并在内部加载对应 `.node`。本课没有构建 WASI 产物或 JS 乘法降级；不要只移动加载器而把原生库留在别处。

先直接调用一次底层生成加载器：

```bash
node --input-type=module -e 'import { multiplyAsync } from "./build/index.js"; console.log(JSON.stringify(await multiplyAsync([[1, 2]], [[3], [4]])))'
```

应输出 `[[11]]`。这个原生入口的校验错误可能同步抛出，参数数量也遵循底层绑定规则；下一节定义对外使用的 TS 接口，统一 Promise 和数量语义。

## 8. TS 适配层、await 与并发调用

### 8.1 创建 `src/native.ts`

<!-- file: src/native.ts -->
```ts
type NativeAddon = typeof import("../build/index.js");

const addonUrl = new URL("../../build/index.js", import.meta.url);
const addon = (await import(addonUrl.href)) as NativeAddon;

export type Matrix = readonly (readonly number[])[];

export async function multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]> {
  if (arguments.length !== 2) {
    throw new TypeError("multiplyAsync expects exactly 2 arguments");
  }
  return addon.multiplyAsync(a, b);
}
```

先区分两条路径：

- `typeof import("../build/index.js")` 在源码位置读取生成声明，只用于类型，编译后消失。
- `new URL("../../build/index.js", import.meta.url)` 在 `dist/src/native.js` 的运行位置退两级，定位项目 build。中文、空格和不同启动目录均由模块 URL 处理。
- 顶层动态 import 加载 ESM 绑定；`as NativeAddon` 使用生成声明描述结果，不会在运行时验证二进制。

公开函数是具名 async function，因此可以用 `arguments.length` 检查实际数量；TS 正常调用仍受两个参数的签名约束。缺少或多余参数都通过 rejected Promise 报告。

**函数体会立即执行到返回原生调用结果这一步。** Rust 在原生函数返回前已经完成输入复制，所以调用方随后修改原数组不会影响任务。这里没有把复制延迟到下一轮事件循环。

async 包装将 Rust 原生入口的同步校验异常转为 Promise rejection，也会接纳原生 AsyncTask 的 Promise。这个包装本身不把 CPU 运算移出主线程；三重循环仍由 Rust compute 在后台执行。Node 的模块 URL、动态 import 与顶层 await 见 [Node ESM 文档](https://nodejs.org/download/release/v24.21.0/docs/api/esm.html)。

### 8.2 创建 `src/index.ts`

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

这个示例与第三课保持相同输出：先提交任务并继续当前 JS，再 await；用 Promise.all 等待两个独立任务；最后捕获尺寸不匹配的拒绝。

Promise.all 的结果按输入顺序排列，不要求任务按同样顺序完成，也不保证线程池同时运行所有任务。源码相对导入写 `.js`，让 TS 对应到 `.ts` 并为输出保留 Node 可运行的路径。

### 8.3 编译、运行与静态检查

```bash
npm run build:ts
npm start
npm run check
```

固定输出：

```text
submitted; JavaScript continues before await
2x3 * 3x2 = [[58,64],[139,154]]
Promise.all = [[[6]],[[32]]]
caught: RangeError a columns must equal b rows
```

check 成功意味着 rustfmt 没有格式差异，Clippy 没有警告，TS 没有类型错误。之后可用 `npm run build` 统一构建两端。不要直接 node 运行 src/index.ts，本课的加载路径按 tsc 输出布局设计。

### 8.4 第二个里程碑：提交可运行实现

验收是矩阵结果与错误输出正确，npm run check 通过：

```bash
git -C ../.. status --short
git -C ../.. diff -- 04-ts-rust-async-matrix/practice
git -C ../.. add 04-ts-rust-async-matrix/practice/Cargo.toml 04-ts-rust-async-matrix/practice/Cargo.lock 04-ts-rust-async-matrix/practice/build.rs 04-ts-rust-async-matrix/practice/native/matrix.rs 04-ts-rust-async-matrix/practice/native/lib.rs 04-ts-rust-async-matrix/practice/src/native.ts 04-ts-rust-async-matrix/practice/src/index.ts
git -C ../.. diff --cached
git -C ../.. commit -m "feat: multiply matrices asynchronously with Rust AsyncTask"
git -C ../.. status --short
git -C ../.. log -1 --oneline
```

## 9. 运行定时心跳演示

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

输入为 600×800 和 800×500 的全 1 矩阵，结果为 600×500，每项为 800。输出示意：

```text
queued 600x800 * 800x500; waiting with await
heartbeat 1
heartbeat 2
...
result: 600x500; first = 800
heartbeats: 4; elapsed: 321.0 ms
```

只有形状与首元素是固定结果。心跳次数和耗时依机器、调度和负载改变，快机器可能看到 0 次；需要更长观察时间时，增大文件内的维度，再编译运行。finally 在成功或失败时都清除定时器。

校验、复制输入和结果转换仍然占用 JS 主线程，只有乘法循环移到后台。线程池还被部分文件、密码学等原生任务共享，任务可能排队；本课不调整池大小，不承诺异步更快。[Node 线程池说明](https://nodejs.org/download/release/v24.21.0/docs/api/cli.html#uv_threadpool_sizesize)

## 10. 测试真实跨语言调用

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

test("creates and completes the AsyncTask native async resource", async () => {
  type Binding = typeof import("../build/index.js");
  const bindingUrl = new URL("../../build/index.js", import.meta.url);
  const binding = (await import(bindingUrl.href)) as Binding;
  const records: { id: number; type: string; resource: object }[] = [];
  const callbacks = new Set<number>();
  const hook = createHook({
    init(id, type, _trigger, resource) {
      records.push({ id, type, resource });
    },
    before(id) {
      callbacks.add(id);
    },
  });
  hook.enable();
  try {
    const pending = binding.multiplyAsync([[2]], [[4]]);
    assert.ok(pending instanceof Promise);
    const work = records.filter(({ type, resource }) =>
      type !== "PROMISE" && resource === pending,
    );
    assert.equal(work.length, 1);
    assert.deepEqual(await pending, [[8]]);
    assert.ok(callbacks.has(work[0].id));
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

关键统计为：

```text
ℹ tests 25
ℹ pass 25
ℹ fail 0
```

测试的设计目的：

- 小规模 TS 算法只用于对照结果，被测 multiplyAsync 始终调用真实 Rust `.node`。
- 非方阵、不同尺寸、单元素、单位矩阵、零矩阵、负数和小数容限验证数学行为。
- 冻结输入、输入不被修改、提交后改变数组、结果行独立、Promise.all 和失败任务隔离验证所有权。
- Reflect.apply 模拟动态 JS 错误调用；辅助函数先确认返回 Promise，再断言 TypeError 或 RangeError。
- Number.MAX_VALUE 的乘积与累加溢出经过实际 compute/reject；getter 异常也必须以拒绝传播并保留原异常。

异步资源测试直接观察底层 AsyncTask 返回的 Promise，因为公开 async function 还会创建外层 Promise。该锁定版本把原生 Promise 作为异步工作的 resource；测试按对象身份匹配非 PROMISE 类型资源，并确认其完成回调运行。

本机资源类型字符串显示为 `undefined`，测试不把这个名字写死，也不照搬第三课的 C++ 名字。hook 内只保存记录，不调用 console.log，避免日志自身的异步资源干扰观察。async_hooks 只用于诊断测试，结合 compute 的代码边界与心跳演示验证后台路径，不使用毫秒阈值。[Node async_hooks 文档](https://nodejs.org/download/release/v24.21.0/docs/api/async_hooks.html)

确认产物最新时可单独重跑：

```bash
node --test dist/test/matrix.test.js
```

修改源码后继续使用 npm test，先重新构建两端。

## 11. 验证安装、清理与加载路径

### 11.1 用两套锁文件获取依赖

```bash
npm ci
cargo fetch --locked
npm test
npm start
```

npm ci 按锁文件替换 node_modules，不更新依赖声明；cargo fetch --locked 获取已锁定 crate，不清理 Cargo 缓存。

首次手抄项目的 npm install 和 cargo generate-lockfile 会按当时解析间接依赖；需要严格使用成品依赖树时，在 reference 中使用已有的两套锁文件。

### 11.2 清理后重建

```bash
npm run clean
npm test
npm run check
npm start
npm run demo:heartbeat
```

target、build、dist 被移除后会重新生成；测试仍为 25 项通过，主程序输出正确。clean 不删除源码、node_modules 和锁文件，不需要重新初始化项目。

### 11.3 从其他目录启动

用子 shell 临时回到仓库根目录，外层仍保留 practice 工作目录：

```bash
(
  cd ../..
  node 04-ts-rust-async-matrix/practice/dist/src/index.js
)
```

应得到第 8 节相同输出，确认加载不依赖 process.cwd()。

| 修改内容 | 后续操作 |
| --- | --- |
| Rust 算法、绑定、Cargo 配置 | npm test 与 npm run check |
| TS、演示或测试 | npm test；只改演示也可先 build:ts 再运行 |
| 需要排除旧二进制影响 | npm run clean，再 npm test |
| 有意修改 npm 版本 | npm install 更新锁文件，再检查测试 |
| 有意修改 Cargo 版本 | cargo generate-lockfile 更新锁文件，再检查测试 |

## 12. 编写项目说明

创建当前 practice 目录下的 `README.md`：

<!-- file: README.md -->
````markdown
# TypeScript 异步调用 Rust：矩阵乘法

本项目使用 napi-rs AsyncTask，在 libuv 工作线程中计算动态二维矩阵乘法。
实测 Ubuntu/Linux x64、Node.js 24.21.0、Rust 1.99.1。
需要 npm、rustfmt、Clippy、系统 C 链接工具；不需要构建其他课程。

## 安装与运行

在本文件所在目录执行：

```bash
npm ci
cargo fetch --locked
npm test
npm run check
npm start
npm run demo:heartbeat
```

预期 25 项集成测试通过，演示得到 `[[58,64],[139,154]]`。
`test` 先构建 Rust 和 TS；`check` 运行格式、Clippy 与类型检查。
`start`、`demo:heartbeat` 只运行已有产物。

## 公开接口

从 src/native.ts 的编译产物导入：
`multiplyAsync(a: Matrix, b: Matrix): Promise<number[][]>`，
`Matrix = readonly (readonly number[])[]`。

非空、每行等长、元素有限的普通二维数组：m×n 乘 n×p，结果 m×p。
类型、稀疏数组和参数数量错误拒绝为 TypeError；形状、非有限数值和
计算溢出拒绝为 RangeError，其他原生任务错误拒绝为 Error。
生成加载器是底层接口，其参数校验可能同步抛出；对外调用使用 TS 适配层。

## 数据与线程

Rust 在 JS 线程检查并复制输入，将拥有独立 Vec<f64> 的 Matrix move 到任务。
Task::compute 在 libuv 线程计算，resolve/reject 回 JS 线程转换结果和错误。
TS async function 统一 Promise 错误语义；它本身不调度 CPU 计算。
任务完成后，Rust 自动释放其数据。

调用返回后修改原数组不影响已提交任务；输入不被修改，结果不共享行。
校验、输入复制和结果转换仍占 JS 主线程；线程池任务可能排队。
心跳例子的 600×800 乘 800×500 应输出形状 600×500、首元素 800，
心跳次数和耗时不作为固定验收条件。

## 清理与版本控制

```bash
npm run clean
npm test
npm run check
npm start
```

clean 删除当前项目 target/、build/、dist/，保留源码和依赖。
提交 package-lock.json、Cargo.lock、源码、配置、测试和本说明；
不提交依赖目录或生成产物。
````

这份说明描述项目自身，供以后进入项目回顾；外层手册记录从零操作流程。

## 13. 第三个里程碑：提交测试、心跳和文档

先完成最终检查：

```bash
npm test
npm run check
npm start
git -C ../.. check-ignore 04-ts-rust-async-matrix/practice/node_modules/ 04-ts-rust-async-matrix/practice/target/ 04-ts-rust-async-matrix/practice/build/ 04-ts-rust-async-matrix/practice/dist/
git -C ../.. status --short --untracked-files=all
```

应通过测试与检查，check-ignore 列出四类产物目录，状态中没有大量依赖文件。然后提交本里程碑：

```bash
git -C ../.. diff -- 04-ts-rust-async-matrix/practice
git -C ../.. add 04-ts-rust-async-matrix/practice/src/heartbeat.ts 04-ts-rust-async-matrix/practice/test/matrix.test.ts 04-ts-rust-async-matrix/practice/README.md
git -C ../.. diff --cached
git -C ../.. commit -m "test: verify Rust async matrix behavior and document the lab"
git -C ../.. status --short
git -C ../.. log -3 --oneline
```

三条学习提交依次对应配置、实现、测试与说明。其他未提交教材和个人工作保留在状态中，本课不要求创建远端或推送。

## 14. 常见故障与检查

**以下命令仍在 practice 运行。** 查看实际依赖与生成声明：

```bash
npm ls --depth=0
cargo tree --locked --depth 1
node -p 'process.versions.napi'
ls -l build
cat build/index.d.ts
```

| 现象 | 检查与处理 |
| --- | --- |
| cargo/rustc 找不到 | 检查 PATH；rustup 安装后在当前终端读取 $HOME/.cargo/env |
| 链接器 cc 缺失 | 按第 1 节安装 build-essential，并重新检查 |
| Rust 版本被依赖拒绝 | 检查报错中的版本要求，必要时更新 stable |
| 缺少 rustfmt/Clippy | rustup component add rustfmt clippy |
| CLI 找不到 | 检查 npm ls @napi-rs/cli，有锁文件时 npm ci，通过 npm script 运行 |
| Cargo.lock 不匹配 | 首次按第 6 节生成；有意改依赖后重新生成并审阅差异 |
| TS 找不到 build/index.js 的声明 | 先 build:native；npm run typecheck 会自动构建声明 |
| 返回类型变成 Promise<unknown> | 检查 Task impl 上的 napi 属性及 JsValue，重新构建查看 index.d.ts |
| readonly 输入编译不通过 | 检查生成的只读声明；ts_args_type 要与手写运行时校验一致 |
| 找不到 dist/src/index.js | 先 npm run build，不直接运行 TS 源文件 |
| Cannot find native binding | 检查 build 中加载器与 .node 是否相邻，再 build:native |
| 直接运行生成入口时同步抛错 | 对外使用 src/native 的编译产物，公开 async function 统一 Promise 语义 |
| NaN、Infinity 或计算溢出被拒绝 | 本课要求有限输入和结果，检查数值范围 |
| 心跳少或为 0 | 核对异步资源测试；必要时加大演示维度重新编译，不用次数单独判断异步 |
| 并发任务有等待 | 线程池容量有限，Promise.all 不保证同时执行 |
| fmt:check 给差异 | 根据差异手动改格式，或主动运行 cargo fmt --all 后审阅 diff |
| Clippy 警告导致失败 | 按位置修复问题；本课将警告视为错误 |
| npm ci 拒绝不匹配的锁文件 | 有意改 npm 依赖时运行 npm install，检查并提交两份文件 |

可单独检查公开接口的拒绝处理：

```bash
node --input-type=module -e 'import { multiplyAsync } from "./dist/src/native.js"; try { await multiplyAsync([[1, 2]], [[3, 4]]); } catch (error) { console.log(error.name, error.message); }'
```

应输出：

```text
RangeError a columns must equal b rows
```

## 15. 最终验收清单

- [ ] 能说明 m×n 与 n×p 的结果尺寸，不同尺寸无需改接口。
- [ ] 能指出 TS 包装、Rust 校验、compute、resolve/reject 各在哪个线程执行。
- [ ] 能解释 Vec 所有权、move、借用和 Send 在本课中的作用。
- [ ] 知道 Result 传递预期失败，未把输入校验写成 panic/unwrap。
- [ ] 公开函数返回 Promise，参数与后台计算错误都能用 await/try-catch 捕获。
- [ ] 生成声明明确包含只读数值输入和数值矩阵 Promise。
- [ ] npm test 的 25 项实际 Rust 集成测试通过，异步资源检查通过。
- [ ] npm run check 通过 rustfmt、Clippy 和 TS 检查。
- [ ] 锁文件重装、清理重建和异目录启动成功。
- [ ] 运行心跳并理解数据复制仍占主线程，次数不是固定阈值。
- [ ] 完成三个学习提交，提交两套锁文件，依赖和产物被忽略。
- [ ] 保留前三课与个人工作，课程内没有嵌套 Git 仓库。

## 教材维护者的提交命令

此段适用于本次新教材尚未提交的情况；跟随已含教材的 clone 学习时无需重复。仍在 practice 时用第一行回到仓库根目录，已在根目录时跳过第一行。

本次开始时第二、三课教材和根索引仍有未提交改动，先自行安排原有教材。`git add README.md` 会暂存根索引全部改动，需审阅前几课入口与本课入口的提交安排；下面的目录路径只包含第四课教材，不包含用户练习。

```bash
cd ../..
git status --short
git diff --check
git diff -- README.md
git add README.md 04-ts-rust-async-matrix/README.md 04-ts-rust-async-matrix/VERIFICATION.md 04-ts-rust-async-matrix/reference
git diff --cached
git commit -m "docs: add verified asynchronous Rust matrix lesson"
git status --short
git log -1 --oneline
```

Agent 只在临时副本验证提交命令，正式仓库的暂存、提交和推送由你执行。
