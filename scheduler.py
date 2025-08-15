import asyncio
import logging

from app.providers import logging_provider
from bootstrap.scheduler import create_asyncio_scheduler

logging_provider.register()

asyncio_scheduler = create_asyncio_scheduler()

if __name__ == '__main__':
    try:
        # 启动 AsyncIOScheduler 在 asyncio 事件循环中
        loop = asyncio.get_event_loop()
        asyncio_scheduler.start()

        # 阻塞主线程以保持事件循环运行
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        logging.info('Scheduler will shutdown...')
    finally:
        if asyncio_scheduler:
            try:
                asyncio_scheduler.shutdown(wait=False)
            except Exception as shutdown_exception:
                logging.error(f'Error occurred while shutting down asyncio scheduler: {shutdown_exception}')
