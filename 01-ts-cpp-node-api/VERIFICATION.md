# 第一课验证记录

验证日期：2026-10-22（Asia/Singapore）。本记录对应同目录教程与 `reference/` 成品。

## 实测环境

| 项目 | 版本/配置 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x64 |
| Node.js | 24.21.0 |
| npm | 12.2.1 |
| 运行时支持的 Node-API | 10 |
| 插件声明的 Node-API | 8 |
| CMake | 4.2.3，Ubuntu 包 4.2.3-2ubuntu2 |
| CMake generator | Unix Makefiles |
| C++ 编译器 | G++ 15.2.0 |
| GNU Make | 4.4.1 |
| Git | 2.53.0 |
| TypeScript | 7.0.2 |
| `@types/node` | 24.19.2 |
| `node-addon-api` | 8.9.2 |
| `cmake-js` | 8.0.0 |
| `node-api-headers`（间接依赖） | 1.9.0 |

实际终端为 zsh。依赖版本见成品的 `package.json` 和 `package-lock.json`。

## 工具准备的边界

本机最初缺少 CMake，系统安装需要交互式 sudo 密码。因此本次通过 apt 下载 Ubuntu 官方的 `cmake`、`cmake-data` 和所需共享库软件包，使用 `dpkg-deb -x` 解压到临时目录，再为验证进程设置 `PATH` 和 `LD_LIBRARY_PATH`。构建实际调用的仍是 Ubuntu 的 CMake 4.2.3。

没有修改系统包状态，也没有给用户安装全局 npm 工具。教程中的 `sudo apt-get update/install` 和可选 nvm 安装/切换属于环境准备指引，本次没有执行这些需要交互式权限或切换环境的步骤。之后在普通终端运行成品前，需要按教程第 1 节安装 CMake。

## 已完成的验证

### 1. 成品安装、编译与执行

在 `reference/` 安装依赖后，执行并通过：

```bash
npm test
npm start
npm run typecheck
npm ci
npm run clean
npm test
npm start
npm run typecheck
```

`npm ci` 成功按已交付锁文件重新安装；清理后能够从源码重新生成 CMake 构建目录、原生插件和 JS。

关键输出：

```text
[100%] Linking CXX shared library Release/addon.node
[100%] Built target addon
ℹ tests 8
ℹ pass 8
ℹ fail 0
add(2, 3) = 5
```

8 项集成测试覆盖正数、负数、零、小数、NaN/Infinity、两处参数的错误类型、缺少参数和多余参数。错误类型包含字符串、undefined、null、boolean、对象和 bigint。错误测试同时断言 JS 异常名称与消息。

### 2. 从教程代码块重建练习项目

在临时目录建立独立的学习仓库，预置教材和对照成品，但让 `practice/` 从不存在开始。按教程顺序提取并执行命令、创建文件，练习源码没有从 `reference/` 复制。

- 执行 `npm init -y`，再写入教程中的完整配置，执行 `npm install`。
- 从教程的 11 个文件代码块创建根目录忽略规则和 10 份项目文件，逐份核对与成品内容完全一致。
- 执行 22 个命令块，涵盖环境版本检查、构建、TS 类型检查、演示、测试、`npm ci`、清理、异目录启动、Git 和诊断命令。
- 跳过的三个命令块仅为 sudo 安装、可选 nvm 操作、可选 Git 身份占位配置；临时 Git 提交通过进程环境使用验证专用身份。
- 从第一次编译到 `npm ci` 重装、清理重建，各次测试均为 8 项通过、0 项失败。

### 3. 原生插件和加载路径

- `file` 确认构建产物为 x86-64 ELF 共享库。
- `nm -D` 确认产物具有 `napi_register_module_v1`、`node_api_module_get_api_version_v1` 和 C++ 加法函数符号。
- 从临时仓库根目录运行练习入口，以及从 `/tmp` 运行成品的绝对路径，均打印 `add(2, 3) = 5`。
- 在临时练习中暂时移走 `.node` 文件后，启动以 `MODULE_NOT_FOUND` 失败；恢复文件后可正常运行，确认没有 JS 降级替代实现。

### 4. Git 教学命令

只在临时验证仓库实际执行教程的四次提交，验证初始化、分阶段暂存、查看差异、提交和日志命令。历史顺序为：

```text
docs: add verified TypeScript to C++ lesson and reference
feat: call C++ add from TypeScript through Node-API
chore: initialize TypeScript native addon project
chore: initialize ffi learning repository
```

最终临时仓库工作区干净；`node_modules/`、`build/`、`dist/` 和 `.node` 产物均未进入版本历史。当前真实仓库只初始化到 `main`，没有代用户执行正式提交；用户的 `practice/` 保持未创建。

## 范围

这里只声明 Ubuntu/Linux x64、Node.js 24 下的实测结果。没有验证 macOS、Windows、其他 Node 主版本、其他 CPU 架构、Rust、异步调用或 npm 发布。

直接依赖已固定版本，成品锁文件也固定了间接依赖。首次手抄项目的 `npm install` 会在当时重新解析间接依赖；若要严格重现成品的依赖树，应在成品中使用 `npm ci`。
