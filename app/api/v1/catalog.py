from typing import Any, Literal

from fastapi import APIRouter, Query

from app.services.catalog import get_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/{category}")
async def catalog(
    category: Literal["vocabulary", "listening", "reading"],
    part: int | None = Query(default=None, ge=1, le=7),
) -> dict[str, list[dict[str, Any]]]:
    return {"entries": get_catalog().list_entries(category, part=part)}
