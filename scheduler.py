import asyncio
import signal
import sys

from app.providers.logging_provider import initialize
from bootstrap.scheduler import JobRunner, create_asyncio_scheduler, stop_scheduler
from config.settings import load_settings


async def run_scheduler() -> None:
    """运行独立调度进程，在停止或取消时收尾在途协作作业"""
    settings = load_settings()

    # 启动调度器前应用进程日志配置
    initialize(settings)

    # 停止事件承接进程信号，不直接在回调中关闭调度器
    stop = asyncio.Event()

    # 作业执行与收尾绑定到当前事件循环
    runner = JobRunner()
    scheduler = create_asyncio_scheduler(runner)

    # POSIX信号唤醒停止事件；Windows Ctrl+C由asyncio.run取消主任务后进入finally
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    if sys.platform != 'win32':
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, stop.set)
            installed.append(signum)

    # 运行至停止信号或取消，退出时统一收尾
    try:
        scheduler.start()
        await stop.wait()
    finally:
        # 先停止调度，并收尾仍在途的作业
        await stop_scheduler(scheduler, runner)

        # 仅撤销本轮安装的信号处理
        for signum in installed:
            loop.remove_signal_handler(signum)


if __name__ == '__main__':
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        pass
