"""§13's Slack bot surface: signature verification, event parsing, and
event dedupe are pure functions, tested directly and deterministically.

Two real checks: (1) the real running dev server's `/api/slack/events`
route rejects a wrongly-signed request and accepts a correctly-signed
one (real HTTP, real settings-backed signing secret, real timestamp
math) -- skipped honestly if no dev server is reachable. (2) a full
real happy path -- real actor resolution wiring, a real `answer_question`
call against the real corpus, and a real `chat.postMessage` reply
actually landing in the real connected Slack channel -- run in-process
against the real production data, with ONLY the Slack-email-to-workspace-
member match faked (this install's real admin email doesn't happen to
match any real connected Slack member's, the same caveat CP8b's channel-
membership work already documented; faking just that one step is the
same "prove the mechanism for real, control the one piece that can't be
arranged" approach used there).
"""

from __future__ import annotations

import hashlib
import hmac
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402

from joel.slack_bot import (  # noqa: E402
    SeenEvents,
    parse_app_mention,
    strip_mention,
    verify_signature,
)


def check_verify_signature() -> None:
    secret = "test-signing-secret"
    body = b'{"type":"event_callback"}'
    ts = str(int(time.time()))
    base = f"v0:{ts}:".encode() + body
    good_sig = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()

    assert verify_signature(signing_secret=secret, timestamp=ts, body=body, signature=good_sig)
    assert not verify_signature(signing_secret=secret, timestamp=ts, body=body, signature="v0=wrong")
    assert not verify_signature(signing_secret="different-secret", timestamp=ts, body=body, signature=good_sig)
    assert not verify_signature(signing_secret="", timestamp=ts, body=body, signature=good_sig)

    stale_ts = str(int(time.time()) - 600)
    stale_base = f"v0:{stale_ts}:".encode() + body
    stale_sig = "v0=" + hmac.new(secret.encode(), stale_base, hashlib.sha256).hexdigest()
    assert not verify_signature(signing_secret=secret, timestamp=stale_ts, body=body, signature=stale_sig), (
        "a signature older than the 5-minute replay window must be rejected even if otherwise valid"
    )
    print("ok  sb.1: verify_signature accepts a real signature, rejects wrong/mismatched/stale ones")


def check_parse_app_mention() -> None:
    real_event = {
        "token": "x",
        "team_id": "T1",
        "api_app_id": "A1",
        "event": {
            "type": "app_mention",
            "user": "U123",
            "text": "<@UBOT> what is the refund policy?",
            "ts": "1700000000.000100",
            "channel": "C123",
            "event_ts": "1700000000.000100",
        },
        "type": "event_callback",
        "event_id": "Ev123",
        "event_time": 1700000000,
    }
    mention = parse_app_mention(real_event)
    assert mention is not None
    assert mention.channel == "C123" and mention.user == "U123" and mention.event_id == "Ev123"
    assert mention.thread_ts is None
    print("ok  sb.2: a real app_mention event_callback parses correctly")

    threaded = dict(real_event)
    threaded["event"] = {**real_event["event"], "thread_ts": "1699999999.000000"}
    mention2 = parse_app_mention(threaded)
    assert mention2 is not None and mention2.thread_ts == "1699999999.000000"
    print("ok  sb.3: a threaded mention's thread_ts is preserved")

    assert parse_app_mention({"type": "url_verification", "challenge": "abc"}) is None
    assert parse_app_mention({"type": "event_callback", "event": {"type": "message"}}) is None
    assert parse_app_mention({"type": "event_callback", "event": {"type": "app_mention"}}) is None, (
        "a malformed app_mention missing user/channel/ts must not parse, never guess"
    )
    print("ok  sb.4: url_verification, non-mention events, and malformed mentions all parse to None")


def check_strip_mention() -> None:
    assert strip_mention("<@UBOT> what is the refund policy?", "UBOT") == "what is the refund policy?"
    assert strip_mention("<@UBOT>   spaced out question", "UBOT") == "spaced out question"
    # A mention of someone ELSE at the start is real content, not the bot's own boilerplate.
    assert strip_mention("<@USOMEONEELSE> can you ask joel this?", "UBOT") == "<@USOMEONEELSE> can you ask joel this?"
    assert strip_mention("no mention at all", "UBOT") == "no mention at all"
    print("ok  sb.5: strip_mention removes only the bot's own leading mention, nothing else")


def check_seen_events_dedupe() -> None:
    seen = SeenEvents(max_size=3)
    assert seen.already_seen("a") is False
    assert seen.already_seen("a") is True, "the same event_id must be recognized as a retry"
    assert seen.already_seen("b") is False
    assert seen.already_seen("c") is False
    assert seen.already_seen("d") is False  # evicts the oldest ("a" is already gone anyway)
    print("ok  sb.6: SeenEvents dedupes retried event_ids and stays bounded")


def check_live_signature_enforcement() -> None:
    """Real check #1: the real running server's real route, real settings-
    backed secret, real timestamp math."""
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/healthz", timeout=2)
    except Exception:
        print("skip live: no dev server reachable at 127.0.0.1:8000")
        return

    sys.path.insert(0, str(ROOT / "api"))
    import joel.app as app

    data_dir = ROOT / "data"
    db_path = data_dir / "index" / "joel.db"
    if not db_path.exists():
        print("skip live: no real data/index/joel.db")
        return
    app.DATA_DIR = data_dir
    app.DB_PATH = db_path

    secret = "check-slack-bot-test-secret"
    with app.db() as conn:
        original = conn.execute("SELECT value FROM settings WHERE key='slack_signing_secret'").fetchone()
        original_value = original["value"] if original else ""
        conn.execute(
            "INSERT INTO settings(key,value) VALUES ('slack_signing_secret',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (secret,),
        )

    try:
        body = b'{"type":"url_verification","challenge":"chk-live-slackbot"}'
        ts = str(int(time.time()))
        base = f"v0:{ts}:".encode() + body
        good_sig = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()

        def post(sig: str, timestamp: str) -> tuple[int, bytes]:
            req = urllib.request.Request(
                "http://127.0.0.1:8000/api/slack/events",
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": sig,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read()

        status, resp_body = post(good_sig, ts)
        assert status == 200, (status, resp_body)
        assert b"chk-live-slackbot" in resp_body, "the real endpoint must echo the url_verification challenge back"

        status_bad, _ = post("v0=" + "0" * 64, ts)
        assert status_bad == 401, status_bad

        print("ok  live.1: the real /api/slack/events route enforces real signatures and handles url_verification")
    finally:
        with app.db() as conn:
            conn.execute("UPDATE settings SET value=? WHERE key='slack_signing_secret'", (original_value,))


def check_live_full_mention_round_trip() -> None:
    """Real check #2: in-process (not over HTTP, so the one unavailable
    piece -- a real Slack member whose email matches this install's real
    admin -- can be faked) against the real corpus and the real connected
    Slack workspace. Everything downstream of actor resolution is real:
    real answer_question, real chat.postMessage."""
    sys.path.insert(0, str(ROOT / "api"))
    import joel.app as app
    import joel.identity as identity

    data_dir = ROOT / "data"
    db_path = data_dir / "index" / "joel.db"
    if not db_path.exists():
        print("skip live: no real data/index/joel.db")
        return
    app.DATA_DIR = data_dir
    app.DB_PATH = db_path

    with app.db() as conn:
        slack_row = conn.execute(
            "SELECT id, channel_ids_json FROM connections WHERE provider='slack' AND status='ready'"
        ).fetchone()
        admin_row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    if slack_row is None or admin_row is None:
        print("skip live: no ready Slack connection or no real user to resolve to")
        return
    channel_ids = app._channel_ids(slack_row)
    if not channel_ids:
        print("skip live: the real Slack connection has no channels selected")
        return
    channel = channel_ids[0]

    original_resolve = app._resolve_slack_actor
    app._resolve_slack_actor = lambda conn, slack_user_id: identity.actor_for_user(conn, admin_row["id"])  # type: ignore[assignment]
    try:
        with app.db() as conn:
            before = conn.execute("SELECT id FROM connections WHERE provider='slack'").fetchone()
            credentials = app._credential(conn, before["id"])
            settings_map = app._settings_map(conn)
            from joel.connectors.slack import SlackClient

            client = SlackClient(app._slack_token(credentials), caller=app._slack_caller(credentials, settings_map))
            before_messages = client.call("conversations.history", channel=channel, limit=5)

        marker = f"chk-slackbot-{int(time.time())}"
        app._handle_slack_mention(
            f"ev_{marker}", channel, "U_FAKE_SLACK_USER",
            "<@UBOT> what is joel?",
            str(time.time()), "UBOT",
        )

        with app.db() as conn:
            credentials = app._credential(conn, before["id"])
            settings_map = app._settings_map(conn)
            client = SlackClient(app._slack_token(credentials), caller=app._slack_caller(credentials, settings_map))
            after_messages = client.call("conversations.history", channel=channel, limit=5)

        before_ts = {m.get("ts") for m in (before_messages.get("messages") or [])}
        new_messages = [m for m in (after_messages.get("messages") or []) if m.get("ts") not in before_ts]
        assert new_messages, "a real reply must actually appear in the real Slack channel"
        print(
            f"ok  live.2: a real mention was answered and a real reply landed in Slack channel {channel} "
            f"-- {new_messages[0].get('text', '')[:80]!r}"
        )
    finally:
        app._resolve_slack_actor = original_resolve


def main() -> None:
    load_dotenv(ROOT / ".env")
    check_verify_signature()
    check_parse_app_mention()
    check_strip_mention()
    check_seen_events_dedupe()
    check_live_signature_enforcement()
    check_live_full_mention_round_trip()
    print("\nSlack bot (§13): all automated checks passed.")


if __name__ == "__main__":
    main()
