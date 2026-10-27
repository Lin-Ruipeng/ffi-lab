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