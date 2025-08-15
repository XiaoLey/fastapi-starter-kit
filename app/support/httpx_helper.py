#
# HTTPX 辅助函数模块
#
# 提供了基于 HTTPX 的高级下载功能，支持多线程、断点续传和代理。
#

import asyncio
import logging

import httpx
from httpx_socks import AsyncProxyTransport
from tenacity import retry, stop_after_attempt, wait_fixed

from app.providers.httpx import httpx_client_params
from config.http import settings as http_settings

_head_headers = {'User-Agent': http_settings.USER_AGENT, 'Range': 'bytes=0-'}

_download_headers = {'User-Agent': http_settings.USER_AGENT}


class DownloadManager:
    def __init__(
        self,
        url: str,
        file_size: int,
        chunk_size: int,
        num_workers: int,
        supports_resume: bool,
        headers=None,
        max_semaphore: int = 16,
        client: httpx.AsyncClient = None,
    ):
        self.url = url
        self.file_size = file_size
        self.chunk_size = chunk_size  # 控制每次从aiter_bytes读取的大小
        self.num_workers = num_workers
        self.supports_resume = supports_resume
        self.cache = {}  # 用于存储各个块的缓存
        self.current_yield_pos = 0  # 当前可以 yield 的数据块位置
        self.lock = asyncio.Lock()  # 用于确保并发访问缓存的安全
        self.semaphore = asyncio.Semaphore(max_semaphore)  # 控制最大并发数量
        self.headers = headers  # 请求头
        self.client = client  # httpx 异步客户端

    def calculate_ranges(self):
        """根据文件大小和 num_workers 计算 ranges"""
        block_size = self.file_size // self.num_workers
        ranges = [(i * block_size, (i + 1) * block_size - 1) for i in range(self.num_workers)]

        # 如果文件大小不能被整除，需要处理最后一个块
        if self.file_size % self.num_workers:
            ranges[-1] = (ranges[-1][0], self.file_size - 1)

        return ranges

    @retry(wait=wait_fixed(3), stop=stop_after_attempt(3))
    async def download_chunk(self, start: int, end: int, index: int) -> tuple:
        """下载指定范围的文件块，返回块和其 index"""
        headers = {'Range': f'bytes={start}-{end}'} if self.supports_resume else {}
        headers.update(self.headers)
        async with self.client.stream('GET', self.url, headers=headers) as response:
            response.raise_for_status()
            chunk = b''.join([chunk async for chunk in response.aiter_bytes(self.chunk_size)])  # 这里使用 chunk_size
            return index, chunk  # 返回块的索引和内容

    @retry(wait=wait_fixed(3), stop=stop_after_attempt(3))
    async def download_full_file(self):
        """下载整个文件，不支持断点续传"""
        async with self.client.stream('GET', self.url, headers=self.headers) as response:
            # 检查响应状态码
            response.raise_for_status()
            async for chunk in response.aiter_bytes(self.chunk_size):
                yield chunk

    async def download_file_iterator(self):
        """并行下载文件并按完成顺序处理（如果支持断点续传）"""
        if self.supports_resume and self.file_size is not None and self.file_size > 0 and self.num_workers > 1:
            ranges = self.calculate_ranges()

            # 创建下载任务
            tasks = [self.download_and_cache_chunk(start, end, index) for index, (start, end) in enumerate(ranges)]

            # 使用 asyncio.as_completed 按任务完成顺序处理
            for task in asyncio.as_completed(tasks):
                await task
                # 尝试按顺序输出已完成的块
                async for chunk in self.try_yield():
                    yield chunk
        else:
            if self.supports_resume:
                # 不支持断点续传的情况，直接一次性下载整个文件
                logging.info(
                    f'Download file without resume, because the server does not support resume. URL: {self.url}'
                )
            async for chunk in self.download_full_file():
                yield chunk

    async def download_and_cache_chunk(self, start: int, end: int, index: int):
        """下载并缓存文件块"""
        async with self.semaphore:  # 控制并发下载数量
            index, chunk = await self.download_chunk(start, end, index)
            async with self.lock:
                self.cache[index] = chunk

    async def try_yield(self):
        """检查缓存并按顺序 yield 数据"""
        async with self.lock:
            while self.current_yield_pos in self.cache:
                chunk = self.cache.pop(self.current_yield_pos)
                yield chunk
                self.current_yield_pos += 1


async def download_file_iterator(
    url: str, chunk_size: int = 1024, num_workers: int = 4, max_semaphore: int = 16, proxy_url: str | None = None
):
    """下载文件（迭代下载）

    Args:
        url: 文件下载地址
        chunk_size: 每次从aiter_bytes读取的块大小
        num_workers: 并行下载任务数
        max_semaphore: 最大并发数量
        proxy_url: 代理地址，可选

    Returns:
        文件块迭代器
    """
    httpx_mounts = {
        'all://': AsyncProxyTransport.from_url(
            proxy_url.replace('socks5h://', 'socks5://'), rdns='socks5h://' in proxy_url, http2=True
        )
        if proxy_url
        else httpx.AsyncHTTPTransport(retries=2, http2=True)
    }

    # 创建一个 httpx 异步客户端，使用代理（如果提供）
    async with httpx.AsyncClient(**httpx_client_params, mounts=httpx_mounts) as client:
        # 获取文件大小并检查是否支持断点续传
        response = await client.head(url, headers=_head_headers)
        try:
            file_size = int(response.headers['Content-Length'])
            supports_resume = response.headers.get('Accept-Ranges') == 'bytes'
        except KeyError:
            logging.warning('Content-Length not found, falling back to full file download.')
            file_size = None
            supports_resume = False

        manager = DownloadManager(
            url, file_size, chunk_size, num_workers, supports_resume, _download_headers, max_semaphore, client
        )

        # 迭代下载
        async for chunk in manager.download_file_iterator():
            yield chunk


async def get_file_content_type(url: str, proxy_url: str | None = None) -> str | None:
    """获取文件MIME类型，如果未获取到则返回 None

    Args:
        url: 文件地址
        proxy_url: 代理地址，可选

    Returns:
        Content-Type 或 None
    """
    httpx_mounts = {
        'all://': AsyncProxyTransport.from_url(
            proxy_url.replace('socks5h://', 'socks5://'), rdns='socks5h://' in proxy_url, http2=True
        )
        if proxy_url
        else httpx.AsyncHTTPTransport(retries=2, http2=True)
    }

    async with httpx.AsyncClient(**httpx_client_params, mounts=httpx_mounts) as client:
        response = await client.head(url, headers=_head_headers)
        return response.headers.get('Content-Type', default=None)
