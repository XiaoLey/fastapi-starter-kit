# 普通业务开发

以下示例添加一个不要求登录的便笺接口，直接使用 FastAPI、Pydantic 和 SQLAlchemy。先完成 [README 的默认启动](../README.md#1-先跑起来)，确认数据库已升级到当前 head。

## 模型与 schema

普通业务表通常继承 `TableModel`，获得 UUID、审计时间和软删除字段；不需要这些表级生命周期字段时继承 `Base`。软删除不会自动过滤，读取时按需要显式加入 `exist_filter()`。

```python
# app/models/note.py
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import TableModel


class NoteModel(TableModel):
    __tablename__ = 'notes'

    title: Mapped[str] = mapped_column(sa.String(200))
    body: Mapped[str] = mapped_column(sa.Text, default='')
```

```python
# app/schemas/note.py
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSc


class NoteCreateSc(BaseSc):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default='', max_length=20000)


class NoteSc(BaseSc):
    id: UUID
    title: str
    body: str
```

## HTTP API 与显式注册

```python
# app/http/api/notes.py
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.deps.database_deps import get_db
from app.models.note import NoteModel
from app.schemas.note import NoteCreateSc, NoteSc

router = APIRouter(prefix='/notes', tags=['notes'])


@router.post('', response_model=NoteSc, status_code=201)
async def create_note(
    data: NoteCreateSc, session: Annotated[AsyncSession, Depends(get_db)]
) -> NoteSc:
    note = NoteModel(title=data.title, body=data.body)
    session.add(note)
    await session.commit()
    return NoteSc.model_validate(note)
```

```python
# app/http/api/__init__.py
from fastapi import APIRouter

from app.http.api.notes import router as notes_router

router = APIRouter()
router.include_router(notes_router)
```

普通 HTTP 与 WebSocket 路由都用标准 `APIRouter`，由 `app/http/api/__init__.py` 显式组合；不会扫描目录自动发现。`get_db` 不自动提交，业务在成功完成写入后显式 `commit()`；依赖退出时未提交事务会回滚。查询软删除表时可写 `sa.select(NoteModel).where(NoteModel.exist_filter())`，并与业务条件组合。

应用工厂在 `bootstrap/application.py:create_app`，中间件在 `app/providers/middleware_provider.py:register` 显式添加。普通业务无需修改这两个入口。

新增模型后运行迁移，再启动服务：

```bash
uv run --locked python -X utf8 -m alembic revision --autogenerate -m "add notes"
uv run --locked python -X utf8 -m alembic upgrade head
uv run --locked python main.py
```

迁移环境会导入 `app.models` 下的模型模块。检查生成的 revision 后再提交，不手改生成产物。以下 curl 使用 Bash；PowerShell 用户也可在 `/docs` 提交相同 JSON：

```bash
curl -X POST http://127.0.0.1:8000/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"title":"第一条便笺","body":"你好"}'
```

预期 **201**，响应包含新记录的 `id`、`title` 和 `body`。

## 可选鉴权与错误

默认无认证。需要使用内置本地 token 的路由，在参数上显式添加 `Depends(get_auth_user)`，并启用相应认证能力；该依赖返回的 `UserModel` 已脱离数据库会话。要修改当前用户，应在业务 `get_db` 会话中重新读取，例如 `user = await session.get(UserModel, auth_user.id)`，不要直接提交脱离会话的对象。自定义的非本地认证方式应使用它自己的鉴权依赖。

```python
from typing import Annotated

from fastapi import Depends

from app.http.deps.auth_deps import get_auth_user
from app.models.user import UserModel

async def private_endpoint(user: Annotated[UserModel, Depends(get_auth_user)]) -> dict[str, str]:
    return {'user_id': str(user.id)}
```

已知业务失败用 `ApiError(status_code, code, message)` 返回固定的业务说明。需要在 Pydantic 校验器中显示作者控制的固定说明时，使用 `SafeValueError('标题为保留值')`；不要把输入值拼进说明。422 detail 保留字段位置和类型，并且仅显示这种显式安全说明，不回显输入、校验上下文或普通第三方错误文本。未知异常和内部响应/模型校验失败仍返回固定 500。

修改用户字段时，数据库模型在 `app/models/user.py`；公开输入、响应白名单在 `app/schemas/user.py`。如果新字段允许注册时提交，还要同步 `app/services/auth/user_service.py:create_user` 中的显式写入映射。数据库列变化需要生成并检查 Alembic revision。

认证选项和接入边界见[认证接入教程](auth.md)；迁移、调度、日志、探针和真实测试服务见[运行与开发说明](operations.md)。
