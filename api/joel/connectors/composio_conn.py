"""Composio as auth broker. Joel still fetches and adapts on its own."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from composio import Composio

COMPOSIO_USER_ID = "joel-owner"
COMPOSIO_KEY_SETTING = "composio_api_key"
TOOLKIT_VERSIONS = {
    "jira": "20260812_00",
    "confluence": "20260721_00",
    "fireflies": "20260625_00",
}


class ComposioError(RuntimeError):
    pass


def _prepare_cache() -> None:
    cache = Path(os.getenv("COMPOSIO_CACHE_DIR") or os.getenv("JOEL_DATA", "data"))
    if cache.name != ".composio":
        cache = cache / ".composio"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("COMPOSIO_CACHE_DIR", str(cache))


def _composio_cls():
    _prepare_cache()
    from composio import Composio

    return Composio


def mask_api_key(key: str) -> str:
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}…{key[-4:]}"


def resolve_composio_key(settings: dict[str, str]) -> tuple[str | None, str]:
    from_settings = (settings.get(COMPOSIO_KEY_SETTING) or "").strip()
    if from_settings:
        return from_settings, "settings"
    from_env = os.getenv("COMPOSIO_API_KEY", "").strip()
    if from_env:
        return from_env, "env"
    return None, "none"


def get_composio(settings: dict[str, str]) -> Composio:
    api_key, _source = resolve_composio_key(settings)
    if not api_key:
        raise ComposioError(
            "Composio API key not set — add it on Integrations or set COMPOSIO_API_KEY"
        )
    return _composio_cls()(api_key=api_key)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    dump = getattr(value, "dict", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if not str(k).startswith("_")}
    return {}


def _records(listed: Any) -> list[Any]:
    if listed is None:
        return []
    if isinstance(listed, list):
        return listed
    items = getattr(listed, "items", None)
    if isinstance(items, list):
        return items
    data = _as_dict(listed)
    nested = data.get("items")
    if isinstance(nested, list):
        return nested
    return []


def _toolkit_slug(account: Any) -> str:
    data = _as_dict(account)
    toolkit = data.get("toolkit") or getattr(account, "toolkit", None)
    if isinstance(toolkit, str) and toolkit:
        return toolkit.lower()
    nested = _as_dict(toolkit)
    slug = nested.get("slug") or nested.get("name")
    if isinstance(slug, str) and slug:
        return slug.lower()
    for key in ("toolkitSlug", "toolkit_slug", "appName", "app_name"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    return "unknown"


def _account_label(account: Any) -> str | None:
    bags = [_as_dict(account)]
    for key in ("data", "state", "params", "status_reason", "statusReason"):
        value = bags[0].get(key)
        if value is not None:
            bags.append(_as_dict(value))
            inner_val = _as_dict(value).get("val")
            if inner_val is not None:
                bags.append(_as_dict(inner_val))
    fields = (
        "email",
        "user_email",
        "account_email",
        "username",
        "login",
        "team_name",
        "team",
        "name",
        "display_name",
        "displayName",
    )
    for bag in bags:
        for field in fields:
            value = bag.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
            nested = bag.get("team")
            if isinstance(nested, dict):
                name = nested.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        for nest in ("user", "profile", "member", "team"):
            inner = bag.get(nest)
            if isinstance(inner, dict):
                for field in fields:
                    value = inner.get(field)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return None


def _redirect_url(value: Any) -> str | None:
    data = _as_dict(value)
    url = (
        getattr(value, "redirect_url", None)
        or getattr(value, "redirectUrl", None)
        or data.get("redirect_url")
        or data.get("redirectUrl")
    )
    return url if isinstance(url, str) and url else None


def start_toolkit_connect(
    composio: Composio,
    toolkit: str,
    callback_url: str,
    auth_config_id: str | None = None,
) -> str:
    slug = toolkit.strip().lower()
    create_kwargs: dict[str, Any] = {"user_id": COMPOSIO_USER_ID}
    config_id = (auth_config_id or "").strip()
    if config_id:
        create_kwargs["auth_configs"] = {slug: config_id}
    session = composio.create(**create_kwargs)
    request = session.authorize(slug, callback_url=callback_url)
    url = _redirect_url(request)
    if url:
        return url
    raise ComposioError("Composio did not return a redirect URL")


def list_connected_accounts(composio: Composio) -> list[dict[str, Any]]:
    listed = composio.connected_accounts.list(
        user_ids=[COMPOSIO_USER_ID],
        limit=100,
    )
    accounts: list[dict[str, Any]] = []
    for raw in _records(listed):
        data = _as_dict(raw)
        account_id = data.get("id") or getattr(raw, "id", None)
        if not account_id:
            continue
        status = str(data.get("status") or getattr(raw, "status", "UNKNOWN"))
        accounts.append(
            {
                "id": str(account_id),
                "toolkit": _toolkit_slug(raw),
                "status": status,
                "label": _account_label(raw),
                "user_id": data.get("user_id") or data.get("userId"),
            }
        )
    return accounts


def find_active_account(composio: Composio, toolkit: str) -> dict[str, Any] | None:
    active = {"ACTIVE", "SUCCESS", "CONNECTED"}
    slug = toolkit.lower()
    for account in list_connected_accounts(composio):
        if account["toolkit"] == slug and account["status"].upper() in active:
            return account
    return None


@dataclass
class ProxyResult:
    status: int
    data: Any
    headers: dict[str, str] = field(default_factory=dict)


def _relative_endpoint(endpoint: str) -> str:
    text = endpoint.strip()
    if text.startswith("http://") or text.startswith("https://"):
        parts = urlsplit(text)
        path = parts.path or "/"
        if parts.query:
            return f"{path}?{parts.query}"
        return path
    if not text.startswith("/"):
        return f"/{text}"
    return text


def proxy_call(
    composio: Composio,
    account_id: str,
    endpoint: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: object | None = None,
) -> ProxyResult:
    """Call a provider API through Composio so Joel never stores a raw token.

    Composio masks access tokens on connected-account reads, so hitting
    Slack/GitHub/Gmail directly with extracted credentials fails.
    """
    parameters: list[dict[str, str]] = []
    for key, value in (headers or {}).items():
        if value is not None:
            parameters.append({"name": str(key), "value": str(value), "type": "header"})
    for key, value in (params or {}).items():
        if value is not None and value != "":
            parameters.append({"name": str(key), "value": str(value), "type": "query"})
    last_error = "proxy failed"
    verb = method.upper()
    if verb not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}:
        raise ComposioError(f"Unsupported proxy method {method}")
    path = _relative_endpoint(endpoint)
    for attempt in range(4):
        try:
            kwargs: dict[str, Any] = {
                "endpoint": path,
                "method": verb,
                "connected_account_id": account_id,
                "parameters": parameters or None,
            }
            if body is not None:
                kwargs["body"] = body
            response = composio.tools.proxy(**kwargs)
        except Exception as exc:
            last_error = str(exc)
            if attempt < 3 and "429" in last_error:
                time.sleep(1 + attempt)
                continue
            raise ComposioError(last_error) from exc
        status = int(getattr(response, "status", 200) or 200)
        if status == 429:
            time.sleep(1 + attempt)
            continue
        raw = getattr(response, "data", None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                pass
        header_map = getattr(response, "headers", None)
        headers_out = dict(header_map) if isinstance(header_map, dict) else {}
        return ProxyResult(status=status, data=raw, headers=headers_out)
    raise ComposioError(last_error)


def execute_tool(
    composio: Composio,
    slug: str,
    arguments: dict[str, Any],
    *,
    account_id: str | None = None,
    user_id: str = COMPOSIO_USER_ID,
) -> Any:
    toolkit = slug.split("_", 1)[0].lower()
    version = os.getenv(f"COMPOSIO_TOOLKIT_VERSION_{toolkit.upper()}") or TOOLKIT_VERSIONS.get(
        toolkit
    )
    kwargs: dict[str, Any] = {
        "connected_account_id": account_id,
        "user_id": user_id,
    }
    if version:
        kwargs["version"] = version
    else:
        kwargs["dangerously_skip_version_check"] = True
    try:
        response = composio.tools.execute(slug, arguments, **kwargs)
    except Exception as exc:
        raise ComposioError(str(exc)) from exc
    raw = _as_dict(response)
    if raw.get("successful") is False:
        raise ComposioError(str(raw.get("error") or "tool execution failed"))
    return raw.get("data")


def slack_proxy_call(
    composio: Composio,
    account_id: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Slack Web API via Composio proxy. Returns the Slack JSON body."""
    result = proxy_call(composio, account_id, f"/{method}", params=params)
    if result.status >= 400:
        raise ComposioError(f"Composio Slack proxy HTTP {result.status}")
    raw = result.data
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ComposioError("Composio Slack proxy returned non-JSON") from exc
    if not isinstance(raw, dict):
        raw = _as_dict(raw)
    for key in ("data", "response", "body"):
        inner = raw.get(key)
        if isinstance(inner, dict) and (
            "ok" in inner
            or "channels" in inner
            or "members" in inner
            or "messages" in inner
        ):
            raw = inner
            break
    return raw
