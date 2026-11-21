import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.catalog import CatalogStore, get_catalog


def _write_catalog(
    directory: Path, vocab_entries: list[dict[str, object]], listening_entries: list[dict[str, object]]
) -> None:
    (directory / "vocabulary.json").write_text(
        json.dumps({"entries": vocab_entries}, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "listening.json").write_text(
        json.dumps({"entries": listening_entries}, ensure_ascii=False), encoding="utf-8"
    )


def _sample_vocab(entry_id: str = "word-0001") -> dict[str, object]:
    return {
        "id": entry_id,
        "word": "company",
        "senses": [{"pos": "n.", "meaning": "公司"}],
        "example": "She works for a tech company.",
        "translation": "她在一家科技公司工作。",
        "page": 1,
        "unit": 1,
    }


def _sample_listening(entry_id: str = "listen-001") -> dict[str, object]:
    return {
        "id": entry_id,
        "topic": "workplace",
        "prompt": "When will the meeting start?",
        "promptZh": "會議什麼時候開始？",
        "options": [
            {"label": "A", "text": "At nine.", "translation": "九點。"},
            {"label": "B", "text": "In room 2.", "translation": "在二號會議室。"},
            {"label": "C", "text": "Yes, she did.", "translation": "是的，她有。"},
        ],
        "answer": "A",
        "explanation": "When 問時間。",
        "keywords": ["meeting"],
    }


def test_default_repository_catalog_files_load_cleanly() -> None:
    store = get_catalog()
    assert len(store.list_entries("vocabulary")) == 1000
    assert len(store.list_entries("listening")) == 332
    assert len(store.list_entries("listening", part=1)) == 25
    assert len(store.list_entries("listening", part=2)) == 139
    assert len(store.list_entries("listening", part=3)) == 90
    assert len(store.list_entries("listening", part=4)) == 78
    assert len(store.list_entries("reading")) == 805
    assert len(store.list_entries("reading", part=5)) == 328
    assert len(store.list_entries("reading", part=6)) == 120
    assert len(store.list_entries("reading", part=7)) == 357
    assert store.total_count == 2137
    word = store.get("word-0001")
    question = store.get("listen-001")
    reading_q = store.get("P5-001")
    assert word is not None and word.category == "vocabulary" and word.content["word"] == "company"
    assert question is not None and question.category == "listening" and question.content["answer"] == "A"
    assert reading_q is not None and reading_q.category == "reading" and reading_q.content["part"] == 5


def test_catalog_store_rejects_duplicate_ids(tmp_path: Path) -> None:
    _write_catalog(tmp_path, [_sample_vocab("same-id")], [_sample_listening("same-id")])
    with pytest.raises(ValueError, match="Duplicate catalog entry ID"):
        CatalogStore(tmp_path)


def test_catalog_store_rejects_invalid_listening_option_order(tmp_path: Path) -> None:
    bad_listening = _sample_listening()
    bad_listening["options"] = list(reversed(bad_listening["options"]))  # type: ignore[arg-type]
    _write_catalog(tmp_path, [_sample_vocab()], [bad_listening])
    with pytest.raises(ValidationError):
        CatalogStore(tmp_path)
