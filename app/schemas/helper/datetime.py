#
# 日期时间验证
#

import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Union

from dateutil import parser


def wrap_datetime(value: Union[datetime.datetime, str, None]) -> Union[datetime.datetime, None]:
    """
    包装时间对象

    :param value: 时间或时间字符串
    :return: 包装后的时间对象
    """
    if not value:
        return None
    if isinstance(value, str):
        return parser.parse(value, fuzzy=True)
    return value


def wrap_date(value: Union[datetime.date, datetime.datetime, str, None]) -> Union[datetime.date, None]:
    """
    包装日期对象

    :param value: 日期或日期字符串
    :return: 包装后的日期对象
    """
    if not value:
        return None
    if isinstance(value, str):
        return parser.parse(value, fuzzy=True).date()
    return value


def format_datetime(value: Union[datetime.datetime, str, None]) -> Union[str, None]:
    """
    格式化时间，支持时区处理。如果 datetime 对象有时区信息，则转换为 UTC 后再进行格式化。

    :param value: 时间或时间字符串
    :return: 格式化后的时间字符串
    """
    if not value:
        return None

    # 如果输入是字符串，使用 dateutil 解析为 datetime 对象
    if isinstance(value, str):
        value = parser.parse(value)

    # 如果 datetime 对象有时区信息，转换为 UTC
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc)

    return value.strftime('%Y-%m-%d %H:%M:%S')


def format_date(value: Union[datetime.date, datetime.datetime, str, None]) -> Union[str, None]:
    """
    格式化日期，支持时区处理。如果 datetime 对象有时区信息，则转换为 UTC 后再进行格式化。

    :param value: 日期或日期字符串
    :return: 格式化后的日期字符串
    """
    if not value:
        return None

    # 如果输入是字符串，使用 dateutil 解析为 datetime 对象
    if isinstance(value, str):
        value = parser.parse(value)

    # 如果是 datetime 对象，并且有时区信息，先转换为 UTC
    if isinstance(value, datetime.datetime) and value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc)

    # 格式化为日期字符串
    return value.strftime('%Y-%m-%d')


def truncate_price(value: Decimal) -> Decimal:
    """
    截断价格，保留 2 位小数

    :param value: 价格
    :return: 截断后的价格
    """
    if isinstance(value, float) or isinstance(value, str):
        value = Decimal(value)
    return value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
