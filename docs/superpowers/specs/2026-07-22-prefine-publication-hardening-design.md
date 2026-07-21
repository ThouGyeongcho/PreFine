# PreFine 公开发布安全加固设计

## 背景与目标

PreFine 的容器分发、品牌统一、历史清理和私有 GHCR 构建已经完成第一轮实现。公开前复审发现两项严重问题和若干重要问题：示例凭据可以直接用于生产、备份恢复不是失败即停止、发布工作流缺少源码门禁和镜像运行烟测、浏览器会话数据可能在注销后残留，以及请求来源和反向代理信任边界不够严格。

本轮采用“完整加固后一次公开”方案。仓库、GHCR 包和 `v0.1.0` 标签在全部修复、复审和私有流水线验证通过前保持未公开状态。本地发布流程不构建 Docker 镜像；GitHub Actions 仍是唯一镜像构建者。

项目采用 MIT 许可证，版权行固定为 `Copyright (c) 2026 ThouGyeongcho`。公开版本新增标准 MIT `LICENSE` 和安全报告说明 `SECURITY.md`。

## 后端安全边界

### 启动凭据验证

`Settings` 在应用或维护命令启动前执行以下验证：

- `ADMIN_PASSWORD` 至少 12 个字符。
- `SESSION_SECRET` 至少 32 个字符。
- `.env.example` 使用 `ADMIN_PASSWORD=CHANGE_ME_ADMIN_PASSWORD` 和 `SESSION_SECRET=CHANGE_ME_SESSION_SECRET`。
- 即使占位值满足长度要求，也必须按精确值拒绝，确保复制示例文件后不能直接启动。
- 验证错误必须指出需要替换的变量，但不得回显实际密钥。

`ADMIN_USERNAME=admin` 可以作为非秘密默认示例继续存在。README 的首次部署步骤明确要求生成随机管理员密码和会话密钥。

### 写请求来源验证

所有使用会话 Cookie 的 `POST`、`PUT`、`PATCH` 和 `DELETE` 请求继续通过统一依赖验证来源。规则为：

1. 有 `Origin` 时，协议必须为 HTTP/HTTPS，主机和端口必须与请求 `Host` 完全一致。
2. 没有 `Origin` 但有 `Referer` 时，按相同规则验证其来源。
3. 两者都没有但 `Sec-Fetch-Site` 为 `same-origin` 时允许。
4. 三类来源信息全部缺失、值格式错误、值为 `same-site` 或 `cross-site` 时均返回 403。

登录请求尚未持有有效会话 Cookie，不依赖该防护。非浏览器客户端如需执行受保护写操作，也必须显式发送匹配的 `Origin` 或 `Referer`，不再以缺少浏览器请求头为由放行。

### 反向代理与登录限流

Uvicorn 显式使用 `--no-proxy-headers`，默认不让任意客户端通过转发头改变连接身份。新增可选环境变量 `TRUSTED_PROXY_IPS`，其值为逗号分隔的精确 IPv4/IPv6 地址；空值表示不信任任何代理。配置中出现无效 IP 时启动失败。

登录限流地址按以下顺序确定：

1. 获取实际套接字直连地址。
2. 只有直连地址位于 `TRUSTED_PROXY_IPS` 时，才检查 `X-Forwarded-For`。
3. 仅接受只含一个有效 IP 的 `X-Forwarded-For`；缺失、含多个地址或格式无效时回退到直连地址。

运维文档要求受信反向代理覆盖而不是追加客户端提供的 `X-Forwarded-For`。本轮只支持单层受信代理拓扑，避免在没有完整代理链模型时错误信任用户输入。

### 身份统一

税源客户端的 User-Agent 从旧的压缩名称改为 `PreFine`。身份回归测试同时扫描带空格、连字符和压缩拼写，防止旧名称再次进入源码、配置或文档。

## 原子备份与恢复

### 维护命令接口

镜像新增 `backend.app.database_maintenance` 命令模块。公开接口为：

```console
docker compose run --rm --no-deps app python -m backend.app.database_maintenance backup
docker compose run --rm --no-deps app python -m backend.app.database_maintenance restore <backup-file-name>
```

`restore` 只接受文件名，不接受绝对路径、父目录跳转或符号链接逃逸；来源必须解析到 `/data/backups/` 内的普通文件。

容器入口脚本保留无参数时的现有启动路径：准备 `/data` 权限、降权、迁移、启动单 worker Web 服务。传入维护命令时，入口脚本只准备挂载权限并降权执行原命令，不运行迁移或 Web 服务。

### 备份数据流

1. 要求 `/data/prefine.db` 已存在且为可读 SQLite 数据库。
2. 在 `/data/backups/` 创建同一文件系统内的唯一临时文件。
3. 使用 Python `sqlite3` backup API 生成一致快照。
4. 对临时数据库执行 `PRAGMA integrity_check`；结果必须严格为 `ok`。
5. 将临时文件原子改名为带 UTC 时间戳的 `prefine-YYYYMMDDTHHMMSSZ.db`，并输出最终路径。
6. 任一步失败时返回非零退出码并清理临时文件，不覆盖已有备份。

### 恢复数据流

1. 验证指定备份来源位于 `/data/backups/` 且完整性检查通过。
2. 使用备份流程为当前数据库创建并校验 `pre-restore-YYYYMMDDTHHMMSSZ.db`。
3. 将来源备份写入与 `/data/prefine.db` 同目录的唯一临时数据库。
4. 对临时数据库执行完整性检查。
5. 仅在全部检查通过后使用 `os.replace` 原子替换当前数据库。
6. 失败时保留原数据库和已验证的恢复前备份，并删除未完成的临时文件。

运维文档在备份和恢复前都停止 `app` 并验证服务已经停止。POSIX 示例以 `set -eu` 开始；PowerShell 示例设置 `$ErrorActionPreference = "Stop"`，并在每个外部 Docker 命令后检查 `$LASTEXITCODE`。维护失败时不自动重启应用，使故障保持显式和可诊断。成功后才启动应用并检查 `/api/health`。

## 前端会话与表单一致性

### 会话数据清理

前端增加统一会话失效边界，集中连接 API 层、React Query 和路由：

- `apiRequest` 识别任何 401 响应并发出会话失效通知。
- 会话边界收到通知后清除全部查询缓存，并以 `replace` 方式导航到 `/login`。
- 登录失败仍在登录页显示原始错误；清理查询缓存不得清除当前登录 mutation 的错误状态。
- 主动注销成功后先清除全部查询缓存，再替换导航到登录页。
- 登录成功后重新获取当前用户和业务查询，不复用注销前缓存。

这样浏览器后退、30 秒 `staleTime` 和并发业务请求均不能重新显示前一会话的数据。

### 提醒天数编辑

提醒天数输入框使用独立文本草稿，不直接把每次按键转换为数字数组。提交时按逗号拆分，先去除空白项，再接受合法整数；空输入和尾随逗号不会产生 `0`。

保存成功后，以服务器返回的设置作为唯一事实来源：父级页面数据、结构化编辑草稿和文本输入值全部更新为服务器规范化后的排序、去重结果。保存失败时恢复到最近一次服务器确认的设置并显示错误。

## GitHub Actions 发布门禁

工作流保持固定提交 SHA 的第三方 Action、最小权限和严格引用验证，并拆分为连续依赖的三个阶段。

### 1. 源码验证

在任何 GHCR 登录或镜像推送前运行：

- 完整历史 checkout 和 Gitleaks 扫描；
- 后端 pytest、Ruff 和生产 Python 依赖审计；
- 前端 lint、Vitest、生产构建、Playwright 和 pnpm 生产依赖审计。

审计发现未处理的高危或严重漏洞、秘密扫描命中、测试失败或构建失败时，工作流立即停止。

### 2. 单架构运行烟测

GitHub Actions 使用 Buildx 构建仅供本次运行使用的 `linux/amd64` 镜像并加载到 runner，不推送。烟测使用随机有效管理员密码、随机会话密钥和临时 bind mount：

- 容器内 Web 进程不是 root；
- Alembic 迁移成功并创建数据库；
- 健康检查返回成功；
- 管理员登录成功；
- 写入一条业务数据后停止并重启容器，数据仍可读取；
- 清理逻辑无论成功失败都删除测试容器和 runner 临时目录。

烟测镜像使用与最终发布相同的 Dockerfile 和提交。构建缓存可供下一阶段复用。

### 3. 多架构发布

只有前两阶段成功后才登录 GHCR，构建并推送 `linux/amd64` 和 `linux/arm64`。标签规则保持不变：

- `main` 或默认分支人工触发只发布 `latest`；
- 精确 `vX.Y.Z` 只发布对应的 `X.Y.Z`；
- 不生成 `X.Y`、`X` 或其他别名。

推送后检查 manifest 必须同时包含两个目标平台。无效 Git 引用必须在 QEMU、Buildx、登录或任何发布副作用前失败。

### 4. GitHub Release 同步

`main` 推送和默认分支人工触发只更新 Docker `latest`，不创建 GitHub Release。只有通过严格验证的 `vX.Y.Z` 标签才在多架构镜像和 manifest 验证成功后创建正式 Release，顺序不得颠倒。

Release 标题使用完整标签名，例如 `v0.1.0`。工作流使用 GitHub runner 自带的 `gh release create`，同时启用 `--verify-tag` 和 `--generate-notes`，不新增第三方 Release Action。自定义说明放在自动生成记录之前，至少包含：

```console
docker pull ghcr.io/thougyeongcho/prefine:0.1.0
```

说明同时链接到仓库中的 Compose 部署和升级文档。Release 不上传 Docker 镜像副本；GitHub 自动提供源码归档，容器只由 GHCR 分发。

Release 任务独立授予 `contents: write`。源码验证任务保持 `contents: read`，镜像推送任务只增加 `packages: write`，避免整个工作流共享写权限。重复运行时先读取现有 Release：不存在时创建；已经存在时必须验证其标签和目标提交与当前运行一致，不重复创建、不移动标签，也不覆盖指向其他提交的 Release。

任一源码门禁、烟测、镜像推送或 manifest 检查失败时，不运行 Release 任务。Release 创建失败会使正式版本工作流失败；重新运行可以安全完成尚未创建的 Release。

## 公开治理与发布顺序

实现同时完成以下文档治理：

- 新增标准 MIT `LICENSE`，版权行为 `Copyright (c) 2026 ThouGyeongcho`。
- 新增 `SECURITY.md`，说明通过 GitHub 私有漏洞报告渠道提交安全问题，不要求在公开 issue 中披露漏洞细节；公开仓库后立即启用 GitHub private vulnerability reporting。
- 更新 README、`docs/operations.md`、`.env.example`、Compose 环境变量说明和已经过时的 `AGENTS.md`。
- 不新增本地 Docker 构建步骤；最终用户继续只拉取远程镜像并挂载主机数据目录。

发布顺序为：

1. 完成实现、测试、复审和当前树安全扫描。
2. 正常推送私有 `main`，等待更新后的私有发布工作流全部通过。
3. 复核远端提交、完整历史、Logo 唯一性、工作流日志和私有 `latest` 双架构 manifest。
4. 将 GitHub 源码仓库改为公开，并启用 private vulnerability reporting。
5. 将 GHCR 包改为公开，并验证未登录状态能够查看和拉取 `latest`。
6. 创建并推送不可移动的 `v0.1.0` 标签。
7. 等待 `0.1.0` 工作流通过；该工作流在双架构 manifest 验证后自动创建 `v0.1.0` GitHub Release。
8. 验证 `latest` 与 `0.1.0` 均公开且同时包含 amd64、arm64，并确认 GitHub Release 指向同一标签和提交。

任何门禁失败都停止后续步骤。不得使用未租约强推，不得移动已发布版本标签，也不得在安全复审完成前改变仓库或包的公开状态。

## 测试与验收

后端新增或扩展测试覆盖：占位凭据、密码长度、秘密长度、缺失来源头、来源不匹配、`same-origin`、伪造代理头、受信单层代理、无效代理配置、User-Agent，以及维护命令的成功、损坏、缺失、权限、临时清理、恢复前备份和原子替换路径。

前端新增测试覆盖：主动注销后浏览器返回、任意业务请求 401、错误登录、重新登录不复用旧缓存、空白提醒项、尾随逗号，以及服务器排序和去重后的草稿同步。

容器与工作流契约测试覆盖：维护命令降权、默认启动不变、Compose 新环境变量、源码门禁位于登录前、烟测位于推送前、清理路径、精确标签、多架构、固定 Action SHA、Release 位于 manifest 验证后，以及 Release 任务的独立最小权限。

公开发布的完成标准为：全部本地非 Docker 验证通过，私有 GitHub Actions 源码门禁和运行烟测通过，私有及公开 manifest 验证通过，仓库历史无秘密和已删除品牌过程文件，匿名用户可拉取两个目标标签，`v0.1.0` GitHub Release 与 `0.1.0` 镜像指向同一提交，且工作树与远端 `main` 一致。
