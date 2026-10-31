# 运行与开发说明

首次启动见 [README](../README.md)，普通业务示例见[开发指南](development.md)，认证选择和自定义方式见 [认证接入教程](auth.md)。本文保留二次开发和部署需要的边界，不是额外的首次启动步骤。

## 配置与运行资源

根 `.env` 从项目目录定位，进程环境优先；不要复制 `docker/.env`。配置由 `config/settings.py` 定义；应用工厂只组装，每次 lifespan 创建并关闭当前应用自己的运行资源，不导出全局数据库/Redis/HTTP 客户端。

| 配置 | 默认 / 说明 |
| --- | --- |
| `APP_ENV` / `APP_DEBUG` | development / false；示例 dotenv 开发开启文档和 reload，production 拒绝 DEBUG |
| `APP_API_PREFIX` | `/api` |
| `AUTH_MODULES` | `[]`，默认无认证；只选择代码已注册 ID，不接受动态导入路径 |
| `APP_QPS` | 10，每 IP 跨业务路径共享的固定窗口每秒配额，回环也不豁免 |
| `APP_CORS_ORIGINS` | JSON 列表 `[]` |
| `APP_CORS_ALLOW_CREDENTIALS` | false；开启后不能使用 `*` origin |
| `APP_TRUSTED_PROXY_IPS` | 空；逗号分隔 IP/CIDR，默认不信任转发头 |
| `REDIS_KEY_PREFIX` | fastapi；生产必须改为应用/环境独有值，同应用 worker 共享 |
| `POSTGRES_POOL_SIZE` / `POSTGRES_MAX_OVERFLOW` | 4 / 4，总连接容量乘以 worker 数 |
| `POSTGRES_POOL_TIMEOUT` / `POSTGRES_POOL_RECYCLE` | 30 / 1800 秒，启用 pre-ping |
| `JWT_TTL` / `JWT_ISSUER` / `JWT_AUDIENCE` | 30 分钟 / fastapi-starter-kit / api，仅选择本地 token 能力时需要有效 JWT 密钥 |
| `AUTH_CODE_TTL_SECONDS` / `AUTH_CODE_MAX_ATTEMPTS` / `AUTH_CODE_SEND_INTERVAL_SECONDS` | 300 / 5 / 60；验证码能力才要求独立验证码密钥 |
| `LOG_LEVEL` | INFO，默认 stdout；显式 LOG_PATH 才写文件 |

零认证不等于零基础设施：数据库、Redis、HTTP 客户端与业务限流继续可用。不启用认证时不创建认证发送器、不要求认证密钥；生产的数据库/Redis 凭据与 namespace 安全校验仍生效。

## 迁移与数据

```bash
uv run --locked python -X utf8 -m alembic upgrade head
```

所有 Alembic 命令均使用 `python -X utf8 -m alembic`，保证 Windows 历史 SQL 正确解码。初始化只创建表、原生 enum 和实际使用的更新时间函数/触发器，不预装业务扩展，迁移角色需要相应权限。目标 PostgreSQL 实例须提供 `users.nickname` 使用的 `zh-x-icu` collation；迁移只引用它，不执行 `CREATE COLLATION`。初始化只用于全新数据库，不能套用到已有业务库。

已经应用的 revision 不会重复执行。派生项目应保留自己的迁移历史，后续变更追加 revision，不复制模板的初始化文件覆盖已有历史。

本模板面向全新数据库，不提供旧 API/旧账号/bcrypt 兼容或旧库重置脚本。users 仅保存主体资料，auth_identities 保存开放身份域的归属，密码凭据是内置密码模块自己的表。

**启用配置不改变 schema。** 提交的迁移包含随源码交付的表，默认无 auth 时认证表可为空；切换模块不会跳过 revision 或删表。派生项目裁剪源码或新增模块表时，维护自己的迁移，不按运行环境临时生成不同历史。

模型或 SQL 源修改后生成迁移，不手改生成产物：

```bash
uv run --locked python -X utf8 -m alembic revision --autogenerate -m "describe schema change"
uv run --locked python -X utf8 -m alembic check
```

生成的迁移把模型附属 DDL 安排在建表之后、回退删表之前；初始化回退额外清理原生 enum。后续 schema 变化仍须检查生成结果并在可销毁数据库演练，不把 downgrade 当作无损生产回退。

DDDL 插件比较 SQL 源与历史快照，不能检测数据库实际被人工删改的 function/trigger/view。新增或删除 DDL 都要验证实际 catalog 和行为；移除登记不会自动生成 DROP。不要在真实数据库上做 base/head 往返演练。

开发 Compose 端口只绑定 127.0.0.1；使用命名卷，down 不删数据。PostgreSQL 大版本升级另做备份与 dump/restore 或 pg_upgrade，不能直接把旧数据目录挂给 18。不要用删除卷解决未知迁移问题。

### 按需使用 PostgreSQL 扩展

扩展按实际业务需要启用，先确认服务器提供该扩展、部署环境允许安装，以及迁移角色具有所需权限。常见需求例如：

- 模糊搜索或 trigram 索引：`pg_trgm`
- 忽略重音字符：`unaccent`
- GiST / GIN 索引中的普通标量字段：`btree_gist` / `btree_gin`

需要时，在 `app/models/base_model.py` 的 `Base.get_init_sql_alembic_ddls()` 中登记扩展 DDL，按上述流程生成并检查迁移，确保安装先于依赖它的索引或其他对象。不要只在数据库中手工安装，也不要在应用每次启动时安装。

PostgreSQL 已内建 `gen_random_uuid()`，普通随机 UUID 不需要 `uuid-ossp`。其他能力及安装要求见 [PostgreSQL 官方扩展目录](https://www.postgresql.org/docs/current/contrib.html)。

## 代理、限流和错误

应用使用服务器规范化后的 `scope.client`，不自行信任 X-Real-IP / X-Forwarded-For。普通 HTTP/WS 业务路由由标准 `APIRouter` 显式组合，继承来源封禁和 APP_QPS；不自动要求登录。健康探针独立，不走业务封禁和配额。中间件显式登记，CORS 保持在错误边界外层。`main.py` 显式传入 Uvicorn 信任配置并关闭原始 access log；直接启动 Uvicorn 时需自己提供等价边界：

```bash
uv run --locked uvicorn api_app:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Nginx 单层代理应覆盖转发头为实际来源，只让受信网关访问后端；多层代理先配置可信 real_ip 来源再转发。不要配置 `*`。浏览器来源示例：`APP_CORS_ORIGINS='["http://localhost:5173"]'`。

Redis 故障时认证、限流和封禁返回 503，不静默降级到进程内算法。固定窗口允许窗口边界突发，不是任意滚动一秒的严格 QPS。

| 路由 | 语义 |
| --- | --- |
| GET `/api/ping` | JSON 字符串 pong，不依赖 Redis |
| GET `/api/health/live` | 进程存活，200 |
| GET `/api/health/ready` | DB/Redis 共同 2 秒预算，200 或 503 |

健康路由定义在 `app/http/health.py`；探针独立于业务封禁和配额，部署时限制其访问范围。

业务错误统一 `{code,message,detail?}`。422 detail 保留字段位置和错误类型；作者在 Pydantic 校验器中显式抛出的 `SafeValueError` 可额外提供固定安全说明，普通校验/第三方错误文本、input 和 ctx 不回显。未知异常及内部模型/响应错误仍返回固定 500。常用状态：401 身份失败、403 权限/封禁、409 身份占用、422 输入/证明错误、429 超限、503 依赖/交付不可用。WWW-Authenticate、Retry-After 保持标准头值。

例如，生产配置误开 DEBUG 时会明确提示 `Production requires APP_DEBUG=false`，不会打印配置值。用户名注册缺少密码时返回：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "输入校验失败",
  "detail": [{"loc": ["body"], "type": "value_error", "message": "Username registration requires a password"}]
}
```

ready 使用独立状态模型；CORS preflight 和已开始发送的响应不强行改写。`APP_DEBUG` 仅控制 docs/OpenAPI 与 reload，不向客户端开启 traceback。未知异常日志只记录异常类型和代码位置，不记录异常文本、输入或局部值；主入口关闭 Uvicorn 原始 access log，并抑制 HTTPX/httpcore INFO/DEBUG 的 URL 日志。适配器自行记录的信息也须遵守不含秘密的边界。排查时可使用 `.vscode/launch.json` 中的 **Debug FastAPI** 或 **Debug Scheduler** 配置，在 VS Code Run and Debug 的 Breakpoints 面板启用 Raised Exceptions，按调用栈定位失败位置。

## WebSocket 扩展

模板不预置 WS 业务端点。共用本地 token 的鉴权支持非浏览器 Authorization 头 Bearer，不提供浏览器 query token/subprotocol 凭据方案。

握手和消息配额分离，消息处理显式调用 `verify_ws_message_limit`。握手可用 HTTP 429/503 拒绝；不支持 denial 扩展时在 accept 前关闭；连接建立后使用 1008（策略）、1013（依赖）、1011（内部失败）。

数据库鉴权/每次操作使用短会话；不要为整个 WS 连接持有 HTTP `get_db`，也不能在并发任务间共享 AsyncSession。自定义非 JWT 方式自行提供匹配的鉴权依赖，不能把禁用 auth 当作通过认证。

## 调度与生产启动

本地调度入口：

```bash
uv run --locked python scheduler.py
```

在 `bootstrap/scheduler.py:register_asyncio_jobs` 显式登记任务；模板不预置业务任务。新增协作异步作业时使用 `runner.wrap`，使停止流程能够等待在途任务：

```python
async def refresh_cache() -> None:
    ...  # 替换为具体业务操作


def register_asyncio_jobs(scheduler: AsyncIOScheduler, runner: JobRunner) -> None:
    scheduler.add_job(runner.wrap(refresh_cache), 'interval', minutes=5, id='refresh-cache')
```

调度器是独立进程，Web worker 不启动 scheduler；默认独立进程单实例，不承诺多副本 exactly-once。它不提供 Web 应用的 `Resources`。需要数据库或 Redis 的任务应自行创建并关闭所需资源，按任务边界使用短会话；不要假设可复用 Web worker 的会话或客户端。

Linux SIGINT/SIGTERM 停止新任务后给予在途任务 30 秒完成窗口，随后取消并等待收尾；Windows 支持 Ctrl+C。阻塞同步线程不能被 asyncio 强杀，不能把 30 秒理解为任意业务的硬退出保证。

生产显式配置 APP_ENV=production、APP_DEBUG=false、独立真实依赖密码和 Redis 前缀；认证按实际选择配置。同步依赖、独立迁移后再启动：

```bash
uv sync --locked
uv run --locked python -X utf8 -m alembic upgrade head
bash start_web.sh
# 独立进程，另行启动
bash start_scheduler.sh
```

POSIX 脚本定位仓库、使用 `.venv`、exec 转交信号，不安装依赖或自动迁移。Windows 使用 Python/uv 入口，不承诺 Bash/POSIX 信号的等价部署。当前验收平台为 Windows/Linux、Python 3.13/3.14，不包括 macOS 或 Python 3.15。

## 核心验证

静态与不依赖服务的装配测试：

```bash
uv lock --check
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked python -X utf8 -m pytest -q -m "not integration"
```

真实集成测试只使用独立开发/测试服务，不得指向生产。可用已有的开发 Compose 首次启动 PostgreSQL/Redis，并创建一次 control 库 `fastapi_test_control`；这仅适用于本地隔离环境：

```bash
docker compose --env-file .env -f docker/docker-compose-middleware.yaml up -d --wait
docker compose --env-file .env -f docker/docker-compose-middleware.yaml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE fastapi_test_control;"'
```

若 control 库已存在，跳过创建命令。测试连接的 PostgreSQL 角色必须可连接该库并有 `CREATEDB` 权限；测试不会自动创建或清空 control 库。下面是 Bash 环境设置，用户名和密码使用该隔离服务的凭据，密码中的 URL 保留字符需 percent-encode：

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://<CREATEDB_USER>:<URL_ENCODED_PASSWORD>@127.0.0.1:5432/fastapi_test_control'
export TEST_REDIS_URL='redis://:<URL_ENCODED_PASSWORD>@127.0.0.1:6379/15'
uv run --locked python -X utf8 -m pytest -q
```

PowerShell 用 `$env:TEST_DATABASE_URL='...'`、`$env:TEST_REDIS_URL='...'`。control 库需已存在，角色需有建库权限；不要传生产 URL。

测试只在 fastapi_test_* control URL 上创建随机新库，结束时删除本次新库，**不迁移/清空 control 库**。Redis 只清随机前缀，不执行 FLUSHDB。缺服务 skip 不代表集成验收通过；Linux 专属进程测试在 Windows 跳过。

长期测试围绕认证、数据库、运行时、进程四组核心组合，不追求逐函数/字段覆盖率。共享准备集中 conftest.py，外部发送用最小 fake，数据库、验证码和限流算法使用真实服务；不为测试拆生产模块。Ruff 和 basedpyright 以项目配置为准，只处理 warning/error，忽略 information/hint。
