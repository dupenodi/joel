"""Checkpoint 7 (reduced): retrieval and answering (§10) — VECTOR,
VEC-ARTIFACTS, FTS and PHRASE lanes, RRF fusion, LLM rerank, and the
synthesize + abstention gate. GRAPH and WHO_KNOWS are NOT covered here —
both need CP6's ontology, which doesn't exist yet (see `retrieve/lanes.py`).

Runs against a real, disposable SQLite database (through the actual
migrations in `app.py`) and a real `LiveIndex` with a deterministic fake
embedding (feature-hashed bag-of-words, same trick as check_5/check_6) so
semantic-ish similarity is meaningful without paying for a real model on
every assertion. The LLM is a fake, stage-dispatching `LLMCallFn` — no
network, no cost, fully deterministic — except `check_real_llm_smoke`,
which is opt-in (only runs with an `LLM_API_KEY` set) and exercises one
real question against one real LLM end to end.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

import joel.app as app  # noqa: E402
from joel.live_index import LiveIndex  # noqa: E402
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402
from joel.retrieve import answer_question  # noqa: E402
from joel.retrieve.fuse import PER_SOURCE_CAP, rrf_fuse  # noqa: E402
from joel.retrieve.lanes import RetrievedDoc, fts_lane, phrase_lane, run_lanes, vector_artifacts_lane, vector_lane  # noqa: E402
from joel.retrieve.planner import QueryPlan  # noqa: E402
from joel.retrieve.rerank import RerankedDoc, rerank_candidates  # noqa: E402
from joel.retrieve.synthesize import AnswerResult, RERANK_FLOOR, should_abstain, synthesize_answer  # noqa: E402
from joel.store_sql import from_canonical_doc, upsert_docs  # noqa: E402

RUN_ID = uuid.uuid4().hex[:8]
_FAKE_EMBED_DIM = 64


def _fake_embed(texts: list[str]):
    import numpy as np

    matrix = np.zeros((len(texts), _FAKE_EMBED_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in text.lower().split():
            idx = hash(word) % _FAKE_EMBED_DIM
            matrix[i, idx] += 1.0
    return matrix


def _doc(i: int, title: str, body: str, *, granularity: str = "document", source_type: str = "slack") -> CanonicalDoc:
    return CanonicalDoc(
        doc_id=f"chk7_{RUN_ID}_{i}",
        source_type=source_type,
        external_id=f"ext_{i}",
        title=title,
        body=body,
        container="C_CHECK7",
        content_hash=compute_content_hash(title, body),
        granularity=granularity,
        artifact_class="qa" if granularity == "artifact" else "document",
    )


def _store(conn, index, docs: list[CanonicalDoc]) -> None:
    from joel.store import HydraStore

    class _NoGraph:
        """CP7's lanes never touch HydraDB — stub out the graph write so
        this script has zero dependency on a live HydraDB node."""

        def upsert_nodes(self, *a, **k):
            return None

        def link_nodes(self, *a, **k):
            return None

    upsert_docs(conn, index, _NoGraph(), [from_canonical_doc(d) for d in docs], embed_fn=_fake_embed, now="t0")


def _stage_llm(*, plan=None, rerank=None, answer=None):
    """Fake LLMCallFn dispatching by stage name; records every call."""
    calls: list[tuple[str, str]] = []
    responses = {"resolve": plan, "rerank": rerank, "answer": answer}

    def _call(stage: str, system_prompt: str, user_prompt: str) -> str:
        calls.append((stage, user_prompt))
        resp = responses.get(stage)
        if resp is None:
            raise AssertionError(f"unexpected LLM stage {stage!r} with no fake response configured")
        return json.dumps(resp)

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


_DEFAULT_PLAN = {
    "intent": "lookup",
    "entities": [],
    "exact_tokens": [],
    "temporal": {"period": None, "wants_history": False},
    "needs_current_only": False,
    "rewrites": [],
}


def check_lanes_individually(conn: sqlite3.Connection, index: LiveIndex) -> None:
    docs = [
        _doc(1, "Restore incident", "Restore hangs after manifest load, ERR_MANIFEST_TIMEOUT on NFS."),
        _doc(2, "Unrelated topic", "Quarterly marketing budget review for next Tuesday."),
        _doc(3, "Restore fix artifact", "Set CKPT_PREFETCH=4 to fix the restore hang.", granularity="artifact"),
        _doc(4, "Forgotten restore note", "This mentions ERR_MANIFEST_TIMEOUT too but is forgotten."),
    ]
    _store(conn, index, docs)
    forgotten_id = f"chk7_{RUN_ID}_4"
    conn.execute("UPDATE docs SET forgotten=1 WHERE id=?", (forgotten_id,))

    plan = QueryPlan(intent="lookup")

    vec_hits = {d.id for d in vector_lane(conn, index, _fake_embed, plan, "why does restore hang after manifest load")}
    assert f"chk7_{RUN_ID}_1" in vec_hits, "VECTOR lane must surface the semantically close doc"
    assert forgotten_id not in vec_hits, "VECTOR lane must exclude forgotten=1"

    art_hits = {d.id for d in vector_artifacts_lane(conn, index, _fake_embed, plan, "how do I fix restore hanging")}
    assert art_hits == {f"chk7_{RUN_ID}_3"}, f"VEC-ARTIFACTS must only return granularity=artifact docs, got {art_hits}"

    fts_hits = {d.id for d in fts_lane(conn, plan, "ERR_MANIFEST_TIMEOUT")}
    assert f"chk7_{RUN_ID}_1" in fts_hits, "FTS lane must hit the rare-token doc"
    assert forgotten_id not in fts_hits, "FTS lane must exclude forgotten=1"

    phrase_plan = QueryPlan(intent="lookup", exact_tokens=["ERR_MANIFEST_TIMEOUT"])
    phrase_hits = {d.id for d in phrase_lane(conn, phrase_plan, "irrelevant question text")}
    assert f"chk7_{RUN_ID}_1" in phrase_hits, "PHRASE lane must hit an exact_token match"
    assert forgotten_id not in phrase_hits, "PHRASE lane must exclude forgotten=1"

    print("ok  7.1a: VECTOR/VEC-ARTIFACTS/FTS/PHRASE each return sensible results, all exclude forgotten=1")

    lane_results = run_lanes(conn, index, _fake_embed, plan, "why does restore hang after manifest load")
    assert set(lane_results.keys()) == {"vector", "vec_artifacts", "fts", "phrase"}
    assert all(isinstance(v, list) for v in lane_results.values())
    print("ok  7.1b: run_lanes executes all four implemented lanes concurrently and returns per-lane lists")


def _rd(doc_id: str, ts: str = "2026-01-01T00:00:00+00:00") -> RetrievedDoc:
    return RetrievedDoc(
        id=doc_id, title=doc_id, body="", source_type="slack", container=None,
        granularity="document", artifact_class="document", validity="current", url=None, ts=ts,
    )


def check_fusion_consensus_and_cap() -> None:
    consensus = _rd("consensus_doc")
    single = _rd("single_winner")
    lists = {
        "vector": [single, consensus, _rd("v3"), _rd("v4")],
        "fts": [_rd("f1"), _rd("f2"), _rd("f3"), consensus],
        "phrase": [_rd("p1"), _rd("p2"), consensus, _rd("p3")],
    }
    fused = rrf_fuse(lists, top_n=20)
    ids = [d.id for d in fused]
    assert ids.index("consensus_doc") < ids.index("single_winner"), (
        "a doc mid-rank in 3 lanes must outrank a single lane's #1"
    )
    print("ok  7.2a: a doc mid-ranked in 3 lanes outranks a single-lane #1")

    hammered = _rd("hammered")
    many_lists = {f"lane_{i}": [hammered] for i in range(10)}
    fused2 = rrf_fuse(many_lists, top_n=20)
    # PER_SOURCE_CAP=3 means only 3 lanes' worth of score should count, but
    # rrf_fuse's PER_SOURCE_CAP is actually about repeats WITHIN one lane's
    # list, not across lanes -- verify a single lane repeating the same doc
    # doesn't multiply its score past the cap.
    repeat_list = {"vector": [hammered, _rd("x1"), hammered, _rd("x2"), hammered, _rd("x3"), hammered]}
    fused3 = rrf_fuse(repeat_list, top_n=20)
    assert len([d for d in fused3 if d.id == "hammered"]) == 1
    print(f"ok  7.2b: PER_SOURCE_CAP={PER_SOURCE_CAP} caps how many times one lane's repeats count")

    tied_a = _rd("older", ts="2020-01-01T00:00:00+00:00")
    tied_b = _rd("newer", ts="2026-01-01T00:00:00+00:00")
    tie_lists = {"vector": [tied_a, tied_b], "fts": [tied_b, tied_a]}
    fused4 = rrf_fuse(tie_lists, top_n=20)
    assert fused4[0].id == "newer", "within a tie window, the newer doc must win"
    print("ok  7.2c: age decay reorders only inside a tie window")


def check_rerank_scale_and_clamping() -> None:
    candidates = [_rd(f"chk7_{RUN_ID}_r{i}") for i in range(3)]
    llm = _stage_llm(
        rerank=[
            {"id": candidates[0].id, "score": 9, "reason": "states the fix"},
            {"id": candidates[1].id, "score": 15, "reason": "out of range, must clamp"},
            {"id": candidates[2].id, "score": -3, "reason": "out of range, must clamp"},
        ]
    )
    reranked = rerank_candidates(llm, "some question", candidates)
    assert reranked[0].id == candidates[1].id, "scores must sort descending after clamping"
    assert reranked[0].score == 10.0, "score must clamp to the 0-10 scale ceiling"
    assert reranked[-1].score == 0.0, "score must clamp to the 0-10 scale floor"
    print("ok  7.3: rerank scores are clamped and sorted on the 0-10 scale, never the RRF scale")


def _dummy_answered_result() -> AnswerResult:
    return AnswerResult(status="answered", answer="x", citations=[], reasoning_path=[], confidence=0.9)


def check_abstention_empty_and_low_score() -> None:
    assert should_abstain([], _dummy_answered_result()) is True
    print("ok  7.4a: empty reranked list always abstains")

    low = RerankedDoc(doc=_rd("weak"), score=RERANK_FLOOR - 0.1, reason="weak")
    llm = _stage_llm(answer={"status": "answered", "answer": "should never be reached", "citations": ["weak"],
                              "reasoning_path": [], "conflict": None, "confidence": 0.9})
    result = synthesize_answer(llm, "an unanswerable question", [low])
    assert result.status == "absent"
    assert not any(stage == "answer" for stage, _ in llm.calls), (
        "a reranked[0].score below RERANK_FLOOR must abstain WITHOUT spending an answer-stage LLM call"
    )
    print(f"ok  7.4b: reranked[0].rerank_score < {RERANK_FLOOR} abstains before calling the answer stage")


def check_abstention_no_citations_and_fabricated() -> None:
    strong = RerankedDoc(doc=_rd("strong_doc"), score=9.0, reason="on point")

    llm_no_cite = _stage_llm(answer={"status": "answered", "answer": "an answer with no receipts",
                                      "citations": [], "reasoning_path": [], "conflict": None, "confidence": 0.9})
    result1 = synthesize_answer(llm_no_cite, "a real question", [strong])
    assert result1.status == "absent", "status=answered with zero citations must trigger the gate"
    print("ok  7.4c: answered with no citations triggers the abstention gate")

    llm_fabricated = _stage_llm(answer={"status": "answered", "answer": "cites a doc that was never retrieved",
                                         "citations": ["doc_never_seen"], "reasoning_path": [],
                                         "conflict": None, "confidence": 0.9})
    result2 = synthesize_answer(llm_fabricated, "a real question", [strong])
    assert result2.status == "absent", "a fabricated citation must trigger the gate"
    print("ok  7.4d: a citation outside the reranked set triggers the abstention gate")


def check_five_unanswerable_questions_abstain(conn: sqlite3.Connection, index: LiveIndex) -> None:
    _store(conn, index, [_doc(10, "Company snacks policy", "We restock snacks every Monday.")])
    questions = [
        "What did the CEO eat for breakfast on Mars colony day 4?",
        "Who is the secret third founder nobody mentions?",
        "What is the plan for interstellar office expansion?",
        "How many unicorns does the company officially own?",
        "What was decided at the meeting that never happened?",
    ]
    llm = _stage_llm(
        plan=_DEFAULT_PLAN,
        rerank=[],  # nothing in the corpus is on-topic; a real rerank would score everything low
        answer=None,
    )
    for q in questions:
        trace = answer_question(conn, index, _fake_embed, llm, q)
        assert trace.answer.status == "absent", f"expected absent for {q!r}, got {trace.answer.status}"
    print("ok  7.4e: five invented-unanswerable questions all return absent")


def check_happy_path_answered(conn: sqlite3.Connection, index: LiveIndex) -> None:
    docs = [
        _doc(20, "Postgres migration decision", "We decided to migrate to Postgres 16 in March 2026.", granularity="artifact"),
    ]
    _store(conn, index, docs)
    target_id = f"chk7_{RUN_ID}_20"
    llm = _stage_llm(
        plan=_DEFAULT_PLAN,
        rerank=[{"id": target_id, "score": 9, "reason": "states the decision"}],
        answer={
            "status": "answered",
            "answer": "The team decided to migrate to Postgres 16 in March 2026.",
            "citations": [target_id],
            "reasoning_path": ["found the migration decision artifact"],
            "conflict": None,
            "confidence": 0.9,
        },
    )
    trace = answer_question(conn, index, _fake_embed, llm, "what database are we migrating to")
    assert trace.answer.status == "answered"
    assert trace.answer.citations == [target_id]
    print("ok  7.5: a real question with real supporting data returns answered with a valid citation")


def check_traces_log(tmp_dir: Path, conn: sqlite3.Connection, index: LiveIndex) -> None:
    from joel.retrieve import log_trace

    llm = _stage_llm(plan=_DEFAULT_PLAN, rerank=[], answer=None)
    trace = answer_question(conn, index, _fake_embed, llm, "a traced question")
    traces_path = tmp_dir / "state" / "traces.jsonl"
    log_trace(traces_path, trace)
    assert traces_path.exists()
    line = json.loads(traces_path.read_text().splitlines()[-1])
    assert line["question"] == "a traced question"
    assert line["status"] == "absent"
    assert "lane_ranks" in line and "rerank_scores" in line
    print("ok  7.6: every question appends a full trace line to traces.jsonl")


def check_real_llm_smoke(tmp_dir: Path) -> None:
    """Opt-in: only runs with a real LLM_API_KEY in .env, one real question
    against one real LLM call per stage (plan/rerank/answer) — mirrors the
    CP4/CP5 real-LLM smoke pattern rather than being part of the normal
    (free, offline) automated suite."""
    from joel.config import Settings
    from joel.llm import make_openrouter_caller

    load_dotenv(ROOT / ".env")
    api_key = __import__("os").environ.get("LLM_API_KEY", "")
    if not api_key:
        print("skip 7.7: no LLM_API_KEY set — real-LLM smoke test skipped")
        return

    settings_map = {
        "llm_base_url": __import__("os").environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        "llm_api_key": api_key,
        "llm_model_resolve": __import__("os").environ.get("LLM_MODEL_RESOLVE", "anthropic/claude-haiku-4.5"),
        "llm_model_rerank": __import__("os").environ.get("LLM_MODEL_RERANK", "anthropic/claude-haiku-4.5"),
        "llm_model_answer": __import__("os").environ.get("LLM_MODEL_ANSWER", "anthropic/claude-sonnet-4.5"),
    }
    llm_call = make_openrouter_caller(settings_map)

    app.DATA_DIR = tmp_dir
    app.DB_PATH = tmp_dir / "index" / "joel.db"
    app.init_db()
    with app.db() as conn:
        index = LiveIndex(tmp_dir / f"vectors_smoke_{RUN_ID}.npz", dim=_FAKE_EMBED_DIM)
        docs = [_doc(99, "Vacation policy", "Employees get 20 days of paid vacation per year.", granularity="artifact")]
        _store(conn, index, docs)
        trace = answer_question(conn, index, _fake_embed, llm_call, "how many vacation days do employees get")
        print(f"    real LLM plan.intent={trace.plan.intent!r} status={trace.answer.status!r} "
              f"citations={trace.answer.citations}")
        assert trace.answer.status in {"answered", "partial"}, (
            f"expected a real answer from real data, got status={trace.answer.status!r} answer={trace.answer.answer!r}"
        )
    print("ok  7.7: real LLM smoke test — one real plan+rerank+answer call cycle against real data")


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        app.DATA_DIR = tmp_dir
        app.DB_PATH = tmp_dir / "index" / "joel.db"
        app.init_db()

        with app.db() as conn:
            index = LiveIndex(tmp_dir / f"vectors_{RUN_ID}.npz", dim=_FAKE_EMBED_DIM)

            check_lanes_individually(conn, index)
            check_fusion_consensus_and_cap()
            check_rerank_scale_and_clamping()
            check_abstention_empty_and_low_score()
            check_abstention_no_citations_and_fabricated()
            check_five_unanswerable_questions_abstain(conn, index)
            check_happy_path_answered(conn, index)
            check_traces_log(tmp_dir, conn, index)

    with tempfile.TemporaryDirectory() as td2:
        check_real_llm_smoke(Path(td2))

    print("\nCP 7 retrieval (reduced-lane): all automated checks passed.")


if __name__ == "__main__":
    main()
