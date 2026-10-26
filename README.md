# FastAPI Starter Kit

默认**无认证**的异步 FastAPI 模板，带 PostgreSQL、Redis 和独立调度进程。需要登录时，可选用内置密码、手机验证码、邮箱验证码，也可以只接入自己的认证模块。

Python **3.13 / 3.14**，默认开发版本 3.14；依赖使用 uv 和项目 `.venv`。以下命令在仓库根目录执行，需要先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Docker Compose。

## 1. 先跑起来

### 安装依赖、准备配置

```bash
uv sync --locked
cp .env.example .env
# PowerShell：Copy-Item .env.example .env
```

生成两个独立密码，分别填入 `.env` 的 `POSTGRES_PASSWORD`、`REDIS_PASSWORD`：

```bash
uv run --locked python -c "import secrets; print(secrets.token_urlsafe(32)); print(secrets.token_urlsafe(32))"
```

默认 `AUTH_MODULES=[]`，**不用配置 JWT 或发送器**。只维护根目录 `.env`，不要再复制到 `docker/`。

### 启动中间件、初始化空库

```bash
docker compose --env-file .env -f docker/docker-compose-middleware.yaml up -d --wait
uv run --locked python -X utf8 -m alembic upgrade head
```

这是面向新项目的初始化 schema，不能直接套到已有业务库。开发镜像采用 PostgreSQL 18、Redis 8.10；**不要把旧 PostgreSQL 数据目录直接挂到新大版本镜像**。

### 启动后端、验证效果

```bash
uv run --locked python main.py
```

保留这个终端，在另一终端执行（PowerShell 可用 `curl.exe`）：

```bash
curl http://127.0.0.1:8000/api/ping
# 预期："pong"

curl http://127.0.0.1:8000/api/health/ready
# 预期：{"status":"ready","database":"ok","redis":"ok"}
```

开发文档：<http://127.0.0.1:8000/docs>。到这里就有可运行的后端；默认没有注册、登录或 `/users/me` 接口。

停止中间件使用下面命令，**不会删除命名卷中的数据**：

```bash
docker compose --env-file .env -f docker/docker-compose-middleware.yaml down
```

## 2. 需要登录时再选装

### 最短路径：用户名 + 密码

生成一个独立 JWT 密钥：

```bash
uv run --locked python -c "import secrets; print(secrets.token_urlsafe(48))"
```

修改 `.env`，将密钥占位说明替换成刚生成的值，然后重启后端：

```dotenv
AUTH_MODULES=["password"]
AUTH_PASSWORD_IDENTIFIERS=["username"]
JWT_SECRET_KEY=replace-with-a-generated-secret
```

下面多行 curl 命令使用 Bash；PowerShell 用户也可在 `/docs` 的 **Try it out** 中提交相同 JSON。注册一个普通账号：

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"identities":[{"kind":"username","identifier":"demo-user"}],"password":"a-long-demo-password"}'
```

预期 **201**，返回新用户资料。再登录：

```bash
curl -X POST http://127.0.0.1:8000/api/auth/password/token \
  -H 'Content-Type: application/json' \
  -d '{"kind":"username","identifier":"demo-user","password":"a-long-demo-password"}'
```

预期 **200**，返回 `token_type`、`expires_in`、`access_token`。把返回的 token 填入下列占位处：

```bash
curl http://127.0.0.1:8000/api/users/me -H 'Authorization: Bearer <access_token>'
curl -X DELETE http://127.0.0.1:8000/api/auth/token -H 'Authorization: Bearer <access_token>'
```

退出后，该 token 再访问 `/users/me` 返回 **401**。不要把真实密码或 token 写入仓库、命令记录或日志。

### 其他选择

| `AUTH_MODULES` | 能力 | 还需要什么 |
| --- | --- | --- |
| `[]` | 无认证，默认值 | 无认证密钥或发送器 |
| `["password"]` | 用户名 / 手机 / 邮箱 + 密码 | JWT；手机/邮箱注册还需所有权验证 |
| `["phone_otp"]` | 手机 + 验证码，首次登录建号 | JWT、独立验证码密钥、短信发送器 |
| `["email_otp"]` | 邮箱 + 验证码，首次登录建号 | JWT、独立验证码密钥、邮件发送器 |
| 多个 ID | 组合内置方式 | 对应能力的依赖 |
| 自定义 ID | 只用自己的模块也可以 | 在应用中注册自己的 factory |

三种内置实现不是全集，未选择的登录路由和 OpenAPI operation 不会出现。短信/邮件发送器必须接入真实供应商，模板不假装发送成功。

详见 [认证接入教程](docs/auth.md)：选择标识、发送器接入、初始多身份注册及限制。

## 3. 接入自己的认证方式

按 [自定义模块示例](docs/auth.md#自定义模块) 实现 `build_module` 后，在 `api_app.py` 注册它：

```python
from app.http.auth_methods.service_key import build_module
from app.services.auth.modules import AuthModuleFactory
from bootstrap.application import create_app

app = create_app(auth_module_factories=[AuthModuleFactory('service_key', build_module)])
```

随后设置 `AUTH_MODULES=["service_key"]`。这份注册清单可以不包含三个内置模块；需要同时保留时，再加入 `builtin_factories()`。不修改核心身份枚举，也不从环境变量动态导入代码。

## 4. 继续开发

- 普通业务路由放在 `app/http/api`；认证模块显式装配，不放进业务自动发现目录
- 模型和 schema 分别在 `app/models`、`app/schemas`；应用工厂为 `bootstrap/application.py:create_app`
- [运行与开发说明](docs/operations.md)：生产启动、迁移、调度、代理、错误边界、WS 和测试

提交前运行：

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked pytest -q -m "not integration"
```

真实 PostgreSQL/Redis 测试需显式配置隔离服务，参见运行说明；缺服务的 skip 不代表通过。Ruff/basedpyright 以项目配置为准，只处理 warning/error。

许可证：[LICENSE](LICENSE)。
