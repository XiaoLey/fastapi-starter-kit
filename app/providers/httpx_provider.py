import httpx


def create_client() -> httpx.AsyncClient:
    """创建由调用者关闭的HTTP客户端，不在导入时创建连接资源"""
    return httpx.AsyncClient(
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        timeout=httpx.Timeout(connect=10, read=300, write=30, pool=20),
        http2=True,
        follow_redirects=True,
        max_redirects=5,
    )
