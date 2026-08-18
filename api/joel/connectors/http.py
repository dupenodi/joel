"""Shared HTTP caller types for Composio-proxied provider fetchers."""

from __future__ import annotations

from typing import Any, Callable

RequestFn = Callable[..., tuple[Any, dict[str, str]]]


class ProviderAPIError(RuntimeError):
    def __init__(
        self,
        error: str,
        *,
        status: int | None = None,
        provider: str = "API",
    ) -> None:
        super().__init__(f"{provider} error: {error}")
        self.error = error
        self.status = status


def as_dict(data: Any) -> dict[str, Any]:
    return data if isinstance(data, dict) else {}


def as_list(data: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys or ("items", "data", "results", "values"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def tool_request(
    composio: Any,
    account_id: str,
    slug: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Run a Composio tool and return its data payload as a dict."""
    from joel.connectors.composio_conn import ComposioError, execute_tool

    try:
        data = execute_tool(composio, slug, arguments, account_id=account_id)
    except ComposioError as exc:
        text = str(exc)
        lowered = text.lower()
        status = (
            401
            if "unauthorized" in lowered or "authenticated" in lowered
            else None
        )
        raise ProviderAPIError(text, status=status) from exc
    return as_dict(data)
