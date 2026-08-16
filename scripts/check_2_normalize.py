"""Checkpoint 2: verify the benchmark corpus download and build the dev slice.

Four things, per §5's Checkpoint 2 line:
  1. Parse questions.jsonl -- count + category distribution.
  2. Confirm every gold document_id referenced by a question exists somewhere
     in the downloaded corpus (data/raw/bench/corpus/).
  3. Build dev_manifest.json = gold docs + ~150 distractors, chosen backwards
     from the questions (same container as a real gold doc) rather than a
     uniform random sample -- random distractors are easy negatives; the
     benchmark's whole point is near-duplicates and misfiled documents.
  4. Print a thread-grouping table per source, as an early smoke test for the
     thread_id logic Phase 3 adapters will need.

Important corpus-shape finding (read before writing Phase 3 adapters): the
public release's export format is coarser than PLAN.md §6 assumes. There is
no per-message/per-comment raw dict -- each exported .txt file already IS a
whole Slack thread, whole Gmail thread (quotes included), whole Jira/Linear
ticket-plus-comments, or whole GitHub PR-plus-reviews. One file = one
document = one already-assembled conversation. So "thread-grouping" here
isn't "does thread_id cluster N messages into 1 thread" (there's no
message-level granularity to cluster) -- it's "does this document, as a
whole, look like the multi-turn conversation its source type promises, or
did our understanding of the export format get something wrong". A Slack
table with ~0 multi-turn docs would mean we're misreading the export, not
that thread_id extraction has a bug -- there is no thread_id to extract yet.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "data" / "raw" / "bench"
QUESTIONS_PATH = BENCH_DIR / "questions.jsonl"
CORPUS_DIR = BENCH_DIR / "corpus"
MANIFEST_PATH = BENCH_DIR / "dev_manifest.json"

DISTRACTOR_BUDGET = 150
RNG_SEED = 20260816  # fixed seed -- manifest membership should be reproducible

DSID_RE = re.compile(r"^(dsid_[0-9a-f]+)__")

# Heuristic "this line starts a new conversational turn" patterns, tried in
# order, spanning the source types that ship whole-thread documents.
TURN_PATTERNS = [
    re.compile(r"^[A-Za-z][\w .'\-]{1,40}:\s"),  # "cheng: heads up ..." (slack/fireflies)
    re.compile(r"^[A-Za-z][\w .'\-]{1,40} \([A-Za-z][\w /]{1,30}\)[:\-]\s"),  # "Chloe Martin (Support): ..."
    re.compile(r"^From:\s.+$"),  # gmail message header
    re.compile(r"^\d{4}-\d{2}-\d{2}\s*-\s*"),  # "2026-02-27 - Procurement: ..." ticket log lines
    re.compile(r"^\d{2}:\d{2}\s+[A-Za-z][\w .'\-]{1,40}:\s"),  # "00:07 Liam O'Neill: ..." transcript lines
]
MIN_TURNS_FOR_THREAD = 3


def load_questions() -> list[dict]:
    questions = []
    with QUESTIONS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def print_question_stats(questions: list[dict]) -> None:
    print(f"questions.jsonl: {len(questions)} questions")
    by_type = Counter(q["question_type"] for q in questions)
    print(f"{'category':<28}{'count':>6}")
    for qtype, count in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"{qtype:<28}{count:>6}")


def index_corpus() -> dict[str, Path]:
    """dsid -> file path, across every source subdirectory."""
    index: dict[str, Path] = {}
    for path in CORPUS_DIR.rglob("*.txt"):
        m = DSID_RE.match(path.name)
        if m:
            index[m.group(1)] = path
    return index


def source_type_of(path: Path) -> str:
    return path.relative_to(CORPUS_DIR).parts[0]


def container_of(path: Path) -> str | None:
    parts = path.relative_to(CORPUS_DIR).parts
    return parts[1] if len(parts) > 2 else None  # None => file sits directly under the source dir


def check_gold_coverage(questions: list[dict], index: dict[str, Path]) -> set[str]:
    gold_ids: set[str] = set()
    for q in questions:
        gold_ids.update(q.get("expected_doc_ids") or [])

    missing = sorted(gid for gid in gold_ids if gid not in index)
    print(f"\ngold document_ids referenced by questions: {len(gold_ids)}")
    if missing:
        print(f"MISSING from downloaded corpus ({len(missing)}):")
        for gid in missing[:20]:
            print(f"  {gid}")
        raise AssertionError(
            f"{len(missing)} gold document_ids are not present in {CORPUS_DIR} -- "
            "the corpus download/extraction is incomplete."
        )
    print("OK -- every gold document_id exists in the downloaded corpus.")
    return gold_ids


def build_dev_manifest(gold_ids: set[str], index: dict[str, Path]) -> dict:
    rng = random.Random(RNG_SEED)

    gold_paths = {gid: index[gid] for gid in gold_ids}
    gold_by_source: dict[str, list[str]] = defaultdict(list)
    for gid, path in gold_paths.items():
        gold_by_source[source_type_of(path)].append(gid)

    # containers that actually contain a gold doc -- the highest-value
    # distractors are *other* files in those same containers (same channel,
    # same repo, same mailbox), not arbitrary docs from the source at large.
    gold_containers: dict[str, set[str]] = defaultdict(set)
    for gid, path in gold_paths.items():
        c = container_of(path)
        if c is not None:
            gold_containers[source_type_of(path)].add(c)

    total_gold = len(gold_ids)
    distractors: set[str] = set()

    for source, gids in sorted(gold_by_source.items(), key=lambda kv: -len(kv[1])):
        budget = max(1, round(DISTRACTOR_BUDGET * len(gids) / total_gold))

        # Pass 1: siblings from the same containers as this source's gold docs.
        sibling_dsids: list[str] = []
        for container in gold_containers.get(source, ()):
            for path in (CORPUS_DIR / source / container).glob("*.txt"):
                m = DSID_RE.match(path.name)
                if m and m.group(1) not in gold_ids:
                    sibling_dsids.append(m.group(1))
        rng.shuffle(sibling_dsids)

        picked = 0
        for dsid in sibling_dsids:
            if picked >= budget:
                break
            distractors.add(dsid)
            picked += 1

        # Pass 2: still short -- top up with other docs from the same source.
        if picked < budget:
            pool = [
                m.group(1)
                for p in (CORPUS_DIR / source).rglob("*.txt")
                if (m := DSID_RE.match(p.name)) and m.group(1) not in gold_ids and m.group(1) not in distractors
            ]
            rng.shuffle(pool)
            for dsid in pool[: budget - picked]:
                distractors.add(dsid)

    manifest = {
        "gold_doc_ids": sorted(gold_ids),
        "distractor_doc_ids": sorted(distractors),
        "doc_paths": {
            dsid: str(index[dsid].relative_to(CORPUS_DIR))
            for dsid in sorted(gold_ids | distractors)
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(
        f"\nwrote {MANIFEST_PATH.relative_to(ROOT)}: "
        f"{len(gold_ids)} gold + {len(distractors)} distractors "
        f"= {len(gold_ids | distractors)} docs"
    )
    return manifest


def count_turns(text: str) -> tuple[int, int]:
    lines = text.splitlines()
    turn_lines = 0
    speakers: set[str] = set()
    for line in lines:
        for pattern in TURN_PATTERNS:
            m = pattern.match(line)
            if m:
                turn_lines += 1
                speakers.add(line[: m.end()].strip())
                break
    return turn_lines, len(speakers)


def print_thread_table(index: dict[str, Path]) -> None:
    by_source: dict[str, list[Path]] = defaultdict(list)
    for path in index.values():
        by_source[source_type_of(path)].append(path)

    print("\nthread-grouping table (heuristic: >=3 turn-shaped lines => 'threaded')")
    header = f"{'source':<14}{'docs':>8}{'containers':>12}{'threaded':>10}{'thread %':>10}"
    print(header)
    for source, paths in sorted(by_source.items()):
        containers = {container_of(p) for p in paths if container_of(p) is not None}
        threaded = 0
        for path in paths:
            turns, _speakers = count_turns(path.read_text(errors="ignore"))
            if turns >= MIN_TURNS_FOR_THREAD:
                threaded += 1
        pct = 100.0 * threaded / len(paths) if paths else 0.0
        print(f"{source:<14}{len(paths):>8}{len(containers):>12}{threaded:>10}{pct:>9.1f}%")


def main() -> None:
    if not QUESTIONS_PATH.exists():
        raise SystemExit(f"missing {QUESTIONS_PATH} -- download it first")
    if not CORPUS_DIR.exists():
        raise SystemExit(f"missing {CORPUS_DIR} -- extract all_documents.zip first")

    questions = load_questions()
    print_question_stats(questions)

    index = index_corpus()
    print(f"\nindexed {len(index)} documents under {CORPUS_DIR.relative_to(ROOT)}")

    gold_ids = check_gold_coverage(questions, index)
    build_dev_manifest(gold_ids, index)
    print_thread_table(index)

    print("\nCheckpoint 2 passed.")


if __name__ == "__main__":
    main()
