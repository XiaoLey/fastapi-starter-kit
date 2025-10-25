import httpx
from httpx import AsyncHTTPTransport

_limits = httpx.Limits(
    max_connections=32,  # 最大同时并发连接数
    max_keepalive_connections=16,  # 最大保持活动的连接数
)

_timeout = httpx.Timeout(
    connect=10.0,  # 建立连接的超时时间
    read=300.0,  # 每次读取数据的超时时间
    write=30.0,  # 每次发送数据的超时时间
    pool=20.0,  # 从连接池获取连接的最大等待时间
)


httpx_client_params = {
    'limits': _limits,  # 最大并发连接数
    'timeout': _timeout,  # 超时时间
    'http2': True,  # 是否启用HTTP2
    'follow_redirects': True,  # 是否重定向
    'max_redirects': 5,  # 最大重定向次数
}

# 全局客户端实例
httpx_client = httpx.AsyncClient(**httpx_client_params, transport=AsyncHTTPTransport(retries=2, http2=True))


# 清理函数（应用退出时调用）
async def close_httpx_client():
    """关闭全局 httpx 客户端，释放资源"""
    await httpx_client.aclose()
