#
# 信息验证
#

from typing import Union


def hide_cellphone(value: Union[str, None]) -> Union[str, None]:
    """
    隐藏手机号

    :param value: 手机号
    :return: 隐藏后的手机号
    """
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def hide_email(value: Union[str, None]) -> Union[str, None]:
    """
    隐藏邮箱

    :param value: 邮箱
    :return: 隐藏后的邮箱
    """
    if not value:
        return None
    if len(value) <= 2:
        return "****"
    return f"{value[:2]}****{value[-2:]}"
