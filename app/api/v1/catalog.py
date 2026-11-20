from typing import Any, Literal

from fastapi import APIRouter

from app.services.catalog import get_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/{category}")
async def catalog(
    category: Literal["vocabulary", "listening"],
) -> dict[str, list[dict[str, Any]]]:
    return {"entries": get_catalog().list_entries(category)}
