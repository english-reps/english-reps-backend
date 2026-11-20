from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import Progress, StudyEvent, User
from app.schemas.contracts import EventIn, ProgressOut
from app.services.catalog import get_catalog

router = APIRouter(prefix="/progress", tags=["progress"])


async def records(db: AsyncSession, user: User) -> list[ProgressOut]:
    items = await db.scalars(
        select(Progress)
        .where(Progress.user_id == user.id)
        .order_by(Progress.entry_id)
        .execution_options(populate_existing=True)
    )
    return [ProgressOut.model_validate(item) for item in items]


@router.get("")
async def get_progress(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, list[ProgressOut]]:
    return {"records": await records(db, user)}


@router.post("/events")
async def event(
    data: EventIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    catalog = get_catalog()
    item = catalog.get(data.entry_id)
    if item is None:
        raise APIError(404, "item_not_found", "找不到這個題目。")
    correct: bool | None = None
    status = data.rating
    if data.kind == "listening":
        if item.category != "listening" or data.answer not in {"A", "B", "C"}:
            raise APIError(422, "invalid_answer", "聽力回答必須為 A、B 或 C。")
        correct = data.answer == item.content["answer"]
    elif data.kind == "quiz":
        if item.category != "vocabulary":
            raise APIError(422, "invalid_kind", "練習類型與題目不符。")
        answer = catalog.get(data.answer or "")
        if answer is None or answer.category != "vocabulary":
            raise APIError(422, "invalid_answer", "請選擇有效的單字回答。")
        correct = answer.id == item.id
    if data.kind != "card":
        status = "mastered" if correct else "review"
    payload = data.model_dump(mode="json")
    inserted = await db.scalar(
        insert(StudyEvent)
        .values(
            user_id=user.id,
            event_id=data.event_id,
            entry_id=item.id,
            request=payload,
            correct=correct,
        )
        .on_conflict_do_nothing()
        .returning(StudyEvent.event_id)
    )
    if inserted is None:
        previous = await db.get(StudyEvent, (user.id, data.event_id))
        if previous is None or previous.request != payload:
            raise APIError(409, "event_conflict", "相同事件 ID 的內容不同。")
        record = await db.get(Progress, (user.id, item.id), populate_existing=True)
        return {"correct": previous.correct, "record": ProgressOut.model_validate(record)}
    statement = insert(Progress).values(
        user_id=user.id,
        entry_id=item.id,
        category=item.category,
        status=status,
        attempts=int(data.kind != "card"),
        correct=int(bool(correct)),
    )
    record = (
        await db.scalars(
            statement.on_conflict_do_update(
                index_elements=["user_id", "entry_id"],
                set_={
                    "status": status,
                    "attempts": Progress.attempts + statement.excluded.attempts,
                    "correct": Progress.correct + statement.excluded.correct,
                    "updated_at": func.now(),
                },
            )
            .returning(Progress)
            .execution_options(populate_existing=True)
        )
    ).one()
    result = ProgressOut.model_validate(record)
    await db.commit()
    return {"correct": correct, "record": result}
