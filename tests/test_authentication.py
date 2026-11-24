import asyncio
import hmac
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
import pytest
import sqlalchemy as sa
from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import Field, SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AuthenticationError
from app.http.deps import database_deps, firewall_deps
from app.http.deps.runtime_deps import get_jwt_settings
from app.models.auth_identity import AuthIdentityModel
from app.models.password_credential import PasswordCredentialModel
from app.models.user import UserModel
from app.schemas.base import BaseSc
from app.schemas.token import TokenSc
from app.services.auth.identity_service import PreparedIdentity, create_account, resolve_verified_user
from app.services.auth.modules import AuthModule
from app.services.auth.token_service import create_token_response_from_user
from config.settings import Settings
from tests.conftest import SENSITIVE_TEST_VALUE, AppFactory

pytestmark = pytest.mark.integration


def headers(response: httpx.Response) -> dict[str, str]:
    """将成功的令牌响应转换为 Bearer 请求头"""
    assert response.status_code == 200
    token = TokenSc.model_validate_json(response.content)
    return {'Authorization': f'Bearer {token.access_token}'}


async def test_password_lifecycle_and_unavailable_account(app_factory: AppFactory) -> None:
    """密码账号停用或软删除后不能登录，退出只撤销指定令牌"""
    application = await app_factory(AUTH_MODULES=['password'], AUTH_CODE_SECRET_KEY=None)
    client = application.client

    # 同一用户名不能重复注册
    registration = {
        'identities': [{'kind': 'username', 'identifier': ' tester '}],
        'password': 'long-password-123',
        'profile': {'nickname': '测试账号'},
    }
    created = await client.post('/api/auth/register', json=registration)
    assert created.status_code == 201
    user_id = UUID(created.json()['id'])
    assert (await client.post('/api/auth/register', json=registration)).status_code == 409

    # 仅启用用户名密码时不装配验证码发送器或通用建号入口
    assert application.sms is None and application.email is None
    assert (await client.post('/api/users', json={})).status_code == 404

    # 只有正确密码才能换取令牌
    login = {'kind': 'username', 'identifier': 'tester', 'password': 'wrong'}
    assert (await client.post('/api/auth/password/token', json=login)).status_code == 401
    login['password'] = 'long-password-123'
    first = headers(await client.post('/api/auth/password/token', json=login))
    second = headers(await client.post('/api/auth/password/token', json=login))

    # 登录后的资料响应不暴露凭据和登录标识
    me = await client.get('/api/users/me', headers=first)
    assert me.status_code == 200 and me.json()['id'] == str(user_id)
    assert me.json()['is_admin'] is False
    assert not {'username', 'password', 'cellphone', 'identities'}.intersection(me.json())
    assert (await client.get('/api/auth/token/status', headers=first)).status_code == 200

    # 撤销单个令牌不影响同一账号的其他会话
    assert (await client.delete('/api/auth/token', headers=first)).status_code == 200
    assert (await client.get('/api/users/me', headers=first)).status_code == 401
    assert (await client.get('/api/users/me', headers=second)).status_code == 200

    # 停用账号后既不能换取新令牌，也不能凭已有令牌访问资料
    async with application.resources.session_factory() as session:
        # 持久化的凭据应是密码哈希
        credential = await session.get(PasswordCredentialModel, user_id)
        assert credential is not None and credential.password_hash.startswith('$argon2')

        user = await session.get(UserModel, user_id)
        assert user is not None
        user.state = 'disabled'
        await session.commit()

    assert (await client.post('/api/auth/password/token', json=login)).status_code == 401
    assert (await client.get('/api/users/me', headers=second)).status_code == 401

    # 软删除后不能登录，但仍可撤销已有令牌
    async with application.resources.session_factory() as session:
        user = await session.get(UserModel, user_id)
        assert user is not None
        user.state = 'enabled'
        user.delete()
        await session.commit()

    assert (await client.post('/api/auth/password/token', json=login)).status_code == 401
    assert (await client.delete('/api/auth/token', headers=second)).status_code == 200


@pytest.mark.parametrize('kind', ['phone', 'email'])
async def test_otp_only_delivery_ownership_and_reuse(
    app_factory: AppFactory, kind: Literal['phone', 'email'], log_messages: list[str]
) -> None:
    """验证码只授权其指定用途，已验证的联系方式在重登时仍归属同一账号"""
    factories = None
    module_id = f'{kind}_otp'

    # 手机验证码能力不依赖注册名或生命周期回调的具体形态
    if kind == 'phone':
        from app.http.auth_methods.phone_otp import build_module

        def wrapped_phone(settings: Settings) -> AuthModule:
            """提供与内置方式等价的手机验证码模块"""
            module = build_module(settings)
            original = module.lifespan
            assert original is not None

            @asynccontextmanager
            async def wrapped(app: FastAPI) -> AsyncGenerator[None]:
                """保留原有资源的初始化与释放语义"""
                async with original(app):
                    yield

            return replace(module, lifespan=wrapped)

        module_id = 'phone_alias'
        factories = {module_id: wrapped_phone}

    # 只装配所选通道的发送器
    application = await app_factory(AUTH_MODULES=[module_id], factories=factories, AUTH_CODE_SEND_INTERVAL_SECONDS=1)
    client = application.client
    sender = application.sms if kind == 'phone' else application.email
    other = application.email if kind == 'phone' else application.sms
    assert sender is not None and other is None

    identifier = '13800000000' if kind == 'phone' else 'Owner@Example.com'
    body = {kind: identifier}
    base = f'/api/auth/{kind}'

    # 发送失败不报成功，响应和日志不泄露供应商的敏感值
    sender.fail = True
    rejected = await client.post(f'{base}/codes/register', json=body)
    assert rejected.status_code == 503
    assert rejected.json() == {'code': 'CODE_SEND_ERROR', 'message': '验证码发送未能确认成功'}
    assert SENSITIVE_TEST_VALUE not in rejected.text + ''.join(log_messages)
    assert not sender.sent

    # 注册码不能作为登录证明
    sender.fail = False
    assert (await client.post(f'{base}/codes/register', json=body)).status_code == 200
    register_code = sender.sent[-1][1]
    assert (await client.post(f'{base}/token', json={**body, 'verification_code': register_code})).status_code == 422

    if kind == 'phone':
        # 别名模块仍可先完成初始注册，随后使用相同身份登录
        assert (
            await client.post(
                '/api/auth/register',
                json={'identities': [{'kind': kind, 'identifier': identifier, 'verification_code': register_code}]},
            )
        ).status_code == 201

    assert (await client.post(f'{base}/codes/login', json=body)).status_code == 200
    login = {**body, 'verification_code': sender.sent[-1][1]}

    # 同一登录码只能使用一次，即使请求并发到达
    results = await asyncio.gather(client.post(f'{base}/token', json=login), client.post(f'{base}/token', json=login))
    assert sorted(result.status_code for result in results) == [200, 422]
    authorized = headers(next(result for result in results if result.status_code == 200))
    me = await client.get('/api/users/me', headers=authorized)
    user_id = me.json()['id']
    assert me.status_code == 200 and me.json()['nickname'] == '新用户'
    assert (await client.post(f'{base}/token', json=login)).status_code == 422

    # 已有归属的联系方式不能再次注册
    assert (
        await client.post(
            '/api/auth/register',
            json={'identities': [{'kind': kind, 'identifier': identifier, 'verification_code': register_code}]},
        )
    ).status_code == 409

    # 等真实发送冷却结束后重登，确认账号归属不变
    await asyncio.sleep(1.1)
    assert (await client.post(f'{base}/codes/login', json=body)).status_code == 200
    again = headers(await client.post(f'{base}/token', json={**body, 'verification_code': sender.sent[-1][1]}))
    assert (await client.get('/api/users/me', headers=again)).json()['id'] == user_id

    # 保留已验证的规范化身份，不创建密码凭据
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(PasswordCredentialModel)) == 0
        identity = await session.scalar(sa.select(AuthIdentityModel))
        assert identity is not None and identity.namespace == f'local/{kind}' and identity.verified_at is not None
        assert identity.subject == identifier.lower()

    # 未启用方式既不能访问，也不应出现在 OpenAPI 中
    assert (await client.post('/api/auth/password/token', json={})).status_code == 404
    opposite = 'email' if kind == 'phone' else 'phone'
    assert (await client.post(f'/api/auth/{opposite}/token', json={})).status_code == 404
    schema = application.app.openapi()
    assert '/api/auth/password/token' not in schema['paths']
    assert f'/api/auth/{opposite}/token' not in schema['paths']
    assert schema['components']['securitySchemes']['Bearer']['type'] == 'http'


async def test_phone_password_does_not_enable_phone_otp(app_factory: AppFactory) -> None:
    """手机号可作为密码标识，启用注册证明不会同时开放手机验证码登录"""
    # 将已验证的手机号和用户名注册到同一密码账号
    application = await app_factory(AUTH_MODULES=['password'], AUTH_PASSWORD_IDENTIFIERS=['username', 'phone'])
    client, sender = application.client, application.sms
    assert sender is not None and application.email is None
    assert (await client.post('/api/auth/phone/codes/register', json={'phone': '13800000000'})).status_code == 200
    created = await client.post(
        '/api/auth/register',
        json={
            'identities': [
                {'kind': 'username', 'identifier': 'phone-owner'},
                {'kind': 'phone', 'identifier': '13800000000', 'verification_code': sender.sent[-1][1]},
            ],
            'password': 'long-password-123',
        },
    )
    assert created.status_code == 201

    # 多种密码标识解析为同一注册主体
    for kind, identifier in [('username', 'phone-owner'), ('phone', '13800000000')]:
        authorized = headers(
            await client.post(
                '/api/auth/password/token',
                json={'kind': kind, 'identifier': identifier, 'password': 'long-password-123'},
            )
        )
        assert (await client.get('/api/users/me', headers=authorized)).json()['id'] == created.json()['id']

    # 未启用的验证码登录入口既不可调用，也不出现在 OpenAPI 中
    for path in ('/api/auth/phone/token', '/api/auth/phone/codes/login'):
        assert (await client.post(path, json={})).status_code == 404
        assert path not in application.app.openapi()['paths']


async def test_initial_multi_identity_and_no_implicit_binding(app_factory: AppFactory) -> None:
    """多个登录标识可共享新账号，但注册不能为已有账号隐式绑定身份或修改密码"""
    application = await app_factory(
        AUTH_MODULES=['password', 'phone_otp', 'email_otp'], AUTH_PASSWORD_IDENTIFIERS=['username', 'phone', 'email']
    )
    client, sms, email = application.client, application.sms, application.email
    assert sms is not None and email is not None

    # 注册证明不能跨联系方式使用
    assert (await client.post('/api/auth/phone/codes/register', json={'phone': '13800000000'})).status_code == 200
    phone_code = sms.sent[-1][1]
    assert (
        await client.post(
            '/api/auth/register',
            json={
                'identities': [{'kind': 'email', 'identifier': 'Alice@Example.com', 'verification_code': phone_code}]
            },
        )
    ).status_code == 422

    # 每个联系方式各自取得证明后才能组合注册
    assert (await client.post('/api/auth/email/codes/register', json={'email': 'Alice@Example.com'})).status_code == 200
    registration = {
        'identities': [
            {'kind': 'username', 'identifier': 'alice'},
            {'kind': 'phone', 'identifier': '13800000000', 'verification_code': phone_code},
            {'kind': 'email', 'identifier': 'Alice@Example.com', 'verification_code': email.sent[-1][1]},
        ],
        'password': 'long-password-123',
    }
    created = await client.post('/api/auth/register', json=registration)
    assert created.status_code == 201
    user_id = created.json()['id']

    # 密码登录以不同标识解析到同一账号
    for kind, identifier in [('username', 'alice'), ('phone', '13800000000'), ('email', 'ALICE@example.COM')]:
        authorized = headers(
            await client.post(
                '/api/auth/password/token',
                json={'kind': kind, 'identifier': identifier, 'password': 'long-password-123'},
            )
        )
        assert (await client.get('/api/users/me', headers=authorized)).json()['id'] == user_id

    # 验证码登录沿用注册时验证的身份，不另建账号
    for kind, identifier, sender in [('phone', '13800000000', sms), ('email', 'alice@example.com', email)]:
        assert (await client.post(f'/api/auth/{kind}/codes/login', json={kind: identifier})).status_code == 200
        authorized = headers(
            await client.post(
                f'/api/auth/{kind}/token', json={kind: identifier, 'verification_code': sender.sent[-1][1]}
            )
        )
        assert (await client.get('/api/users/me', headers=authorized)).json()['id'] == user_id

    async with application.resources.session_factory() as session:
        credential = await session.get(PasswordCredentialModel, UUID(user_id))
        assert credential is not None
        original_hash = credential.password_hash

    # 已有归属的联系方式不能用来组合注册
    assert (
        await client.post(
            '/api/auth/register',
            json={
                'identities': [
                    {'kind': 'username', 'identifier': 'injected'},
                    {'kind': 'phone', 'identifier': '13800000000', 'verification_code': phone_code},
                ],
                'password': 'attacker-password-123',
            },
        )
    ).status_code == 409

    # 注册冲突不能增加主体或身份，也不能覆盖原密码
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(AuthIdentityModel)) == 3
        credential = await session.get(PasswordCredentialModel, UUID(user_id))
        assert credential is not None and credential.password_hash == original_hash


async def test_concurrent_registration_is_atomic(app_factory: AppFactory) -> None:
    """同一用户名的并发注册应原子地建立唯一账号"""
    application = await app_factory(AUTH_MODULES=['password'])
    registration = {'identities': [{'kind': 'username', 'identifier': 'same-user'}], 'password': 'long-password-123'}
    results = await asyncio.gather(*[
        application.client.post('/api/auth/register', json=registration) for _ in range(2)
    ])
    assert sorted(result.status_code for result in results) == [201, 409]

    # 唯一键竞争不能留下多余主体、身份或凭据
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(AuthIdentityModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(PasswordCredentialModel)) == 1


async def test_custom_module_alone_uses_public_core_contract(app_factory: AppFactory) -> None:
    """自定义认证可独立建号登录，复用内置注册名也不继承其能力"""

    class StaffRequestSc(BaseSc):
        subject: str = Field(pattern=r'^employee-[0-9]+$')
        proof: SecretStr

    def staff(settings: Settings) -> AuthModule:
        """提供使用外部员工证明的本地令牌认证方式"""
        router = APIRouter(prefix='/auth/staff')

        @router.post('/token', response_model=TokenSc, dependencies=[Depends(firewall_deps.verify_login_limit)])
        async def login(
            request: Request, data: StaffRequestSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
        ) -> TokenSc:
            """为证明有效的员工签发令牌，同一外部主体复用同一账号"""
            # 固定证明仅代表外部供应商已验证的测试结果
            if not hmac.compare_digest(data.proof.get_secret_value(), 'test-provider-verified-proof'):
                raise AuthenticationError()

            # 自定义证明也通过公共建号契约解析身份
            user = await resolve_verified_user(
                session,
                PreparedIdentity(namespace='test/staff/acme', subject=data.subject, verified_at=datetime.now(UTC)),
            )

            return create_token_response_from_user(user, get_jwt_settings(request))

        return AuthModule(router=router, uses_local_tokens=True)

    # 复用内置注册名，实际装配的能力由传入的工厂决定
    application = await app_factory(
        AUTH_MODULES=['phone_otp'], AUTH_CODE_SECRET_KEY=None, factories={'phone_otp': staff}
    )
    client = application.client
    assert (
        await client.post('/api/auth/staff/token', json={'subject': 'employee-42', 'proof': 'wrong'})
    ).status_code == 401

    # 重复提交有效证明仍登录同一账号
    credentials = {'subject': 'employee-42', 'proof': 'test-provider-verified-proof'}
    first = headers(await client.post('/api/auth/staff/token', json=credentials))
    second = headers(await client.post('/api/auth/staff/token', json=credentials))
    assert (await client.get('/api/users/me', headers=first)).json()['id'] == (
        await client.get('/api/users/me', headers=second)
    ).json()['id']

    # 自定义方式不会隐式装配内置发送器或认证入口
    assert application.sms is None and application.email is None
    paths = application.app.openapi()['paths']
    for path in ('/api/auth/register', '/api/auth/password/token', '/api/auth/phone/token', '/api/auth/email/token'):
        assert (await client.post(path, json={})).status_code == 404 and path not in paths

    # 身份写入自定义域，不产生内置密码凭据
    async with application.resources.session_factory() as session:
        identity = await session.scalar(sa.select(AuthIdentityModel))
        assert identity is not None and identity.namespace == 'test/staff/acme'
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(PasswordCredentialModel)) == 0


async def test_unrelated_constraints_do_not_hide_account_failure(app_factory: AppFactory) -> None:
    """其他约束即使同名也不得误报为身份冲突，建号失败不留下账号数据"""
    application = await app_factory()
    identity = PreparedIdentity(namespace='test/credential-failure', subject='owner')

    for constraint, value, state in (('CHECK (value > 0)', -1, '23514'), ('UNIQUE (value)', 1, '23505')):
        async with application.resources.session_factory() as session:
            # 使用与身份唯一键同名的外部表约束检验错误归因
            await session.execute(
                sa.text(
                    f'CREATE TEMP TABLE addon_credentials (value integer, '
                    f'CONSTRAINT uq_auth_identity_namespace_subject {constraint}) ON COMMIT DROP'
                )
            )
            await session.execute(sa.text('INSERT INTO addon_credentials VALUES (1)'))

            # 在真实身份写入阶段触发外部表约束
            await session.execute(
                sa.text(f"""
                CREATE FUNCTION pg_temp.reject_identity() RETURNS trigger AS $$
                BEGIN
                    INSERT INTO pg_temp.addon_credentials VALUES ({value});
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            )
            await session.execute(
                sa.text(
                    'CREATE TRIGGER credential_failure BEFORE INSERT ON auth_identities '
                    'FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_identity()'
                )
            )

            # 身份写入必须保留实际数据库错误，不能误报唯一键冲突
            with pytest.raises(IntegrityError) as from_identity:
                await create_account(session, [identity])
            assert getattr(from_identity.value.orig, 'sqlstate', None) == state

            assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 0

            # 移除身份写入的触发器，只检验凭据保存失败
            await session.execute(sa.text('DROP TRIGGER credential_failure ON auth_identities'))

            async def write_credentials(db: AsyncSession, user_id: UUID, bad_value: int = value) -> None:
                """写入违反测试约束的凭据值，向调用方暴露原始数据库错误"""
                await db.execute(sa.text('INSERT INTO addon_credentials VALUES (:value)'), {'value': bad_value})

            with pytest.raises(IntegrityError) as from_credentials:
                await create_account(session, [identity], write_credentials=write_credentials)
            assert getattr(from_credentials.value.orig, 'sqlstate', None) == state

            assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 0
            assert await session.scalar(sa.select(sa.func.count()).select_from(AuthIdentityModel)) == 0


async def test_global_quota_shared_between_apps(app_factory: AppFactory) -> None:
    """全局请求额度由同一测试命名空间的应用共享，耗尽后仍允许探活"""
    first = await app_factory(AUTH_MODULES=['password'], APP_QPS=2)
    second = await app_factory(AUTH_MODULES=['password'], APP_QPS=2)

    # 鉴权失败也会消耗跨应用的额度
    assert (await first.client.get('/api/users/me')).status_code == 401
    assert (await second.client.get('/api/auth/token/status')).status_code == 401
    limited = await first.client.delete('/api/auth/token')
    assert limited.status_code == 429 and int(limited.headers['Retry-After']) >= 1

    assert (await second.client.get('/api/ping')).status_code == 200
