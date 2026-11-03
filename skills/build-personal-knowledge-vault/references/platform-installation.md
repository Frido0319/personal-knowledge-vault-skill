# 平台安装

## 前置条件

- Python 3.11 或更新版本。
- 发布包内存在 `assets/runtime/personal_knowledge_vault-*.whl` 与 `assets/runtime/SHA256SUMS`。
- Vault 和 Data 必须位于 Skill 公共源码仓库之外。
- 标准模式不需要管理员权限；Windows Firewall hardened 模式例外且必须单独确认。

## 安装已校验 runtime

在 Skill 目录中先预览：

```bash
python scripts/install_runtime.py --preview
```

安装器只接受同目录 `SHA256SUMS` 中唯一匹配的内置 wheel。若当前 Python 环境已经提供兼容 PyYAML，可离线安装：

```bash
python scripts/install_runtime.py --apply
```

仅在用户同意从 Python package index 解析缺失依赖后使用：

```bash
python scripts/install_runtime.py --apply --allow-network
```

安装器不会升级已有环境；目标存在时停止。使用 `scripts/verify_install.py --target <venv>` 复验。Linux CLI 位于 `<venv>/bin/personal-vault`，Windows CLI 位于 `<venv>\Scripts\personal-vault.exe`。

## Linux

默认路径：

- Vault：`~/Documents/PersonalKnowledgeVault`
- Data：`~/.local/share/personal-vault`

示例：

```bash
personal-vault init --vault "$HOME/Documents/PersonalKnowledgeVault" --data "$HOME/.local/share/personal-vault" --language zh-CN --dry-run
personal-vault init --vault "$HOME/Documents/PersonalKnowledgeVault" --data "$HOME/.local/share/personal-vault" --language zh-CN
personal-vault schedule install --config "$HOME/.local/share/personal-vault/config/config.yaml" --preview
```

调度使用当前用户的 systemd user timer。没有可用 systemd user session 时，不静默改写 crontab；报告限制并保留手动更新命令。

## 原生 Windows 10/11

使用 Windows PowerShell 或 PowerShell 7，直接调用本机 Python；不要求 WSL，也不要创建 Ubuntu 依赖。

默认路径：

- Vault：`%USERPROFILE%\Documents\PersonalKnowledgeVault`
- Data：`%LOCALAPPDATA%\PersonalVault`

示例：

```powershell
personal-vault init --vault "$env:USERPROFILE\Documents\PersonalKnowledgeVault" --data "$env:LOCALAPPDATA\PersonalVault" --language zh-CN --dry-run
personal-vault init --vault "$env:USERPROFILE\Documents\PersonalKnowledgeVault" --data "$env:LOCALAPPDATA\PersonalVault" --language zh-CN
personal-vault schedule install --config "$env:LOCALAPPDATA\PersonalVault\config\config.yaml" --preview
```

调度使用当前用户 Task Scheduler，标准模式使用 `RunLevel Limited`。`platform/windows/Enable-PersonalVaultFirewall.ps1` 是可选 hardened 模式，需要管理员权限；对应 Disable 脚本必须一并保留以便回滚。

## 初始化后首个来源

```bash
personal-vault source add --config <config> --id projects --kind project --path <exact-path>
personal-vault source enable --config <config> --id projects --confirmation ENABLE:projects
personal-vault update --config <config> --preview
```

先检查预览，再使用 `update --apply`。不要把示例路径替换为自动发现出的目录。
