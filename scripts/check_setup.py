"""Setup-pass checks: Slack/settings keys, Indexed vs Live allowlist jobs."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel.connectors.gate import INTEGRATIONS, LIVE_PROVIDERS  # noqa: E402
from joel import identity  # noqa: E402


def check_live_vs_indexed_jobs() -> None:
    live_ids = {item.id for item in INTEGRATIONS if item.job == "live"}
    indexed_ids = {item.id for item in INTEGRATIONS if item.job == "indexed"}
    assert live_ids == {"github", "linear"}, live_ids
    assert live_ids == LIVE_PROVIDERS
    assert "notion" in indexed_ids and "slack" in indexed_ids and "gmail" in indexed_ids
    for item in INTEGRATIONS:
        if item.id in live_ids:
            assert item.ingest is True, f"{item.id} must still ingest in v1"
    print("ok  setup.1: GitHub and Linear are Live; everyone else Indexed; ingest stays on")


def check_new_settings_seeded() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app.DATA_DIR = tmp
        app.DB_PATH = tmp / "index" / "joel.db"
        app.init_db()
        with app.db() as conn:
            actor, _ = identity.setup(
                conn,
                email="ada@acme.dev",
                password="secretsecret",
                display_name="Ada",
                domain="acme.dev",
            )
            app.seed_org_defaults(conn, actor.org_id)
            settings = app._settings_map(conn, actor.org_id)
            for key in ("slack_bot_token", "voice", "workspace_about"):
                assert key in app.DEFAULT_SETTINGS
                assert key in settings, f"{key} missing after seed"
            assert app._is_secret_setting("slack_bot_token")
            assert not app._is_secret_setting("voice")
            assert not app._is_secret_setting("workspace_about")
    print("ok  setup.2: slack_bot_token / voice / workspace_about seed on a new org")


def main() -> None:
    check_live_vs_indexed_jobs()
    check_new_settings_seeded()
    print("\nSetup pass: all automated checks passed.")


if __name__ == "__main__":
    main()
