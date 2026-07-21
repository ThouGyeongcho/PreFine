# 财务工具包

面向中国大陆财务团队的私有化单管理员工具箱。第一版包含人民币金额大小写严格双向转换、12366 税收日历缓存、企业税务清单、工具内设置、邮件提醒和同源登录。

## 功能

- 使用 `Decimal` 校验和转换人民币金额，支持负数、角分、规范千分位和严格反向回环。
- 按 36 个地区和月份同步 12366 税历，原样保存并展示官方 `bssz` 文本。
- 根据一般纳税人或小规模纳税人身份及关注事项生成个性化清单，无法识别的项目标记为“其他待确认”。
- 采用 24 小时缓存、过期先返回和失败保留旧数据策略。
- 按北京时间发送 7/3/1/0 天到期提醒，支持发送去重、失败重试和测试邮件。
- 提供 12 小时签名会话、登录限速、HttpOnly Cookie 和同源写操作校验。

个性化清单只是对官方文字的本地辅助筛选，不等同于企业在电子税务局中的真实税种核定结果，也不构成税务或法律意见。

## Docker 部署

需要 Docker 与 Docker Compose。首次启动前先复制环境变量模板。

Linux / macOS：

```bash
cp .env.example .env
# 编辑 .env，替换管理员密码，并将 SESSION_SECRET 设置为至少 32 个字符
docker compose up --build -d
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
# 编辑 .env，替换管理员密码，并将 SESSION_SECRET 设置为至少 32 个字符
docker compose up --build -d
```

打开 `http://localhost:8000`。`ADMIN_PASSWORD` 和 `SESSION_SECRET` 必须在部署前替换；SMTP 变量可留空，待需要邮件提醒时再配置。

### 常用 Docker 命令

```bash
# 查看容器状态
docker compose ps

# 检查服务健康状态
curl http://localhost:8000/api/health

# 持续查看最近 200 行应用日志
docker compose logs -f --tail=200 app

# 重启应用
docker compose restart app

# 停止并删除容器和网络，保留数据卷
docker compose down

# 重新构建并启动
docker compose up --build -d
```

PowerShell 可使用 `Invoke-RestMethod http://localhost:8000/api/health` 检查健康状态。

数据保存在命名卷 `finance-toolkit-data`。容器启动时会自动执行 Alembic 迁移，并以非 root 用户运行单个 Uvicorn worker。`docker compose down` 会保留数据；`docker compose down -v` 会永久删除应用数据卷，仅应在确认无需保留数据时执行。详细配置、邮件、备份和升级步骤见 [运行手册](docs/operations.md)。

### 完整 Compose 文件

仓库根目录的 `docker-compose.yml` 完整内容如下：

```yaml
services:
  app:
    build:
      context: .
    image: finance-toolkit:0.1.0
    restart: unless-stopped
    ports:
      - "${APP_PORT:-8000}:8000"
    environment:
      ADMIN_USERNAME: "${ADMIN_USERNAME:?请在 .env 中设置 ADMIN_USERNAME}"
      ADMIN_PASSWORD: "${ADMIN_PASSWORD:?请在 .env 中设置 ADMIN_PASSWORD}"
      SESSION_SECRET: "${SESSION_SECRET:?请在 .env 中设置 SESSION_SECRET}"
      DATA_DIR: /data
      COOKIE_SECURE: "${COOKIE_SECURE:-false}"
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
      - finance-toolkit-data:/data

volumes:
  finance-toolkit-data:
```

## 本地开发

后端要求 Python 3.12：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"  # Windows
python -m uvicorn backend.app.main:create_app --factory --reload
```

启动前设置 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、至少 32 字符的 `SESSION_SECRET`，并将 `DATA_DIR` 指向可写目录。

前端要求 Node.js 22 与 pnpm 11：

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

Vite 开发服务器会将 `/api` 代理到 `http://127.0.0.1:8000`。

## 验证

```bash
python -m pytest backend/tests
ruff check backend
pnpm --dir frontend lint
pnpm --dir frontend exec vitest run
pnpm --dir frontend build
pnpm --dir frontend e2e
```

Playwright 默认使用其安装的 Chromium；本机也可设置 `PLAYWRIGHT_CHANNEL=msedge` 使用 Edge。真实 12366 接口只做手动契约检查，不纳入日常自动化，以免外部网络波动影响构建。

## 项目结构

- `backend/app/`：FastAPI、金额、税源、缓存、税务档案、提醒、认证与调度。
- `backend/tests/`：pytest 单元、API、持久化和验收契约测试。
- `frontend/src/`：React 页面、组件与 API 客户端。
- `frontend/e2e/`：Playwright 桌面和移动关键流程。
- `docs/`：产品设计、实施计划与运行手册。
