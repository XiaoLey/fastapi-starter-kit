import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from config.settings import PROJECT_ROOT
from tests.conftest import make_settings, settings_environment

pytestmark = [
    pytest.mark.integration,
    pytest.mark.process,
    pytest.mark.skipif(sys.platform == 'win32', reason='Linux VM process acceptance'),
]


@pytest.mark.parametrize('trusted', ['', '127.0.0.1'])
def test_real_main_proxy_boundary(tmp_path: Path, trusted: str) -> None:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    settings = make_settings(APP_SERVER_PORT=port, APP_TRUSTED_PROXY_IPS=trusted)
    environment = settings_environment(settings)
    environment['FORWARDED_ALLOW_IPS'] = '*'
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
            # 通过真实入口启动并等待监听，同时检查提前退出
            base = f'http://127.0.0.1:{port}'
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail(log_path.read_text(encoding='utf-8'))
                try:
                    if httpx.get(f'{base}/_probe/client', timeout=0.3, trust_env=False).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)

            # 外部宽泛环境变量不能绕过应用入口的显式代理边界
            response = httpx.get(
                f'{base}/_probe/client',
                headers={'X-Real-IP': '127.0.0.1', 'X-Forwarded-For': '198.51.100.42', 'X-Forwarded-Proto': 'https'},
                trust_env=False,
            )
            expected = (
                {'client': '198.51.100.42', 'scheme': 'https'} if trusted else {'client': '127.0.0.1', 'scheme': 'http'}
            )
            assert response.json() == expected
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    pytest.fail('Uvicorn did not terminate gracefully')
    # 正常信号退出仍必须完成应用收尾
    assert process.returncode in (0, -signal.SIGTERM)
    assert 'Application shutdown complete' in log_path.read_text(encoding='utf-8')


def test_scheduler_sigterm_waits_for_owned_job(tmp_path: Path) -> None:
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
            # 在作业实际运行期间发送信号，完成标记只由正常完成路径写入
            deadline = time.monotonic() + 15
            while not started.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail(log_path.read_text(encoding='utf-8'))
                time.sleep(0.05)
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=10) == 0 and finished.exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
