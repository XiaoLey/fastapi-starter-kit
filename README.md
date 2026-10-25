# FastAPI Starter Kit

带用户名密码认证、可替换短信认证、PostgreSQL、Redis 和独立调度进程的异步 FastAPI 模板。

## 运行基线

- Python **3.13 / 3.14**，默认开发版本 3.14，使用 uv 和 `.venv`
- PostgreSQL；新的开发中间件采用 **18**，旧 PostgreSQL 15 的数据库大版本升级与应用 schema 升级分开处理
- Redis；开发中间件采用 **8.10**，客户端版本由 `uv.lock` 锁定
- Windows / Linux；macOS 和 Python 3.15 不在本轮验收承诺范围内

项目保留服务层与 Provider，不包含前端、管理后台、短信供应商 SDK、刷新 token、密码找回或第三方 OAuth 授权服务器。密码表单兼容 OAuth2 的提交形状，不代表实现了完整 OAuth 授权服务器。

## 快速开始

以下命令在仓库根目录执行。安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后：

### 1. 安装依赖

```bash
uv sync --locked
```

uv 会按 `.python-version` 选择 Python。首次安装可能需要下载 Python；不要把其他项目或 Conda 环境当作本项目的依赖基线。

### 2. 配置环境

```bash
cp .env.example .env
# PowerShell 使用：Copy-Item .env.example .env

# 分别生成 JWT 密钥、数据库密码、Redis 密码；不要共用同一个值
uv run --locked python -c "import secrets; print(secrets.token_urlsafe(48))"
```

编辑 `.env`，替换 `JWT_SECRET_KEY`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD` 的占位值，再启动服务。JWT 密钥至少 32 个 UTF-8 字节；已知演示值、占位密钥和缺失密钥都会被拒绝。

`.env` 从仓库根定位，进程环境优先。只维护根目录这一份文件，**不要再复制到 docker/.env**。

### 3. 启动开发中间件

需要本机或独立测试 VM 已安装 Docker Compose：

```bash
docker compose --env-file .env -f docker/docker-compose-middleware.yaml up -d
docker compose --env-file .env -f docker/docker-compose-middleware.yaml ps
```

开发端口只绑定宿主 `127.0.0.1`。数据库和 Redis 使用独立命名卷；停止服务不会自动删除数据：

```bash
docker compose --env-file .env -f docker/docker-compose-middleware.yaml down
```

**不能将 PostgreSQL 15 的旧数据卷直接挂到 18。** 本配置采用 18 镜像的数据目录约定，命名卷挂载到 `/var/lib/postgresql`。需要保留旧数据时先备份并单独规划 dump/restore 或 pg_upgrade，不删除旧目录试错。

### 4. 数据库迁移

```bash
uv run --locked python -X utf8 -m alembic upgrade head
```

所有 Alembic 入口（包括 revision/check/downgrade）都使用 `python -X utf8 -m alembic`，确保 Windows 下历史 SQL 正确解码。

初始迁移包含历史扩展与 ICU collation，需要具备创建这些对象权限的迁移角色。日常应用角色可以单独收紧权限；不要把运行权限与初始化权限混为一谈。

### 5. 启动 Web

```bash
uv run --locked python main.py
```

默认地址为 `http://127.0.0.1:8000`；示例 `.env` 启用开发 reload 和 `/docs`。`APP_DEBUG` 不会向客户端开启 traceback 响应。

### 6. 跑通认证闭环

用户名密码注册不依赖短信：

```bash
curl -X POST http://127.0.0.1:8000/api/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo-user","password":"a-long-demo-password","nickname":"演示用户","gender":"unknown"}'

curl -X POST http://127.0.0.1:8000/api/auth/token/password \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=demo-user' \
  --data-urlencode 'password=a-long-demo-password'

# 将返回的 access_token 填入，不要把真实 token 写入仓库或日志
curl http://127.0.0.1:8000/api/users/me -H 'Authorization: Bearer <access_token>'
curl -X DELETE http://127.0.0.1:8000/api/auth/token -H 'Authorization: Bearer <access_token>'
```

注册返回 201；登录返回 `token_type`、`expires_in`、`access_token`。退出后旧 token 不能继续访问受保护接口。PowerShell 用户可使用 `curl.exe`，避免其历史别名行为。

## API 与账号规则

所有业务路径位于 `APP_API_PREFIX` 下，默认 `/api`：

| 方法 / 路径 | 行为 |
| --- | --- |
| POST `/users` | 用户名密码注册；手机号与 `cellphone_verification_code` 成对可选 |
| POST `/auth/token/password` | 表单登录；username 可填用户名或手机号，grant_type 可省略 |
| POST `/auth/token/cellphone` | JSON 手机号验证码登录；首次登录创建普通无密码账号 |
| POST `/auth/verification-codes/cellphone` | JSON `cellphone` + 必填 `purpose: register\|login` |
| DELETE `/auth/token` | 吊销当前有效 token；不承诺重复退出幂等 |
| GET `/auth/token/status` | 同时检查 token 和账号可用状态 |
| GET `/users/me` | 只返回当前账号的公开资料，不含密码哈希 |
| GET `/ping` | JSON 字符串 `pong`，不依赖 Redis |
| GET `/health/live` | 进程存活，200 |
| GET `/health/ready` | DB/Redis 就绪，200 或 503 |

新用户名为 3–64 位 ASCII 字母、数字、`_`、`.`、`-`，去首尾空白，保留大小写，不能是合法手机号形态。新密码为 12–128 个 Unicode 字符，不 trim。昵称和 gender 仍必填，昵称最多 255 字符，gender 为 `male` / `female` / `unknown`。

手机号规范形式为 11 位 ASCII 数字、号段 `1[3-9]`，允许去首尾空白，不接受 `+86` 或 Unicode 数字。验证码为 6 位数字字符串，保留前导零。手机号/code 同时省略或同时 null 表示不绑定，只给一项或空串会校验失败。

用户名与手机号在全部历史记录中唯一，软删除后也不自动复用。禁用/已删除身份不会通过手机号登录自动复活。注册不能写入 `is_admin`、state 等内部属性。

访问 token 默认 30 分钟，使用 HS256、固定 issuer/audience 和必需声明；单 token 吊销依赖 Redis。旧 bcrypt 可登录后升级 Argon2，但超过旧 bcrypt **72 个 UTF-8 字节**的输入不截断，需要下游自行安排重设。已有短密码的兼容登录不套用新注册的最小长度。

## 短信接入

默认 `SMS_ENABLED=false`，发送验证码、手机号登录和带手机号注册明确返回 503，不伪造发送成功；普通用户名密码注册仍可用。

启用前必须：

1. 生成独立 `SMS_CODE_SECRET_KEY`，至少 32 字节，不能与 JWT 密钥共用
2. 实现 `app.services.sms.sms_sender.SmsSender` 协议
3. 在 `api_app.py` 或自己的应用组装模块中，把 **创建新实例的 callable** 作为 `sms_sender_factory` 传给 `create_app`
4. 最后设置 `SMS_ENABLED=true`

发送接口为：

```python
async def send_verification_code(
    self, *, cellphone: str, code: str,
    purpose: Literal['register', 'login'], expires_in: int,
) -> None:
    ...

async def aclose(self) -> None:
    ...
```

正常返回仅表示供应商接受，不保证最终送达；明确失败抛 `SmsSendError`。实现须支持协作取消。每次 lifespan 由 factory 创建新实例，应用在退出/启动失败时关闭；不要注入模块级共享实例，也不要假定关闭后可复活。

验证码默认 300 秒、5 次错误后失效，同 challenge 并发只能成功消费一次，注册码和登录码不能混用。发送冷却按手机号/用途 60 秒，固定窗口每小时 5 次；同 IP 跨用途合计每分钟 5 次、每小时 20 次。发送失败仍消耗已扣配额。

发送超时或服务返回 503 **不表示短信一定没发送**；供应商或 Redis 的结果可能未知，不自动重发。验证码消费后数据库提交失败不会恢复旧码，需要重新发送。测试 fake sender 只位于测试中，不提供默认打印验证码的生产发送器。

## 配置与网络边界

| 配置 | 默认 / 说明 |
| --- | --- |
| `APP_ENV` | development；production 拒绝 DEBUG、演示依赖密码及默认 Redis 前缀 |
| `APP_QPS` | 10，每 IP 跨业务路径固定窗口每秒配额；回环地址也不豁免 |
| `APP_CORS_ORIGINS` | JSON 列表 `[]`；前端来源需显式填写 |
| `APP_CORS_ALLOW_CREDENTIALS` | false；true 不能搭配 `*` origin |
| `APP_TRUSTED_PROXY_IPS` | 空，不信任转发头；配置逗号分隔的 IP/CIDR |
| `JWT_TTL` / `JWT_ISSUER` / `JWT_AUDIENCE` | 30 分钟 / fastapi-starter-kit / api |
| `REDIS_KEY_PREFIX` | 开发 fastapi；生产须改为应用/环境独有值，同应用 worker 间相同 |
| `POSTGRES_POOL_SIZE` / `POSTGRES_MAX_OVERFLOW` | 4 / 4；最大连接容量乘以 worker 数 |
| `POSTGRES_POOL_TIMEOUT` / `POSTGRES_POOL_RECYCLE` | 30 / 1800 秒；启用 pre-ping |
| `LOG_LEVEL` | INFO；stdout 默认，只有显式 `LOG_PATH` 才写文件 |

Redis 故障时认证、限流和封禁不能静默失效，业务返回 503，不退化为进程内限流。固定窗口允许边界突发，不是任意滚动一秒的严格 QPS。登录额外按 IP 5 次/分钟、注册 3 次/分钟。

应用只采用服务器规范化后的 `scope.client`，不自行信任 `X-Real-IP` / `X-Forwarded-For`。`main.py` 显式传入 Uvicorn 信任配置；如果直接启动 Uvicorn，须自己提供等价参数，应用的 `APP_TRUSTED_PROXY_IPS` 无法反向配置服务器外层：

```bash
uv run --locked uvicorn api_app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Nginx 单层代理应覆盖转发头为实际来源，并只让受信网关访问后端；多层代理先配置可信 real_ip 来源再转发。不要配置 `*`。浏览器跨域来源示例：`APP_CORS_ORIGINS='["http://localhost:5173"]'`。

健康路由不走封禁或业务配额，ready 有共同 2 秒探测预算，只返回依赖状态。探针访问范围由部署网络限制。

## 错误与 WebSocket 扩展

业务错误模型为 `{code, message, detail?}`；422 detail 只保留字段位置和错误类型。常用状态：401 身份失败、403 权限/封禁、409 重复身份、422 输入/验证码错误、429 超限、503 依赖/短信不可用。`WWW-Authenticate`、`Retry-After` 保持标准头值。

ready 使用独立状态模型；CORS preflight 和已经开始发送的响应不强行改成 JSON 错误。日志不转储密码、token、验证码、SQL 参数、供应商异常输入或局部变量。

模板没有默认 WS 业务端点，只提供鉴权、限流与异常边界。握手与消息配额分离，消息处理显式调用 `verify_ws_message_limit`。握手可用 HTTP 429/503 拒绝；服务端不支持 denial 扩展时，在 accept 前关闭。已建立连接分别使用 1008（策略限制）、1013（依赖故障）、1011（内部错误）。

WS 仅内置非浏览器客户端的 Authorization 头 Bearer，不提供浏览器 query token/subprotocol 凭据方案。WS 的 DB 鉴权/每次操作使用短事务，不能为整条连接持有 HTTP `get_db`，也不能在并发任务间共享 AsyncSession。

## 调度和生产启动

```bash
uv run --locked python scheduler.py
```

在 `bootstrap/scheduler.py:register_asyncio_jobs` 集中注册协作异步任务，使用 `runner.wrap` 跟踪在途作业；模板不预置业务任务。Web worker 不启动 scheduler，调度进程默认只部署一份，不承诺多副本 exactly-once。

Linux 收到 SIGINT/SIGTERM 后先停止新任务，给予在途协作任务 30 秒正常完成窗口，随后取消并等待收尾。Windows 支持 Ctrl+C；同步阻塞线程不能被 asyncio 强杀，30 秒不是任意业务任务的硬退出保证。

生产先设置 `APP_DEBUG=false`、真实独立凭据与 Redis 前缀，单独执行迁移，再启动：

```bash
uv run --locked python -X utf8 -m alembic upgrade head
bash start_web.sh
# 独立调度进程，另行启动
bash start_scheduler.sh
```

两个 POSIX 脚本定位仓库目录、使用 `.venv`、显式 production、exec 转交信号；不会安装依赖或自动迁移。Windows 使用 Python/uv 入口，不把 Bash 脚本与 POSIX 信号机制视为 Windows 等价部署方案。多 worker 文件日志应由下游选择合适的进程外收集策略。

## 验证与二次开发

```bash
uv lock --check
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked pytest -q -m "not integration"
```

Ruff 与 basedpyright 分别以 `ruff.toml`、`pyrightconfig.json` 为准，information/hint 不作为修正目标。历史生成迁移不重排。

测试集中在认证、迁移、运行时和进程四组核心流程，用注册→登录→资料→退出等组合验证相关模块，不追求覆盖率或逐 helper/参数穷举。共享准备放在 `tests/conftest.py`，仅短信供应商使用最小 fake；数据库、验证码脚本和限流使用真实服务，不在替身中重写算法。

真实集成测试必须显式设置 `TEST_DATABASE_URL`、`TEST_REDIS_URL`，并使用独立测试服务：

```bash
# URL 中的用户和密码自行替换；control 库须已存在，角色需可创建数据库
export TEST_DATABASE_URL='postgresql+asyncpg://test_user:test_password@127.0.0.1:5432/fastapi_test_control'
export TEST_REDIS_URL='redis://:test_password@127.0.0.1:6379/15'
uv run --locked python -X utf8 -m pytest -q -m integration
```

测试只在 `fastapi_test_*` control URL 上创建随机命名的新库，结束时删除本次新库；不迁移/清空传入 control 库。Redis 只清理随机测试前缀，不执行 FLUSHDB。不要传生产 URL。缺服务时 skip 不代表集成验收通过。

修改模型/SQL 源后生成新迁移，而不是修改旧 revision：

```bash
uv run --locked python -X utf8 -m alembic revision --autogenerate -m "describe schema change"
uv run --locked python -X utf8 -m alembic check
```

DDDL 源/历史比较不能检测实际数据库中被人工删改的 trigger/function/view，必须另验 PostgreSQL catalog 和行为。新增视图需登记 DDL；删除其登记不会自动生成 DROP，应显式设计反向迁移。

应用目录仍为 `app/http`、`app/models`、`app/schemas`、`app/services`、`app/providers`、`app/support`；入口为 `bootstrap/application.py:create_app`。配置与运行资源属于应用，不再从旧 `config.xxx.settings` 或 Provider 模块导入全局 client。

旧项目升级与回退限制见 [迁移指南](docs/migration-guide.md)。项目许可证见 [LICENSE](LICENSE)。
