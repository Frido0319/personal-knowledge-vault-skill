# 隐私边界

## 授权分级

| 来源 | kind | 默认状态 | 启用确认 |
|---|---|---|---|
| 项目目录 | `project` | 关闭 | `ENABLE:<id>` |
| 学习资料 | `learning` | 关闭 | `ENABLE:<id>` |
| 文档目录 | `documents` | 关闭 | `ENABLE:<id>` |
| 本地 Skill | `skill` | 关闭 | `ENABLE:<id>` |
| Codex/Claude 显式导出 | `agent_history` | 关闭、二次授权 | `AUTHORIZE:<id>:agent_history` |
| WeFlow/微信显式导出 | `weflow` | 关闭、二次授权 | `AUTHORIZE:<id>:weflow` |
| QQ Chat Exporter 显式导出 | `qq` | 关闭、二次授权 | `AUTHORIZE:<id>:qq` |

一次授权只覆盖该精确根路径，不推导父目录、兄弟目录或其他账号。路径不存在、根路径是符号链接或越过授权根的符号链接时，停止该来源。

## 禁止读取

- 整块磁盘、整个 Home、浏览器 Profile、历史、Cookie 和下载记录。
- `.ssh`、`.gnupg`、钱包、密码管理器、系统凭据库、认证缓存。
- `.env`、私钥、token、证书、未知二进制和未知符号链接目标。
- 微信、QQ 或其他聊天应用的内部数据库、缓存和运行目录。
- 用户未逐项指定的网络盘、云盘、移动设备和远端仓库。

发现敏感模式时，不把值打印到终端、日志、页面或错误报告。只报告类别、来源 ID 和被拒绝的相对路径。

## 数据分区

- **公共源码仓库**：Skill、runtime 源码、合成测试和文档；不得包含真实 Vault、聊天、配置、凭据或用户名绝对路径。
- **Vault**：可读 Markdown、Obsidian 配置、`_staging` 和显式保留的 `_raw`。
- **Data**：授权配置、manifest、审计、索引、临时镜像和备份状态；权限按平台尽可能收紧。
- **备份**：优先使用加密 Restic；私有 GitHub 镜像不是加密备份的替代品。

## 联网与上传确认

以下动作逐项确认：安装依赖联网、GitHub 登录、创建仓库、上传 Vault、下载可选工具或模型。GitHub 镜像必须在准备前、push 前和 push 后都返回 `PRIVATE`；任何一次未知、空值或非私有都停止。

公网永久链接只能指向公开 Skill 或用户明确允许公开的内容。私人知识证据保留在私有仓库，并固定到 commit SHA，不能用漂移的 `main` 充当证据链接。
