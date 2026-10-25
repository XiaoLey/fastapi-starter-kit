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
        @wraps(job)
        async def run(*args: P.args, **kwargs: P.kwargs) -> R:
            task = asyncio.current_task()
            if task is None:
                raise RuntimeError('Job requires an asyncio task')
            self.tasks.add(task)
            try:
                return await job(*args, **kwargs)
            finally:
                self.tasks.discard(task)

        return run

    async def drain(self, grace_seconds: float = 30) -> None:
        # 允许已投递到事件循环的作业先登记，再冻结本次等待集合
        await asyncio.sleep(0)
        if not self.tasks:
            return
        _, pending = await asyncio.wait(tuple(self.tasks), timeout=grace_seconds)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


def register_asyncio_jobs(scheduler: AsyncIOScheduler, runner: JobRunner) -> None:
    """集中注册业务协作异步作业；模板不预置业务任务"""


def create_asyncio_scheduler(runner: JobRunner) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop())
    register_asyncio_jobs(scheduler, runner)
    return scheduler


async def stop_scheduler(scheduler: AsyncIOScheduler, runner: JobRunner, grace_seconds: float = 30) -> None:
    if not scheduler.running:
        return
    scheduler.pause()
    await runner.drain(grace_seconds)

    # shutdown是普通方法，通过公开关闭事件确认真正完成
    stopped = asyncio.Event()

    def on_shutdown(event: SchedulerEvent) -> None:
        stopped.set()

    scheduler.add_listener(on_shutdown, EVENT_SCHEDULER_SHUTDOWN)
    try:
        scheduler.shutdown(wait=False)
        await asyncio.wait_for(stopped.wait(), timeout=5)
    finally:
        scheduler.remove_listener(on_shutdown)
