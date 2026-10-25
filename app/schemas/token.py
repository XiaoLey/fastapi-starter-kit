from datetime import datetime
from uuid import UUID

from app.schemas.base import BaseSc


class TokenSc(BaseSc):
    token_type: str = 'bearer'
    expires_in: int
    access_token: str


class TokenStatusSc(BaseSc):
    user_id: UUID
    expires_at: datetime
    issued_at: datetime
    is_valid: bool = True
