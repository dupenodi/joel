"""Checkpoint 3: adapter core — manifests, hashing, triage, thread grouping.

Runs entirely against synthetic fixtures (no live OAuth). Once this is green,
provider fetch/auth can be wired one connector at a time and re-checked here
with real payloads during onboarding.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.adapters import (  # noqa: E402
    GITHUB_ISSUE,
    GITHUB_PR,
    SLACK,
    adapt,
    adapt_many,
    group_threads,
    triage,
    triage_batch,
)
from joel.models import CanonicalDoc, compute_content_hash  # noqa: E402


def _slack_msgs() -> list[dict]:
    """Twenty Slack-shaped messages: one 5-msg thread, one 3-msg, rest roots."""
    base = 1_700_000_000.0
    msgs: list[dict] = []

    # Thread A — 5 messages (root + 4 replies)
    root_a = f"{base:.6f}"
    msgs.append(
        {
            "ts": root_a,
            "text": "Anyone know why restore hangs after the manifest load step?",
            "user": "U_SOHAM",
            "channel": "C_INFRA",
            "team_domain": "acme",
            "reactions": [{"name": "eyes", "count": 2}],
        }
    )
    for i, text in enumerate(
        [
            "We've seen that when NFS is slow — check `CKPT_PREFETCH`.",
            "Setting CKPT_PREFETCH=4 made it complete for me <@U_SOHAM>.",
            "Can confirm — same fix on the staging box.",
            "Thanks all, documenting this in the runbook now.",
        ],
        start=1,
    ):
        msgs.append(
            {
                "ts": f"{base + i:.6f}",
                "thread_ts": root_a,
                "text": text,
                "user": f"U_USER{i}",
                "channel": "C_INFRA",
                "team_domain": "acme",
            }
        )

    # Thread B — exactly 3 messages
    root_b = f"{base + 100:.6f}"
    msgs.append(
        {
            "ts": root_b,
            "text": "Did we decide to bump the enterprise tier by 8% this quarter?",
            "user": "@alice",
            "channel": "C_PRICING",
            "team_domain": "acme",
        }
    )
    msgs.append(
        {
            "ts": f"{base + 101:.6f}",
            "thread_ts": root_b,
            "text": "Yes — decided Friday, effective next Monday.",
            "user": "@bob",
            "channel": "C_PRICING",
            "team_domain": "acme",
        }
    )
    msgs.append(
        {
            "ts": f"{base + 102:.6f}",
            "thread_ts": root_b,
            "text": "I'll update the sales deck <@U_ALICE>.",
            "user": "@carol",
            "channel": "C_PRICING",
            "team_domain": "acme",
        }
    )

    # Short body — must be skipped
    msgs.append(
        {
            "ts": f"{base + 200:.6f}",
            "text": "ok thanks",
            "user": "U_NOISE",
            "channel": "C_INFRA",
            "team_domain": "acme",
        }
    )

    # Enough standalone messages to reach ≥20 kept docs after the skip
    for i in range(12):
        msgs.append(
            {
                "ts": f"{base + 300 + i:.6f}",
                "text": (
                    f"Standalone status update #{i}: deploy pipeline is green "
                    f"and the canary looks healthy on shard {i}."
                ),
                "user": f"U_STAND{i}",
                "channel": "C_ENG",
                "team_domain": "acme",
                "reactions": [{"name": "thumbsup", "count": i}],
            }
        )

    return msgs


def check_hash_stability() -> None:
    a = compute_content_hash("title", "body text here")
    b = compute_content_hash("title", "body text here")
    assert a == b and len(a) == 64, "content_hash must be stable sha256 hex"
    assert a != compute_content_hash("title", "body text herE"), "body edit must change hash"
    # Provider metadata must not affect hash — only title+body do.
    d1 = CanonicalDoc(
        doc_id="slack__1",
        source_type="slack",
        external_id="1",
        title="t",
        body="hello world this is long enough",
        extra={"reactions": [{"count": 1}]},
        content_hash=compute_content_hash("t", "hello world this is long enough"),
    )
    d2 = d1.model_copy(update={"extra": {"reactions": [{"count": 99}]}})
    assert d1.content_hash == d2.content_hash
    print("ok  hash stability")


def check_slack_adapt() -> list[CanonicalDoc]:
    raws = _slack_msgs()
    docs = adapt_many(SLACK, raws)
    assert len(docs) >= 20, f"expected ≥20 docs, got {len(docs)}"
    assert all(d.body and d.content_hash and d.granularity for d in docs)
    assert all(len(d.body) >= 20 for d in docs)
    assert all(d.timestamp is not None and d.timestamp.tzinfo for d in docs)

    # Short "ok thanks" skipped
    assert all("ok thanks" not in d.body for d in docs)

    # Root has no parent; reply does
    by_ts = {d.external_id: d for d in docs}
    root = next(d for d in docs if d.thread_id == d.external_id and "restore hangs" in d.body)
    assert root.parent_id is None
    reply = next(d for d in docs if d.parent_id == root.external_id)
    assert reply.thread_id == root.external_id

    # Raw handles / mention forms preserved (not stripped to bare names)
    mentioned = next(d for d in docs if "@U_SOHAM" in d.body or "@U_SOHAM" in d.participants_raw)
    assert any("@U_SOHAM" in p for p in mentioned.participants_raw) or "@U_SOHAM" in mentioned.body

    # Reaction metadata in extra, not hashed into identity
    reacted = next(d for d in docs if d.extra.get("reactions"))
    assert reacted.extra["reactions"]

    # Permalink built
    assert root.url and "slack.com/archives" in root.url

    print(f"ok  slack adapt ({len(docs)} docs)")
    return docs


def check_thread_grouping(docs: list[CanonicalDoc]) -> None:
    threads = group_threads(docs)
    assert len(threads) >= 2, f"expected ≥2 threads, got {len(threads)}"
    sizes = sorted(len(v) for v in threads.values())
    assert sizes[-1] >= 5 and sizes[-2] >= 3
    # Standalone messages must not form singleton "threads"
    assert all(len(v) >= 3 for v in threads.values())
    print(f"ok  thread grouping ({len(threads)} threads: {sizes})")


def check_change_detection(docs: list[CanonicalDoc]) -> None:
    known = {d.doc_id: d.content_hash for d in docs}
    report = triage_batch(docs, known)
    assert report.counts == {"new": 0, "changed": 0, "unchanged": len(docs)}
    assert not report.dirty_thread_ids

    # Re-adapt identical payloads → still all unchanged
    again = adapt_many(SLACK, _slack_msgs())
    report2 = triage_batch(again, known)
    assert report2.counts["unchanged"] == len(again)
    assert report2.counts["new"] == 0
    assert report2.counts["changed"] == 0

    # Edit one body → exactly one changed + dirty thread
    edited_raw = _slack_msgs()[0]
    edited_raw = dict(edited_raw)
    edited_raw["text"] = edited_raw["text"] + " (edited with more detail for the runbook)"
    edited = adapt(SLACK, edited_raw)
    assert edited is not None
    assert triage(edited, known) == "changed"
    report3 = triage_batch([edited], known)
    assert report3.counts["changed"] == 1
    assert edited.thread_id in report3.dirty_thread_ids

    # Brand-new ts → new
    fresh = adapt(
        SLACK,
        {
            "ts": "1700000999.000001",
            "text": "Brand new message that is definitely long enough to keep.",
            "user": "U_NEW",
            "channel": "C_ENG",
            "team_domain": "acme",
        },
    )
    assert fresh is not None
    assert triage(fresh, known) == "new"

    # Reaction-only churn must not flip content_hash
    churn = dict(_slack_msgs()[0])
    churn["reactions"] = [{"name": "fire", "count": 99}]
    churned = adapt(SLACK, churn)
    assert churned is not None
    assert triage(churned, known) == "unchanged"

    print("ok  change detection (zero LLM path)")


def check_github_identity() -> None:
    issue = adapt(
        GITHUB_ISSUE,
        {
            "number": 42,
            "title": "Restore hangs on NFS",
            "body": "After manifest load the restore stalls forever on the NFS mount.",
            "user": {"login": "soham"},
            "repository": {"full_name": "acme/hydra"},
            "created_at": "2026-08-01T12:00:00Z",
            "html_url": "https://github.com/acme/hydra/issues/42",
            "state": "open",
            "labels": ["bug"],
        },
    )
    pr = adapt(
        GITHUB_PR,
        {
            "number": 42,
            "title": "Fix CKPT_PREFETCH default",
            "body": "Bumps the default prefetch so restore does not hang on slow NFS.",
            "user": {"login": "soham"},
            "repository": {"full_name": "acme/hydra"},
            "created_at": "2026-08-02T12:00:00Z",
            "html_url": "https://github.com/acme/hydra/pull/42",
            "state": "open",
            "draft": False,
            "merged": False,
        },
    )
    assert issue is not None and pr is not None
    assert issue.doc_id != pr.doc_id
    assert issue.doc_id == "github__issue_42"
    assert pr.doc_id == "github__pr_42"
    assert issue.thread_id == "issue_42"
    assert pr.thread_id == "pr_42"
    assert issue.author_raw == "soham"
    print("ok  github issue/PR identity")


def check_doc_id_collisions(docs: list[CanonicalDoc]) -> None:
    ids = [d.doc_id for d in docs]
    assert len(ids) == len(set(ids)), "doc_id collision inside slack fixture"
    issue_pr_docs = []
    for manifest, number in ((GITHUB_ISSUE, 7), (GITHUB_PR, 7)):
        doc = adapt(
            manifest,
            {
                "number": number,
                "title": f"Item {number} with a sufficiently long body for keep.",
                "body": f"Body for item {number} that clears the minimum length gate easily.",
                "user": {"login": "dev"},
                "repository": {"full_name": "acme/app"},
                "created_at": "2026-08-10T00:00:00+00:00",
                "html_url": f"https://github.com/acme/app/{'issues' if manifest is GITHUB_ISSUE else 'pull'}/{number}",
            },
        )
        assert doc is not None
        issue_pr_docs.append(doc)
    all_ids = ids + [d.doc_id for d in issue_pr_docs]
    assert len(all_ids) == len(set(all_ids))
    print("ok  zero doc_id collisions")


def main() -> None:
    check_hash_stability()
    docs = check_slack_adapt()
    check_thread_grouping(docs)
    check_change_detection(docs)
    check_github_identity()
    check_doc_id_collisions(docs)
    print("\nCP 3 adapter core: all automated checks passed.")
    print("👁 still needed on real data: code chunk boundaries, gmail quote-strip.")


if __name__ == "__main__":
    main()
