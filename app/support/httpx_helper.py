#
# HTTPX 辅助函数模块
#
# 提供了基于 HTTPX 的高级下载功能，支持多线程、断点续传和代理。
#

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator

import aiofiles
import httpx
from httpx_socks import AsyncProxyTransport

from app.providers.httpx_provider import httpx_client_params
from config.http import settings as http_settings

_head_headers = {'User-Agent': http_settings.USER_AGENT, 'Range': 'bytes=0-'}
_download_headers = {'User-Agent': http_settings.USER_AGENT}

# 常量定义
MIN_BLOCK_SIZE = 1024 * 1024  # 1MB
MAX_BLOCK_SIZE = 50 * 1024 * 1024  # 50MB
MAX_CHUNK_IN_MEMORY = 10 * 1024 * 1024  # 10MB


class DownloadError(Exception):
    """下载相关异常"""

    pass


class DownloadManager:
    def __init__(
        self,
        url: str,
        file_size: int,
        chunk_size: int,
        num_workers: int,
        supports_resume: bool,
        headers: dict | None = None,
        max_semaphore: int = 16,
        client: httpx.AsyncClient = None,
        timeout: float | None = None,
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
        self.headers = headers or {}  # 请求头
        self.client = client  # httpx 异步客户端
        self.timeout = timeout  # 超时时间
        self._cancelled = False  # 取消标志

    def calculate_optimal_ranges(self) -> list[tuple[int, int]]:
        """根据文件大小动态计算最优的块大小和数量"""
        if not self.file_size or self.file_size < MIN_BLOCK_SIZE * 2:
            # 小文件不分块
            return [(0, self.file_size - 1)] if self.file_size else []

        # 计算块大小，限制在合理范围内
        block_size = self.file_size // self.num_workers
        block_size = max(MIN_BLOCK_SIZE, min(block_size, MAX_BLOCK_SIZE))

        # 重新计算实际需要的 workers 数
        actual_workers = (self.file_size + block_size - 1) // block_size

        ranges = []
        for i in range(actual_workers):
            start = i * block_size
            end = min(start + block_size - 1, self.file_size - 1)
            ranges.append((start, end))

        logging.debug(f'Calculated {len(ranges)} download ranges for file size {self.file_size}')
        return ranges

    async def download_chunk_with_retry(
        self, start: int, end: int, index: int, max_retries: int = 3
    ) -> tuple[int, bytes]:
        """带重试的下载块"""
        last_error = None

        for attempt in range(max_retries):
            if self._cancelled:
                raise asyncio.CancelledError('Download cancelled')

            try:
                return await self._download_chunk_internal(start, end, index)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # 404 不重试
                    raise
                elif e.response.status_code in [503, 429]:  # 服务不可用或限流
                    wait_time = min(2**attempt, 10)  # 指数退避
                    logging.warning(
                        f'HTTP {e.response.status_code} error, retry {attempt + 1}/{max_retries} '
                        f'after {wait_time}s for chunk {index}'
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    raise

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                wait_time = min(2**attempt, 10)
                logging.warning(
                    f'Network error: {e.__class__.__name__}, retry {attempt + 1}/{max_retries} '
                    f'after {wait_time}s for chunk {index}'
                )
                await asyncio.sleep(wait_time)
                last_error = e

            except Exception as e:
                logging.error(f'Unexpected error downloading chunk {index}: {e}')
                raise

        raise DownloadError(f'Max retries exceeded for chunk {index}') from last_error

    async def _download_chunk_internal(self, start: int, end: int, index: int) -> tuple[int, bytes]:
        """内部下载实现，含内存优化处理"""
        headers = {}
        if self.supports_resume:
            headers['Range'] = f'bytes={start}-{end}'
        headers.update(self.headers)

        async with self.client.stream('GET', self.url, headers=headers) as response:
            response.raise_for_status()

            # 分批读取以优化内存使用
            chunks = []
            total_size = 0

            async for chunk in response.aiter_bytes(self.chunk_size):
                if self._cancelled:
                    raise asyncio.CancelledError('Download cancelled')

                chunks.append(chunk)
                total_size += len(chunk)

                # 如果累积太大，先合并一次以减少内存碎片
                if total_size > MAX_CHUNK_IN_MEMORY:
                    chunks = [b''.join(chunks)]

            return index, b''.join(chunks)

    async def download_full_file(self) -> AsyncIterator[bytes]:
        """下载整个文件，不支持断点续传"""
        async with self.client.stream('GET', self.url, headers=self.headers) as response:
            response.raise_for_status()

            async for chunk in response.aiter_bytes(self.chunk_size):
                if self._cancelled:
                    raise asyncio.CancelledError('Download cancelled')
                yield chunk

    async def download_file_iterator(self) -> AsyncIterator[bytes]:
        """并行下载文件并按顺序输出"""
        try:
            if self.supports_resume and self.file_size and self.file_size > 0 and self.num_workers > 1:
                ranges = self.calculate_optimal_ranges()

                if len(ranges) == 1:
                    # 如果只有一个范围，直接下载
                    logging.debug('File too small for parallel download, using single connection')
                    async for chunk in self.download_full_file():
                        yield chunk
                else:
                    # 创建下载任务
                    tasks = [
                        self.download_and_cache_chunk(start, end, index) for index, (start, end) in enumerate(ranges)
                    ]

                    # 使用 asyncio.as_completed 按任务完成顺序处理
                    for task in asyncio.as_completed(tasks):
                        await task
                        # 尝试按顺序输出已完成的块
                        async for chunk in self.try_yield():
                            yield chunk

                    # 最后确保所有块都已输出
                    async for chunk in self.try_yield():
                        yield chunk
            else:
                if self.supports_resume:
                    logging.info(f'Download file without resume support. URL: {self.url}')
                async for chunk in self.download_full_file():
                    yield chunk

        except asyncio.CancelledError:
            self._cancelled = True
            logging.info(f'Download cancelled for URL: {self.url}')
            raise

    async def download_and_cache_chunk(self, start: int, end: int, index: int):
        """下载并缓存文件块"""
        async with self.semaphore:  # 控制并发下载数量
            index, chunk = await self.download_chunk_with_retry(start, end, index)
            async with self.lock:
                self.cache[index] = chunk

    async def try_yield(self) -> AsyncIterator[bytes]:
        """检查缓存并按顺序 yield 数据"""
        async with self.lock:
            while self.current_yield_pos in self.cache:
                chunk = self.cache.pop(self.current_yield_pos)
                yield chunk
                self.current_yield_pos += 1

    def cancel(self):
        """取消下载"""
        self._cancelled = True


async def check_resume_support(
    client: httpx.AsyncClient, url: str, headers: dict | None = None
) -> tuple[int | None, bool]:
    """检测断点续传支持

    Returns:
        (file_size, supports_resume)
    """
    headers = headers or {}
    headers.update(_head_headers)

    try:
        # 先用 HEAD 请求
        response = await client.head(url, headers=headers)
        file_size = int(response.headers.get('Content-Length', 0)) if 'Content-Length' in response.headers else None

        # 初步检查 Accept-Ranges
        if response.headers.get('Accept-Ranges') != 'bytes' or not file_size:
            return file_size, False

        # 验证 Range 请求的实际支持情况（部分服务器仅声明支持）
        try:
            test_headers = dict(headers)
            test_headers['Range'] = 'bytes=0-0'
            test_response = await client.get(url, headers=test_headers)
            # 检查是否返回 206 Partial Content
            supports_resume = test_response.status_code == 206
        except Exception:
            supports_resume = False

    except Exception as e:
        logging.warning(f'Failed to check resume support: {e}')
        return None, False

    return file_size, supports_resume


async def download_file_iterator(
    url: str,
    chunk_size: int = 8192,
    num_workers: int = 4,
    max_semaphore: int = 16,
    proxy_url: str | None = None,
    timeout: float | None = None,
    verify_ssl: bool = True,
) -> AsyncIterator[bytes]:
    """下载文件（迭代下载）

    Args:
        url: 文件下载地址
        chunk_size: 每次从aiter_bytes读取的块大小
        num_workers: 并行下载任务数
        max_semaphore: 最大并发数量
        proxy_url: 代理地址，可选
        timeout: 超时时间（秒），可选
        verify_ssl: 是否验证SSL证书

    Yields:
        文件块

    Raises:
        DownloadError: 下载失败
        asyncio.TimeoutError: 下载超时
    """
    httpx_mounts = {
        'all://': AsyncProxyTransport.from_url(
            proxy_url.replace('socks5h://', 'socks5://'), rdns='socks5h://' in proxy_url, http2=True
        )
        if proxy_url
        else httpx.AsyncHTTPTransport(retries=0, http2=True)  # 自行处理重试逻辑
    }

    client_params = dict(httpx_client_params)
    client_params['verify'] = verify_ssl

    # 创建一个 httpx 异步客户端
    async with httpx.AsyncClient(**client_params, mounts=httpx_mounts) as client:
        # 检查文件大小和断点续传支持
        file_size, supports_resume = await check_resume_support(client, url)

        if not file_size:
            logging.warning('Content-Length not found, falling back to single connection download.')
            supports_resume = False

        manager = DownloadManager(
            url=url,
            file_size=file_size,
            chunk_size=chunk_size,
            num_workers=num_workers,
            supports_resume=supports_resume,
            headers=_download_headers,
            max_semaphore=max_semaphore,
            client=client,
            timeout=timeout,
        )

        # 迭代下载
        try:
            if timeout:
                async with asyncio.timeout(timeout):
                    async for chunk in manager.download_file_iterator():
                        yield chunk
            else:
                async for chunk in manager.download_file_iterator():
                    yield chunk
        except asyncio.TimeoutError:
            manager.cancel()
            logging.error(f'Download timeout after {timeout} seconds for URL: {url}')
            raise


async def download_with_hash_verification(
    url: str, expected_hash: str | None = None, hash_algorithm: str = 'sha256', **kwargs
) -> AsyncIterator[bytes]:
    """下载并验证文件哈希

    Args:
        url: 下载URL
        expected_hash: 期望的哈希值（十六进制字符串）
        hash_algorithm: 哈希算法（默认sha256）
        **kwargs: 传递给download_file_iterator的其他参数

    Yields:
        文件块

    Raises:
        ValueError: 哈希值不匹配
    """
    hasher = hashlib.new(hash_algorithm)

    async for chunk in download_file_iterator(url, **kwargs):
        hasher.update(chunk)
        yield chunk

    if expected_hash:
        actual_hash = hasher.hexdigest()
        if actual_hash.lower() != expected_hash.lower():
            raise ValueError(f'Hash mismatch for {url}: expected {expected_hash}, got {actual_hash}')
        logging.info(f'Hash verification successful for {url}')


async def get_file_content_type(url: str, proxy_url: str | None = None, verify_ssl: bool = True) -> str | None:
    """获取文件MIME类型，如果未获取到则返回 None

    Args:
        url: 文件地址
        proxy_url: 代理地址，可选
        verify_ssl: 是否验证SSL证书

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

    client_params = dict(httpx_client_params)
    client_params['verify'] = verify_ssl

    async with httpx.AsyncClient(**client_params, mounts=httpx_mounts) as client:
        try:
            response = await client.head(url, headers=_head_headers)
            return response.headers.get('Content-Type', default=None)
        except Exception as e:
            logging.warning(f'Failed to get content type for {url}: {e}')
            return None


async def download_to_file(url: str, output_path: str, expected_hash: str | None = None, **kwargs) -> None:
    """下载文件并保存到本地

    Args:
        url: 下载URL
        output_path: 输出文件路径
        expected_hash: 期望的哈希值（可选）
        **kwargs: 传递给download_file_iterator的其他参数
    """

    iterator = (
        download_with_hash_verification(url, expected_hash, **kwargs)
        if expected_hash
        else download_file_iterator(url, **kwargs)
    )

    async with aiofiles.open(output_path, 'wb') as f:
        async for chunk in iterator:
            await f.write(chunk)

    logging.info(f'Successfully downloaded {url} to {output_path}')
