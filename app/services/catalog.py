import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["vocabulary", "listening", "reading"]
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


class CatalogOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal["A", "B", "C", "D"]
    text: str = Field(min_length=1)
    translation: str = ""


class ListeningEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    part: Literal[1, 2, 3, 4] = 2
    topic: str = Field(min_length=1)
    difficulty: str | None = None
    groupId: str | None = None
    prompt: str = Field(min_length=1)
    promptZh: str = ""
    audioText: str | None = None
    audioTranslation: str | None = None
    image: str | None = None
    imageAlt: str | None = None
    imageCredit: str | None = None
    imageSource: str | None = None
    options: list[CatalogOption] = Field(min_length=3, max_length=4)
    answer: Literal["A", "B", "C", "D"]
    explanation: str = Field(min_length=1)
    keywords: list[str]

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        expected_labels = ["A", "B", "C"] if self.part == 2 else ["A", "B", "C", "D"]
        actual_labels = [option.label for option in self.options]
        if actual_labels != expected_labels:
            raise ValueError(f"Part {self.part} listening options must have labels {expected_labels}")
        if self.answer not in actual_labels:
            raise ValueError(f"Answer {self.answer} is not among options {actual_labels}")
        if self.part == 1 and not self.image:
            raise ValueError("Part 1 listening entry requires an image path")
        if self.part in {3, 4} and not self.audioText:
            raise ValueError(f"Part {self.part} listening entry requires audioText")
        return self


class ReadingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    part: Literal[5, 6, 7]
    topic: str = Field(min_length=1)
    difficulty: str | None = None
    groupId: str | None = None
    passage: str | None = None
    prompt: str = Field(min_length=1)
    promptZh: str = ""
    options: list[CatalogOption] = Field(min_length=4, max_length=4)
    answer: Literal["A", "B", "C", "D"]
    explanation: str = Field(min_length=1)
    evidence: str | None = None
    evidenceLocation: str | None = None
    keywords: list[str]

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        expected_labels = ["A", "B", "C", "D"]
        actual_labels = [option.label for option in self.options]
        if actual_labels != expected_labels:
            raise ValueError("Reading options must have labels A, B, C, D in order")
        if self.part in {6, 7} and not self.passage:
            raise ValueError(f"Part {self.part} reading entry requires a passage")
        return self


class VocabularyCatalogFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entries: list[VocabularyEntry] = Field(min_length=1)


class ListeningCatalogFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entries: list[ListeningEntry] = Field(min_length=1)


class ReadingCatalogFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entries: list[ReadingEntry] = Field(min_length=1)


@dataclass(frozen=True)
class CatalogRecord:
    id: str
    category: Category
    content: dict[str, Any]


def _load_listening_entries(data_dir: Path) -> list[dict[str, Any]]:
    listening_dir = data_dir / "listening"
    if listening_dir.is_dir():
        part_files = sorted(listening_dir.glob("part*.json"))
        if not part_files:
            raise FileNotFoundError(f"No part*.json files found in {listening_dir}")
        entries: list[dict[str, Any]] = []
        for path in part_files:
            validated = ListeningCatalogFile.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            entries.extend(entry.model_dump(mode="json") for entry in validated.entries)
        return entries
    validated = ListeningCatalogFile.model_validate(
        json.loads((data_dir / "listening.json").read_text(encoding="utf-8"))
    )
    return [entry.model_dump(mode="json") for entry in validated.entries]


def _load_reading_entries(data_dir: Path) -> list[dict[str, Any]]:
    reading_dir = data_dir / "reading"
    if reading_dir.is_dir():
        part_files = sorted(reading_dir.glob("part*.json"))
        if not part_files:
            raise FileNotFoundError(f"No part*.json files found in {reading_dir}")
        entries: list[dict[str, Any]] = []
        for path in part_files:
            validated = ReadingCatalogFile.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            entries.extend(entry.model_dump(mode="json") for entry in validated.entries)
        return entries
    reading_file = data_dir / "reading.json"
    if reading_file.exists():
        validated = ReadingCatalogFile.model_validate(
            json.loads(reading_file.read_text(encoding="utf-8"))
        )
        return [entry.model_dump(mode="json") for entry in validated.entries]
    return []


class CatalogStore:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR) -> None:
        vocab_file = VocabularyCatalogFile.model_validate(
            json.loads((data_dir / "vocabulary.json").read_text(encoding="utf-8"))
        )
        vocab_entries = [entry.model_dump(mode="json") for entry in vocab_file.entries]
        listening_entries = _load_listening_entries(data_dir)
        reading_entries = _load_reading_entries(data_dir)

        by_id: dict[str, CatalogRecord] = {}
        groups: tuple[tuple[Category, list[dict[str, Any]]], ...] = (
            ("vocabulary", vocab_entries),
            ("listening", listening_entries),
            ("reading", reading_entries),
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
            "reading": reading_entries,
        }
        self._by_id = by_id

    def list_entries(self, category: Category, part: int | None = None) -> list[dict[str, Any]]:
        entries = self._entries[category]
        if part is None:
            return entries
        return [entry for entry in entries if entry.get("part") == part]

    def get(self, entry_id: str) -> CatalogRecord | None:
        return self._by_id.get(entry_id)

    @property
    def total_count(self) -> int:
        return len(self._by_id)


@lru_cache(maxsize=1)
def get_catalog() -> CatalogStore:
    return CatalogStore()
