from typing import Literal, Protocol


class EmailSender(Protocol):
    """确认供应商接受邮件，支持协作取消；实例属于单个启动周期"""

    async def send_verification_code(
        self, *, email: str, code: str, purpose: Literal['register', 'login'], expires_in: int
    ) -> None:
        """请求交付验证码，有效期以秒计；正常返回仅表示供应商接受

        Raises:
            EmailSendError: 供应商未确认接受发送
        """
        ...

    async def aclose(self) -> None:
        """关闭本实例拥有的交付资源"""
        ...
