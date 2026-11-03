# Personal Knowledge Vault Skill 设计规格

## 1. 目标

`build-personal-knowledge-vault` 把已经验证过的 Personal Brain 方法整理成一个可公开复用的 Skill：代理在 Linux 或原生 Windows 上，引导单个用户建立私密、可读、可审计、可持续更新的 Obsidian Markdown 知识库。

首个版本服务个人使用，不实现企业权限、多人审批、组织级 SSO 或中心化服务。它必须形成真实可运行的产品闭环，而不是只输出一份建议文档。

## 2. 可验收用户成果

一次完整部署后，用户应得到：

1. 一个仓库外的 Obsidian Vault，包含首页、L0-L5 分层知识地图、项目、学习资料、文档、Skills、知识条目和来源证据。
2. 一个只监听 `127.0.0.1` 的中英双语管理控制台，可查看状态、授权来源、更新预览、待审核知识、搜索、备份和私有 GitHub 状态。
3. 一套显式来源授权配置；默认只处理用户逐项选择的项目、学习资料、文档和 GitHub Skills。
4. 每日确定性更新和每周/按需 AI 语义整理；AI 结果先进入 `_staging`，经人工批准才进入正式知识层。
5. 可选 QMD 本地索引、Restic 加密备份和 GitHub 私有镜像。没有这些工具时，核心 Vault 和内建搜索仍可使用。
6. 可重复安装、更新、恢复和审计的证据；同一输入重复运行不产生重复页面。

## 3. 明确边界

### 3.1 默认允许

- 用户逐项指定的项目目录、学习资料目录和文档目录。
- 用户逐项指定的本地或 GitHub Skill 仓库。
- 用户二次授权后显式提供的 Codex/Claude 导出文件。
- 用户单独启用后显式提供的 WeFlow/微信导出和 QQ Chat Exporter 导出。

### 3.2 永不自动扫描

- 整块磁盘、整个 Home、浏览器 Profile/历史/Cookie。
- 钱包、SSH/GPG 目录、系统凭据库、密码管理器。
- 微信、QQ 或其他聊天软件的内部数据目录。
- `.env`、token、私钥、认证缓存和未知符号链接目标。

### 3.3 不做的事情

- 不默认安装或常驻运行通用本地大模型。
- 不把 QMD 的检索模型宣传成知识提炼模型。
- 不让 GitHub 私有镜像替代本地加密备份。
- 不让软件升级与知识更新共享一个命令。
- 不把 CI 通过等同于用户真实数据导入、真实 Windows 桌面或科学结论。

## 4. 架构

公开仓库是单一源代码树：

```text
personal-knowledge-vault-skill/
├── src/personal_vault/                 # 跨平台运行时唯一源码
├── skills/build-personal-knowledge-vault/
│   ├── SKILL.md                        # 代理工作流入口
│   ├── agents/openai.yaml
│   ├── scripts/                        # 安装/验收入口
│   ├── references/                     # 隐私、平台、运维参考
│   └── assets/config-templates/         # 合成配置模板
├── platform/linux/                     # systemd user 模板
├── platform/windows/                   # PowerShell/Task Scheduler 模板
├── tests/                              # 仅合成夹具
└── dist/                               # 构建产物，不作为运行时源码
```

发布时从同一个 commit 构建 Python wheel，再把该 wheel 注入 `.skill` 包。Skill 不复制第二套运行时源码，也不内置 Obsidian、QMD、Restic、Git 或 GGUF 模型。

用户数据布局默认位于仓库外：

```text
Vault/
├── 00-首页.md
├── map/ projects/ learning/ documents/ skills/
├── knowledge/ synthesis/ references/
├── _staging/                           # 待人工审核，不进入正式图谱
├── _raw/                               # 明确导入的原始证据，默认隐藏
└── .obsidian/

Data/
├── config/config.yaml
├── state/manifest.sqlite
├── state/*.json
├── audit/*.jsonl
├── backups/
├── qmd/
└── github/
```

## 5. 核心状态机

### 5.1 确定性更新

`preview -> apply -> validate -> index -> backup -> report`

- `preview` 只读授权源，计算内容哈希和差异，不创建 Vault、数据库或日志。
- `apply` 只写带 `generated_by` 标记的页面，使用临时文件加原子替换。
- 手工页面和无匹配生成器标记的文件永不覆盖。
- manifest 以来源 ID、相对路径和内容哈希保证幂等。
- 任一步失败时保留上一个已验证 Vault；索引和镜像使用 staging 后切换。

### 5.2 语义知识整理

`explicit export -> redact -> agent distill -> stage -> human review -> promote/reject`

- 代理只读取用户本次明确提供的导出或 delta。
- 提案必须包含标题、摘要、正文、知识类型、来源引用、置信度和敏感性。
- `_staging` 页面不计入正式知识图谱和默认检索集合。
- `promote` 需要预览和确认字符串；批准后写入 `knowledge/` 或 `synthesis/`，并记录审批账本。
- 拒绝只删除 staging 提案，不删除原始来源；“忘记来源”是独立且更严格的流程。

## 6. 知识模型与人类可读性

- L0：个人知识库总入口。
- L1：领域，例如研究、工程、学习、个人工具。
- L2：长期主线。
- L3：项目、课程、Skill 或稳定主题。
- L4：项目内主题、阶段成果和操作知识。
- L5：来源证据、文件哈希和导出片段。

全局首页和图谱只突出 L0-L3；L4 在局部导航出现；L5 默认隐藏但可追溯。项目页至少显示“用途、当前状态、已确认成果、下一步、关键资料、本机路径、GitHub 固定链接”。会话原文不直接作为首页节点。

## 7. CLI 与本地控制台

命令入口为 `personal-vault`：

```text
init                 初始化仓库外 Vault/Data
source add/list/...  管理显式授权来源
update --preview     只读差异预览
update --apply       应用确定性更新
stage add/list       导入代理生成的知识提案
review promote/reject
search               内建离线全文搜索
status               输出 text/json 状态
github prepare/publish
index qmd             可选 QMD 更新
backup restic         可选 Restic 备份
schedule install      安装每日任务
serve                 启动 localhost 控制台
doctor                检查平台、权限和可选依赖
```

控制台使用标准库 HTTP 服务和静态 HTML/CSS/JS，不提供任意命令执行端点。所有写操作要求 CSRF、preview 和确认。界面首屏直接呈现知识规模、来源覆盖、待审核项、最近更新和保护状态，并提供来源、审核、搜索、维护四个工作视图。

## 8. 跨平台策略

### Linux

- Python 3.11+；安装到隔离 venv 或 `pipx/uv tool`。
- 默认路径使用 `~/Documents/PersonalKnowledgeVault` 与 `~/.local/share/personal-vault`。
- 自动化使用 systemd user units；没有 systemd 时输出可审计 cron 建议但不静默写入。
- 标准模式无需 root。

### 原生 Windows 10/11

- Python 3.11+ 与 Windows PowerShell 5.1+；不要求 WSL。
- 默认路径使用 `%USERPROFILE%\Documents\PersonalKnowledgeVault` 与 `%LOCALAPPDATA%\PersonalVault`。
- 自动化使用当前用户 Task Scheduler。
- 标准模式只绑定回环地址、使用应用级边界，无需管理员。
- 可选 hardened 模式在明确同意后生成可逆 Windows Firewall 规则；执行需要管理员。

路径、调度器和命令生成必须通过 Linux 与 `windows-latest` CI 的原生测试。

## 9. GitHub 与隐私

- 公共 Skill 仓库使用 MIT License。
- 每个用户的知识仓库默认创建为 `PRIVATE`。
- `publish` 在准备、push 前和 push 后都用 GitHub CLI/API 验证 `PRIVATE`；状态不明即停止。
- 发布前拒绝越界符号链接、密钥模式、`.env`、凭据目录和超限文件，并生成逐文件 SHA-256 manifest。
- 永久链接固定到 commit SHA，不使用漂移的 `main` 链接作为证据地址。
- 用户未登录 `gh` 或未同意联网时，仅保留本地 Vault，不视为失败。

## 10. 更新、升级与恢复

- `update` 只更新知识内容，不改运行时代码。
- `upgrade` 由 Skill 代理执行：先备份，检查 release/checksum，预览配置迁移，获得明确确认，再安装新 wheel；失败回滚旧 wheel 与配置。
- Restic 为推荐加密备份；仓库发布前不保存 Restic 密码。
- 恢复顺序：Restic 快照 -> 私有 GitHub 正本 -> 本地来源重新生成。每次发布必须包含合成恢复演练。

## 11. 发行与自举

1. 公共仓库发布源码、wheel、`.skill` 和 `SHA256SUMS`。
2. `.skill` 内 wheel 必须与同一 tag/commit 的独立 wheel 哈希一致。
3. Skill 安装器只安装包内已校验 wheel；外部工具必须从官方来源下载并验证锁文件哈希。
4. 发布后把公共仓库作为 `authored` Skill 加入作者自己的私有知识库，保存公共 commit permalink。
5. 私有知识仓库在自举前后都必须验证为 `PRIVATE`。

## 12. 验收门

- Skill 结构通过官方 `quick_validate.py`，且无 TODO/占位文本。
- Linux 本机端到端合成流程通过：init、授权、preview/apply、幂等、stage/promote、search、UI、备份适配器和隐私拒绝。
- GitHub Actions 的 Ubuntu 与原生 Windows 测试通过。
- 控制台桌面/移动截图实际检查，无重叠、横向溢出、截断或空白主视图。
- 公共仓库 secret/path/privacy 审计通过，历史中无私人 Vault、真实聊天或本机凭据。
- `.skill` 两次干净构建 SHA-256 一致，并可在临时 HOME 中安装和运行。
- GitHub 公共 Skill 仓库为 `PUBLIC`；用户知识仓库为 `PRIVATE`。
- 新 Skill 已进入作者知识库、QMD 索引和加密备份，固定链接指向发布 commit。

