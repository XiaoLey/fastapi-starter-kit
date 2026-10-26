# 认证接入教程

先完成 [README 的默认启动](../README.md#1-先跑起来)。认证默认关闭；下面按需要选择，不必同时接入三个内置模板。

## 选择内置方式

在根 `.env` 设置 `AUTH_MODULES`，重启后端生效：

```dotenv
# 用户名密码；不需要短信、邮件或验证码密钥
AUTH_MODULES=["password"]
AUTH_PASSWORD_IDENTIFIERS=["username"]

# 仅手机验证码：AUTH_MODULES=["phone_otp"]
# 仅邮箱验证码：AUTH_MODULES=["email_otp"]
# 组合：AUTH_MODULES=["password","phone_otp","email_otp"]
```

这些内置方式都需要独立随机 `JWT_SECRET_KEY`。密钥生成方法见 README；没有默认生产密钥。未知或重复模块 ID 会启动失败，不会静默退回无认证。

密码模块可设置 `AUTH_PASSWORD_IDENTIFIERS=["username","phone","email"]`，也可只选其中一部分。选择 phone/email 后，注册仍须验证联系方式，按下一节接入发送器；**不必同时启用对应 OTP 登录**。

### 内置 API

全部采用 JSON，路径位于 `APP_API_PREFIX`（默认 `/api`）下：

| 接口 | 请求 / 行为 |
| --- | --- |
| POST `/auth/register` | 初始注册，返回 201 和用户资料 |
| POST `/auth/password/token` | `kind`、`identifier`、`password` |
| POST `/auth/phone/codes/register` 或 `/login` | `{"phone":"13800000000"}` |
| POST `/auth/phone/token` | `phone`、`verification_code` |
| POST `/auth/email/codes/register` 或 `/login` | `{"email":"alice@example.com"}` |
| POST `/auth/email/token` | `email`、`verification_code` |
| GET `/auth/token/status` | 检查当前 token 和账号状态 |
| DELETE `/auth/token` | 吊销当前有效 token，不承诺重复退出幂等 |
| GET `/users/me` | 当前用户资料白名单，不返回认证身份或秘密 |

只有选中的能力才有对应路由：例如只开 phone_otp 时没有密码登录；只开 phone 密码时有 register 发码，但没有 phone OTP 登录或 login 发码。默认无 auth 时，上述接口全部不存在；使用共用本地 token 的自定义模块也可接入最后三项。

## 接入短信 / 邮件发送器

只有需要 phone/email 注册或 OTP 登录时才做这一步：

1. 生成独立随机 `AUTH_CODE_SECRET_KEY`，至少 32 个 UTF-8 字节，不能与 JWT 共用
2. 实现需要的发送协议，不能默认打印验证码或假成功
3. 在 `api_app.py` 将创建新实例的 callable 传给工厂

短信协议在 `app/services/sms/sms_sender.py`：

```python
async def send_verification_code(
    self, *, cellphone: str, code: str,
    purpose: Literal['register', 'login'], expires_in: int,
) -> None: ...

async def aclose(self) -> None: ...
```

邮件协议在 `app/services/email/email_sender.py`，签名相同，仅将 `cellphone` 改为 `email`。`Literal` 来自 `typing`。适配器正常返回表示供应商接受，明确失败分别抛 `SmsSendError` / `EmailSendError`；须支持协作取消和关闭。

假设你已在自己的 `app/services/delivery.py` 实现 `MySmsSender` / `MyEmailSender`，组装为：

```python
from app.services.delivery import MyEmailSender, MySmsSender
from bootstrap.application import create_app

app = create_app(
    sms_sender_factory=MySmsSender,
    email_sender_factory=MyEmailSender,
)
```

这些示意实现不由模板提供；只传实际需要的通道即可。未选中的通道不会创建实例，选中但缺 factory 则启动失败。每轮 lifespan 创建并关闭新实例，不注入已关闭或模块级共享实例。

### 跑通 OTP

以手机为例，选择 phone_otp 并完成发送器接入后：

```bash
curl -X POST http://127.0.0.1:8000/api/auth/phone/codes/login \
  -H 'Content-Type: application/json' -d '{"phone":"13800000000"}'

# 将验证码替换成实际收到的6位数字字符串，保留前导零
curl -X POST http://127.0.0.1:8000/api/auth/phone/token \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800000000","verification_code":"012345"}'
```

邮箱将路径的 phone 改成 email，请求字段也改为 email。首次登录创建普通、无密码账号；之后复用原账号。成功仍返回标准 token 响应，后续访问与退出同 README。

## 初始多身份注册

需要一个用户同时拥有多种身份时，**首次注册一次完成**。例如选择三种内置方式，并允许密码使用三种标识：

1. 分别调用 phone/email 的 `codes/register` 验证接口
2. 收到两种验证码后，提交一次 `/auth/register`

```json
{
  "identities": [
    {"kind": "username", "identifier": "alice"},
    {"kind": "phone", "identifier": "13800000000", "verification_code": "012345"},
    {"kind": "email", "identifier": "alice@example.com", "verification_code": "678901"}
  ],
  "password": "a-long-example-password",
  "profile": {"nickname": "示例用户", "gender": "unknown"}
}
```

示例验证码必须替换为实际注册码。资料 profile 可省略；不设置密码时，至少一个身份必须支持已启用的 OTP 登录。用户名必须有密码；不允许注册没有可用登录途径的账号。

- 同类本地身份一次最多一个；三种密码标识共用用户级的一份 Argon2 密码
- 手机/邮箱需证明所有权，用户名不带验证码；全部身份在同一个数据库事务中创建
- 任一身份已占用，整体 409，包括停用/软删除账号；不自动合并、追加身份或覆盖密码
- **OTP 先建号后，本轮不能再补绑用户名、密码或另一联系方式**；模板没有绑定/解绑、密码重置接口

用户名为 3–64 位 ASCII 字母、数字、`_ . -`，trim 且区分大小写，不能是合法手机号形态。手机为大陆 11 位 ASCII 数字，不接受 +86。邮箱规范值全地址大小写不敏感，不做供应商去点/去加号转换。新密码为 12–128 个 Unicode 字符，不 trim。

## 自定义模块

认证核心不限定请求形状、身份种类或是否使用 JWT。下面用一个**服务调用密钥**演示接入：它只保护一个接口，不创建用户、不使用本地 token，也不需要 JWT 密钥。

创建 `app/http/auth_methods/service_key.py`（该目录不参与业务自动发现）：

```python
from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import APIKeyHeader
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.exceptions import ApiError
from app.services.auth.modules import AuthModule
from config.settings import PROJECT_ROOT, Settings


class KeySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / '.env', env_file_encoding='utf-8', extra='ignore'
    )
    SERVICE_API_KEY: SecretStr = Field(min_length=32)


def build_module(settings: Settings) -> AuthModule:
    try:
        config = KeySettings.model_validate({})
    except ValidationError:
        raise ValueError('SERVICE_API_KEY 至少32字符，且必须显式提供') from None

    router = APIRouter()
    header = APIKeyHeader(name='X-Service-Key', auto_error=False)

    @router.get('/service/check')
    async def check(key: Annotated[str | None, Depends(header)]) -> dict[str, bool]:
        if key is None or not compare_digest(key.encode(), config.SERVICE_API_KEY.get_secret_value().encode()):
            raise ApiError(401, 'SERVICE_KEY_INVALID', '调用密钥无效', headers={'WWW-Authenticate': 'ApiKey'})
        return {'authenticated': True}

    return AuthModule(router=router)
```

按 README 第 3 节在 `api_app.py` 注册该 factory，在 `.env` 设置：

```dotenv
AUTH_MODULES=["service_key"]
SERVICE_API_KEY=这里替换为生成的独立随机密钥
```

重启后，用该密钥请求：

```bash
curl http://127.0.0.1:8000/api/service/check -H 'X-Service-Key: <SERVICE_API_KEY>'
# 预期：{"authenticated":true}；不带或错误密钥返回401
```

这只是最小服务密钥示例，不含密钥管理、轮换和用户授权系统。需要这些能力时在自己的模块完善，不把共享调用密钥用于区分最终用户。

### 自定义用户登录复用什么

- `auth_module_factories={'my_auth': build_module}`：代码注册；AUTH_MODULES 是唯一启用选择。需同时保留内置模板时使用 `{**builtin_factories(), 'my_auth': build_module}`，其中 builtin_factories 来自 `app.http.auth_methods`
- `AuthModule(router=router, uses_local_tokens=True)`：按需接入共用 JWT/status/logout/me；声明后必须配置 JWT_SECRET_KEY
- `PreparedIdentity` + `resolve_verified_user`：完成真实上游证明验证后，按可信 namespace 与稳定 subject 解析/首次建号；不能相信客户端自报“已验证”
- `create_account`：初始多身份及模块凭据在同一事务创建；凭据写入回调不能自己 commit。需要组合注册时由自己的请求模型编排，不修改全局三类注册模型
- `create_token_response_from_user(user, get_jwt_settings(request))`：账号可用且事务成功后签发统一 token
- `AuthModule.lifespan`：可选异步上下文，使用当前应用资源，负责关闭自己的资源；不为每个新模块增加工厂顶层参数
- 路由自动继承封禁与 APP_QPS；登录/注册还应分别使用 `verify_login_limit` / `verify_register_limit`

通用身份归属是 `(namespace, subject)` 唯一；不同 issuer/tenant 使用不同域，同域多个身份可以归属同一用户。不要把认证方式 ID 当作共享手机号的另一个域，也不要因为外部邮箱相同就自动绑定本地用户。自定义秘密凭据使用自己的强类型表/迁移，不塞入 users 或通用 JSON 密码列。

## 验证码和错误注意事项

验证码默认 300 秒、最多 5 次错误、发码冷却 60 秒；同 IP 跨手机/邮箱/用途合计 5 次/分钟、20 次/小时，接收者/用途 5 次/小时。失败不返还已扣配额；登录额外共用 5 次/IP/分钟，注册 3 次/IP/分钟。

注册码与登录码、不同域与通道不能混用。证明一次消费；发送超时或 503 不表示供应商一定未发送，不能自动重发。验证码消费后 DB 失败不会恢复旧码，需要重新获取。停用/软删用户不能认证，但仍可吊销尚有效的 token。

没有密码找回、刷新 token、绑定/解绑或默认浏览器 WS 凭据方案。更多运行边界见 [运行与开发说明](operations.md)。
