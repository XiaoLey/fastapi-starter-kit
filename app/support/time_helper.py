from datetime import datetime, timezone

import pytz


def parse_datetime(time_str, timezone_str, time_format: str = '%Y-%m-%d %H:%M:%S'):
    """
    Parses a given time string into a timezone-aware datetime object.

    :param time_str: String representing the time.
    :param time_format: Format of the time string, e.g., '%Y-%m-%d %H:%M:%S'.
    :param timezone_str: Timezone string, e.g., 'Asia/Tokyo'.
    :return: A timezone-aware datetime object.
    """
    # 创建一个无时区信息的 datetime 对象
    naive_datetime = datetime.strptime(time_str, time_format)
    # 获取时区对象
    timezone = pytz.timezone(timezone_str)
    # 本地化 datetime 对象
    aware_datetime = timezone.localize(naive_datetime)
    return aware_datetime


def convert_timezone(datetime_obj: datetime, target_timezone_str: str) -> datetime:
    """
    Converts a given timezone-aware datetime object to a different timezone.

    :param datetime_obj: A timezone-aware datetime object.
    :param target_timezone_str: Target timezone string, e.g., 'UTC'.
    :return: A new datetime object in the target timezone.
    """
    # 获取目标时区对象
    target_timezone = pytz.timezone(target_timezone_str)
    # 转换时区
    converted_datetime = datetime_obj.astimezone(target_timezone)
    return converted_datetime


def datetime_to_iso8601_z(dt):
    """
    将 datetime 对象转换为 ISO 8601 格式，包含毫秒，并以 'Z' 结尾表示 UTC

    :param dt: datetime 对象
    :return: ISO 8601 格式的字符串
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()  # 本地化到本地时区
    dt_utc = dt.astimezone(timezone.utc)  # 转换为 UTC 时间
    # 格式化为 ISO 8601 格式，包含毫秒，并以 'Z' 结尾表示 UTC
    iso_format = dt_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    return iso_format
