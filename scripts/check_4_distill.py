"""Checkpoint 4: distillation — burst grouping, noise filter, distill_thread,
and the re-distillation diff. Runs entirely against synthetic fixtures with a
fake LLM (no API key, no network) so it's fast and deterministic; a real
model only needs to be pointed at once these all pass, same as CP 3.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.distill.artifact import (  # noqa: E402
    DistillFailure,
    diff_kept_set,
    distill_thread,
)
from joel.distill.bursts import GAP_MINUTES, group_bursts  # noqa: E402
from joel.distill.df_index import DocFrequencyIndex, has_rare_tokens, keep_burst  # noqa: E402
from joel.distill.state import load_prior_kept, save_thread_state  # noqa: E402
from joel.llm import LLMError, call_json  # noqa: E402
from joel.models import Burst, CanonicalDoc  # noqa: E402

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _msg(
    i: int,
    author: str,
    body: str,
    *,
    minutes: float,
    thread_id: str = "restore-thread",
    reactions: bool = False,
) -> CanonicalDoc:
    return CanonicalDoc(
        doc_id=f"slack__{thread_id}_{i}",
        source_type="slack",
        external_id=f"{thread_id}_{i}",
        title="",
        body=body,
        author_raw=author,
        container="C_INFRA",
        thread_id=thread_id,
        timestamp=T0 + timedelta(minutes=minutes),
        extra={"reactions": [{"name": "eyes"}]} if reactions else {},
    )


def _restore_thread() -> list[CanonicalDoc]:
    """The plan's own worked example (§7.2/§7.3): a Slack thread that ends
    in a concrete fix, with a code-token error string, a supporting
    confirmation, and a pure-noise close."""
    return [
        _msg(0, "@soham", "Anyone know why restore hangs after the manifest load step? Getting ERR_MANIFEST_TIMEOUT.", minutes=0, reactions=True),
        _msg(1, "@alice", "We've seen that when NFS is slow — check CKPT_PREFETCH.", minutes=1),
        _msg(2, "@bob", "Setting CKPT_PREFETCH=4 made it complete for me @soham.", minutes=2),
        _msg(3, "@carol", "Can confirm — same fix on the staging box.", minutes=3),
        _msg(4, "@soham", "Thanks all, documenting this in the runbook now.", minutes=4),
    ]


def _fake_llm_for_restore_thread(*, malformed_first: bool = False):
    """Fake LLMCallFn that answers the distill prompt for `_restore_thread()`
    with a canned, schema-correct response. Optionally returns unparseable
    JSON on the first call to exercise the repair-retry path."""
    calls = {"n": 0}
    response = {
        "message_roles": [
            {"index": 0, "role": "question"},
            {"index": 1, "role": "context"},
            {"index": 2, "role": "resolution"},
            {"index": 3, "role": "answer"},
            {"index": 4, "role": "noise"},
        ],
        "question": "Why does restore hang after manifest load?",
        "summary": "Restore stalled after the manifest-load step on slow NFS mounts.",
        "resolution": "Set CKPT_PREFETCH=4 for the NFS mount.",
        "resolved": True,
        "systems": ["restore", "nfs"],
        "code_refs": ["ERR_MANIFEST_TIMEOUT", "CKPT_PREFETCH"],
        "actors": [
            {"name": "@soham", "role": "asker"},
            {"name": "@bob", "role": "resolver"},
        ],
        "artifact_class": "qa",
        "supersedes": None,
        "confidence": 0.92,
    }

    def _call(stage: str, system_prompt: str, user_prompt: str) -> str:
        calls["n"] += 1
        assert stage == "distill"
        assert "ERR_MANIFEST_TIMEOUT" in user_prompt
        if malformed_first and calls["n"] == 1:
            return "```json\n{not valid json"
        return json.dumps(response)

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


def check_burst_grouping() -> None:
    msgs = _restore_thread()
    bursts = group_bursts(msgs)
    # 5 different authors in a row -> 5 bursts, one message each.
    assert len(bursts) == 5, f"expected 5 bursts, got {len(bursts)}"
    assert all(len(b.message_external_ids) == 1 for b in bursts)

    # Same author, back-to-back within GAP_MINUTES -> merges into one burst.
    same_author = [
        _msg(0, "@dana", "Digging into the timeout now.", minutes=0, thread_id="t2"),
        _msg(1, "@dana", "Looks like it's the manifest fetch retrying forever.", minutes=2, thread_id="t2"),
        _msg(2, "@erin", "Found it — retry loop has no backoff cap.", minutes=3, thread_id="t2"),
        _msg(3, "@erin", "Capped it at 5 retries, deploying now.", minutes=GAP_MINUTES + 5, thread_id="t2"),
    ]
    merged = group_bursts(same_author)
    assert len(merged) == 3, f"expected 3 bursts (merge, merge-break, gap-break), got {len(merged)}"
    assert merged[0].author_raw == "@dana" and len(merged[0].message_external_ids) == 2
    assert merged[1].author_raw == "@erin" and len(merged[1].message_external_ids) == 1
    assert merged[2].author_raw == "@erin"  # same author but past the gap -> new burst
    assert "Digging" in merged[0].text and "manifest fetch" in merged[0].text
    print(f"ok  burst grouping ({len(bursts)} single-author bursts, gap+author-change both split correctly)")


def check_noise_filter() -> None:
    df = DocFrequencyIndex()
    for _ in range(100):
        df.add_document("the team met to discuss status updates sounds good thanks")
    df.add_document("ERR_MANIFEST_TIMEOUT CKPT_PREFETCH nfs restore manifest")

    def burst(text: str, *, role: str | None = None, reactions: bool = False) -> Burst:
        return Burst(
            burst_id="b0",
            thread_id="t",
            author_raw="x",
            text=text,
            message_external_ids=["m0"],
            start_ts=T0,
            end_ts=T0,
            has_reactions=reactions,
            role=role,
        )

    resolution = burst("Setting CKPT_PREFETCH=4 makes it complete.", role="resolution")
    assert keep_burst(resolution, df), "role=resolution must always be kept"

    reacted = burst("nice", reactions=True)
    assert keep_burst(reacted, df), "reacted bursts must always be kept"

    long_rare = burst(
        " ".join(["discussing the incident timeline in detail today"] * 6)
        + " ERR_MANIFEST_TIMEOUT keeps recurring on the larger cluster nodes",
        role="context",
    )
    assert len(long_rare.text.split()) >= 30
    assert has_rare_tokens(long_rare.text, df)
    assert keep_burst(long_rare, df), "long + rare-vocabulary context should be kept"

    short_common = burst("sounds good, thanks! will try that", role="noise")
    assert not keep_burst(short_common, df), "short/common/unreacted noise must be dropped"

    tangent = burst("My laptop also stalls when it sees Monday.", role="context")
    assert not keep_burst(tangent, df), "short common context with no rare tokens must be dropped"

    print("ok  noise filter: resolution/reaction/long+rare kept, short+common+context dropped")


def check_distill_thread_happy_path() -> None:
    msgs = _restore_thread()
    bursts = group_bursts(msgs)
    df = DocFrequencyIndex()
    for m in msgs:
        df.add_document(m.body)
    llm = _fake_llm_for_restore_thread()

    artifact, resolved = distill_thread(msgs, bursts, llm_call=llm, df=df)

    assert artifact is not None
    assert artifact.question == "Why does restore hang after manifest load?"
    assert artifact.resolution == "Set CKPT_PREFETCH=4 for the NFS mount."
    assert artifact.resolved is True
    assert artifact.artifact_class == "qa"
    assert "CKPT_PREFETCH" in artifact.code_refs
    assert artifact.confidence == 0.92
    assert artifact.thread_id == "restore-thread"
    assert artifact.artifact_id == "art__slack__restore-thread"
    assert len(artifact.source_message_ids) == 5

    roles = {b.burst_id: b.role for b in resolved}
    assert roles["restore-thread_b0"] == "question"
    assert roles["restore-thread_b2"] == "resolution"
    kept_ids = {b.burst_id for b in resolved if b.kept}
    assert "restore-thread_b2" in kept_ids  # the resolution, always kept
    assert "restore-thread_b0" in kept_ids  # question, has reactions too
    assert "restore-thread_b4" not in kept_ids  # noise close, short + common + unreacted

    print(f"ok  distill_thread happy path (artifact={artifact.artifact_id!r}, {len(kept_ids)}/{len(resolved)} bursts kept)")


def check_distill_thread_noise_and_low_confidence() -> None:
    msgs = [
        _msg(0, "@x", "hey", minutes=0, thread_id="chitchat"),
        _msg(1, "@y", "hey how's it going", minutes=1, thread_id="chitchat"),
        _msg(2, "@x", "good good, you?", minutes=2, thread_id="chitchat"),
    ]
    bursts = group_bursts(msgs)
    df = DocFrequencyIndex()

    def noise_llm(stage: str, system: str, user: str) -> str:
        return json.dumps(
            {
                "message_roles": [{"index": i, "role": "noise"} for i in range(len(msgs))],
                "question": "n/a",
                "summary": "chit-chat",
                "resolution": None,
                "resolved": False,
                "systems": [],
                "code_refs": [],
                "actors": [],
                "artifact_class": "noise",
                "supersedes": None,
                "confidence": 0.9,
            }
        )

    artifact, resolved = distill_thread(msgs, bursts, llm_call=noise_llm, df=df)
    assert artifact is None, "artifact_class=noise must not produce an artifact"
    assert len(resolved) == len(bursts), "bursts are still returned even when the thread is dropped"

    def low_confidence_llm(stage: str, system: str, user: str) -> str:
        return json.dumps(
            {
                "message_roles": [],
                "question": "Is this a real question?",
                "summary": "unclear",
                "resolution": None,
                "resolved": False,
                "systems": [],
                "code_refs": [],
                "actors": [],
                "artifact_class": "qa",
                "supersedes": None,
                "confidence": 0.1,
            }
        )

    artifact2, _ = distill_thread(msgs, bursts, llm_call=low_confidence_llm, df=df)
    assert artifact2 is None, "confidence < 0.3 must not produce an artifact"
    print("ok  distill_thread drops noise-class and low-confidence threads (never indexed)")


def check_repair_retry_and_failure() -> None:
    msgs = _restore_thread()
    bursts = group_bursts(msgs)
    df = DocFrequencyIndex()
    llm = _fake_llm_for_restore_thread(malformed_first=True)

    artifact, _ = distill_thread(msgs, bursts, llm_call=llm, df=df)
    assert artifact is not None
    assert llm.calls["n"] == 2, "first call malformed, second call (the repair) must succeed"

    def always_broken(stage: str, system: str, user: str) -> str:
        return "not json at all"

    try:
        call_json(always_broken, "distill", "sys", "user")
        raise AssertionError("expected LLMError on double-malformed JSON")
    except LLMError:
        pass

    def raises(stage: str, system: str, user: str) -> str:
        raise LLMError("simulated 500")

    try:
        distill_thread(msgs, bursts, llm_call=raises, df=df)
        raise AssertionError("expected DistillFailure when the LLM call itself raises")
    except DistillFailure as exc:
        assert exc.thread_id == "restore-thread"

    print("ok  JSON repair retry succeeds once, fails loudly on a second malformed response or an LLM error")


def check_redistill_diff() -> None:
    b0 = Burst(burst_id="b0", thread_id="t", author_raw="a", text="original resolution text", message_external_ids=["m0"], start_ts=T0, end_ts=T0, role="resolution", kept=True)
    b1 = Burst(burst_id="b1", thread_id="t", author_raw="b", text="a kept context burst", message_external_ids=["m1"], start_ts=T0, end_ts=T0, role="context", kept=True)

    # First distillation: nothing prior.
    diff0 = diff_kept_set([b0, b1], prior_kept_ids=set(), prior_text_by_id={})
    assert sorted(diff0.to_upsert) == ["b0", "b1"]
    assert diff0.to_delete == []
    assert diff0.unchanged == []

    # Re-distill with identical text -> nothing to touch.
    prior_ids = {"b0", "b1"}
    prior_text = {"b0": b0.text, "b1": b1.text}
    diff1 = diff_kept_set([b0, b1], prior_kept_ids=prior_ids, prior_text_by_id=prior_text)
    assert diff1.to_upsert == []
    assert diff1.to_delete == []
    assert sorted(diff1.unchanged) == ["b0", "b1"]

    # A message edit changes b0's text, b1 drops out of the kept set, a new
    # burst b2 appears and is kept.
    b0_edited = b0.model_copy(update={"text": "corrected resolution text"})
    b2 = Burst(burst_id="b2", thread_id="t", author_raw="c", text="a brand new kept burst", message_external_ids=["m2"], start_ts=T0, end_ts=T0, role="answer", kept=True)
    diff2 = diff_kept_set([b0_edited, b2], prior_kept_ids=prior_ids, prior_text_by_id=prior_text)
    assert sorted(diff2.to_upsert) == ["b0", "b2"], diff2.to_upsert
    assert diff2.to_delete == ["b1"], diff2.to_delete
    assert diff2.unchanged == []

    print("ok  re-distillation diff: new/unchanged/text-changed/dropped bursts bucketed correctly")


def check_thread_state_persistence(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "check4.db")
    conn.execute(
        """CREATE TABLE thread_state (
             thread_id TEXT PRIMARY KEY,
             source_type TEXT NOT NULL,
             artifact_id TEXT NOT NULL,
             kept_bursts_json TEXT NOT NULL DEFAULT '{}',
             last_distilled_at TEXT NOT NULL
           )"""
    )

    empty_ids, empty_text = load_prior_kept(conn, "restore-thread")
    assert empty_ids == set() and empty_text == {}

    save_thread_state(
        conn,
        thread_id="restore-thread",
        source_type="slack",
        artifact_id="art__slack__restore-thread",
        kept_bursts={"restore-thread_b0": "q text", "restore-thread_b2": "resolution text"},
        distilled_at="2026-08-01T12:05:00+00:00",
    )
    conn.commit()
    ids, text = load_prior_kept(conn, "restore-thread")
    assert ids == {"restore-thread_b0", "restore-thread_b2"}
    assert text["restore-thread_b2"] == "resolution text"

    # Re-save (the same thread re-distilled) must upsert, not duplicate.
    save_thread_state(
        conn,
        thread_id="restore-thread",
        source_type="slack",
        artifact_id="art__slack__restore-thread",
        kept_bursts={"restore-thread_b2": "corrected resolution text"},
        distilled_at="2026-08-01T13:00:00+00:00",
    )
    conn.commit()
    row_count = conn.execute("SELECT COUNT(*) FROM thread_state").fetchone()[0]
    assert row_count == 1, "re-distilling the same thread must upsert, not insert a second row"
    ids2, text2 = load_prior_kept(conn, "restore-thread")
    assert ids2 == {"restore-thread_b2"}
    conn.close()
    print("ok  thread_state persists and upserts kept-burst state across re-distillation")


def main() -> None:
    import tempfile

    check_burst_grouping()
    check_noise_filter()
    check_distill_thread_happy_path()
    check_distill_thread_noise_and_low_confidence()
    check_repair_retry_and_failure()
    check_redistill_diff()
    with tempfile.TemporaryDirectory() as td:
        check_thread_state_persistence(Path(td))
    print("\nCP 4 distillation: all automated checks passed.")


if __name__ == "__main__":
    main()
