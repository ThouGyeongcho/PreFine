# 财务工具包运行手册

## 首次部署

1. 复制 `.env.example` 为 `.env`。
2. 设置独立的 `ADMIN_PASSWORD`，并为 `SESSION_SECRET` 生成至少 32 个随机字符。
3. 执行 `docker compose up --build -d`。
4. 打开 `http://localhost:8000`，或通过 `GET /api/health` 检查状态。

应用在每次启动时先执行 Alembic 迁移；迁移失败时不会启动 Web 服务。SQLite 数据保存在命名卷 `finance-toolkit-data` 的 `/data/finance-toolkit.db` 中。容器以非 root 用户运行，并且 Uvicorn 固定为一个 worker，以避免计划任务和提醒重复执行。

## HTTPS 与 Cookie

直接使用本地 HTTP 时保持 `COOKIE_SECURE=false`。通过 HTTPS 反向代理对外提供服务时，将其设为 `true`，并让代理原样转发 `Host`；写操作会校验浏览器提供的 `Origin` 是否与当前主机一致。

## 邮件提醒

要启用邮件，必须同时设置 `SMTP_HOST`、`SMTP_PORT`、`SMTP_FROM` 和 `REMINDER_TO_EMAIL`。需要认证时再设置 `SMTP_USERNAME` 与 `SMTP_PASSWORD`。

- 直连 TLS：`SMTP_USE_TLS=true`
- STARTTLS：`SMTP_STARTTLS=true`

二者不能同时启用。保存税务身份、关注事项、默认地区和提醒天数后，可在税收日历底部发送测试邮件。未配置 SMTP 时，测试邮件按钮保持禁用。

## 备份与恢复

备份前先停止应用，避免复制到一半的数据库状态：

```bash
docker compose stop app
docker run --rm -v finance-toolkit-data:/data -v "$PWD":/backup alpine \
  cp /data/finance-toolkit.db /backup/finance-toolkit.db
docker compose start app
```

恢复时同样先停止应用，将备份数据库复制回命名卷，再启动并检查 `/api/health`。不要只复制 `-wal` 或 `-shm` 文件。

## 升级与诊断

```bash
docker compose pull
docker compose up --build -d
docker compose ps
docker compose logs --tail=200 app
docker compose exec app python -m alembic -c backend/alembic.ini current
```

健康响应只包含应用、数据库、调度器和版本状态。12366 暂时不可用时，已有缓存仍会展示并标记为过期；首次同步且没有缓存时会返回可重试的不可用提示。
