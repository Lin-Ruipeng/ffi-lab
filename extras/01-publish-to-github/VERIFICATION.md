# 番外 01 验证记录

验证日期：2026-10-22（Asia/Singapore）。对应[番外教程](README.md)。

本记录将官方核对、只读检查、本地实测和未执行的线上操作分开。**没有在 GitHub 创建仓库或上传代码，不将本地 bare 仓库测试称为 GitHub 全流程实测。**

## 环境与只读检查

| 项目 | 检查结果 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS，Linux x64 |
| Shell | zsh |
| Git | 2.53.0 |
| GitHub CLI | 2.102.0（2026-09-30） |
| GitHub 登录状态 | 已登录个人账号，活跃账号使用 HTTPS |
| 正式仓库分支 | `main` |
| 正式仓库已有历史 | 两条本地学习提交，保留原样 |
| 正式仓库远端 | 验证开始时尚未配置，交付时保持不变 |

实际执行了 `gh --version`、`gh auth status --hostname github.com` 和 `gh config get git_protocol --host github.com`。未导出或记录认证 token。

本地帮助核对了 `gh repo create` 的 `--public`、`--private`、`--source`、`--remote`、`--push`，以及 `gh auth login`、`gh auth setup-git`、`gh repo view` 和 `gh repo edit --default-branch`。

## 官方资料核对

- [创建仓库](https://cli.github.com/manual/gh_repo_create)：从现有本地仓库创建远端，指定可见性、源目录、远端名，可选同时推送。
- [浏览器登录](https://cli.github.com/manual/gh_auth_login)：GitHub 主机、HTTPS 协议及浏览器授权参数。
- [配置 Git 凭据助手](https://cli.github.com/manual/gh_auth_setup-git)：让 Git 使用 GitHub CLI 作为凭据助手。
- [导入本地代码](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)：创建远端、避免额外初始化历史、添加远端与首次推送流程。
- [Git push](https://git-scm.com/docs/git-push)：推送分支和 `--set-upstream`。
- [修改默认分支](https://cli.github.com/manual/gh_repo_edit)：首次成功推送后，可将 GitHub 的默认展示分支设为 `main`。

官方核对用于确认命令含义，不等于已执行对应的 GitHub 写入操作。

## 本地场景实测

### 验证方法

在隔离临时目录从空文件夹初始化两个仓库：一个模拟已完成第一课的 `ffi-lab` 工作仓库，一个使用 `git init --bare -b main` 创建的本地远端。用验证专用作者身份创建临时提交。

测试夹具包含第一课的源码、配置、教材及根目录忽略规则，另准备依赖/构建产物占位文件和不打算公开的 `.vscode/` 设置。没有重新执行第一课的 C++ 构建，也没有更改真实 `practice/`。

从教程提取并按顺序复走了 16 个 Bash 命令块：

- 回到仓库根目录、检查分支/历史/工作区/远端。
- 使用教程明确列出的路径暂存教材，查看暂存差异并提交。
- 将可选 `git restore --staged` 示例中的占位路径替换为临时 `.vscode/settings.json`，验证撤销暂存保留本地文件。
- 检查真实 `gh` 版本。
- 将 **GitHub 创建远端这一个步骤** 替换为 `git remote add origin <本地 bare 路径>`；不伪造 `gh repo create` 的成功输出。
- 原样执行教程的 `git push -u origin main`、跟踪检查和两端哈希查询。
- 从教程的完整 Markdown 代码块创建学习笔记，按教程提交并执行普通 `git push`。

### 结果

| 场景 | 实测结果 |
| --- | --- |
| 首次推送 | 本地 `main` 成功推送到 bare 远端 `main` |
| upstream | 输出 `origin/main`，分支状态能显示跟踪关系 |
| 两端一致 | 首次推送和后续更新后，工作仓库与远端 `main` 哈希相同 |
| 后续更新 | 笔记提交后领先一个提交，普通 `git push` 成功同步，领先数量归零 |
| 忽略规则 | `node_modules/`、`build/`、`dist/` 和 `.node` 文件未进入远端文件树 |
| 未提交文件 | 即使执行成功的 push，未提交文件和未暂存的 `.vscode/` 设置仍只存在于本地 |
| 重复添加 origin | 报 `remote origin already exists`，原地址未被替换 |
| 推送失败恢复 | 暂时改为不存在的本地目标后推送失败；修复 URL 后可推送，无需重新创建 origin |
| 没有本地提交 | 独立空仓库推送失败，报 `src refspec main does not match any` |

关键输出形式：

```text
* [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
origin/main
```

实际传输地址为临时本地路径。所有断言均通过；本地远端最终包含教材、第一课文件和新增学习笔记，不含依赖、构建产物或未提交文件。

## 未执行的操作

- 未安装或升级系统 `gh`，因为当前工具已可用。
- 未重新执行浏览器登录、修改 `gh` 协议或凭据助手配置，因为本次只做只读检查和隔离验证。
- 未执行 GitHub 仓库创建、线上 push、默认分支修改、浏览器打开或删除仓库。
- 未实际制造 GitHub 同名仓库、权限不足、HTTPS 凭据失效等线上故障；对应教程说明依据官方文档及本机帮助。本地不可达目标的恢复测试不代表线上认证已实测。

正式发布时，仍需用户在自己的账号下完成教程的线上步骤，并按第 10 节验收。

## 文档与工作区检查

检查番外和入口文档的相对链接、代码围栏、Shell 语法、空白字符及章节顺序。核对正文主路线为“本地提交 → 创建远端 → 首次推送 → 验收 → 后续更新”，快捷写法与排错路径均明确为可选分支。

本次教材改动只有仓库首页、第一课末尾的番外链接，以及本目录的教程和验证记录。真实仓库的 HEAD、暂存区和远端配置与开始时一致。用户同时继续编写了 `practice/` 内容；这些进度没有被覆盖，本次没有向真实练习文件写入。教材提交命令交给用户执行。
