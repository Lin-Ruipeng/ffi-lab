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
