from typing import Literal, Protocol


class EmailSender(Protocol):
    """确认供应商接受邮件，支持协作取消；实例属于单个启动周期"""

    async def send_verification_code(
        self, *, email: str, code: str, purpose: Literal['register', 'login'], expires_in: int
    ) -> None: ...

    async def aclose(self) -> None: ...
