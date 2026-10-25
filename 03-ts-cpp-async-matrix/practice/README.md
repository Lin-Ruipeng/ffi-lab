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
