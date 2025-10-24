#
# 时间处理辅助函数
#
# 提供处理时区转换、时间格式化等常用时间操作的函数。
#

from datetime import datetime, timezone

import pytz


def parse_datetime_in_timezone(time_str: str, timezone_str: str, time_format: str = '%Y-%m-%dT%H:%M:%SZ') -> datetime:
    """按给定格式解析无时区的时间字符串，并附加指定时区"""
    naive_dt = datetime.strptime(time_str, time_format)
    tz = pytz.timezone(timezone_str)
    return tz.localize(naive_dt)


def convert_to_timezone(dt: datetime, target_timezone_str: str) -> datetime:
    """将 aware datetime 转换到目标时区"""
    target_tz = pytz.timezone(target_timezone_str)
    return dt.astimezone(target_tz)


def format_datetime_as_utc_iso8601(dt: datetime) -> str:
    """格式化为带毫秒且以 Z 结尾的 UTC ISO8601 字符串"""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
