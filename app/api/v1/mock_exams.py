import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import MockExam, User
from app.schemas.contracts import (
    MockExamCreate,
    MockExamOut,
    MockExamSubmit,
    MockExamUpdate,
)
from app.services.catalog import get_catalog
from app.services.mock_exam import (
    duration_for_section,
    generate_mock_exam_question_ids,
    grade_mock_exam,
)

router = APIRouter(prefix="/mock-exams", tags=["mock-exams"])


async def _get_owned_exam(db: AsyncSession, user: User, exam_id: uuid.UUID) -> MockExam:
    exam = await db.scalar(
        select(MockExam)
        .where(MockExam.id == exam_id, MockExam.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    if exam is None:
        raise APIError(404, "mock_exam_not_found", "找不到這個模擬測驗紀錄。")
    return exam


def _apply_progress_patch(
    exam: MockExam,
    payload: MockExamUpdate | MockExamSubmit,
) -> None:
    allowed_ids = set(exam.question_ids)
    catalog = get_catalog()

    if payload.answers is not None:
        cleaned_answers: dict[str, str] = {}
        for entry_id, choice in payload.answers.items():
            if entry_id not in allowed_ids:
                raise APIError(422, "invalid_answer", "作答題目不屬於本次模擬測驗。")
            item = catalog.get(entry_id)
            valid_labels = {opt["label"] for opt in item.content.get("options", [])} if item else set()
            if choice not in valid_labels:
                raise APIError(422, "invalid_answer", f"題目 {entry_id} 的選項無效。")
            cleaned_answers[entry_id] = choice
        exam.answers = cleaned_answers

    if payload.flagged_ids is not None:
        seen_flags: set[str] = set()
        cleaned_flags: list[str] = []
        for entry_id in payload.flagged_ids:
            if entry_id not in allowed_ids:
                raise APIError(422, "invalid_flag", "標記題目不屬於本次模擬測驗。")
            if entry_id not in seen_flags:
                seen_flags.add(entry_id)
                cleaned_flags.append(entry_id)
        exam.flagged_ids = cleaned_flags

    if payload.played_keys is not None:
        seen_keys: set[str] = set()
        cleaned_keys: list[str] = []
        for key in payload.played_keys[:200]:
            text = str(key).strip()[:64]
            if text and text not in seen_keys:
                seen_keys.add(text)
                cleaned_keys.append(text)
        exam.played_keys = cleaned_keys

    if payload.current_index is not None:
        if payload.current_index >= len(exam.question_ids):
            raise APIError(422, "invalid_index", "題號超出測驗範圍。")
        exam.current_index = payload.current_index

    if payload.remaining_seconds is not None:
        exam.remaining_seconds = min(exam.duration_seconds, max(0, payload.remaining_seconds))

    exam.updated_at = datetime.now(UTC)


@router.get("")
async def list_mock_exams(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, list[MockExamOut]]:
    rows = await db.scalars(
        select(MockExam)
        .where(MockExam.user_id == user.id)
        .order_by(desc(MockExam.created_at))
        .execution_options(populate_existing=True)
    )
    return {"exams": [MockExamOut.model_validate(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_mock_exam(
    data: MockExamCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, MockExamOut]:
    catalog = get_catalog()
    question_ids = generate_mock_exam_question_ids(catalog, data.section)
    duration = duration_for_section(data.section)
    now = datetime.now(UTC)
    exam = MockExam(
        id=uuid.uuid4(),
        user_id=user.id,
        section=data.section,
        status="in_progress",
        question_ids=question_ids,
        answers={},
        flagged_ids=[],
        played_keys=[],
        current_index=0,
        duration_seconds=duration,
        remaining_seconds=duration,
        total_questions=len(question_ids),
        created_at=now,
        updated_at=now,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return {"exam": MockExamOut.model_validate(exam)}


@router.get("/{exam_id}")
async def get_mock_exam(
    exam_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, MockExamOut]:
    exam = await _get_owned_exam(db, user, exam_id)
    return {"exam": MockExamOut.model_validate(exam)}


@router.patch("/{exam_id}")
async def update_mock_exam(
    exam_id: uuid.UUID,
    data: MockExamUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, MockExamOut]:
    exam = await _get_owned_exam(db, user, exam_id)
    if exam.status != "in_progress":
        raise APIError(409, "exam_already_completed", "這場模擬測驗已經交卷完成，無法再修改。")
    _apply_progress_patch(exam, data)
    await db.commit()
    await db.refresh(exam)
    return {"exam": MockExamOut.model_validate(exam)}


@router.post("/{exam_id}/submit")
async def submit_mock_exam(
    exam_id: uuid.UUID,
    data: MockExamSubmit | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, MockExamOut]:
    exam = await _get_owned_exam(db, user, exam_id)
    if exam.status == "completed":
        return {"exam": MockExamOut.model_validate(exam)}
    if data is not None:
        _apply_progress_patch(exam, data)
    section = cast(Literal["listening", "reading"], exam.section)
    grading = grade_mock_exam(get_catalog(), section, exam.question_ids, exam.answers)
    now = datetime.now(UTC)
    exam.status = "completed"
    exam.correct_count = grading.correct_count
    exam.scaled_score = grading.scaled_score
    exam.wrong_ids = grading.wrong_ids
    exam.part_stats = grading.part_stats
    exam.completed_at = now
    exam.updated_at = now
    await db.commit()
    await db.refresh(exam)
    return {"exam": MockExamOut.model_validate(exam)}


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mock_exam(
    exam_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    exam = await _get_owned_exam(db, user, exam_id)
    await db.delete(exam)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
