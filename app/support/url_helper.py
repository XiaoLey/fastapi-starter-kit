#
# URL 处理辅助函数
#
# 提供 URL 验证、编码等相关功能。
#

from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse


def is_url(url: str) -> bool:
    """
    判断是否为有效的 URL
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def encode_url(url: str) -> str:
    """对 URL 的 path、query 和 fragment 部分进行编码

    Args:
        url: 原始 URL

    Returns:
        编码后的 URL
    """
    # 解析 URL
    parsed_url = urlparse(url)

    # 编码 path、query 和 fragment
    encoded_path = quote(parsed_url.path)
    query_params = dict(parse_qsl(parsed_url.query))
    encoded_query = urlencode(query_params)
    encoded_fragment = quote(parsed_url.fragment)

    # 构建新的 URL
    new_url = urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        encoded_path,
        parsed_url.params,
        encoded_query,
        encoded_fragment,
    ))

    return new_url
