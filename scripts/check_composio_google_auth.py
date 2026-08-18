"""Smoke-test Composio Google OAuth outside Joel's app flow.

This script exercises the plain Composio session authorize flow from the docs:

    composio = Composio(api_key=...)
    session = composio.create(user_id=..., auth_configs={...})
    request = session.authorize(toolkit, callback_url=...)

Use it to compare:
1. Managed auth with Composio defaults (no auth config id)
2. Custom auth config (pass --auth-config-id ac_...)

If the managed path reproduces "This app is blocked" here too, the issue is
outside Joel and sits with the Composio Google auth configuration/behavior.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience only
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]


def _redirect_url(value: object) -> str | None:
    if value is None:
        return None
    for key in ("redirect_url", "redirectUrl"):
        direct = getattr(value, key, None)
        if isinstance(direct, str) and direct:
            return direct
    if isinstance(value, dict):
        for key in ("redirect_url", "redirectUrl"):
            raw = value.get(key)
            if isinstance(raw, str) and raw:
                return raw
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            for key in ("redirect_url", "redirectUrl"):
                raw = data.get(key)
                if isinstance(raw, str) and raw:
                    return raw
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--toolkit",
        choices=("gmail", "googledrive"),
        required=True,
        help="Google toolkit to test.",
    )
    parser.add_argument(
        "--callback-url",
        default="http://localhost:8000/api/composio/callback",
        help="OAuth callback URL passed to Composio.",
    )
    parser.add_argument(
        "--user-id",
        default="joel-composio-smoke",
        help="Composio user_id for the smoke session.",
    )
    parser.add_argument(
        "--auth-config-id",
        default="",
        help="Optional custom Composio auth config id (ac_...).",
    )
    parser.add_argument(
        "--api-key-env",
        default="COMPOSIO_API_KEY",
        help="Environment variable that holds the Composio API key.",
    )
    return parser.parse_args()


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    args = parse_args()

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing {args.api_key_env}")

    try:
        from composio import Composio
    except ImportError as exc:
        raise SystemExit(
            "Missing composio package. Install it in your venv first, "
            "for example: `pip install composio`."
        ) from exc

    composio = Composio(api_key=api_key)

    auth_configs: dict[str, str] | None = None
    mode = "managed-defaults"
    if args.auth_config_id.strip():
        auth_configs = {args.toolkit: args.auth_config_id.strip()}
        mode = "custom-auth-config"

    print(f"toolkit={args.toolkit}")
    print(f"mode={mode}")
    print(f"user_id={args.user_id}")
    print(f"callback_url={args.callback_url}")
    if auth_configs:
        print(f"auth_config_id={auth_configs[args.toolkit]}")
    print("", flush=True)

    create_kwargs: dict[str, object] = {"user_id": args.user_id}
    if auth_configs:
        create_kwargs["auth_configs"] = auth_configs
    session = composio.create(**create_kwargs)
    request = session.authorize(args.toolkit, callback_url=args.callback_url)
    redirect_url = _redirect_url(request)
    if not redirect_url:
        print("Composio response did not include a redirect URL.", file=sys.stderr)
        print(repr(request), file=sys.stderr)
        return 2

    print("Open this URL and continue the OAuth flow:")
    print(redirect_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
