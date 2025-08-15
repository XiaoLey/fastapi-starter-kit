#
# 时间处理辅助函数
#
# 提供处理时区转换、时间格式化等常用时间操作的函数。
#

from datetime import datetime, timezone

import pytz


def parse_datetime(time_str, timezone_str, time_format: str = '%Y-%m-%d %H:%M:%S'):
    """将给定的时间字符串解析为带时区信息的 datetime 对象

    Args:
        time_str: 表示时间的字符串
        time_format: 时间字符串的格式，例如 '%Y-%m-%d %H:%M:%S'
        timezone_str: 时区字符串，例如 'Asia/Tokyo'

    Returns:
        带时区信息的 datetime 对象
    """
    # 创建一个无时区信息的 datetime 对象
    naive_datetime = datetime.strptime(time_str, time_format)
    # 获取时区对象
    timezone = pytz.timezone(timezone_str)
    # 本地化 datetime 对象
    aware_datetime = timezone.localize(naive_datetime)
    return aware_datetime


def convert_timezone(datetime_obj: datetime, target_timezone_str: str) -> datetime:
    """将给定的带时区 datetime 对象转换为另一个时区的时间

    Args:
        datetime_obj: 带时区信息的 datetime 对象
        target_timezone_str: 目标时区字符串，例如 'UTC'

    Returns:
        转换到目标时区后的新的 datetime 对象
    """
    # 获取目标时区对象
    target_timezone = pytz.timezone(target_timezone_str)
    # 转换时区
    converted_datetime = datetime_obj.astimezone(target_timezone)
    return converted_datetime


def datetime_to_iso8601_z(dt):
    """将 datetime 对象转换为 ISO 8601 格式字符串，包含毫秒，并以 'Z' 结尾表示 UTC

    Args:
        dt: datetime 对象

    Returns:
        ISO 8601 格式的字符串（UTC，带毫秒，结尾为 Z）
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()  # 本地化到本地时区
    dt_utc = dt.astimezone(timezone.utc)  # 转换为 UTC 时间
    # 格式化为 ISO 8601 格式，包含毫秒，并以 'Z' 结尾表示 UTC
    iso_format = dt_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    return iso_format
