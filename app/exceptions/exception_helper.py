#
# 异常操作
#

from fastapi import HTTPException


def exceptions_to_response(*args: HTTPException):
    """
    异常转换为HTTP响应

    :param args: 异常（HTTPException）
    :return: HTTP响应
    """
    result_dict = {}

    for exception in args:
        # 判断是否继承HTTPException
        if issubclass(exception, HTTPException):
            e = exception()
            result_dict[e.status_code] = {"content": {"application/json": {"example": {"detail": e.detail}}}}

    return result_dict
