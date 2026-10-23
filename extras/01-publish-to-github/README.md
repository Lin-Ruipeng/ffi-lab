# 番外 01：用 GitHub CLI 把本地仓库发布到 GitHub

完成[第一课](../../01-ts-cpp-node-api/README.md)之后，你已经有一个带提交历史的本地 `ffi-lab` 仓库。这篇教程从 **GitHub 上还没有远端仓库** 开始，用命令行创建公开仓库并上传本地历史，之后再练习更新。

全文使用 Ubuntu/Linux、个人 GitHub 账号、HTTPS、`main` 分支、`origin` 远端名。默认上传整个 `ffi-lab`，包含各课教材、成品和你已经提交的练习。

**验证范围：** Git 流程已在临时本地远端实测；GitHub CLI 参数已核对本机帮助和官方文档。本次没有创建 GitHub 仓库或进行线上推送，线上步骤由你操作。[详细验证记录](VERIFICATION.md)

## 0. 先理解：这次到底要完成哪几件事

```text
本地文件
   │ git add：选择要记录的文件
   ▼
暂存区
   │ git commit：形成一次本地历史
   ▼
本地 main 分支
   │ git push：发送提交和分支
   ▼
GitHub 上的 main 分支
```

`gh repo create` 负责在 GitHub 创建仓库，并可为本地仓库添加远端地址。`git push` 负责把提交发送过去。这是两个阶段，主教程将它们拆开；第 8 节再给出合并操作的快捷写法。

| 名称 | 含义 |
| --- | --- |
| Git | 本地版本管理工具，第一课已经使用 |
| GitHub | 托管远端 Git 仓库的网站 |
| `gh` | GitHub CLI，可从终端登录账号、创建和查看 GitHub 仓库 |
| `origin` | 本地为一个远端地址起的名字，惯例叫这个；不是分支名 |
| `main` | 本课的本地分支名，也是准备推送的远端分支名 |
| `origin/main` | 本地记录的远端 `main` 分支状态，不是另一个目录 |
| upstream | 本地分支默认跟踪的远端分支，这里会设置为 `origin/main` |

**上传的是已经提交的历史。** 尚未 `git add` 或 `git commit` 的文件不会因为执行了创建仓库或推送命令而自动上传。第一次推送会发送 `main` 可到达的历史提交，不只发送最后一次修改。

这次选择公开仓库：提交的文件和历史可被其他人查看。提交前要确认暂存区都是你打算公开的内容；账号登录信息不应写进教材或仓库文件。

## 1. 回到整个学习仓库的根目录

**工作目录：`ffi-lab` 根目录。** 如果你还在第一课的 `practice/` 中，先执行：

```bash
cd ../..
```

若终端在其他位置，请先用 `cd` 进入你自己的仓库路径，例如当前机器可以执行 `cd /home/folin/文档/Code/ffi-lab`。后续命令都相对于仓库根目录，不要求 clone 到固定位置。

确认目录与历史：

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
git log --oneline -4
git status --short --branch
git remote -v
```

成功标志：

- `pwd` 与 `git rev-parse --show-toplevel` 指向同一个 `ffi-lab` 目录。
- 当前分支是 `main`，`git log` 至少显示一条提交；条数、提交哈希随你的练习进度变化。
- 首次发布前，`git remote -v` 没有输出，表示尚未配置远端。

这里不需要重新 `git init`，也不需要在 `practice/` 新建 Git 仓库。如果分支不是 `main`，先确认当前进度及 `git branch --list`，不要把不确定的分支直接推送；本文从第一课的 `main` 继续。

若还没有完成第一课的实现和测试，请先完成。只有本地仓库并不要求已经构建过才能上传，但本番外以“第一课已完成”为练习起点。

## 2. 把准备公开的文件记录进本地历史

**工作目录：仓库根目录。**

```bash
git status --short --untracked-files=all
git diff --stat
git diff
git diff --cached --stat
```

`??` 表示未跟踪文件；`git diff` 显示已跟踪文件尚未暂存的修改，不会展示所有未跟踪文件的正文。新文件要自己打开阅读，稍后暂存后也能用 `git diff --cached` 检查。

第一课的源码、测试和配置应已按原教程提交。这次为教材更新做一次独立提交，路径明确列出：

```bash
git add .gitignore AGENTS.md README.md 01-ts-cpp-node-api/README.md 01-ts-cpp-node-api/VERIFICATION.md 01-ts-cpp-node-api/reference extras/01-publish-to-github
git diff --cached --stat
git diff --cached
git diff --cached --check
```

这会暂存仓库共享约定、教材、对照成品与番外，不自动暂存你的其他练习修改或 `.vscode/` 设置。当前仓库有 `AGENTS.md`；若你在别的仓库复用命令，应按实际文件路径调整列表。

查看暂存文件清单：

```bash
git diff --cached --name-only
```

应包含你本次想发布的教材文件；不应包含 `node_modules/`、`build/`、`dist/` 或 `.node` 二进制。根目录 `.gitignore` 已覆盖这些产物。

如果发现暂存区还包含其他实验的内容，可以只撤销对应文件的暂存，保留工作区文件。下面的 `path/to/file` 需要替换为实际路径：

```bash
git restore --staged -- path/to/file
```

确认暂存区后提交：

```bash
git commit -m "docs: prepare ffi lab tutorials for GitHub publication"
git log -1 --oneline
git status --short --branch
```

若提示 `nothing to commit`，而这些文件已经在历史中，直接继续。若仍有打算上传的未提交练习，先返回第一课第 10 节，用它的明确路径命令提交，再继续本篇。

本机专用且未提交的文件可以留在工作区；它们不会被推送。关键是所有 **你打算发布的文件** 已经进入提交。`git status` 的 `?? .vscode/` 不等于发布失败。

## 3. 检查 GitHub CLI 并完成 HTTPS 登录

### 3.1 检查安装

**工作目录：仓库根目录；安装和登录本身不依赖这个目录。**

```bash
gh --version
```

本机检查时输出首行为：

```text
gh version 2.102.0 (2026-09-30)
```

版本可能变化。已有 `gh` 就继续；如果提示找不到命令，可以通过 Ubuntu 软件源安装：

```bash
sudo apt-get update
sudo apt-get install -y gh
gh --version
```

Ubuntu 软件源的版本可能早于实测版本。可以用 `gh repo create --help` 确认支持后文参数；这些参数已在本机 `2.102.0` 核对。

### 3.2 确认登录账号

```bash
gh auth status --hostname github.com
```

找到当前活跃账号与 Git 协议。输出示意如下，`YOUR-LOGIN` 表示你的 GitHub 用户名，不是让你原样输入：

```text
github.com
  ✓ Logged in to github.com account YOUR-LOGIN (...)
  - Active account: true
  - Git operations protocol: https
```

实际输出可能还包含凭据信息，不必复制到学习笔记。本机已经登录并使用 HTTPS，可以跳过下面的登录命令。

**仅在尚未登录或需要重新认证时执行：**

```bash
gh auth login --hostname github.com --git-protocol https --web
```

这三个参数分别选择 `github.com`、Git 操作的 HTTPS 协议、浏览器授权流程。按终端提示复制一次性验证码，在浏览器登录你自己的 GitHub 账号并授权；若询问是否使用 GitHub 凭据认证 Git，选择 `Y`。授权完成后，再运行 `gh auth status --hostname github.com` 确认成功。[登录命令官方说明](https://cli.github.com/manual/gh_auth_login)

如果已登录但协议显示 `ssh`，本篇统一切换为 HTTPS：

```bash
gh config set git_protocol https --host github.com
gh config get git_protocol --host github.com
```

最后一条应输出 `https`。这影响 `gh` 之后生成的 Git 远端 URL，不会自动改写已经存在的 SSH 远端；已有远端的处理见第 9 节。

### 3.3 让 Git 使用 gh 的登录凭据

```bash
gh auth setup-git --hostname github.com
```

这是配置步骤：让 Git 的 HTTPS 认证可以通过 `gh` 获取凭据，避免出现“`gh` 已登录，但 `git push` 仍然索要认证”的情况。成功时可能没有输出。它会调整当前用户的 Git 凭据助手配置，不是向仓库添加一个文件。[官方说明](https://cli.github.com/manual/gh_auth_setup-git)

`git config user.name/user.email` 记录提交作者；`gh auth login` 负责登录 GitHub。二者作用不同，第一课设置了 Git 作者身份，并不等于已经登录 GitHub。

## 4. 在 GitHub 上创建一个全新的公开仓库

**工作目录：仓库根目录。创建前再检查：**

```bash
git branch --show-current
git log -1 --oneline
git remote -v
```

当前应是 `main`，至少有一条提交，且没有远端。若 `origin` 已存在，先按第 9 节核对状态，不要重复走“首次创建”。

执行：

```bash
gh repo create ffi-lab --public --source=. --remote=origin
```

参数逐个拆开看：

| 部分 | 含义 |
| --- | --- |
| `gh repo create` | 在 GitHub 创建远端仓库 |
| `ffi-lab` | GitHub 仓库名；不写 `OWNER/` 时，归属当前活跃登录账号 |
| `--public` | 创建公开仓库；想私有时在创建前改成 `--private`，二者选一个 |
| `--source=.` | 使用当前目录的现有 Git 仓库作为本地源 |
| `--remote=origin` | 在本地添加名为 `origin` 的远端，指向刚创建的仓库 |

它会创建类似 `https://github.com/YOUR-LOGIN/ffi-lab` 的仓库，并为本地添加远端。输出内容可能随版本变化，通常包含仓库地址和添加远端的成功提示。本步没有使用 `--push`，所以提交还没有上传。[创建命令官方说明](https://cli.github.com/manual/gh_repo_create)

你不必先打开 GitHub 网页手动创建仓库，也不必先 clone 一遍。这里已有本地 README、忽略规则和历史，因此不传 `--add-readme`、`--gitignore` 或 `--license`，避免再生成一份远端初始历史。[GitHub 官方导入指引](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

立即核对地址：

```bash
git remote -v
```

预期形式：

```text
origin  https://github.com/YOUR-LOGIN/ffi-lab.git (fetch)
origin  https://github.com/YOUR-LOGIN/ffi-lab.git (push)
```

用户名替换为你自己的；URL 的 `.git` 后缀可能被省略，均可正常用于 Git。`fetch` 和 `push` 两行是同一个远端的读取与推送地址，不是创建了两份仓库。确认地址属于你准备发布的账号和仓库。

## 5. 首次推送 main，并设置跟踪关系

**工作目录：仓库根目录。**

```bash
git push -u origin main
```

- `push`：把本地提交和分支发送给远端。
- `origin`：使用上一节添加的远端地址。
- `main`：将本地 `main` 推送为远端的 `main`。
- `-u`，即 `--set-upstream`：推送成功后，让本地 `main` 跟踪 `origin/main`，为后续普通 `git push` 建立默认关系。

日志中的对象数量、进度和提交哈希会变化，关键成功信息类似：

```text
To https://github.com/YOUR-LOGIN/ffi-lab.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

本次是把 `main` 的提交历史推送到 GitHub；目录里的课程源码、教材和练习，只要在这些提交中都会跟随上传，不需要分别给每一课创建远端。其他分支和标签不在本次显式推送范围内。[Git push 官方说明](https://git-scm.com/docs/git-push)

## 6. 确认第一次发布成功

### 6.1 检查本地跟踪关系

```bash
git branch -vv
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git status --short --branch
```

`git branch -vv` 中 `main` 附近应显示 `[origin/main]`。第二条应输出：

```text
origin/main
```

第三条的分支行应类似 `## main...origin/main`，刚推送的提交不会再显示为 `ahead`。未提交的文件仍可能列在下面，它们不会因为 push 而消失。

如果要进一步核对两端提交：

```bash
git rev-parse main
git ls-remote origin refs/heads/main
```

第一条是一行本地 `main` 的完整提交哈希；第二条是一行远端哈希及 `refs/heads/main`。在没有其他人同时更新远端的情况下，两边哈希应相同。

### 6.2 查看 GitHub 仓库元信息

```bash
gh repo view --json nameWithOwner,visibility,url,defaultBranchRef
```

应能看到自己的 `YOUR-LOGIN/ffi-lab`、`"visibility": "PUBLIC"` 和仓库 URL。`defaultBranchRef.name` 应为 `main`。输出字段顺序不固定。

账号的新仓库默认分支设置可能不同。若远端默认分支不是 `main`，在已经成功推送 `main` 后执行：

```bash
gh repo edit --default-branch main
gh repo view --json defaultBranchRef
```

这一步只对齐 GitHub 仓库的默认展示分支，不会重写本地提交。[默认分支命令说明](https://cli.github.com/manual/gh_repo_edit)

### 6.3 打开网页检查文件

```bash
gh repo view --web
```

浏览器中确认仓库是公开的，能看到仓库首页、第一课、番外及你已提交的 `practice/`。打开提交历史，能找到第一课的学习提交和本篇的教材提交。

若某个文件夹没有显示，先看它是否含有已提交文件。Git 不单独记录空目录；依赖和构建产物不显示是预期行为。

## 7. 以后新增学习记录，如何继续上传

**工作目录：仓库根目录。** 不需要再次创建远端。下面做一个小练习：在 `extras/01-publish-to-github/LEARNING-NOTES.md` 创建自己的发布笔记，完整内容如下：

<!-- file: extras/01-publish-to-github/LEARNING-NOTES.md -->
```markdown
# GitHub 发布学习笔记

- Git 保存本地提交，GitHub 托管远端仓库。
- origin 是远端地址的本地名称，main 是分支名。
- 更新顺序：检查修改 → git add → git commit → git push。
```

新文件不会被普通 `git diff` 展示，所以也要检查未跟踪状态：

```bash
git status --short
git diff
git add extras/01-publish-to-github/LEARNING-NOTES.md
git diff --cached --stat
git diff --cached
git diff --cached --check
git commit -m "docs: record GitHub publication learning notes"
git log -1 --oneline
git status --short --branch
```

此时分支状态通常会显示 `ahead 1`，表示本地领先远端一个提交。再执行：

```bash
git push
git status --short --branch
```

由于首次推送已经设置 upstream，这次无需重复写 `-u origin main`。推送成功后，`ahead 1` 消失。网页刷新后应能看到新笔记。如果原先已有这个笔记文件，先补上一条自己的心得，再按相同流程提交。

后续增添新课程也按这个流程：先检查和提交明确路径，再推送。一次只提交一个有明确含义的学习里程碑。

## 8. 理解流程后，再看首次发布的快捷写法

**这是第 4、5 节的替代路线，不是做完它们后再执行的一步。** 仅在远端还没有创建、`origin` 尚不存在且本地已有提交时使用：

```bash
gh repo create ffi-lab --public --source=. --remote=origin --push
```

新增的 `--push` 要求 `gh` 在创建远端和添加远端地址后，继续推送本地提交。执行前仍要完成登录、检查分支及本地提交；它不会替你 `git add` 或 `git commit`。完成后仍按第 6 节验收。

为明确后续普通 `git push` 的跟踪关系，也可以再执行一次：

```bash
git push -u origin main
```

若提交已经上传，会提示 `Everything up-to-date`，并建立或确认 upstream。若创建后推送失败，使用下一节恢复，不要重复创建同名仓库。

## 9. 常见问题与恢复步骤

所有命令仍在仓库根目录。下面各小节按你遇到的问题选择，不需要顺序全部执行。

### 9.1 没有登录，或没有仓库创建权限

先执行：

```bash
gh auth status --hostname github.com
```

确认活跃账号是你想使用的个人账号。未登录或凭据失效时，重新走第 3 节的浏览器授权；不要用 Git 的 `user.name` 判断登录账号。若是组织权限报错，本篇的默认路线不填写组织前缀，只创建到个人账号。

### 9.2 提示没有提交，或 src refspec main does not match any

```bash
git log -1 --oneline
git branch --show-current
```

没有提交时先完成第一课和本篇第 2 节的本地提交。若实际分支不是 `main`，确认是否回到了正确仓库、是否还在第一课使用的分支，先解决分支不一致再推送。

### 9.3 GitHub 页面上缺少本地文件

```bash
git status --short --untracked-files=all
git ls-files
```

`git ls-files` 列出索引里记录的路径，还应结合 `git status` 判断有没有只暂存却未提交的文件。若文件仍为 `??`，或者已经暂存但没有提交，先按第 7 节的流程选择实际路径、提交并推送。被忽略的构建产物不用上传。

### 9.4 提示同名仓库已经存在

如果第 4 节执行过，即使随后推送失败，远端仓库也可能已经成功创建。先把 `YOUR-LOGIN` 换成刚才活跃账号的真实用户名，再检查：

```bash
gh repo view YOUR-LOGIN/ffi-lab --json nameWithOwner,url,isEmpty
git remote -v
```

若这是你刚创建的目标仓库，接着用下一节的方法连接并推送；不必再次创建。如果同名仓库是另一个项目，希望保持独立，可以在尚未配置远端的本地仓库中改用一个新名字，例如：

```bash
gh repo create ffi-lab-learning --public --source=. --remote=origin
git push -u origin main
```

此时远端仓库名变为 `ffi-lab-learning`，本地文件夹仍可叫 `ffi-lab`。

### 9.5 origin 已存在，或创建成功后添加远端/推送失败

先检查：

```bash
git remote -v
```

分情况处理，下面 URL 中的 `YOUR-LOGIN` 必须替换为你实际使用的 GitHub 用户名；若改过仓库名也要一起替换：

- **`origin` 正好指向目标仓库：** 远端创建步骤已经完成，直接 `git push -u origin main`。
- **目标 GitHub 仓库已创建，但本地没有 `origin`：** 只补上远端地址：

```bash
git remote add origin https://github.com/YOUR-LOGIN/ffi-lab.git
git remote -v
git push -u origin main
```

- **`origin` 指向另一个仓库，或仍是 SSH 地址：** 在确认本地仓库确实应该发布到这个目标后，更新地址，再推送：

```bash
git remote set-url origin https://github.com/YOUR-LOGIN/ffi-lab.git
git remote -v
git push -u origin main
```

`set-url` 修改的是本地远端配置，不会重命名或删除 GitHub 上的旧仓库。创建成功但认证或网络导致推送失败时，修复问题后重复 `git push` 即可。

### 9.6 gh 已登录，但 git push 仍认证失败

```bash
gh auth status --hostname github.com
gh config get git_protocol --host github.com
git remote get-url origin
```

检查活跃账号是否正确、远端是否为该账号有权写入的 HTTPS 仓库。再执行 `gh auth setup-git --hostname github.com` 后重试推送；凭据确实失效时，重新走浏览器登录。GitHub 的 HTTPS Git 操作不使用账号密码作为普通 Git 密码，本文通过 `gh` 的授权凭据完成认证。

如果报错是 `Could not resolve host`、连接超时或 TLS 连接失败，那是网络连接问题；恢复 GitHub 可达后重试，不用重新创建仓库。

### 9.7 推送被拒绝：远端已有不在本地的提交

如果出现 `non-fast-forward` 或 `fetch first`，先确认 `origin` 没有误指向别的项目，再查看分歧：

```bash
git remote -v
git fetch origin
git log --oneline --graph --decorate --all -12
```

本篇创建的是空远端，正常首次推送不需要合并历史。若你曾在网页初始化 README，或别人已经修改了仓库，就需要先决定如何保留两边历史，再进行合并或变基；遇到这种情况先停在检查结果，不用强推覆盖远端。本文不把有分歧的历史当作全新远端继续操作。

## 10. 最终验收

回到仓库根目录检查：

```bash
git remote -v
git branch -vv
git status --short --branch
git rev-parse main
git ls-remote origin refs/heads/main
gh repo view --json nameWithOwner,visibility,url,defaultBranchRef
```

逐项确认：

- [ ] 远端归属正确的个人账号，仓库名是你选择的名字，公开可见。
- [ ] `origin` 使用正确的 HTTPS 地址。
- [ ] 本地 `main` 跟踪 `origin/main`；准备发布的提交没有剩余 `ahead`。
- [ ] 本地 `main` 与远端 `main` 的哈希一致。
- [ ] 网页能看到教材、已提交的第一课练习与提交历史；GitHub 默认展示 `main`。
- [ ] 第 7 节笔记经过一次普通 `git push` 后，也能在网页看到。
- [ ] 依赖和构建产物没有进入提交，剩余工作区文件都是你明确还不打算发布的内容。

完成这些检查后，后续学习只需要继续在本地按课程组织文件、提交学习进度，再用 `git push` 同步到这个仓库。
