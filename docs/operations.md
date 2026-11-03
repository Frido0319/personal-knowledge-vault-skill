# 运维手册

## 日常知识更新

先预览，再应用：

```bash
personal-vault update --config <config> --preview
personal-vault update --config <config> --apply
personal-vault status --config <config> --format text
```

`update` 只处理已启用来源和生成页面，不改 runtime 代码、不下载依赖、不批准 `_staging`。相同输入的第二次运行应为零新增、零更新、零删除。

## 人工审核

AI 只生成符合 schema 的 JSON 提案。先执行 `stage add --dry-run`，再写入 `_staging`。阅读正文、来源、置信度和敏感级别后，逐条执行：

```bash
personal-vault review promote --config <config> --id <id> --confirmation PROMOTE:<id>
personal-vault review reject --config <config> --id <id> --confirmation REJECT:<id>
```

拒绝提案不删除原始来源。当前 runtime 没有“忘记来源”命令时，不用手工批量删除代替。

## schedule

Linux 安装 systemd user timer，Windows 安装当前用户 Task Scheduler。始终先看生成内容：

```bash
personal-vault schedule show --config <config>
personal-vault schedule install --config <config> --preview
personal-vault schedule install --config <config> --apply
```

任务只运行 `update --apply`。卸载前预览，再使用 `schedule remove --apply`。Windows 标准模式为 Limited，不需要管理员；Firewall hardened 脚本需要单独的管理员确认且必须保留 Disable 回滚脚本。

## 搜索与 QMD

内建搜索无需额外服务：

```bash
personal-vault search --config <config> --query <terms>
```

QMD 只索引正式 Markdown，不索引 `_raw` 或 `_staging`。QMD 不可用时保持内建搜索，不把检索 embedding 描述为知识提炼模型。

## Restic 备份

配置只保存 repository 和可执行文件，不保存密码。密码通过 `RESTIC_PASSWORD`、`RESTIC_PASSWORD_FILE` 或 `RESTIC_PASSWORD_COMMAND` 注入：

```bash
personal-vault backup restic --config <config> --preview
personal-vault backup restic --config <config> --apply
```

检查返回的 snapshot ID，并定期执行 Restic 官方 `check` 与恢复演练。GitHub `PRIVATE` 镜像不替代加密备份。

## 恢复

1. 恢复到新的临时目录，不覆盖当前 Vault。
2. 优先使用已验证 Restic snapshot；其次使用仍可证明 `PRIVATE` 的 GitHub 知识正本；最后从授权来源重新生成。
3. 对比文件 manifest、页面数和代表性 SHA-256。
4. 在临时 config 上运行 `doctor`、`status`、搜索和两次确定性更新。
5. 实际打开 Obsidian 与 localhost 控制台，确认无丢页、重复或布局错误。
6. 记录恢复证据后再切换正式路径，并保留旧路径到观察期结束。

## runtime upgrade

`upgrade` 与知识 `update` 分离。首版安装器拒绝覆盖已有 venv，因此升级采用并列环境：

1. 记录旧版本、wheel 哈希和 config 哈希，完成备份。
2. 校验新 release 的 `SHA256SUMS` 和 source commit。
3. 在新路径安装，运行合成验收及用户 config 的只读 `doctor/status`。
4. 明确确认后切换 CLI/调度入口。
5. 失败时切回旧 venv 和旧 config；不要原地 `pip install --upgrade`。

## 故障判定

- 核心失败：config/Vault 不可读、路径重叠、来源越界、生成页面校验失败。停止应用。
- 可选降级：QMD、Restic、GitHub 或浏览器不可用。保留本地 Vault，并明确标记未验证项。
- GitHub visibility 不是 `PRIVATE` 或未知：禁止上传。
- 调度命令失败：配置保持 `schedule.enabled: false`，不要把“模板已生成”写成“任务已安装”。
