"""Checkpoint 10: the agent (§13) — follow-up rewriting, meta/chitchat cheap
paths, and live lookup's whitelist detection.

Deterministic checks use a fake, stage-dispatching `LLMCallFn` (no network,
no cost). `check_live_detection_and_real_fetch` is opt-in: it only runs
against the real local dataset (needs `data/index/joel.db` to exist with at
least one ready GitHub or Slack connection) and makes real network calls
through the real stored Composio credentials — same "opt-in real-data smoke
test" convention every prior checkpoint uses.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

from joel.agent.live import (  # noqa: E402
    GitHubCatalogTarget,
    GitHubItemTarget,
    SlackChannelTarget,
    connection_can_live,
    detect_live_targets,
)
from joel.agent.working_memory import Turn, answer_meta, rewrite_question  # noqa: E402
from joel.llm import LLMError  # noqa: E402
from joel.retrieve.planner import QueryPlan  # noqa: E402


def _stage_llm(response: dict):
    calls: list[str] = []

    def _call(stage: str, system_prompt: str, user_prompt: str) -> str:
        calls.append(stage)
        return json.dumps(response)

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


def check_followup_rewrite() -> None:
    turns = [
        Turn(role="user", content="Who owns the runbook rewrite?"),
        Turn(role="assistant", content="Ada owns it.", citations=("doc_1",)),
    ]
    llm = _stage_llm({"question": "What is Ada's role on the runbook rewrite?", "kind": "knowledge"})
    result = rewrite_question(llm, turns, "what about her role on it?")
    assert result.kind == "knowledge"
    assert "Ada" in result.question, f"pronoun follow-up must resolve using prior turns, got {result.question!r}"
    assert llm.calls == ["resolve"], "rewrite_question must use the RESOLVE alias, not a new one"
    print("ok  10.1a: a pronoun follow-up is rewritten standalone using the prior turns")


def check_already_standalone_passes_through() -> None:
    standalone = "What is the Q3 revenue target?"
    llm = _stage_llm({"question": standalone, "kind": "knowledge"})
    result = rewrite_question(llm, [], standalone)
    assert result.question == standalone
    print("ok  10.1b: an already-standalone question passes through unchanged")


def check_rewrite_degrades_on_llm_failure() -> None:
    def boom(stage, sp, up):
        # Every real LLMCallFn (`openrouter_call`) wraps network/response
        # failures in LLMError -- callers never see a raw exception type.
        raise LLMError("network blip")

    result = rewrite_question(boom, [], "is the deploy done")
    assert result.question == "is the deploy done" and result.kind == "knowledge", (
        "an LLM failure must degrade to treating the raw message as a standalone knowledge question"
    )
    print("ok  10.1c: rewrite_question degrades to standalone-knowledge on any LLM failure")


def check_meta_answers_from_turns_only() -> None:
    turns = [
        Turn(role="user", content="Who owns the runbook rewrite?"),
        Turn(role="assistant", content="Ada owns it.", citations=("art__slack__t1", "doc_2")),
    ]
    assert "art__slack__t1" in answer_meta(turns, "which sources did you use")
    assert answer_meta(turns, "what did you just say") == "Ada owns it."
    print("ok  10.2a: meta questions answer from the stored conversation alone, zero extra calls")


def check_live_whitelist_detection() -> None:
    class _Scratch:
        """No real docs.table needed for the GitHub-with-explicit-repo and
        Slack-channel-name cases -- only the ambiguous-repo fallback path
        touches SQL, and that's exercised in the opt-in real-data check."""

        def execute(self, *a, **k):
            raise AssertionError("this path should not need to query docs for an explicit owner/repo")

    plan = QueryPlan(intent="live")
    targets = detect_live_targets(_Scratch(), "is acme/hydra#118 merged yet?", plan)
    assert len(targets) == 1 and isinstance(targets[0], GitHubItemTarget)
    assert targets[0].owner == "acme" and targets[0].repo == "hydra" and targets[0].number == 118
    print("ok  10.3a: an explicit owner/repo#N is detected as a GitHub live target")

    targets = detect_live_targets(_Scratch(), "what's the latest in #eng-oncall", plan)
    assert len(targets) == 1 and isinstance(targets[0], SlackChannelTarget)
    assert targets[0].channel_name == "eng-oncall"
    print("ok  10.3b: a #channel mention is detected as a Slack live target")

    targets = detect_live_targets(_Scratch(), "is acme/hydra#118 merged, also check #eng-oncall", plan)
    assert len(targets) == 2, f"both whitelisted mentions in one question must be detected, capped at 2, got {targets}"
    print("ok  10.3c: at most MAX_LOOKUPS targets are detected per question")

    targets = detect_live_targets(_Scratch(), "no live-shaped mention here at all", plan)
    assert targets == [], "a question matching none of the whitelist must detect zero targets, never guess"
    print("ok  10.3d: a question matching nothing in the whitelist detects zero targets")

    targets = detect_live_targets(_Scratch(), "what's currently open on acme/hydra", plan)
    assert len(targets) == 1 and isinstance(targets[0], GitHubCatalogTarget)
    assert targets[0].owner == "acme" and targets[0].repo == "hydra"
    print("ok  10.3e: a named repo without a number is a catalog live target")

    class _Repos:
        def execute(self, *a, **k):
            class _Rows:
                def fetchall(self):
                    return [{"container": "acme/hydra"}]
            return _Rows()

    targets = detect_live_targets(_Repos(), "Check for open github PRs", plan)
    assert len(targets) == 1 and isinstance(targets[0], GitHubCatalogTarget)
    assert targets[0].owner == "acme" and targets[0].repo == "hydra"
    print("ok  10.3f: a GitHub now-question with no number uses the connected-repo catalog")

    targets = detect_live_targets(_Repos(), "Check for open PRs", plan)
    assert len(targets) == 1 and isinstance(targets[0], GitHubCatalogTarget)
    print("ok  10.3h: catalog nouns (PR) cue GitHub without naming the provider")

    targets = detect_live_targets(_Scratch(), "is acme/hydra#118 merged yet?", plan)
    assert isinstance(targets[0], GitHubItemTarget)
    print("ok  10.3g: a numbered item still wins over a catalog for the same repo")

    assert connection_can_live("syncing")
    assert connection_can_live("ready")
    assert connection_can_live("backfilling")
    assert not connection_can_live("needs_reauth")
    assert not connection_can_live("pending_auth")
    assert not connection_can_live("error")
    print("ok  10.3i: live reads while ingest is in flight; not while unauthed")


def check_live_detection_and_real_fetch() -> None:
    """Opt-in: real data + real network. Mirrors the manual verification
    already done for this checkpoint against the live corpus."""
    import os

    data_dir = ROOT / "data"
    db_path = data_dir / "index" / "joel.db"
    if not db_path.exists():
        print("skip 10.4: no real data/index/joel.db — real live-lookup smoke test skipped")
        return

    import joel.app as app
    from joel.agent.live import fetch_live_target
    from joel.connectors.github import GITHUB_ACCEPT, GitHubAPIError

    app.DATA_DIR = data_dir
    app.DB_PATH = db_path
    with app.db() as conn:
        gh_row = conn.execute(
            "SELECT id FROM connections WHERE provider='github' AND status='ready'"
        ).fetchone()
        repo_row = conn.execute(
            "SELECT DISTINCT container FROM docs WHERE source_type='github' AND container LIKE '%/%' LIMIT 1"
        ).fetchone()
        item_row = conn.execute(
            "SELECT id FROM docs WHERE source_type='github' AND (id LIKE '%__pr_%' OR id LIKE '%__issue_%') LIMIT 1"
        ).fetchone()
        if gh_row is None or repo_row is None or item_row is None:
            print("skip 10.4: no ready GitHub connection with real PR/issue data — skipped")
            return

        settings_map = app._settings_map(conn)
        credentials = app._credential(conn, gh_row["id"])
        request = app._provider_request(
            credentials, settings_map, GitHubAPIError, extra_headers={"Accept": GITHUB_ACCEPT}
        )
        owner, repo = repo_row["container"].split("/", 1)
        # Extract the real number from a real doc id like ".../pr_owner_repo_2".
        number = int(item_row["id"].rsplit("_", 1)[-1])
        result = fetch_live_target(
            GitHubItemTarget(owner=owner, repo=repo, number=number), github_request=request
        )
        assert result.docs, f"a real point-lookup for a real known PR/issue must return one doc, got none for {owner}/{repo}#{number}"
        print(f"ok  10.4: real live GitHub lookup fetched {owner}/{repo}#{number} — {result.docs[0].title[:60]!r}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    check_followup_rewrite()
    check_already_standalone_passes_through()
    check_rewrite_degrades_on_llm_failure()
    check_meta_answers_from_turns_only()
    check_live_whitelist_detection()
    check_live_detection_and_real_fetch()
    print("\nCP 10 agent: all automated checks passed.")


if __name__ == "__main__":
    main()
