# PreFine GitHub 发布设计

## 目标

将当前 PreFine 第一版初始化为 Git 仓库，并发布到新的私有 GitHub 仓库 `ThouGyeongcho/PreFine`。默认分支为 `main`，发布后远程仓库应包含完整源码、测试、Docker 部署配置和运行文档，不包含密钥、本地数据库、虚拟环境、依赖目录或构建产物。

## README 结构

保留现有产品说明、功能、本地开发、验证和项目结构，并扩展 Docker 部署章节：

1. 展示复制 `.env.example`、编辑凭据和首次构建启动的命令。
2. 展示查看状态、健康检查、日志、重启、停止和重新构建命令。
3. 说明 `prefine-data` 命名卷、Alembic 启动迁移、非 root 用户和单 Uvicorn worker。
4. 将仓库根目录当前 `docker-compose.yml` 全文原样嵌入 README，确保文档示例与可执行配置一致。
5. 明确必须替换管理员密码与至少 32 字符的会话密钥，SMTP 仍为可选配置。

## Git 历史与分支

1. 在当前目录初始化 Git，初始分支为 `main`。
2. 先单独提交本发布设计，提交信息为 `docs: define github publication design`。
3. README 修改和当前完整第一版源码作为发布提交，提交信息为 `feat: release prefine v1`。
4. 新仓库没有既有基础分支，因此直接推送 `main`，不创建人为的空分支或无意义 Pull Request。

## GitHub 发布

使用已认证的 GitHub CLI 创建私有仓库 `ThouGyeongcho/PreFine`，将本地 `origin` 指向该仓库并推送 `main`。如果同名仓库在执行前已存在，则停止创建并先核对远程内容，绝不覆盖未知历史。

## 安全门禁

提交前执行以下检查：

- 确认 `.gitignore` 排除 `.env`、`.venv`、数据库、缓存、`node_modules`、`dist` 和测试输出。
- 扫描管理员密码、会话密钥和 SMTP 密码引用，只允许环境变量名称、示例占位符与测试专用值。
- 使用 `git status` 和暂存区文件列表确认整个工作区均属于第一版发布范围。
- 重新运行 README/Compose 一致性检查和必要的代码门禁；Docker 运行时仍不可用时，在发布结果中明确保留该验证缺口。

## 成功标准

- 本地分支为 `main`，工作树干净。
- `origin` 为 `https://github.com/ThouGyeongcho/PreFine.git` 或等价认证地址。
- GitHub 仓库可读取，保持私有，默认分支为 `main`。
- 远程最新提交为第一版发布提交。
- README 包含可复制的 Docker 命令和与根目录一致的完整 Compose 文件。
