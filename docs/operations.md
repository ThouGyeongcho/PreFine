# PreFine 运行手册

## 首次部署

PreFine 使用 GHCR 中已发布的镜像。请勿在部署机上运行 Docker 构建命令。

```bash
cp .env.example .env
# 编辑 .env：设置 ADMIN_PASSWORD，并生成至少 32 字符的 SESSION_SECRET
docker compose up -d
```

容器以非 root 用户运行；入口点会根据 `PUID` 和 `PGID`（默认均为 `1000`）调整 `/data` 的访问权限。`PREFINE_DATA_DIR` 配置挂载到 `/data` 的主机目录，默认值为 `./data`；SQLite 数据库文件位于该目录的 `prefine.db`。

## HTTPS 与 Cookie

直接使用本地 HTTP 时保持 `COOKIE_SECURE=false`。通过 HTTPS 反向代理对外提供服务时，将其设为 `true`，并让代理原样转发 `Host`；写操作会校验浏览器提供的 `Origin` 是否与当前主机一致。

## 邮件提醒

要启用邮件，必须同时设置 `SMTP_HOST`、`SMTP_PORT`、`SMTP_FROM` 和 `REMINDER_TO_EMAIL`。需要认证时再设置 `SMTP_USERNAME` 和 `SMTP_PASSWORD`。

- 直连 TLS：`SMTP_USE_TLS=true`
- STARTTLS：`SMTP_STARTTLS=true`

二者不能同时启用。未配置 SMTP 时，测试邮件按钮保持禁用。

## 备份与恢复

备份或恢复前先停止应用，避免复制到不完整的 SQLite 状态。Docker Compose 会读取 `.env` 来插值 `PREFINE_DATA_DIR`，但直接运行备份命令的主机 shell 不会。以下命令通过 `docker compose config --environment` 读取 Compose 实际用于插值的值；未设置时回退到默认目录。

### POSIX sh

备份：

```sh
prefine_data_dir="$(
  docker compose config --environment |
    awk -F= '$1 == "PREFINE_DATA_DIR" { print substr($0, index($0, "=") + 1); exit }'
)"
if [ -z "$prefine_data_dir" ]; then
  prefine_data_dir="./data"
fi
backup_dir="./backups"

docker compose stop app
mkdir -p "$backup_dir"
cp "$prefine_data_dir/prefine.db" "$backup_dir/prefine.db"
docker compose start app
```

恢复：

```sh
prefine_data_dir="$(
  docker compose config --environment |
    awk -F= '$1 == "PREFINE_DATA_DIR" { print substr($0, index($0, "=") + 1); exit }'
)"
if [ -z "$prefine_data_dir" ]; then
  prefine_data_dir="./data"
fi
backup_dir="./backups"

docker compose stop app
cp "$backup_dir/prefine.db" "$prefine_data_dir/prefine.db"
docker compose start app
curl http://localhost:8000/api/health
```

### PowerShell

备份：

```powershell
$prefineDataDirLine = docker compose config --environment |
  Where-Object { $_ -like "PREFINE_DATA_DIR=*" } |
  Select-Object -First 1
if ($prefineDataDirLine) {
  $prefineDataDir = $prefineDataDirLine.Substring($prefineDataDirLine.IndexOf("=") + 1)
}
if ([string]::IsNullOrEmpty($prefineDataDir)) {
  $prefineDataDir = ".\data"
}
$backupDir = ".\backups"

docker compose stop app
New-Item -ItemType Directory -LiteralPath $backupDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path -Path $prefineDataDir -ChildPath "prefine.db") -Destination (Join-Path -Path $backupDir -ChildPath "prefine.db")
docker compose start app
```

恢复：

```powershell
$prefineDataDirLine = docker compose config --environment |
  Where-Object { $_ -like "PREFINE_DATA_DIR=*" } |
  Select-Object -First 1
if ($prefineDataDirLine) {
  $prefineDataDir = $prefineDataDirLine.Substring($prefineDataDirLine.IndexOf("=") + 1)
}
if ([string]::IsNullOrEmpty($prefineDataDir)) {
  $prefineDataDir = ".\data"
}
$backupDir = ".\backups"

docker compose stop app
Copy-Item -LiteralPath (Join-Path -Path $backupDir -ChildPath "prefine.db") -Destination (Join-Path -Path $prefineDataDir -ChildPath "prefine.db") -Force
docker compose start app
Invoke-RestMethod http://localhost:8000/api/health
```

不要只复制 `-wal` 或 `-shm` 文件。

## 升级与诊断

升级镜像或固定版本前请先备份数据库：

```bash
docker compose pull
docker compose up -d

# 固定版本：在 .env 中设置 PREFINE_VERSION=0.1.0
docker compose ps
docker compose logs --tail=200 app
docker compose exec app python -m alembic -c backend/alembic.ini current
```

`PREFINE_VERSION=latest` 会拉取最新发布版本。健康检查位于 `GET /api/health`；容器启动时会运行 Alembic 迁移，迁移失败时 Web 服务不会启动。
