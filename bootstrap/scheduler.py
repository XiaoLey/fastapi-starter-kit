import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# from apscheduler.triggers.cron import CronTrigger
# from apscheduler.triggers.date import DateTrigger


def create_asyncio_scheduler() -> AsyncIOScheduler:
    logging.info('AsyncIOScheduler initializing')
    scheduler: AsyncIOScheduler = AsyncIOScheduler()
    register_asyncio_jobs(scheduler)
    return scheduler


def register_asyncio_jobs(scheduler: AsyncIOScheduler):
    """注册异步任务"""
    first_run_time = datetime.datetime.now() + datetime.timedelta(seconds=10)  # 延迟 10 秒启动

    # 测试
    # scheduler.add_job(
    #     lambda: logging.info("AsyncIOScheduler job test"),
    #     trigger=CronTrigger(second="*/5"),  # 每 5 秒执行一次
    #     next_run_time=first_run_time,
    # )
