import asyncio

import httpx
import pytest
import sqlalchemy as sa
from pwdlib.hashers.bcrypt import BcryptHasher

from app.models.user import UserModel
from app.schemas.token import TokenSc
from bootstrap.application import create_app
from config.settings import Settings
from tests.conftest import AppClient, SmsRecorder

pytestmark = pytest.mark.integration


async def test_username_authentication_lifecycle(application: AppClient) -> None:
    # 同一账号的注册冲突和错误凭据均从公开接口验证
    client = application.client
    registration = {'username': 'tester', 'password': 'long-password-123', 'nickname': '测试账号', 'gender': 'unknown'}
    assert (await client.post('/api/users', json=registration)).status_code == 201
    assert (await client.post('/api/users', json=registration)).status_code == 409
    assert (
        await client.post('/api/auth/token/password', data={'username': 'tester', 'password': 'wrong'})
    ).status_code == 401

    # 缺省grant_type和兼容scope输入不能改变账号权限
    response = await client.post(
        '/api/auth/token/password',
        data={'username': 'tester', 'password': 'long-password-123', 'scope': 'admin', 'client_id': 'admin'},
    )
    assert response.status_code == 200
    token = TokenSc.model_validate_json(response.content)
    headers = {'Authorization': f'Bearer {token.access_token}'}
    me = await client.get('/api/users/me', headers=headers)
    assert me.status_code == 200 and me.json()['username'] == 'tester'
    assert me.json()['is_admin'] is False and 'password' not in me.json()
    assert (await client.get('/api/auth/token/status', headers=headers)).status_code == 200

    # 退出必须真正影响后续受保护请求，而不只是返回success
    assert (await client.delete('/api/auth/token', headers=headers)).status_code == 200
    assert (await client.get('/api/users/me', headers=headers)).status_code == 401
    assert (await client.get('/api/health/ready')).status_code == 200


async def test_legacy_password_upgrade_and_disabled_identity(application: AppClient) -> None:
    # 保留旧数据形态，认证流程负责持久化兼容升级
    async with application.resources.session_factory() as session:
        user = UserModel(username=' old name ', nickname='旧账号', password=BcryptHasher().hash('short'))
        session.add(user)
        await session.commit()
        identity = user.id

    # 旧用户名和短密码按旧值登录，验证升级确实提交到数据库
    response = await application.client.post(
        '/api/auth/token/password', data={'username': ' old name ', 'password': 'short'}
    )
    assert response.status_code == 200
    token = TokenSc.model_validate_json(response.content)
    headers = {'Authorization': f'Bearer {token.access_token}'}
    async with application.resources.session_factory() as session:
        user = await session.get(UserModel, identity)
        assert user is not None and user.password is not None and user.password.startswith('$argon2')
        user.state = 'disabled'
        await session.commit()

    assert (await application.client.get('/api/users/me', headers=headers)).status_code == 401
    assert (await application.client.get('/api/auth/token/status', headers=headers)).status_code == 401
    assert (await application.client.delete('/api/auth/token', headers=headers)).status_code == 200


async def test_phone_registration_login_and_sender_failure(application: AppClient) -> None:
    # 供应商失败不生成可用验证码，也不能返回发送成功
    client, sender = application.client, application.sender
    sender.fail = True
    response = await client.post(
        '/api/auth/verification-codes/cellphone', json={'cellphone': '13800000000', 'purpose': 'register'}
    )
    assert response.status_code == 503 and not sender.sent
    sender.fail = False

    # 注册码不能用于登录，带手机号注册后仍支持手机号密码登录
    assert (
        await client.post(
            '/api/auth/verification-codes/cellphone', json={'cellphone': '13800000000', 'purpose': 'register'}
        )
    ).status_code == 200
    register_code = sender.sent[-1][1]
    assert (
        await client.post(
            '/api/auth/token/cellphone', json={'cellphone': '13800000000', 'verification_code': register_code}
        )
    ).status_code == 422
    assert (
        await client.post(
            '/api/users',
            json={
                'username': 'phone-owner',
                'password': 'long-password-123',
                'nickname': '手机号账号',
                'gender': 'unknown',
                'cellphone': '13800000000',
                'cellphone_verification_code': register_code,
            },
        )
    ).status_code == 201
    assert (
        await client.post('/api/auth/token/password', data={'username': '13800000000', 'password': 'long-password-123'})
    ).status_code == 200

    # 已有手机号登录保持原账号身份，不产生重复账号
    assert (
        await client.post(
            '/api/auth/verification-codes/cellphone', json={'cellphone': '13800000000', 'purpose': 'login'}
        )
    ).status_code == 200
    response = await client.post(
        '/api/auth/token/cellphone', json={'cellphone': '13800000000', 'verification_code': sender.sent[-1][1]}
    )
    assert response.status_code == 200
    existing = TokenSc.model_validate_json(response.content)
    me = await client.get('/api/users/me', headers={'Authorization': f'Bearer {existing.access_token}'})
    assert me.json()['username'] == 'phone-owner'

    # 对外的并发登录验证一次性消费，使用真实Redis执行验证码脚本
    assert (
        await client.post(
            '/api/auth/verification-codes/cellphone', json={'cellphone': '13900000000', 'purpose': 'login'}
        )
    ).status_code == 200
    login = {'cellphone': '13900000000', 'verification_code': sender.sent[-1][1]}
    responses = await asyncio.gather(
        client.post('/api/auth/token/cellphone', json=login), client.post('/api/auth/token/cellphone', json=login)
    )
    assert sorted(response.status_code for response in responses) == [200, 422]
    token = TokenSc.model_validate_json(next(response.content for response in responses if response.status_code == 200))
    me = await client.get('/api/users/me', headers={'Authorization': f'Bearer {token.access_token}'})
    assert me.json()['username'].startswith('u_') and me.json()['is_admin'] is False
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 2


async def test_concurrent_registration_creates_one_identity(application: AppClient) -> None:
    registration = {
        'username': 'same-user',
        'password': 'long-password-123',
        'nickname': '并发注册',
        'gender': 'unknown',
    }
    responses = await asyncio.gather(*[application.client.post('/api/users', json=registration) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [201, 409]
    async with application.resources.session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(UserModel)) == 1


async def test_global_quota_is_shared_across_apps_and_routes(integration_settings: Settings) -> None:
    # 独立客户端使用同一命名空间，业务配额必须共享
    settings = integration_settings.model_copy(update={'APP_QPS': 2})
    first, second = (
        create_app(settings, sms_sender_factory=SmsRecorder),
        create_app(settings, sms_sender_factory=SmsRecorder),
    )
    async with first.router.lifespan_context(first), second.router.lifespan_context(second):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=first), base_url='http://test') as a:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url='http://test') as b:
                assert (await a.get('/api/users/me')).status_code == 401
                assert (await b.get('/api/auth/token/status')).status_code == 401
                response = await a.delete('/api/auth/token')
                assert response.status_code == 429 and int(response.headers['Retry-After']) >= 1
                assert (await b.get('/api/ping')).status_code == 200
