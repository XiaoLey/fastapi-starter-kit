from typing import Literal, Protocol


class SmsSender(Protocol):
    """确认供应商接受发送，支持协作取消；实例只属于一个启动周期"""

    async def send_verification_code(
        self, *, cellphone: str, code: str, purpose: Literal['register', 'login'], expires_in: int
    ) -> None:
        """请求交付验证码，有效期以秒计；正常返回仅表示供应商接受

        Raises:
            SmsSendError: 供应商未确认接受发送
        """
        ...

    async def aclose(self) -> None:
        """关闭本实例拥有的交付资源"""
        ...
