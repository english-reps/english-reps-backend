import random
from dataclasses import dataclass
from typing import Any, Literal

from app.services.catalog import CatalogStore

MockSection = Literal["listening", "reading"]

LISTENING_DURATION_SECONDS = 45 * 60
READING_DURATION_SECONDS = 75 * 60


def duration_for_section(section: MockSection) -> int:
    return LISTENING_DURATION_SECONDS if section == "listening" else READING_DURATION_SECONDS


def _group_entries(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    by_gid: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        gid = entry.get("groupId")
        if gid:
            bucket = by_gid.get(str(gid))
            if bucket is None:
                bucket = []
                by_gid[str(gid)] = bucket
                groups.append(bucket)
            bucket.append(entry)
        else:
            groups.append([entry])
    return groups


def _classify_part7_group(group: list[dict[str, Any]]) -> Literal["single", "double", "triple"]:
    first = group[0]
    passage = str(first.get("passage") or "")
    topic = str(first.get("topic") or "")
    keywords = " ".join(str(k) for k in first.get("keywords") or []).lower()
    if "triple" in keywords or "三篇" in topic or "DOCUMENT 3" in passage:
        return "triple"
    if "double" in keywords or "雙篇" in topic or "DOCUMENT 2" in passage:
        return "double"
    return "single"


def _pick_exact_subset(
    groups: list[list[dict[str, Any]]],
    target_questions: int,
    exact_groups: int | None,
    rng: random.Random,
) -> list[list[dict[str, Any]]] | None:
    pool = list(groups)
    rng.shuffle(pool)
    sizes = [len(g) for g in pool]
    n = len(pool)

    # Memoize impossible states (idx, remaining_q, remaining_g)
    failed: set[tuple[int, int, int | None]] = set()
    chosen: list[list[dict[str, Any]]] = []

    def dfs(idx: int, rem_q: int, rem_g: int | None) -> bool:
        if rem_q == 0 and (rem_g is None or rem_g == 0):
            return True
        if rem_q < 0 or idx >= n or (rem_g is not None and rem_g <= 0):
            return False
        state = (idx, rem_q, rem_g)
        if state in failed:
            return False
        sz = sizes[idx]
        if sz <= rem_q:
            chosen.append(pool[idx])
            if dfs(idx + 1, rem_q - sz, None if rem_g is None else rem_g - 1):
                return True
            chosen.pop()
        if dfs(idx + 1, rem_q, rem_g):
            return True
        failed.add(state)
        return False

    if dfs(0, target_questions, exact_groups):
        return chosen
    return None


def _pick_part7_questions(
    entries: list[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    all_groups = _group_entries(entries)
    singles = [g for g in all_groups if _classify_part7_group(g) == "single"]
    doubles = [g for g in all_groups if _classify_part7_group(g) == "double"]
    triples = [g for g in all_groups if _classify_part7_group(g) == "triple"]

    # Official TOEIC Part 7: 29 single-passage questions across 10 passages + 25 multi-passage questions
    picked_singles = _pick_exact_subset(singles, 29, 10, rng)
    if picked_singles is None:
        picked_singles = _pick_exact_subset(singles, 29, None, rng)

    # Multi-passage (25 questions): try balanced double + triple combinations
    picked_multi: list[list[dict[str, Any]]] | None = None
    multi_splits = [(10, 15), (8, 17), (12, 13), (13, 12), (9, 16)]
    rng.shuffle(multi_splits)
    for double_q, triple_q in multi_splits:
        d_pick = _pick_exact_subset(doubles, double_q, None, rng)
        t_pick = _pick_exact_subset(triples, triple_q, None, rng)
        if d_pick is not None and t_pick is not None:
            picked_multi = d_pick + t_pick
            break
    if picked_multi is None:
        picked_multi = _pick_exact_subset(doubles + triples, 25, None, rng)

    if picked_singles is None or picked_multi is None:
        fallback = _pick_exact_subset(all_groups, 54, None, rng)
        if fallback is None:
            raise ValueError("Insufficient Part 7 questions to build a 54-question section")
        return [q for group in fallback for q in group]

    # Sort single passages by ascending question count (2->3->4) like the real exam,
    # followed by double then triple passages.
    picked_singles.sort(key=len)
    picked_doubles = [g for g in picked_multi if _classify_part7_group(g) == "double"]
    picked_triples = [g for g in picked_multi if _classify_part7_group(g) == "triple"]
    return [q for group in (picked_singles + picked_doubles + picked_triples) for q in group]


def generate_mock_exam_question_ids(
    catalog: CatalogStore,
    section: MockSection,
    rng: random.Random | None = None,
) -> list[str]:
    generator = rng or random.Random()
    if section == "listening":
        p1 = catalog.list_entries("listening", part=1)
        p2 = catalog.list_entries("listening", part=2)
        p3_groups = _group_entries(catalog.list_entries("listening", part=3))
        p4_groups = _group_entries(catalog.list_entries("listening", part=4))

        picked_p1 = generator.sample(p1, 6)
        picked_p2 = generator.sample(p2, 25)
        picked_p3 = [q for group in generator.sample(p3_groups, 13) for q in group]
        picked_p4 = [q for group in generator.sample(p4_groups, 10) for q in group]
        selected = picked_p1 + picked_p2 + picked_p3 + picked_p4
        return [str(entry["id"]) for entry in selected]

    p5 = catalog.list_entries("reading", part=5)
    p6_groups = _group_entries(catalog.list_entries("reading", part=6))
    p7 = catalog.list_entries("reading", part=7)

    picked_p5 = generator.sample(p5, 30)
    picked_p6 = [q for group in generator.sample(p6_groups, 4) for q in group]
    picked_p7 = _pick_part7_questions(p7, generator)
    selected = picked_p5 + picked_p6 + picked_p7
    return [str(entry["id"]) for entry in selected]


def estimate_toeic_section_score(section: MockSection, correct: int, total: int) -> int:
    if total <= 0 or correct <= 0:
        return 5
    ratio = min(1.0, max(0.0, correct / total))
    # Approximate TOEIC raw-to-scaled curve (5..495 in steps of 5):
    # Listening has a slightly higher floor at mid/high raw scores than Reading.
    if section == "listening":
        raw_scaled = 5 + round((ratio**0.92) * 490 / 5) * 5
        if correct >= total - 3:
            raw_scaled = 495
    else:
        raw_scaled = 5 + round((ratio**1.03) * 490 / 5) * 5
        if correct >= total - 1:
            raw_scaled = 495
    return max(5, min(495, int(raw_scaled)))


@dataclass(frozen=True)
class MockExamGrading:
    correct_count: int
    scaled_score: int
    wrong_ids: list[str]
    part_stats: list[dict[str, int]]


def grade_mock_exam(
    catalog: CatalogStore,
    section: MockSection,
    question_ids: list[str],
    answers: dict[str, str],
) -> MockExamGrading:
    correct_count = 0
    wrong_ids: list[str] = []
    per_part: dict[int, list[int]] = {}

    for entry_id in question_ids:
        record = catalog.get(entry_id)
        if record is None:
            wrong_ids.append(entry_id)
            continue
        part = int(record.content.get("part", 2 if section == "listening" else 5))
        bucket = per_part.setdefault(part, [0, 0])
        bucket[0] += 1
        chosen = answers.get(entry_id)
        if chosen is not None and chosen == record.content.get("answer"):
            correct_count += 1
            bucket[1] += 1
        else:
            wrong_ids.append(entry_id)

    part_stats = [
        {"part": part, "total": counts[0], "correct": counts[1]}
        for part, counts in sorted(per_part.items())
    ]
    scaled_score = estimate_toeic_section_score(section, correct_count, len(question_ids))
    return MockExamGrading(
        correct_count=correct_count,
        scaled_score=scaled_score,
        wrong_ids=wrong_ids,
        part_stats=part_stats,
    )
