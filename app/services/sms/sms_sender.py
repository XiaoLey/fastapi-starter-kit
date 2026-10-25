from typing import Literal, Protocol


class SmsSender(Protocol):
    """确认供应商接受发送，支持协作取消；实例只属于一个启动周期"""

    async def send_verification_code(
        self, *, cellphone: str, code: str, purpose: Literal['register', 'login'], expires_in: int
    ) -> None: ...

    async def aclose(self) -> None: ...
