import asyncio
import signal
import sys

from app.providers.logging_provider import initialize
from bootstrap.scheduler import JobRunner, create_asyncio_scheduler, stop_scheduler
from config.settings import load_settings


async def run_scheduler() -> None:
    # 为独立调度进程加载配置并初始化日志
    settings = load_settings()
    initialize(settings)

    # 将调度任务和停止状态绑定到当前事件循环
    stop = asyncio.Event()
    runner = JobRunner()
    scheduler = create_asyncio_scheduler(runner)
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []

    # POSIX信号唤醒停止事件；Windows Ctrl+C由asyncio.run取消主任务后进入finally
    if sys.platform != 'win32':
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, stop.set)
            installed.append(signum)

    # 运行至停止信号或取消，退出时统一收尾
    try:
        scheduler.start()
        await stop.wait()
    finally:
        await stop_scheduler(scheduler, runner)
        for signum in installed:
            loop.remove_signal_handler(signum)


if __name__ == '__main__':
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        pass
