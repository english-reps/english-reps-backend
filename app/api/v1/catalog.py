from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.entities import CatalogItem

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/{category}")
async def catalog(
    category: Literal["vocabulary", "listening"], db: AsyncSession = Depends(get_db)
) -> dict[str, list[dict[str, Any]]]:
    entries = await db.scalars(
        select(CatalogItem).where(CatalogItem.category == category).order_by(CatalogItem.id)
    )
    return {"entries": [item.content for item in entries]}
