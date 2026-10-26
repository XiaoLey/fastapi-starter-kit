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
from tests.conftest import AppFactory

pytestmark = pytest.mark.integration


def headers(response: httpx.Response) -> dict[str, str]:
    assert response.status_code == 200
    token = TokenSc.model_validate_json(response.content)
    return {'Authorization': f'Bearer {token.access_token}'}


async def test_password_lifecycle_and_unavailable_account(app_factory: AppFactory) -> None:
    application = await app_factory(AUTH_MODULES=['password'], AUTH_CODE_SECRET_KEY=None)
    client = application.client
    registration = {
        'identities': [{'kind': 'username', 'identifier': ' tester '}],
        'password': 'long-password-123',
        'profile': {'nickname': '测试账号'},
    }
    created = await client.post('/api/auth/register', json=registration)
    assert created.status_code == 201
    user_id = UUID(created.json()['id'])
    assert (await client.post('/api/auth/register', json=registration)).status_code == 409
    assert application.sms is None and application.email is None
    assert (await client.post('/api/users', json={})).status_code == 404

    # 错误凭据不泄漏身份，成功登录只返回资料白名单
    login = {'kind': 'username', 'identifier': 'tester', 'password': 'wrong'}
    assert (await client.post('/api/auth/password/token', json=login)).status_code == 401
    login['password'] = 'long-password-123'
    first = headers(await client.post('/api/auth/password/token', json=login))
    second = headers(await client.post('/api/auth/password/token', json=login))
    me = await client.get('/api/users/me', headers=first)
    assert me.status_code == 200 and me.json()['id'] == str(user_id)
    assert me.json()['is_admin'] is False
    assert not {'username', 'password', 'cellphone', 'identities'}.intersection(me.json())
    assert (await client.get('/api/auth/token/status', headers=first)).status_code == 200

    # 单token吊销不影响同一用户的其他有效凭据
    assert (await client.delete('/api/auth/token', headers=first)).status_code == 200
    assert (await client.get('/api/users/me', headers=first)).status_code == 401
    assert (await client.get('/api/users/me', headers=second)).status_code == 200
    async with application.resources.session_factory() as session:
        credential = await session.get(PasswordCredentialModel, user_id)
        assert credential is not None and credential.password_hash.startswith('$argon2')
        user = await session.get(UserModel, user_id)
        assert user is not None
        user.state = 'disabled'
        await session.commit()
    assert (await client.post('/api/auth/password/token', json=login)).status_code == 401
    assert (await client.get('/api/users/me', headers=second)).status_code == 401

    # 软删除同样禁止认证，但已有有效token仍可主动退出
    async with application.resources.session_factory() as session:
        user = await session.get(UserModel, user_id)
        assert user is not None
        user.state = 'enabled'
        user.delete()
        await session.commit()
    assert (await client.post('/api/auth/password/token', json=login)).status_code == 401
    assert (await client.delete('/api/auth/token', headers=second)).status_code == 200


@pytest.mark.parametrize('kind', ['phone', 'email'])
async def test_otp_only_delivery_ownership_and_reuse(app_factory: AppFactory, kind: Literal['phone', 'email']) -> None:
    # 包装资源上下文并改注册名，不应改变内置方式贡献的能力
    factories = None
    module_id = f'{kind}_otp'
    if kind == 'phone':
        from app.http.auth_methods.phone_otp import build_module

        def wrapped_phone(settings: Settings) -> AuthModule:
            module = build_module(settings)
            original = module.lifespan
            assert original is not None

            @asynccontextmanager
            async def wrapped(app: FastAPI) -> AsyncGenerator[None]:
                async with original(app):
                    yield

            return replace(module, lifespan=wrapped)

        module_id = 'phone_alias'
        factories = {module_id: wrapped_phone}

    application = await app_factory(AUTH_MODULES=[module_id], factories=factories, AUTH_CODE_SEND_INTERVAL_SECONDS=1)
    client = application.client
    sender = application.sms if kind == 'phone' else application.email
    other = application.email if kind == 'phone' else application.sms
    assert sender is not None and other is None
    identifier = '13800000000' if kind == 'phone' else 'Owner@Example.com'
    body = {kind: identifier}
    base = f'/api/auth/{kind}'

    # 外部拒绝不伪报成功，注册码不能当作登录证明
    sender.fail = True
    assert (await client.post(f'{base}/codes/register', json=body)).status_code == 503
    assert not sender.sent
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

    # 对外并发登录只消费一次，返回同一无密码普通账号
    results = await asyncio.gather(client.post(f'{base}/token', json=login), client.post(f'{base}/token', json=login))
    assert sorted(result.status_code for result in results) == [200, 422]
    authorized = headers(next(result for result in results if result.status_code == 200))
    me = await client.get('/api/users/me', headers=authorized)
    user_id = me.json()['id']
    assert me.status_code == 200 and me.json()['nickname'] == '新用户'
    assert (await client.post(f'{base}/token', json=login)).status_code == 422
    assert (
        await client.post(
            '/api/auth/register',
            json={'identities': [{'kind': kind, 'identifier': identifier, 'verification_code': register_code}]},
        )
    ).status_code == 409

    # 缩短已有可配置冷却以验证重登，不替换Redis时钟或算法
    await asyncio.sleep(1.1)
    assert (await client.post(f'{base}/codes/login', json=body)).status_code == 200
    again = headers(await client.post(f'{base}/token', json={**body, 'verification_code': sender.sent[-1][1]}))
    assert (await client.get('/api/users/me', headers=again)).json()['id'] == user_id
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(PasswordCredentialModel)) == 0
        identity = await session.scalar(sa.select(AuthIdentityModel))
        assert identity is not None and identity.namespace == f'local/{kind}' and identity.verified_at is not None
        assert identity.subject == identifier.lower()

    assert (await client.post('/api/auth/password/token', json={})).status_code == 404
    opposite = 'email' if kind == 'phone' else 'phone'
    assert (await client.post(f'/api/auth/{opposite}/token', json={})).status_code == 404
    schema = application.app.openapi()
    assert '/api/auth/password/token' not in schema['paths']
    assert f'/api/auth/{opposite}/token' not in schema['paths']
    assert schema['components']['securitySchemes']['Bearer']['type'] == 'http'


async def test_phone_password_does_not_enable_phone_otp(app_factory: AppFactory) -> None:
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
    for kind, identifier in [('username', 'phone-owner'), ('phone', '13800000000')]:
        authorized = headers(
            await client.post(
                '/api/auth/password/token',
                json={'kind': kind, 'identifier': identifier, 'password': 'long-password-123'},
            )
        )
        assert (await client.get('/api/users/me', headers=authorized)).json()['id'] == created.json()['id']
    for path in ('/api/auth/phone/token', '/api/auth/phone/codes/login'):
        assert (await client.post(path, json={})).status_code == 404
        assert path not in application.app.openapi()['paths']


async def test_initial_multi_identity_and_no_implicit_binding(app_factory: AppFactory) -> None:
    application = await app_factory(
        AUTH_MODULES=['password', 'phone_otp', 'email_otp'], AUTH_PASSWORD_IDENTIFIERS=['username', 'phone', 'email']
    )
    client, sms, email = application.client, application.sms, application.email
    assert sms is not None and email is not None
    assert (await client.post('/api/auth/phone/codes/register', json={'phone': '13800000000'})).status_code == 200
    phone_code = sms.sent[-1][1]

    # 手机证明不能消费邮箱域，即使注册输入结构正确
    assert (
        await client.post(
            '/api/auth/register',
            json={
                'identities': [{'kind': 'email', 'identifier': 'Alice@Example.com', 'verification_code': phone_code}]
            },
        )
    ).status_code == 422
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

    # 三个密码入口和两个OTP入口共享同一用户，而非复制身份
    for kind, identifier in [('username', 'alice'), ('phone', '13800000000'), ('email', 'ALICE@example.COM')]:
        authorized = headers(
            await client.post(
                '/api/auth/password/token',
                json={'kind': kind, 'identifier': identifier, 'password': 'long-password-123'},
            )
        )
        assert (await client.get('/api/users/me', headers=authorized)).json()['id'] == user_id
    for kind, identifier, sender in [('phone', '13800000000', sms), ('email', 'alice@example.com', email)]:
        assert (await client.post(f'/api/auth/{kind}/codes/login', json={kind: identifier})).status_code == 200
        authorized = headers(
            await client.post(
                f'/api/auth/{kind}/token', json={kind: identifier, 'verification_code': sender.sent[-1][1]}
            )
        )
        assert (await client.get('/api/users/me', headers=authorized)).json()['id'] == user_id

    # 占用身份的注册不能变成绑定新用户名或覆盖原密码
    async with application.resources.session_factory() as session:
        credential = await session.get(PasswordCredentialModel, UUID(user_id))
        assert credential is not None
        original_hash = credential.password_hash
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
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(AuthIdentityModel)) == 3
        credential = await session.get(PasswordCredentialModel, UUID(user_id))
        assert credential is not None and credential.password_hash == original_hash


async def test_concurrent_registration_is_atomic(app_factory: AppFactory) -> None:
    application = await app_factory(AUTH_MODULES=['password'])
    registration = {'identities': [{'kind': 'username', 'identifier': 'same-user'}], 'password': 'long-password-123'}
    results = await asyncio.gather(*[
        application.client.post('/api/auth/register', json=registration) for _ in range(2)
    ])
    assert sorted(result.status_code for result in results) == [201, 409]
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(AuthIdentityModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(PasswordCredentialModel)) == 1


async def test_custom_module_alone_uses_public_core_contract(app_factory: AppFactory) -> None:
    class StaffRequestSc(BaseSc):
        subject: str = Field(pattern=r'^employee-[0-9]+$')
        proof: SecretStr

    def staff(settings: Settings) -> AuthModule:
        router = APIRouter(prefix='/auth/staff')

        @router.post('/token', response_model=TokenSc, dependencies=[Depends(firewall_deps.verify_login_limit)])
        async def login(
            request: Request, data: StaffRequestSc, session: Annotated[AsyncSession, Depends(database_deps.get_db)]
        ) -> TokenSc:
            # 仅测试接入契约：固定测试证明不进入生产源码
            if not hmac.compare_digest(data.proof.get_secret_value(), 'test-provider-verified-proof'):
                raise AuthenticationError()
            user = await resolve_verified_user(
                session,
                PreparedIdentity(namespace='test/staff/acme', subject=data.subject, verified_at=datetime.now(UTC)),
            )
            return create_token_response_from_user(user, get_jwt_settings(request))

        return AuthModule(router=router, uses_local_tokens=True)

    application = await app_factory(
        AUTH_MODULES=['phone_otp'], AUTH_CODE_SECRET_KEY=None, factories={'phone_otp': staff}
    )
    client = application.client
    assert (
        await client.post('/api/auth/staff/token', json={'subject': 'employee-42', 'proof': 'wrong'})
    ).status_code == 401
    credentials = {'subject': 'employee-42', 'proof': 'test-provider-verified-proof'}
    first = headers(await client.post('/api/auth/staff/token', json=credentials))
    second = headers(await client.post('/api/auth/staff/token', json=credentials))
    assert (await client.get('/api/users/me', headers=first)).json()['id'] == (
        await client.get('/api/users/me', headers=second)
    ).json()['id']
    assert application.sms is None and application.email is None
    paths = application.app.openapi()['paths']
    for path in ('/api/auth/register', '/api/auth/password/token', '/api/auth/phone/token', '/api/auth/email/token'):
        assert (await client.post(path, json={})).status_code == 404 and path not in paths
    async with application.resources.session_factory() as session:
        identity = await session.scalar(sa.select(AuthIdentityModel))
        assert identity is not None and identity.namespace == 'test/staff/acme'
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(PasswordCredentialModel)) == 0


async def test_unrelated_constraints_do_not_hide_account_failure(app_factory: AppFactory) -> None:
    application = await app_factory()
    identity = PreparedIdentity(namespace='test/credential-failure', subject='owner')
    for constraint, value, state in (('CHECK (value > 0)', -1, '23514'), ('UNIQUE (value)', 1, '23505')):
        async with application.resources.session_factory() as session:
            # 真实同名约束既可从身份触发器失败，也可从模块凭据写入失败
            await session.execute(
                sa.text(
                    f'CREATE TEMP TABLE addon_credentials (value integer, '
                    f'CONSTRAINT uq_auth_identity_namespace_subject {constraint}) ON COMMIT DROP'
                )
            )
            await session.execute(sa.text('INSERT INTO addon_credentials VALUES (1)'))
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
            with pytest.raises(IntegrityError) as from_identity:
                await create_account(session, [identity])
            assert getattr(from_identity.value.orig, 'sqlstate', None) == state
            assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 0

            # 模块回调的数据库错误不能进入身份竞争的翻译路径
            await session.execute(sa.text('DROP TRIGGER credential_failure ON auth_identities'))

            async def write_credentials(db: AsyncSession, user_id: UUID, bad_value: int = value) -> None:
                await db.execute(sa.text('INSERT INTO addon_credentials VALUES (:value)'), {'value': bad_value})

            with pytest.raises(IntegrityError) as from_credentials:
                await create_account(session, [identity], write_credentials=write_credentials)
            assert getattr(from_credentials.value.orig, 'sqlstate', None) == state
            assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 0
            assert await session.scalar(sa.select(sa.func.count()).select_from(AuthIdentityModel)) == 0


async def test_global_quota_shared_between_apps(app_factory: AppFactory) -> None:
    first = await app_factory(AUTH_MODULES=['password'], APP_QPS=2)
    second = await app_factory(AUTH_MODULES=['password'], APP_QPS=2)
    assert (await first.client.get('/api/users/me')).status_code == 401
    assert (await second.client.get('/api/auth/token/status')).status_code == 401
    limited = await first.client.delete('/api/auth/token')
    assert limited.status_code == 429 and int(limited.headers['Retry-After']) >= 1
    assert (await second.client.get('/api/ping')).status_code == 200
