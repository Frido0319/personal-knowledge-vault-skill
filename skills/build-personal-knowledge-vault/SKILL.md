---
name: build-personal-knowledge-vault
description: Build, migrate, audit, or maintain a private Obsidian-compatible personal knowledge vault on Linux or native Windows. Use for local-first knowledge bases that distill explicitly authorized projects, learning materials, documents, AI history exports, or authored GitHub Skills into readable layered notes with human review, search, backups, and an optional private GitHub mirror.
---

# 构建个人知识库

把任务当作个人本地知识产品交付，不扩展为企业权限平台。先读取 [隐私边界](references/privacy-boundary.md)；涉及安装时读取 [平台安装](references/platform-installation.md)，涉及自动更新、升级或恢复时读取 [更新与恢复](references/update-and-recovery.md)，交付前逐项执行 [验收清单](references/acceptance-checklist.md)。

## 硬门禁

- 只处理用户逐项给出的精确路径或仓库。执行“禁止自动扫描”：不得枚举整个磁盘、Home、浏览器、凭据目录、钱包、SSH/GPG 或聊天软件内部数据目录。
- 把 Vault、Data、缓存、备份和凭据放在公共 Skill 源码仓库之外；发现重叠就停止。
- 对 `agent_history`、WeFlow/微信和 QQ 导出执行二次显式授权。不要自行寻找聊天记录；默认关闭 WeFlow/QQ。
- 只在预览后写入。AI 提炼结果先写入 `_staging`，逐条人工审核后才能进入 `knowledge/` 或 `synthesis/`。
- 支持 Linux 与原生 Windows，不要求 WSL，也不得把 Windows 强制改造成 Ubuntu。
- 不默认安装本地大模型。内建全文搜索始终可用；QMD、Restic 和 GitHub 均为可选集成。
- 严格区分 `update` 与 `upgrade`：前者只更新知识，后者才更换运行时代码。
- GitHub 知识镜像必须为 `PRIVATE`；无法证明可见性时停止发布。

## 工作流

1. **盘点而不读取。** 确认操作系统、Python 版本、目标 Vault/Data 路径和用户希望纳入的来源类别。只展示拟执行操作，不探测其他目录。
2. **安装运行时。** 从发布的 `.skill` 中运行 `scripts/install_runtime.py --preview`；展示目标 venv、wheel 哈希和是否需要联网。获得明确同意后才使用 `--apply`；仅在用户同意依赖联网时加 `--allow-network`。安装后运行 `scripts/verify_install.py`。
3. **初始化空库。** 先运行 `personal-vault init ... --dry-run`，确认路径位于源码仓库外，再运行正式初始化。默认语言使用用户语言；中文用户选择 `zh-CN`。
4. **逐项授权来源。** 对每个用户指定路径执行 `source add`，检查 ID、类型和绝对路径，再用准确确认串启用。普通来源使用 `ENABLE:<id>`；敏感导出使用 `AUTHORIZE:<id>:<kind>`。
5. **生成可读知识骨架。** 先执行 `update --preview`，向用户解释新增、变化和跳过项，再执行 `update --apply`。确认首页和 L0-L3 主图突出领域、主线和项目，L4-L5 仅在局部导航与来源证据中展开。
6. **整理语义知识。** 只从本次授权的导出或 delta 生成符合仓库 schema 的提案。先执行 `stage add --dry-run`，再写入 `_staging`；展示来源、敏感级别和置信度，要求逐条 `PROMOTE:<id>` 或 `REJECT:<id>`。
7. **启用可选能力。** 仅在用户明确要求后配置 QMD、Restic 或私有 GitHub 镜像。执行 GitHub 发布前、push 前和 push 后都验证 `PRIVATE`，知识证据链接固定到 commit SHA。
8. **配置维护。** 先用 `schedule show` 或 `schedule install --preview` 展示原生任务，再执行安装。每日任务只运行确定性 `update --apply`，不得静默升级软件或自动批准 staging。
9. **验收交付。** 运行状态、搜索、幂等、审核、恢复和隐私检查；实际打开 localhost 控制台检查桌面与移动布局。报告精确路径、已授权来源、可选集成状态、备份证据和仍未验证的边界。

## 命令入口

- 使用 [安装脚本](scripts/install_runtime.py) 校验并安装随 Skill 打包的 runtime wheel。
- 使用 [验证脚本](scripts/verify_install.py) 检查隔离环境、CLI 和可选配置。
- 以 `personal-vault --help` 为实际命令真相；不要凭空构造未提供的迁移、删除或任意 shell 操作。
- 任何需要管理员权限、联网、创建 GitHub 仓库、上传、删除或覆盖的动作，都先说明影响并取得对应确认。
