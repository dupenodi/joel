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
    CONFLUENCE_PAGE,
    FIREFLIES_CHUNK,
    GITHUB_ISSUE,
    GITHUB_PR,
    GMAIL,
    HUBSPOT_DEAL,
    JIRA_ISSUE,
    LINEAR_ISSUE,
    SLACK,
    adapt,
    adapt_many,
    group_threads,
    triage,
    triage_batch,
)
from joel.adapters.manifests import html_to_markdown, split_document_on_h2, strip_gmail_quotes  # noqa: E402
from joel.syncer import ingest_is_schedulable  # noqa: E402
from joel.adapters.code_chunk import chunk_code  # noqa: E402
from joel.connectors.catalog import fetch_gdrive_docs, fetch_linear_docs
from joel.connectors.fireflies import fetch_fireflies_docs
from joel.connectors.github import fetch_github_docs  # noqa: E402
from joel.connectors.gmail import fetch_gmail_docs, gmail_plain_body  # noqa: E402
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
    other = adapt(
        GITHUB_PR,
        {
            "number": 42,
            "title": "SEO audit report for the marketing site",
            "body": "",
            "user": {"login": "soham"},
            "repository": {"full_name": "dupenodi/dupenodi"},
            "created_at": "2026-08-02T12:00:00Z",
            "html_url": "https://github.com/dupenodi/dupenodi/pull/42",
            "state": "open",
        },
    )
    assert issue is not None and pr is not None and other is not None
    assert issue.doc_id != pr.doc_id
    assert pr.doc_id != other.doc_id
    assert issue.doc_id == "github__issue_acme_hydra_42"
    assert pr.doc_id == "github__pr_acme_hydra_42"
    assert other.doc_id == "github__pr_dupenodi_dupenodi_42"
    assert issue.thread_id == "issue_acme/hydra#42"
    assert pr.thread_id == "pr_acme/hydra#42"
    assert issue.author_raw == "soham"
    print("ok  github issue/PR identity")


def check_gmail_quotes() -> None:
    raw = {
        "id": "m1",
        "threadId": "t1",
        "subject": "Restore hang on NFS",
        "from": "soham@acme.dev",
        "to": ["alice@acme.dev"],
        "internalDate": "1755000000000",
        "mailbox": "you@acme.dev",
        "body": (
            "Setting CKPT_PREFETCH=4 unblocked restore on the NFS mount.\n"
            "--\nSoham Ratnaparkhi\n"
            "\nOn Mon, Aug 1, 2026 at 12:00 PM Alice wrote:\n"
            "> still hanging after manifest load\n"
        ),
    }
    cleaned = strip_gmail_quotes(raw)
    assert "CKPT_PREFETCH=4" in cleaned["body"]
    assert "Soham Ratnaparkhi" in cleaned["body"]
    assert "still hanging" not in cleaned["body"]
    doc = adapt(GMAIL, raw)
    assert doc is not None
    assert "still hanging" not in doc.body
    assert doc.author_raw == "soham@acme.dev"
    print("ok  gmail quote strip")


def check_github_fetch() -> None:
    def request(method: str, endpoint: str, params: dict) -> tuple[object, dict]:
        del method, params
        if endpoint.startswith("/user/repos"):
            return (
                [
                    {
                        "full_name": "acme/app",
                        "fork": False,
                        "archived": False,
                        "default_branch": "main",
                    },
                    {
                        "full_name": "acme/forked",
                        "fork": True,
                        "archived": False,
                    },
                ],
                {},
            )
        if "/issues/comments" in endpoint:
            return (
                [
                    {
                        "id": 99,
                        "body": "Confirmed on staging after the prefetch bump landed.",
                        "user": {"login": "alice"},
                        "created_at": "2026-08-10T00:00:00Z",
                        "html_url": "https://github.com/acme/app/issues/7#issuecomment-99",
                        "issue_url": "https://api.github.com/repos/acme/app/issues/7",
                    }
                ],
                {},
            )
        if "/pulls/comments" in endpoint:
            return ([], {})
        if endpoint.rstrip("/").endswith("/reviews"):
            return (
                [
                    {
                        "id": 77,
                        "body": "Please keep CKPT_PREFETCH=4 or restore hangs on NFS.",
                        "user": {"login": "alice"},
                        "submitted_at": "2026-08-11T00:00:00Z",
                        "html_url": "https://github.com/acme/app/pull/8#pullrequestreview-77",
                        "state": "CHANGES_REQUESTED",
                    }
                ],
                {},
            )
        if "/git/trees/" in endpoint:
            src = (
                "class Hydra:\n"
                "    def restore(self):\n"
                "        return CKPT_PREFETCH\n"
            )
            return (
                {
                    "tree": [
                        {
                            "path": "src/restore.py",
                            "type": "blob",
                            "sha": "abc",
                            "size": len(src),
                        }
                    ]
                },
                {},
            )
        if "/git/blobs/" in endpoint:
            import base64

            src = (
                "class Hydra:\n"
                "    def restore(self):\n"
                "        return CKPT_PREFETCH\n"
            )
            return (
                {
                    "encoding": "base64",
                    "content": base64.b64encode(src.encode()).decode(),
                },
                {},
            )
        if endpoint.endswith("/issues") or "/issues?" in endpoint:
            return (
                [
                    {
                        "number": 7,
                        "title": "Restore hangs on NFS",
                        "body": "After manifest load the restore stalls forever on the NFS mount.",
                        "user": {"login": "soham"},
                        "created_at": "2026-08-01T12:00:00Z",
                        "html_url": "https://github.com/acme/app/issues/7",
                        "state": "open",
                        "labels": ["bug"],
                    },
                    {
                        "number": 8,
                        "title": "Fix CKPT_PREFETCH default",
                        "body": "Sets CKPT_PREFETCH=4 so restore does not hang on NFS.",
                        "user": {"login": "soham"},
                        "created_at": "2026-08-02T12:00:00Z",
                        "html_url": "https://github.com/acme/app/pull/8",
                        "state": "open",
                        "pull_request": {
                            "url": "https://api.github.com/repos/acme/app/pulls/8"
                        },
                    },
                ],
                {},
            )
        raise AssertionError(f"unexpected GitHub endpoint {endpoint}")

    docs = fetch_github_docs(since="2026-07-01T00:00:00Z", request=request)
    kinds = {doc.external_id.split("_", 1)[0] for doc in docs}
    assert "issue" in kinds
    assert "comment" in kinds
    issue = next(doc for doc in docs if doc.external_id.startswith("issue_"))
    comment = next(doc for doc in docs if doc.external_id.startswith("comment_"))
    review = next(doc for doc in docs if doc.external_id.startswith("review_"))
    code = next(doc for doc in docs if doc.granularity == "code")
    assert issue.doc_id == "github__issue_acme_app_7"
    assert comment.parent_id == issue.thread_id
    assert issue.container == "acme/app"
    assert "CKPT_PREFETCH" in review.body
    assert "restore.py" in code.title
    print(f"ok  github fetch ({len(docs)} docs)")


def check_gmail_fetch() -> None:
    payload = {
        "mimeType": "text/plain",
        "body": {
            "data": __import__("base64").urlsafe_b64encode(
                b"Setting CKPT_PREFETCH=4 unblocked restore on NFS.\n"
            ).decode()
        },
        "headers": [
            {"name": "Subject", "value": "Restore hang"},
            {"name": "From", "value": "Soham <soham@acme.dev>"},
            {"name": "To", "value": "Alice <alice@acme.dev>"},
        ],
    }
    assert "CKPT_PREFETCH" in gmail_plain_body(payload)

    def request(method: str, endpoint: str, params: dict) -> tuple[object, dict]:
        del method, params
        if endpoint.endswith("/profile"):
            return ({"emailAddress": "you@acme.dev"}, {})
        if endpoint.endswith("/messages"):
            return ({"messages": [{"id": "m1", "threadId": "t1"}]}, {})
        if endpoint.endswith("/messages/m1"):
            return (
                {
                    "id": "m1",
                    "threadId": "t1",
                    "internalDate": "1755000000000",
                    "labelIds": ["INBOX"],
                    "payload": payload,
                },
                {},
            )
        raise AssertionError(f"unexpected Gmail endpoint {endpoint}")

    from datetime import datetime, timezone

    docs = fetch_gmail_docs(
        after=datetime(2026, 8, 1, tzinfo=timezone.utc),
        request=request,
    )
    assert len(docs) == 1
    assert docs[0].source_type == "gmail"
    assert docs[0].author_raw == "soham@acme.dev"
    assert docs[0].container == "you@acme.dev"
    print("ok  gmail fetch")


def check_extra_adapters() -> None:
    issue = adapt(
        LINEAR_ISSUE,
        {
            "identifier": "ENG-9",
            "title": "Restore hangs on NFS",
            "description": "After manifest load the restore stalls forever on the NFS mount.",
            "creator": {"name": "soham"},
            "team": {"key": "ENG"},
            "createdAt": "2026-08-01T12:00:00Z",
            "url": "https://linear.app/acme/issue/ENG-9",
            "state": "In Progress",
            "priority": 2,
        },
    )
    assert issue is not None
    assert issue.doc_id == "linear__eng-9"
    assert issue.container == "ENG"

    jira = adapt(
        JIRA_ISSUE,
        {
            "key": "AUTH-123",
            "summary": "SSO callback rejects the state param",
            "body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "The callback 400s when state is missing from the cookie jar."}]}]},
            "assignee": "alice",
            "project": "AUTH",
            "created": "2026-08-01T12:00:00Z",
            "status": "Open",
            "priority": "High",
            "url": "https://acme.atlassian.net/browse/AUTH-123",
        },
    )
    assert jira is not None
    assert jira.doc_id == "jira__auth-123"
    assert "cookie jar" in jira.body

    html = html_to_markdown("<h1>Runbook</h1><p>Set <code>CKPT_PREFETCH=4</code>.</p>")
    assert "# Runbook" in html
    assert "CKPT_PREFETCH=4" in html
    page = adapt(
        CONFLUENCE_PAGE,
        {
            "id": "42",
            "title": "NFS restore runbook",
            "body": {"storage": {"value": "<h2>Fix</h2><p>Set CKPT_PREFETCH=4 on the restore host.</p>"}},
            "author": "soham",
            "space": "OPS",
            "when": "2026-08-01T12:00:00Z",
            "url": "https://acme.atlassian.net/wiki/spaces/OPS/pages/42",
        },
    )
    assert page is not None
    assert page.extra.get("doc_type") == "runbook"

    deal = adapt(
        HUBSPOT_DEAL,
        {
            "id": "55",
            "properties": {
                "dealname": "Acme renewal",
                "dealstage": "negotiation",
                "amount": "50000",
                "pipeline": "default",
                "hubspot_owner_id": "morgan",
                "description": "Waiting on legal redlines.",
            },
            "updatedAt": "2026-08-01T12:00:00Z",
            "owner": "morgan",
        },
    )
    assert deal is not None
    assert "Acme renewal" in deal.body
    assert deal.extra["data"]["amount"] == "50000"

    chunk = adapt(
        FIREFLIES_CHUNK,
        {
            "id": "m1_c0",
            "thread_id": "m1",
            "title": "Restore incident",
            "body": "soham: We should set CKPT_PREFETCH=4 before the next restore.\nalice: Agreed, I'll change the default.",
            "host": "soham@acme.dev",
            "date": 1755000000000,
            "url": "https://app.fireflies.ai/view/m1",
        },
    )
    assert chunk is not None
    assert chunk.timestamp is not None and chunk.timestamp.tzinfo

    def linear_request(method: str, endpoint: str, params: dict, body=None):
        del method, params
        assert endpoint == "/graphql"
        assert body and "issues" in body["query"]
        return (
            {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "identifier": "ENG-9",
                                "title": "Restore hangs on NFS",
                                "description": "After manifest load the restore stalls forever on the NFS mount.",
                                "createdAt": "2026-08-01T12:00:00Z",
                                "updatedAt": "2026-08-10T12:00:00Z",
                                "url": "https://linear.app/acme/issue/ENG-9",
                                "priority": 2,
                                "state": {"name": "In Progress"},
                                "assignee": {"name": "soham"},
                                "team": {"key": "ENG"},
                                "comments": {
                                    "nodes": [
                                        {
                                            "id": "c1",
                                            "body": "Setting CKPT_PREFETCH=4 unblocked it on staging.",
                                            "createdAt": "2026-08-10T13:00:00Z",
                                            "url": "https://linear.app/acme/issue/ENG-9#c1",
                                            "user": {"name": "alice"},
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            },
            {},
        )

    linear_docs = fetch_linear_docs(since="2026-07-01T00:00:00Z", request=linear_request)
    assert {doc.source_type for doc in linear_docs} == {"linear"}
    assert any(doc.external_id == "ENG-9" for doc in linear_docs)

    def fake_execute_tool(composio, slug, arguments, *, account_id=None, user_id="joel-owner"):
        del composio, arguments, account_id, user_id
        assert slug == "FIREFLIES_GET_TRANSCRIPTS"
        return {
            "transcripts": [
                {
                    "id": "m1",
                    "title": "Restore incident",
                    "date": 1755000000000,
                    "host_email": "soham@acme.dev",
                    "sentences": [
                        {
                            "speaker": "soham",
                            "text": "We should set CKPT_PREFETCH=4 before the next restore.",
                        },
                        {
                            "speaker": "alice",
                            "text": "Agreed, I will change the default in the runbook today.",
                        },
                    ],
                    "summary": {"overview": "Decide prefetch default"},
                }
            ]
        }

    from datetime import datetime, timezone

    import joel.connectors.composio_conn as composio_conn

    original_execute = composio_conn.execute_tool
    composio_conn.execute_tool = fake_execute_tool
    try:
        flies = fetch_fireflies_docs(
            after=datetime(2026, 8, 1, tzinfo=timezone.utc),
            composio=object(),
            account_id="acc_test",
        )
    finally:
        composio_conn.execute_tool = original_execute
    assert len(flies) == 1
    assert flies[0].source_type == "fireflies"
    print("ok  extra adapters (linear/jira/confluence/hubspot/fireflies)")


def check_document_ingest() -> None:
    filler = "Set CKPT_PREFETCH=4 on the restore host. " * 200
    page = {
        "id": "42",
        "title": "NFS restore runbook",
        "body": {
            "storage": {
                "value": (
                    f"<h2>Symptoms</h2><p>{filler}</p>"
                    f"<h2>Fix</h2><p>{filler}</p>"
                )
            }
        },
        "author": "soham",
        "space": "OPS",
        "when": "2026-08-01T12:00:00Z",
        "url": "https://acme.atlassian.net/wiki/spaces/OPS/pages/42",
    }
    parts = split_document_on_h2(page)
    assert len(parts) >= 2
    assert parts[0]["id"] == "42_s0"
    assert parts[1]["parent_id"] == "42"
    assert all(part.get("linked_to") == "42" for part in parts)

    from unittest.mock import patch

    def drive_request(method: str, endpoint: str, params: dict) -> tuple[object, dict]:
        del method
        if endpoint.endswith("/files") and "alt" not in params:
            return (
                {
                    "files": [
                        {
                            "id": "doc1",
                            "name": "Restore notes",
                            "mimeType": "application/vnd.google-apps.document",
                            "modifiedTime": "2026-08-10T00:00:00Z",
                            "owners": [{"emailAddress": "soham@acme.dev"}],
                            "webViewLink": "https://docs.google.com/document/d/doc1",
                            "parents": ["folder1"],
                            "size": 1200,
                        },
                        {
                            "id": "pdf1",
                            "name": "Restore runbook.pdf",
                            "mimeType": "application/pdf",
                            "modifiedTime": "2026-08-11T00:00:00Z",
                            "owners": [{"emailAddress": "alice@acme.dev"}],
                            "webViewLink": "https://drive.google.com/file/d/pdf1",
                            "parents": ["folder1"],
                            "size": 8000,
                        },
                    ]
                },
                {},
            )
        if endpoint.endswith("/export"):
            return ("Setting CKPT_PREFETCH=4 unblocked restore on the NFS mount.", {})
        if endpoint.endswith("/pdf1"):
            return (b"%PDF-fake", {})
        raise AssertionError(f"unexpected Drive endpoint {endpoint} {params}")

    with patch(
        "joel.connectors.catalog._pdf_text",
        return_value="PDF extract: keep CKPT_PREFETCH=4 or restore hangs.",
    ):
        docs = fetch_gdrive_docs(since="2026-07-01T00:00:00Z", request=drive_request)
    kinds = {doc.external_id for doc in docs}
    assert "doc1" in kinds
    assert "pdf1" in kinds
    assert ingest_is_schedulable("github", [])
    assert ingest_is_schedulable("gmail", [])
    assert not ingest_is_schedulable("slack", [])
    assert ingest_is_schedulable("slack", ["C123"])
    print(f"ok  document ingest ({len(parts)} confluence parts, {len(docs)} drive docs)")


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


def check_code_chunk() -> None:
    src = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 1\n"
        "\n"
        "class Baz:\n"
        "    def qux(self):\n"
        "        return 2\n"
    )
    chunks = chunk_code("mod.py", src)
    assert len(chunks) >= 2
    huge = "def big():\n" + ("    x = 1\n" * 200)
    parts = chunk_code("big.py", huge)
    assert len(parts) == 1
    print("ok  code chunk boundaries")


def main() -> None:
    check_hash_stability()
    docs = check_slack_adapt()
    check_thread_grouping(docs)
    check_change_detection(docs)
    check_github_identity()
    check_doc_id_collisions(docs)
    check_gmail_quotes()
    check_code_chunk()
    check_github_fetch()
    check_gmail_fetch()
    check_extra_adapters()
    check_document_ingest()
    print("\nCP 3 adapter core: all automated checks passed.")


if __name__ == "__main__":
    main()
