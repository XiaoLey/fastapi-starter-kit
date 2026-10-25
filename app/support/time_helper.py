from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo


def _aware(dt: datetime, source_timezone_str: str | None, fold: Literal[0, 1] | None) -> datetime:
    if dt.utcoffset() is not None:
        return dt
    if source_timezone_str is None:
        raise ValueError('Naive datetime requires an explicit source timezone')

    # 往返检查拒绝DST空洞；偏移不同则必须显式选择歧义分支
    zone = ZoneInfo(source_timezone_str)
    candidates = [dt.replace(tzinfo=zone, fold=value) for value in (0, 1)]
    valid = [value.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == dt for value in candidates]
    if not any(valid):
        raise ValueError('Nonexistent local time')
    if all(valid) and candidates[0].utcoffset() != candidates[1].utcoffset() and fold is None:
        raise ValueError('Ambiguous local time requires explicit fold')
    selected = fold if fold is not None else 0
    if not valid[selected]:
        raise ValueError('Invalid fold for local time')
    return candidates[selected]


def parse_datetime_in_timezone(
    time_str: str,
    timezone_str: str,
    time_format: str | None = None,
    *,
    source_timezone_str: str | None = None,
    fold: Literal[0, 1] | None = None,
) -> datetime:
    """解析时间并转换到目标时区；无偏移输入须显式提供源时区"""
    parsed = datetime.strptime(time_str, time_format) if time_format else datetime.fromisoformat(time_str)
    if time_str.endswith('Z') and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return _aware(parsed, source_timezone_str, fold).astimezone(ZoneInfo(timezone_str))


def convert_to_timezone(
    dt: datetime, target_timezone_str: str, *, source_timezone_str: str | None = None, fold: Literal[0, 1] | None = None
) -> datetime:
    """转换绝对时刻，无时区值不能依赖机器本地时区解释"""
    return _aware(dt, source_timezone_str, fold).astimezone(ZoneInfo(target_timezone_str))


def format_datetime_as_utc_iso8601(
    dt: datetime, *, source_timezone_str: str | None = None, fold: Literal[0, 1] | None = None
) -> str:
    """返回毫秒精度、以Z结尾的UTC时间文本"""
    return (
        _aware(dt, source_timezone_str, fold).astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    )
