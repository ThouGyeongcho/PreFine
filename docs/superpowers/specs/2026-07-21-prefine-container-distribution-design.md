# PreFine 容器分发设计

## 目标

将项目所有现行名称统一为 `PreFine`／`prefine`，通过 GitHub Actions 构建公开的 GHCR 多架构镜像，并让普通用户通过宿主机目录挂载数据后直接启动，不需要在本地构建镜像。

源码仓库最终公开。容器包最终公开且允许匿名拉取。镜像公开后不可恢复为私有，因此所有公开操作必须位于安全门禁之后。

## 命名规则

- 产品、界面标题和面向用户的文档使用 `PreFine`。
- Docker、Python、Linux 用户、文件名和其他技术标识使用小写 `prefine`。
- GHCR 镜像为 `ghcr.io/thougyeongcho/prefine`。
- Python 项目名为 `prefine`。
- 前端包名为 `prefine-frontend`。
- 容器用户和用户组均为 `prefine`。
- 容器入口脚本为 `prefine-entrypoint`。
- SQLite 数据库路径为 `/data/prefine.db`。
- 会话签名盐值为 `prefine-session-v1`。
- 当前源码、配置和文档中不得保留旧项目标识。

本次不提供旧数据库文件名兼容或自动迁移。现有旧文件不会被自动读取，避免在改名完成后继续保留旧标识。

## 用户部署接口

根目录 `docker-compose.yml` 只引用远程镜像，不包含 `build`：

```yaml
image: ghcr.io/thougyeongcho/prefine:${PREFINE_VERSION:-latest}
pull_policy: always
volumes:
  - "${PREFINE_DATA_DIR:-./data}:/data"
```

`.env.example` 提供以下部署设置：

- `PREFINE_VERSION=latest`
- `PREFINE_DATA_DIR=./data`
- `PUID=1000`
- `PGID=1000`
- 现有服务端口、管理员、会话、Cookie、时区和 SMTP 设置

默认部署流程只有复制环境变量、替换管理员密码与会话密钥、启动容器三步：

```bash
cp .env.example .env
docker compose up -d
```

升级流程为：

```bash
docker compose pull
docker compose up -d
```

用户需要固定版本时，将 `PREFINE_VERSION` 设置为 `0.1.0`。默认 `latest` 每次启动前由 Compose 检查并拉取。

## 挂载目录权限

镜像入口以 root 启动，仅用于准备 `/data`：

1. 读取 `PUID` 和 `PGID`，默认均为 `1000`。
2. 拒绝空值、非十进制正整数和零值，并输出明确错误。
3. 将 `prefine` 用户和用户组调整到指定 UID/GID。
4. 创建 `/data`，递归修复其所属用户；失败时输出挂载路径、PUID/PGID 和处理建议，然后停止启动。
5. 使用轻量降权工具切换到 `prefine`。
6. 以 `prefine` 身份执行 Alembic 迁移和单 worker Uvicorn 服务。

应用进程始终以非 root 身份运行。Linux 和 NAS 用户可以调整 PUID/PGID；Docker Desktop 用户默认使用 `./data`。

## 镜像构建与标签

新增 `.github/workflows/publish-container.yml`，所有容器构建均在 GitHub Actions 中进行，本地发布流程不构建 Docker 镜像。

- 推送默认分支时发布 `ghcr.io/thougyeongcho/prefine:latest`。
- 推送 `vX.Y.Z` Git 标签时只发布精确的 `X.Y.Z` 标签，不生成 `X.Y` 或 `X` 别名。
- 第一版发布 `latest` 和 `0.1.0` 两个标签。
- 支持手动触发默认分支的 `latest` 构建。
- 构建平台为 `linux/amd64` 和 `linux/arm64`。
- 使用 Buildx、QEMU 和 GitHub Actions 构建缓存。
- 镜像包含 OCI source、revision、version、title 和 description 标签。
- 推送后用 Buildx 检查 manifest，确认两个平台均存在。

工作流只授予 `contents: read` 和 `packages: write`。仅默认分支、版本标签和人工触发能够写入镜像仓库。所有第三方及 GitHub Actions 固定到完整提交 SHA，并在行尾注释所对应的稳定版本。

## 公开前安全门禁

源码仓库在以下检查全部通过前保持私有：

1. 扫描当前工作树和完整 Git 历史中的私钥、GitHub Token、云凭据、SMTP 凭据及其他可信密钥形态。
2. 枚举所有历史对象和当前已跟踪路径，确认没有 `.env`、数据库、依赖目录、缓存、测试报告或构建产物。
3. 人工复核 `.env.example`，确认只含无效占位值。
4. 使用 Python 和 pnpm 的生产依赖审计；存在未处理的高危或严重漏洞时停止公开。
5. 复核 GitHub Actions 权限、触发器、条件表达式和固定 SHA。
6. 确认当前源码、配置和文档不存在旧项目标识。
7. 运行后端、Ruff、前端 lint、Vitest、生产构建和 Playwright 全套验证。
8. 校验 README 与根 Compose 完全一致，且 Compose 不含本地构建、使用公开镜像和宿主机目录挂载。
9. 校验入口脚本的 PUID/PGID 拒绝路径、权限失败路径和降权执行路径。

可信密钥或高危生产依赖问题会阻断公开流程。自动扫描只能降低风险，不能证明绝无敏感信息。

## 发布顺序

1. 在本地完成改名、部署配置、工作流和文档修改。
2. 完成全部测试、安全扫描、依赖审计和暂存区检查。
3. 提交并推送默认分支，此时源码仓库保持私有。
4. 等待 GitHub Actions 构建私有的 `latest`，检查 workflow 日志和多架构 manifest。
5. 对远端提交和完整 Git 历史再执行一次安全复核。
6. 将源码仓库改为公开。
7. 将 GHCR 包改为公开；该操作不可逆。
8. 验证未登录状态可以读取包信息和拉取 `latest`。
9. 创建并推送 `v0.1.0` 标签。
10. 等待 `0.1.0` 构建完成，验证两个标签均公开且同时包含 amd64、arm64。

## 错误处理

- PUID/PGID 非法：入口脚本在修改用户前退出，错误中指明变量名和值要求。
- 挂载目录不可写或无法修改所有权：不启动迁移和应用，错误中给出宿主目录与 PUID/PGID 检查建议。
- GitHub Actions 构建或 manifest 检查失败：不执行仓库或包公开操作。
- GHCR 包尚未创建：等待 `latest` workflow 完成后再修改可见性。
- 公开匿名检查失败：不推送版本标签，先恢复包访问配置。
- 版本标签已存在或指向错误提交：停止发布，不移动或强制覆盖标签。

## 验证与成功标准

- 当前源码、配置和文档中只使用 `PreFine`／`prefine`。
- `docker-compose.yml` 没有 `build`，镜像为 `ghcr.io/thougyeongcho/prefine`，数据默认落在宿主机 `./data`。
- README 含最简安装、升级、固定版本、Linux/NAS 权限和完整 Compose 文件。
- 应用迁移与服务进程以 `prefine` 身份运行。
- 后端、Ruff、前端 lint、Vitest、生产构建和 Playwright 均通过。
- GitHub 仓库为公开，默认分支保持 `main`。
- GHCR 包为公开，匿名访问无需登录。
- `latest` 和 `0.1.0` 指向预期提交构建的镜像。
- 两个标签的 manifest 均包含 `linux/amd64` 和 `linux/arm64`。
- 本地工作树干净，远端默认分支与本地提交一致。

## 依据

- [GitHub：发布 Docker 镜像](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [GitHub：Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub：包访问控制与可见性](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
- [Docker：GitHub Actions 多平台镜像](https://docs.docker.com/build/ci/github-actions/multi-platform/)
