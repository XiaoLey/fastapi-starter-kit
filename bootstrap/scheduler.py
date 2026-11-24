import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps

from apscheduler.events import EVENT_SCHEDULER_SHUTDOWN, SchedulerEvent  # pyright: ignore[reportMissingTypeStubs]
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # pyright: ignore[reportMissingTypeStubs]


class JobRunner:
    """跟踪协作异步作业；不支持强制终止同步线程"""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task[object]] = set()

    def wrap[**P, R](self, job: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[object, object, R]]:
        """将作业纳入收尾范围，不改变原作业的参数和返回值"""

        @wraps(job)
        async def run(*args: P.args, **kwargs: P.kwargs) -> R:
            task = asyncio.current_task()
            if task is None:
                raise RuntimeError('Job requires an asyncio task')

            # 在途登记覆盖作业的完整执行周期
            self.tasks.add(task)
            try:
                return await job(*args, **kwargs)
            finally:
                self.tasks.discard(task)

        return run

    async def drain(self, grace_seconds: float = 30) -> None:
        """等待在途作业，超出宽限期时请求取消并等待协作收尾

        Args:
            grace_seconds: 允许作业自然完成的时长（秒），不含取消后的收尾
        """
        # 允许已投递到事件循环的作业先登记，再冻结本次等待集合
        await asyncio.sleep(0)
        if not self.tasks:
            return

        # 给予已登记作业协作完成的窗口
        _, pending = await asyncio.wait(tuple(self.tasks), timeout=grace_seconds)

        # 请求超出宽限期的作业协作取消
        for task in pending:
            task.cancel()

        # 取消后仍需等待收尾，单个作业失败不中断等待
        await asyncio.gather(*pending, return_exceptions=True)


def register_asyncio_jobs(scheduler: AsyncIOScheduler, runner: JobRunner) -> None:
    """集中注册业务协作异步作业；模板不预置业务任务"""


def create_asyncio_scheduler(runner: JobRunner) -> AsyncIOScheduler:
    """创建绑定当前事件循环、已登记作业但尚未启动的调度器"""
    scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop())
    register_asyncio_jobs(scheduler, runner)
    return scheduler


async def stop_scheduler(scheduler: AsyncIOScheduler, runner: JobRunner, grace_seconds: float = 30) -> None:
    """停止调度器并等待受跟踪作业收尾；未运行时不执行操作

    Args:
        grace_seconds: 允许作业自然完成的时长（秒），不含取消后的收尾

    Raises:
        TimeoutError: 调度器未在期限内确认关闭
    """
    if not scheduler.running:
        return

    # 暂停投递，避免等待期间继续触发新作业
    scheduler.pause()

    # 调度器关闭前先等待在途作业收尾
    await runner.drain(grace_seconds)

    # shutdown是普通方法，通过公开关闭事件确认真正完成
    stopped = asyncio.Event()

    def on_shutdown(event: SchedulerEvent) -> None:
        stopped.set()

    # 先订阅再发出关闭请求，不能错过关闭事件
    scheduler.add_listener(on_shutdown, EVENT_SCHEDULER_SHUTDOWN)
    try:
        scheduler.shutdown(wait=False)
        await asyncio.wait_for(stopped.wait(), timeout=5)
    finally:
        scheduler.remove_listener(on_shutdown)
