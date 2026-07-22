# PreFine

## Container publication

Users pull the published [GHCR image](https://github.com/ThouGyeongcho/PreFine/pkgs/container/prefine)
and do not build it locally. Docker image builds run only in GitHub Actions. A
push to `main` publishes `ghcr.io/thougyeongcho/prefine:latest`; `latest` follows
`main`. Only canonical semantic-version tags such as `v0.1.0` publish the matching
image version and create a [GitHub Release](https://github.com/ThouGyeongcho/PreFine/releases).
Each published tag includes both `linux/amd64` and `linux/arm64` images. The image
can be pulled anonymously only after the package visibility gate has been changed
to public in GHCR.

PreFine is available under the [MIT License](LICENSE). Please report security
issues privately according to the [security policy](SECURITY.md).

面向中国大陆财务团队的私有化单管理员工具箱。

## Docker 部署

PreFine 只从 GitHub Container Registry 拉取已发布的镜像；无需也不应在本地构建镜像。复制环境变量模板、编辑必要的凭据，然后启动服务：

```bash
cp .env.example .env
# 编辑 .env：替换所有 CHANGE_ME 凭据；SESSION_SECRET 至少 32 个随机字符
docker compose up -d
```

在 Windows PowerShell 中可使用 `Copy-Item .env.example .env`。启动后访问 `http://localhost:8000`。

`PREFINE_DATA_DIR` 默认是 `./data`，数据库保存在该主机目录的 `prefine.db`。默认的 `PUID` 和 `PGID` 都是 `1000`；如宿主机目录属于其他用户，请在 `.env` 中改成相应的 UID/GID，确保容器内降权后的进程仍可写入数据目录。

For a single-layer reverse proxy, set `TRUSTED_PROXY_IPS` to the proxy's exact
direct IP address. That proxy must overwrite `X-Forwarded-For` with exactly one
client IP. Leave `TRUSTED_PROXY_IPS` empty unless this condition is met; the empty
value is the secure default.

### 升级与版本固定

```bash
docker compose pull
docker compose up -d

# 固定版本：在 .env 中设置 PREFINE_VERSION=0.1.1
```

`PREFINE_VERSION=latest` follows `main`. Before an upgrade, follow the
[operations guide](docs/operations.md) to back up the database.

### 常用命令

```bash
docker compose ps
curl http://localhost:8000/api/health
docker compose logs -f --tail=200 app
docker compose restart app
docker compose down
```

`docker compose down` 会删除容器和网络，但保留宿主机上的数据目录。不要删除由 `PREFINE_DATA_DIR` 配置的数据目录（默认 `./data`），除非已完成备份且确定不再需要数据；备份和恢复步骤请参阅[运行手册](docs/operations.md)。

### 完整 Compose 文件

仓库根目录的 `docker-compose.yml` 完整内容如下：

```yaml
services:
  app:
    image: ghcr.io/thougyeongcho/prefine:${PREFINE_VERSION:-latest}
    pull_policy: always
    restart: unless-stopped
    ports:
      - "${APP_PORT:-8000}:8000"
    environment:
      PUID: "${PUID:-1000}"
      PGID: "${PGID:-1000}"
      ADMIN_USERNAME: "${ADMIN_USERNAME:?请在 .env 中设置 ADMIN_USERNAME}"
      ADMIN_PASSWORD: "${ADMIN_PASSWORD:?请在 .env 中设置 ADMIN_PASSWORD}"
      SESSION_SECRET: "${SESSION_SECRET:?请在 .env 中设置 SESSION_SECRET}"
      DATA_DIR: /data
      COOKIE_SECURE: "${COOKIE_SECURE:-false}"
      TRUSTED_PROXY_IPS: "${TRUSTED_PROXY_IPS:-}"
      TZ: "${TZ:-Asia/Shanghai}"
      SMTP_HOST: "${SMTP_HOST:-}"
      SMTP_PORT: "${SMTP_PORT:-}"
      SMTP_USERNAME: "${SMTP_USERNAME:-}"
      SMTP_PASSWORD: "${SMTP_PASSWORD:-}"
      SMTP_FROM: "${SMTP_FROM:-}"
      REMINDER_TO_EMAIL: "${REMINDER_TO_EMAIL:-}"
      SMTP_USE_TLS: "${SMTP_USE_TLS:-false}"
      SMTP_STARTTLS: "${SMTP_STARTTLS:-false}"
    volumes:
      - "${PREFINE_DATA_DIR:-./data}:/data"
```

## 功能

- 使用 `Decimal` 校验和转换人民币金额，支持负数、角分、规范千分位和严格反向回环。
- 按 36 个地区和月份同步 12366 税历，原样保存并展示官方 `bssz` 文本。
- 根据纳税人身份及关注事项生成个性化清单；无法识别的项目会标记为“其他待确认”。
- 使用 24 小时缓存、过期先返回和失败保留旧数据策略。
- 支持邮件到期提醒、发送去重、失败重试和测试邮件。

## 本地开发

后端需要 Python 3.12：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"  # Windows
python -m uvicorn backend.app.main:create_app --factory --reload
```

前端需要 Node.js 22 和 pnpm 11：

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

## 验证

```bash
python -m pytest backend/tests
ruff check backend
pnpm --dir frontend lint
pnpm --dir frontend exec vitest run
pnpm --dir frontend build
pnpm --dir frontend e2e
```
