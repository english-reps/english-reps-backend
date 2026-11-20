import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["vocabulary", "listening"]
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class WordSense(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pos: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class VocabularyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    word: str = Field(min_length=1)
    senses: list[WordSense] = Field(min_length=1)
    example: str = Field(min_length=1)
    translation: str = Field(min_length=1)
    page: int = Field(ge=1)
    unit: int = Field(ge=1)


class ListeningOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal["A", "B", "C"]
    text: str = Field(min_length=1)
    translation: str = Field(min_length=1)


class ListeningEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    topic: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    promptZh: str = Field(min_length=1)
    options: list[ListeningOption] = Field(min_length=3, max_length=3)
    answer: Literal["A", "B", "C"]
    explanation: str = Field(min_length=1)
    keywords: list[str]

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        if [option.label for option in self.options] != ["A", "B", "C"]:
            raise ValueError("Listening options must have labels A, B, C in order")
        return self


class VocabularyCatalogFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entries: list[VocabularyEntry] = Field(min_length=1)


class ListeningCatalogFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entries: list[ListeningEntry] = Field(min_length=1)


@dataclass(frozen=True)
class CatalogRecord:
    id: str
    category: Category
    content: dict[str, Any]


class CatalogStore:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR) -> None:
        vocab_file = VocabularyCatalogFile.model_validate(
            json.loads((data_dir / "vocabulary.json").read_text(encoding="utf-8"))
        )
        listening_file = ListeningCatalogFile.model_validate(
            json.loads((data_dir / "listening.json").read_text(encoding="utf-8"))
        )
        vocab_entries = [entry.model_dump(mode="json") for entry in vocab_file.entries]
        listening_entries = [entry.model_dump(mode="json") for entry in listening_file.entries]

        by_id: dict[str, CatalogRecord] = {}
        groups: tuple[tuple[Category, list[dict[str, Any]]], ...] = (
            ("vocabulary", vocab_entries),
            ("listening", listening_entries),
        )
        for category, entries in groups:
            for entry in entries:
                entry_id = str(entry["id"])
                if entry_id in by_id:
                    raise ValueError(f"Duplicate catalog entry ID: {entry_id}")
                by_id[entry_id] = CatalogRecord(id=entry_id, category=category, content=entry)

        self._entries: dict[Category, list[dict[str, Any]]] = {
            "vocabulary": vocab_entries,
            "listening": listening_entries,
        }
        self._by_id = by_id

    def list_entries(self, category: Category) -> list[dict[str, Any]]:
        return self._entries[category]

    def get(self, entry_id: str) -> CatalogRecord | None:
        return self._by_id.get(entry_id)

    @property
    def total_count(self) -> int:
        return len(self._by_id)


@lru_cache(maxsize=1)
def get_catalog() -> CatalogStore:
    return CatalogStore()
