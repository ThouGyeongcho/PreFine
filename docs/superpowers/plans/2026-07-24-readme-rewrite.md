# PreFine README 改写实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目根目录 README 改写为重点明确、部署步骤完整、说明文字统一使用中文的项目介绍。

**Architecture:** 只修改文档，不改变应用、镜像或部署行为。README 以使用者阅读顺序组织：先介绍产品价值，再给出首次部署、配置、升级、运维、本地开发和相关文档。

**Tech Stack:** Markdown、Docker Compose、GitHub Container Registry、PowerShell

## Global Constraints

- 说明文字全部使用中文；专有名称、命令、代码、环境变量和路径保持原样。
- 只描述仓库当前已有功能，不增加产品承诺。
- 部署继续使用已发布的 `ghcr.io/thougyeongcho/prefine` 镜像，本地不构建镜像。
- 使用现有 `.env.example` 与 `docker-compose.yml`，不在 README 重复粘贴完整 Compose 文件。
- `SESSION_SECRET` 至少包含 32 个随机字符。
- 数据默认持久化到 `./data/prefine.db`。

---

### Task 1: 重写并验证项目 README

**Files:**
- Modify: `README.md`
- Reference: `.env.example`
- Reference: `docker-compose.yml`
- Reference: `docs/operations.md`
- Reference: `docs/superpowers/specs/2026-07-24-readme-design.md`

**Interfaces:**
- Consumes: 仓库现有镜像地址、环境变量、Docker Compose 服务名、端口和文档链接。
- Produces: 可供最终使用者直接阅读和执行的中文 `README.md`。

- [x] **Step 1: 核对部署事实**

运行：

```powershell
Get-Content -Raw -Encoding utf8 .env.example
Get-Content -Raw -Encoding utf8 docker-compose.yml
Select-String -Path docs/operations.md -Pattern '^#' -Encoding utf8
```

预期：确认镜像地址、必填变量、可选邮件变量、默认端口、数据目录和运行手册章节均与设计说明一致。

- [x] **Step 2: 按确认的信息结构替换 README**

README 必须依次包含：

```text
# PreFine
项目定位
## 简介
## 核心亮点
## Docker 部署
### 环境要求
### 获取项目
### 配置环境变量
### 启动服务
### 邮件提醒
### 数据与安全
## 升级
## 常用命令
## 本地开发
## 测试
## 相关文档
## 许可证与安全
```

首次部署必须给出以下可执行命令：

```bash
git clone https://github.com/ThouGyeongcho/PreFine.git
cd PreFine
cp .env.example .env
docker compose pull
docker compose up -d
```

Windows PowerShell 必须给出：

```powershell
Copy-Item .env.example .env
```

README 必须明确说明修改 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`SESSION_SECRET`，并给出访问地址 `http://localhost:8000` 与健康检查地址 `http://localhost:8000/api/health`。

- [x] **Step 3: 检查内容完整性与中英文一致性**

运行：

```powershell
rg -n "^## (简介|核心亮点|Docker 部署|升级|常用命令|本地开发|测试|相关文档|许可证与安全)$" README.md
rg -n "ADMIN_USERNAME|ADMIN_PASSWORD|SESSION_SECRET|docker compose pull|docker compose up -d|localhost:8000/api/health|PREFINE_VERSION|PREFINE_DATA_DIR|TRUSTED_PROXY_IPS" README.md
rg -n "Container publication|Users pull|For a single-layer|follows main|Before an upgrade|^services:" README.md
```

预期：前两条命令找到所有要求内容；第三条命令无输出，证明旧英文段落和重复的完整 Compose 文件已移除。

- [x] **Step 4: 检查 Markdown 差异**

运行：

```powershell
git diff --check
git diff -- README.md
```

预期：`git diff --check` 无输出；差异只包含经确认的 README 重写。

- [x] **Step 5: 提交 README**

```bash
git add README.md
git commit -m "docs: rewrite Chinese project README"
```
