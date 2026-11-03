# Personal Knowledge Vault Skill 实施计划

> **执行要求：** 使用 `executing-plans` 逐任务实施；所有运行时代码遵循 RED-GREEN-REFACTOR，完成前使用 `verification-before-completion` 做独立终检。

**目标：** 交付并公开发布一个可在 Linux 和原生 Windows 上搭建单用户私密知识库的 Skill，随后把该 Skill 反向登记进作者现有私有知识库。

**架构：** Python 3.11 标准库 + PyYAML 提供跨平台 CLI、确定性生成器、本地控制台和安全发布器。Skill 只编排并安装同 commit 的 wheel。Vault/Data 永远位于源码仓库外；AI 提炼只产出待审 staging 页面。

**技术栈：** Python 3.11、PyYAML、pytest、build、标准库 HTTP/SQLite、vanilla HTML/CSS/JS、PowerShell 5.1、systemd user、GitHub Actions、GitHub CLI、可选 QMD/Restic。

## Task 1：仓库契约、配置和跨平台路径

**文件：**
- Create: `pyproject.toml`
- Create: `src/personal_vault/__init__.py`
- Create: `src/personal_vault/paths.py`
- Create: `src/personal_vault/config.py`
- Create: `src/personal_vault/security.py`
- Create: `tests/test_paths.py`
- Create: `tests/test_config.py`
- Create: `tests/test_security.py`
- Create: `.gitignore`, `LICENSE`, `README.md`

**步骤：**
- [ ] 先写 Linux/Windows 默认路径、仓库外约束、原子 YAML、`0600` best-effort、危险根目录拒绝和 secret/path redaction 的失败测试。
- [ ] 运行 focused pytest，确认因模块缺失失败。
- [ ] 实现不可变 `VaultPaths`、配置 schema/version、原子写入和安全边界。
- [ ] 重跑 focused pytest，确认通过；提交 Task 1。

## Task 2：初始化、来源授权和审计账本

**文件：**
- Create: `src/personal_vault/setup.py`
- Create: `src/personal_vault/sources.py`
- Create: `src/personal_vault/audit.py`
- Create: `src/personal_vault/cli.py`
- Create: `tests/test_setup.py`
- Create: `tests/test_sources.py`
- Create: `tests/test_cli_init.py`
- Create: `skills/build-personal-knowledge-vault/assets/config-templates/config.zh-CN.yaml`
- Create: `skills/build-personal-knowledge-vault/assets/config-templates/config.en.yaml`

**步骤：**
- [ ] 写失败测试：初始化不接触授权源、重复运行幂等、显式 add/enable/disable、聊天/历史二次授权、永不自动发现、JSONL 审计不含正文。
- [ ] 实现 `personal-vault init` 与 `source add/list/enable/disable`。
- [ ] 验证 dry-run 零写入和配置权限；提交 Task 2。

## Task 3：确定性目录盘点和 L0-L5 可读页面

**文件：**
- Create: `src/personal_vault/manifest.py`
- Create: `src/personal_vault/inventory.py`
- Create: `src/personal_vault/render.py`
- Create: `src/personal_vault/update.py`
- Create: `tests/test_manifest.py`
- Create: `tests/test_inventory.py`
- Create: `tests/test_render.py`
- Create: `tests/test_update.py`
- Create: `tests/fixtures/synthetic-project/**`
- Create: `tests/fixtures/synthetic-learning/**`

**步骤：**
- [ ] 写失败测试：显式 root、排除项、越界符号链接、哈希、README 摘要、项目/学习/文档/Skill 页面、手工页保护、preview 零写入、apply 原子性、二次运行零差异。
- [ ] 实现有界扫描、SQLite manifest、中文/英文模板、首页和 L0-L5 导航。
- [ ] 在临时目录执行完整 preview/apply/preview，要求第二次 `changes=0`；提交 Task 3。

## Task 4：语义提案 staging、审核与来源追踪

**文件：**
- Create: `src/personal_vault/proposals.py`
- Create: `src/personal_vault/review.py`
- Create: `schemas/knowledge-proposal.schema.json`
- Create: `tests/test_proposals.py`
- Create: `tests/test_review.py`
- Create: `tests/fixtures/synthetic-proposals.json`

**步骤：**
- [ ] 写失败测试：结构校验、未知 source 拒绝、敏感字段脱敏、staging 不进正式搜索、确认字符串、promote/reject 幂等、审批账本。
- [ ] 实现 `stage add/list` 和 `review promote/reject`，只允许生成 `knowledge/` 或 `synthesis/`。
- [ ] 验证原始会话不会成为首页或全局图节点；提交 Task 4。

## Task 5：搜索、状态、QMD 和 Restic 可选适配器

**文件：**
- Create: `src/personal_vault/search.py`
- Create: `src/personal_vault/status.py`
- Create: `src/personal_vault/integrations.py`
- Create: `tests/test_search.py`
- Create: `tests/test_status.py`
- Create: `tests/test_integrations.py`

**步骤：**
- [ ] 写失败测试：内建 lexical 搜索、staging/raw 默认排除、QMD 命令白名单、只索引 Vault、Restic 密码不入配置、缺失依赖优雅降级。
- [ ] 实现 `search/status/index qmd/backup restic/doctor`。
- [ ] 用 fake executables 验证跨平台 argv 和状态文件；提交 Task 5。

## Task 6：GitHub Skills 目录和严格私有镜像

**文件：**
- Create: `src/personal_vault/github.py`
- Create: `src/personal_vault/skill_catalog.py`
- Create: `tests/test_github.py`
- Create: `tests/test_skill_catalog.py`

**步骤：**
- [ ] 写失败测试：authored/maintained/vendored、commit permalink、secret 扫描、符号链接、文件上限、prepare manifest、push 前后 `PRIVATE`、不明可见性停止。
- [ ] 实现本地 Skill 与 GitHub Skill 页面、私有镜像 prepare/publish 和不可变链接。
- [ ] 所有网络调用通过可注入 runner；单测不访问真实账户；提交 Task 6。

## Task 7：安全的 localhost 管理控制台

**文件：**
- Create: `src/personal_vault/webapp.py`
- Create: `src/personal_vault/web_actions.py`
- Create: `src/personal_vault/web/static/index.html`
- Create: `src/personal_vault/web/static/app.css`
- Create: `src/personal_vault/web/static/app.js`
- Create: `tests/test_webapp.py`
- Create: `tests/test_web_actions.py`

**步骤：**
- [ ] 写失败测试：仅回环绑定、Host 校验、CSP、CSRF、body 上限、固定 action 白名单、preview/confirm、来源/审核/搜索/维护 API。
- [ ] 实现中英双语响应式控制台，不提供 shell/任意路径接口。
- [ ] 启动合成实例，用真实浏览器检查桌面和移动端全页截图、交互及 console；修复全部可见问题；提交 Task 7。

## Task 8：Linux 与原生 Windows 安装和调度

**文件：**
- Create: `src/personal_vault/scheduler.py`
- Create: `platform/linux/personal-vault-maintenance.service.in`
- Create: `platform/linux/personal-vault-maintenance.timer.in`
- Create: `platform/windows/Install-PersonalVaultTask.ps1`
- Create: `platform/windows/Remove-PersonalVaultTask.ps1`
- Create: `platform/windows/Enable-PersonalVaultFirewall.ps1`
- Create: `platform/windows/Disable-PersonalVaultFirewall.ps1`
- Create: `tests/test_scheduler.py`
- Create: `tests/test_platform_assets.py`

**步骤：**
- [ ] 写失败测试：路径转义、当前用户作用域、无管理员标准模式、可逆 firewall hardened 模式、update 与 upgrade 分离。
- [ ] 实现 `schedule install/remove/show` 和平台模板渲染。
- [ ] 在 Ubuntu 本机验证 systemd user 模板；由 GitHub `windows-latest` 原生运行 PowerShell parse/test；提交 Task 8。

## Task 9：Skill 工作流、参考资料和安装脚本

**文件：**
- Modify: `skills/build-personal-knowledge-vault/SKILL.md`
- Modify: `skills/build-personal-knowledge-vault/agents/openai.yaml`
- Create: `skills/build-personal-knowledge-vault/references/privacy-boundary.md`
- Create: `skills/build-personal-knowledge-vault/references/platform-installation.md`
- Create: `skills/build-personal-knowledge-vault/references/update-and-recovery.md`
- Create: `skills/build-personal-knowledge-vault/references/acceptance-checklist.md`
- Create: `skills/build-personal-knowledge-vault/scripts/install_runtime.py`
- Create: `skills/build-personal-knowledge-vault/scripts/verify_install.py`
- Create: `tests/test_skill_contract.py`

**步骤：**
- [ ] 先写失败测试：frontmatter 只有 name/description、触发描述、逐步授权、禁止自动扫描、staging 审批、Windows 无 WSL、无占位词、引用存在。
- [ ] 编写精简主 Skill 和渐进披露参考；安装脚本只安装包内 wheel 并验证 SHA-256。
- [ ] 运行官方 `quick_validate.py` 和 realistic forward tests；提交 Task 9。

## Task 10：可重复构建、CI、安全和恢复演练

**文件：**
- Create: `scripts/build_release.py`
- Create: `scripts/privacy_audit.py`
- Create: `scripts/synthetic_acceptance.py`
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `tests/test_build_release.py`
- Create: `tests/test_privacy_audit.py`
- Create: `docs/operations.md`
- Create: `docs/threat-model.md`

**步骤：**
- [ ] 写失败测试：wheel 与 `.skill` 同 commit、固定时间戳 ZIP、双构建同哈希、私有路径/secret/真实数据拒绝、临时 HOME 安装、合成恢复。
- [ ] 实现构建器、隐私审计和端到端验收器。
- [ ] 本机连续两次干净构建并比较 SHA-256；提交 Task 10。

## Task 11：公开发布与原生 CI 验证

**文件：**
- Create: `CHANGELOG.md`
- Create: `docs/evidence/v0.1.0-acceptance.md`

**步骤：**
- [ ] 运行全量 pytest、compileall、Skill validator、隐私审计、合成端到端、浏览器视觉验收和 clean-tree 检查。
- [ ] 创建 `Frido0319/personal-knowledge-vault-skill` PUBLIC 仓库并 push；核验可见性为 `PUBLIC`。
- [ ] 等待 GitHub Actions Ubuntu + Windows jobs 全部通过，失败则修复并重跑。
- [ ] 创建 `v0.1.0` release，上传 wheel、`.skill`、`SHA256SUMS`；从 release 下载并复验哈希与临时安装。
- [ ] 写入精确 commit、run、release URL 和剩余边界；提交/推送最终证据。

## Task 12：反向登记到作者私有知识库

**文件：**
- Modify outside repo: `<PRIVATE_DATA>/config/github-skills.yaml`
- Regenerate outside repo: `<PRIVATE_VAULT>/skills/我的Skills/**`
- Update private mirror outside repo through guarded publisher.

**步骤：**
- [ ] 先备份作者 Vault 和配置，并再次验证 `Frido0319/personal-knowledge-vault` 为 `PRIVATE`。
- [ ] 以 `authored` 登记公开 Skill 仓库和 v0.1.0 固定 commit permalink。
- [ ] 重建 Skill 目录、UI、QMD 索引，运行 lint/privacy audit 和 Restic 备份。
- [ ] 通过 guarded publisher 更新私有知识正本；push 后再次验证 `PRIVATE`。
- [ ] 记录新页数、Skill 数、QMD 文档数、Restic snapshot、私有镜像 commit；最终确认两个工作树干净。
