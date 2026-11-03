# 更新、升级与恢复

## 知识更新

`update` 只读取已启用来源，生成确定性页面和 manifest；不下载代码、不安装包、不批准 `_staging`。每日任务只运行：

```text
personal-vault update --config <config> --apply
```

人工页面和没有匹配 `generated_by` 标记的文件不得覆盖。同一输入连续运行两次时，第二次应报告零新增和零变化。

## 语义提炼

代理从用户本次授权的导出或 delta 生成 JSON 提案。每条包含 `id`、`title`、`summary`、`body`、`knowledge_type`、`target`、`source_refs`、`confidence` 和 `sensitivity`。执行顺序：

1. 用仓库 schema 校验并脱敏。
2. `stage add --dry-run` 预览。
3. `stage add` 写入 `_staging`。
4. 人工阅读来源、正文和敏感级别。
5. 使用 `PROMOTE:<id>` 或 `REJECT:<id>` 完成逐条决定。

拒绝提案不等于删除来源。“忘记来源”必须作为独立高风险动作设计，当前 runtime 不提供该命令时不得用手工批量删除代替。

## 软件升级

不要用 `update` 升级 runtime。升级时依次执行：

1. 记录当前版本、wheel SHA-256、配置和最近成功状态。
2. 创建并验证加密备份。
3. 从官方 release 获取新 `.skill` 或 wheel，校验 `SHA256SUMS`。
4. 阅读 release notes，预览配置迁移与文件变化。
5. 获得明确升级确认后，在新的临时 venv 安装并运行验收。
6. 切换入口；失败时恢复旧 venv 和旧配置。

首版安装器拒绝覆盖现有目标，因而升级应采用并列 venv 和显式切换，不得原地 `pip install --upgrade`。

## 备份与恢复顺序

推荐恢复优先级：

1. 已验证的 Restic 加密快照。
2. 已证明仍为 `PRIVATE` 的 GitHub 知识正本。
3. 从仍存在的授权来源重新执行确定性生成。

恢复到临时目录，先比较 manifest 和页面数，再切换正式路径。不得直接把未验证快照覆盖到现有 Vault。恢复后运行 `doctor`、`status`、代表性搜索、二次幂等更新和 localhost UI 检查。

## 故障边界

- 核心 Vault 不依赖 QMD、Restic、GitHub 或本地大模型；可选工具失败时报告降级，不破坏已验证 Vault。
- GitHub 可见性无法确认时停止上传，但本地 Vault 仍可使用。
- 索引失败时保留旧索引；备份失败时不得把状态写成成功。
- 调度失败时保持 `schedule.enabled: false`，并给出原生命令和错误类别。
