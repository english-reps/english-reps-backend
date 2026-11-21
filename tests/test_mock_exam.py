import random
from collections import Counter

from app.services.catalog import get_catalog
from app.services.mock_exam import (
    estimate_toeic_section_score,
    generate_mock_exam_question_ids,
    grade_mock_exam,
)


def test_listening_mock_exam_matches_official_part_distribution() -> None:
    catalog = get_catalog()
    for seed in range(10):
        ids = generate_mock_exam_question_ids(catalog, "listening", random.Random(seed))
        assert len(ids) == 100
        assert len(set(ids)) == 100
        parts = [catalog.get(entry_id).content["part"] for entry_id in ids]  # type: ignore[union-attr]
        assert Counter(parts) == {1: 6, 2: 25, 3: 39, 4: 30}
        assert parts == sorted(parts)


def test_reading_mock_exam_matches_official_part_distribution() -> None:
    catalog = get_catalog()
    for seed in range(15):
        ids = generate_mock_exam_question_ids(catalog, "reading", random.Random(seed))
        assert len(ids) == 100
        assert len(set(ids)) == 100
        parts = [catalog.get(entry_id).content["part"] for entry_id in ids]  # type: ignore[union-attr]
        assert Counter(parts) == {5: 30, 6: 16, 7: 54}
        assert parts == sorted(parts)
        # Ensure Part 6 and Part 7 grouped passages stay contiguous
        seen_groups: set[str] = set()
        prev_group: str | None = None
        for entry_id in ids:
            gid = catalog.get(entry_id).content.get("groupId")  # type: ignore[union-attr]
            if gid and gid != prev_group:
                assert gid not in seen_groups
                seen_groups.add(gid)
            prev_group = gid


def test_mock_exam_scoring_and_grading() -> None:
    catalog = get_catalog()
    ids = generate_mock_exam_question_ids(catalog, "reading", random.Random(42))
    answers = {
        entry_id: catalog.get(entry_id).content["answer"]  # type: ignore[union-attr]
        for entry_id in ids[:50]
    }
    wrong_id = ids[50]
    correct_label = catalog.get(wrong_id).content["answer"]  # type: ignore[union-attr]
    answers[wrong_id] = "B" if correct_label != "B" else "A"

    grading = grade_mock_exam(catalog, "reading", ids, answers)
    assert grading.correct_count == 50
    assert len(grading.wrong_ids) == 50
    assert wrong_id in grading.wrong_ids
    assert 5 <= grading.scaled_score <= 495
    assert grading.scaled_score % 5 == 0
    assert sum(stat["total"] for stat in grading.part_stats) == 100
    assert sum(stat["correct"] for stat in grading.part_stats) == 50

    assert estimate_toeic_section_score("listening", 0, 100) == 5
    assert estimate_toeic_section_score("listening", 100, 100) == 495
    assert estimate_toeic_section_score("reading", 0, 100) == 5
    assert estimate_toeic_section_score("reading", 100, 100) == 495
