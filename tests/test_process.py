import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from config.settings import PROJECT_ROOT
from tests.conftest import SENSITIVE_TEST_VALUE, make_settings, settings_environment

pytestmark = [
    pytest.mark.integration,
    pytest.mark.process,
    pytest.mark.skipif(sys.platform == 'win32', reason='Linux VM process acceptance'),
]


@pytest.mark.parametrize('trusted', ['', '127.0.0.1'])
def test_real_main_proxy_boundary(tmp_path: Path, trusted: str) -> None:
    """入口的显式代理信任覆盖环境默认值，收到停止信号后完成清理"""
    # 为本机子进程选取临时监听端口
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]

    # 外部宽泛信任与入口显式配置同时存在时，以入口为准
    settings = make_settings(APP_SERVER_PORT=port, APP_TRUSTED_PROXY_IPS=trusted)
    environment = settings_environment(settings)
    environment['FORWARDED_ALLOW_IPS'] = '*'

    # 通过实际入口启动，探针报告应用看到的客户端地址和协议
    code = f"""
import sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
import uvicorn
import main
from fastapi import Request
from bootstrap.application import create_app
from config.settings import load_settings
app = create_app(load_settings())
@app.get('/_probe/client')
async def client(request: Request):
    return {{'client': request.client.host if request.client else None, 'scheme': request.url.scheme}}
original = uvicorn.run
def run_probe(_app, **options):
    original(app, **options)
uvicorn.run = run_probe
main.main()
"""

    # 保存真实子进程日志，失败和退出路径均可检查
    log_path = tmp_path / 'uvicorn.log'
    with log_path.open('w', encoding='utf-8') as output:
        process = subprocess.Popen(
            [sys.executable, '-X', 'utf8', '-c', code],
            cwd=tmp_path,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )

        try:
            # 等探针可访问后再验证转发头
            base = f'http://127.0.0.1:{port}'
            deadline = time.monotonic() + 20
            while True:
                # 提前退出或等待超时，用已有日志报告失败
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail(log_path.read_text(encoding='utf-8'))

                # 尚未监听时的传输错误不结束等待
                try:
                    if httpx.get(f'{base}/_probe/client', timeout=0.3, trust_env=False).status_code == 200:
                        break
                except httpx.TransportError:
                    pass

                time.sleep(0.1)

            # 只有显式信任的来源才能通过转发头改变客户端地址和协议
            response = httpx.get(
                f'{base}/_probe/client',
                params={'secret': SENSITIVE_TEST_VALUE},
                headers={'X-Real-IP': '127.0.0.1', 'X-Forwarded-For': '198.51.100.42', 'X-Forwarded-Proto': 'https'},
                trust_env=False,
            )
            expected = (
                {'client': '198.51.100.42', 'scheme': 'https'} if trusted else {'client': '127.0.0.1', 'scheme': 'http'}
            )
            assert response.json() == expected
        finally:
            # 请求或断言失败也优先让进程正常退出
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # 超时强制回收，不能当作正常退出
                    process.kill()
                    process.wait(timeout=5)
                    pytest.fail('Uvicorn did not terminate gracefully')

    # 正常信号退出仍必须完成应用收尾
    assert process.returncode in (0, -signal.SIGTERM)
    output = log_path.read_text(encoding='utf-8')
    assert 'Application shutdown complete' in output

    # 查询参数中的敏感内容不能进入进程日志
    assert SENSITIVE_TEST_VALUE not in output


def test_scheduler_sigterm_waits_for_owned_job(tmp_path: Path) -> None:
    """调度器收到停止信号后等待已开始的作业完成，再正常退出"""
    # 用文件标记从进程外观察作业开始与正常完成
    started, finished = tmp_path / 'started', tmp_path / 'finished'
    code = f"""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, {str(PROJECT_ROOT)!r})
import bootstrap.scheduler as bootstrap
import scheduler
async def job():
    Path({str(started)!r}).write_text('started')
    await asyncio.sleep(1)
    Path({str(finished)!r}).write_text('finished')
def register(schedule, runner):
    schedule.add_job(runner.wrap(job), 'date')
bootstrap.register_asyncio_jobs = register
asyncio.run(scheduler.run_scheduler())
"""

    # 在独立工作目录启动调度进程，保留日志供失败诊断
    log_path = tmp_path / 'scheduler.log'
    with log_path.open('w', encoding='utf-8') as output:
        process = subprocess.Popen(
            [sys.executable, '-X', 'utf8', '-c', code],
            cwd=tmp_path,
            env=settings_environment(make_settings()),
            stdout=output,
            stderr=subprocess.STDOUT,
        )

        try:
            # 等待作业进入运行状态，避免把空闲退出误当成等待作业
            deadline = time.monotonic() + 15
            while not started.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail(log_path.read_text(encoding='utf-8'))

                time.sleep(0.05)

            # 作业已开始后发出停止信号，退出必须等到作业完成
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=10) == 0 and finished.exists()
        finally:
            # 即使验证失败也回收仍在运行的进程
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
