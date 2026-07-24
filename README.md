# PreFine

> 面向中国大陆财务团队的私有化财务工具箱。

## 简介

PreFine 将常用财务能力集中在一个简洁的网页工作台中。项目采用单容器、单管理员设计，
前端、后端和 SQLite 数据库均由自己掌控，适合企业内网或个人服务器部署。

当前版本提供人民币金额大小写转换、12366 税收日历、企业税务清单和税期邮件提醒。
部署不依赖外部数据库，只需 Docker 和一个持久化数据目录即可运行。

## 核心亮点

- **人民币金额双向转换**：使用十进制定点计算，支持负数、角分和规范千分位，严格拒绝超过两位的小数。
- **12366 税收日历**：按月份查看 36 个地区的公开税期信息，完整保留官方原文和日期。
- **企业税务清单**：根据纳税人身份和关注事项筛选内容，无法识别的项目统一标记为“其他待确认”。
- **断网容错缓存**：数据缓存 24 小时；上游暂时不可用时继续展示最近一次成功同步的内容。
- **税期邮件提醒**：支持自定义提前天数、发送去重、失败重试和测试邮件。
- **私有化单容器部署**：前后端同源运行，SQLite 数据持久化到宿主机，不依赖外部数据库。

## Docker 部署

PreFine 的容器镜像由 GitHub Actions 构建并发布到
[GitHub 容器镜像仓库](https://github.com/ThouGyeongcho/PreFine/pkgs/container/prefine)。
部署时直接使用仓库中的 [docker-compose.yml](docker-compose.yml) 拉取镜像，
不需要在服务器上构建。

已发布镜像同时支持 `linux/amd64` 和 `linux/arm64`。

### 环境要求

- Git
- Docker
- Docker Compose 2
- 可访问 GitHub 容器镜像仓库的网络

### 获取项目

```bash
git clone https://github.com/ThouGyeongcho/PreFine.git
cd PreFine
```

### 配置环境变量

Linux 或 macOS：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

打开 `.env`，至少修改以下三项：

| 变量 | 要求 | 用途 |
| --- | --- | --- |
| `ADMIN_USERNAME` | 不得为空 | 管理员登录名 |
| `ADMIN_PASSWORD` | 至少 12 个字符，不能保留示例值 | 管理员登录密码 |
| `SESSION_SECRET` | 至少 32 个随机字符，不能保留示例值 | 会话签名密钥 |

`.env.example` 中的 `CHANGE_ME` 值只是待修改标记，保留这些值会导致容器拒绝启动。

### 启动服务

```bash
docker compose pull
docker compose up -d
docker compose ps
```

启动后访问：

- 管理页面：`http://localhost:8000`
- 健康检查：`http://localhost:8000/api/health`

Linux 或 macOS 可执行：

```bash
curl --fail http://localhost:8000/api/health
```

Windows PowerShell 可执行：

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

使用 `.env` 中配置的 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 登录。

如需修改对外端口，在 `.env` 中增加 `APP_PORT`。例如：

```dotenv
APP_PORT=8080
```

修改后通过 `http://localhost:8080` 访问。

### 邮件提醒

邮件提醒是可选功能。未配置时，金额转换和税收日历仍可正常使用。

启用邮件提醒需要在 `.env` 中设置：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=finance@example.com
REMINDER_TO_EMAIL=owner@example.com
SMTP_USE_TLS=false
SMTP_STARTTLS=true
```

`SMTP_USERNAME` 和 `SMTP_PASSWORD` 是否必填取决于邮件服务商。
`SMTP_USE_TLS` 与 `SMTP_STARTTLS` 不能同时设为 `true`。

配置完成后重启容器：

```bash
docker compose up -d
```

随后可在税收日历的工具设置中选择地区、纳税人身份、关注事项和提醒提前天数，
并发送测试邮件验证配置。

### 数据与安全

- 数据默认保存在宿主机的 `./data/prefine.db`，由 `PREFINE_DATA_DIR` 控制宿主机目录。
- 不要删除数据目录；升级前应按照[运行手册](docs/operations.md)完成备份。
- Linux 宿主机默认使用 `PUID=1000`、`PGID=1000`。如果数据目录属于其他用户，请改成对应的用户编号和用户组编号。
- 通过 HTTPS 反向代理访问时，将 `COOKIE_SECURE` 设为 `true`。
- `TRUSTED_PROXY_IPS` 默认留空最安全。仅在单层反向代理直接连接 PreFine，且代理会把 `X-Forwarded-For` 覆盖为一个客户端地址时，才填写代理的准确 IP 地址。
- PreFine 当前按单容器、单进程设计，不要同时运行多个应用副本。

## 升级

升级前先按照[运行手册](docs/operations.md)备份数据库，然后执行：

```bash
docker compose pull
docker compose up -d
curl --fail http://localhost:8000/api/health
```

Windows PowerShell 的健康检查命令：

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

`PREFINE_VERSION=latest` 会跟随 `main` 分支发布的最新镜像。
生产环境建议在 `.env` 中固定已发布版本，例如：

```dotenv
PREFINE_VERSION=0.1.1
```

可用版本请查看 [GitHub 版本发布页](https://github.com/ThouGyeongcho/PreFine/releases)。

## 常用命令

```bash
# 查看运行状态
docker compose ps

# 查看最近 200 行日志并持续跟踪
docker compose logs -f --tail=200 app

# 重启服务
docker compose restart app

# 停止并移除容器与网络
docker compose down
```

`docker compose down` 不会删除 `PREFINE_DATA_DIR` 指向的宿主机数据目录。

## 本地开发

后端需要 Python 3.12。

Linux 或 macOS：

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m uvicorn backend.app.main:create_app --factory --reload
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:create_app --factory --reload
```

前端需要 Node.js 22 和 pnpm 11。

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

前端开发服务器与后端开发服务器需要分别运行。

## 测试

```bash
python -m pytest backend/tests
ruff check backend
pnpm --dir frontend lint
pnpm --dir frontend exec vitest run
pnpm --dir frontend build
pnpm --dir frontend e2e
```

## 相关文档

- [运行、备份与恢复手册](docs/operations.md)
- [版本发布说明](RELEASE_NOTES.md)
- [安全策略](SECURITY.md)
- [项目设计规格](docs/superpowers/specs/2026-07-21-prefine-design.md)

## 许可证与安全

PreFine 使用 [MIT 许可证](LICENSE)发布。

请勿在公开议题中披露安全漏洞。发现安全问题时，请通过
[GitHub 私密漏洞报告](https://github.com/ThouGyeongcho/PreFine/security/advisories/new)
联系维护者。
