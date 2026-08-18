"""Confluence fetcher via Composio tools (generic REST proxy returns 403)."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from joel.adapters import adapt_many
from joel.adapters.manifests import CONFLUENCE_PAGE, split_document_on_h2
from joel.connectors.http import as_dict, as_list, tool_request
from joel.models import CanonicalDoc

MAX_ITEMS = 250


def _cursor_from_links(payload: dict[str, Any]) -> str | None:
    links = as_dict(payload.get("_links"))
    next_link = str(links.get("next") or "")
    if not next_link:
        return None
    query = parse_qs(urlsplit(next_link).query)
    values = query.get("cursor") or []
    return str(values[0]) if values else None


def _page_html(page: dict[str, Any]) -> Any:
    body = page.get("body")
    if isinstance(body, dict) and (
        body.get("storage") or body.get("value") or body.get("atlas_doc_format")
    ):
        return body
    return page.get("body")


def fetch_confluence_docs(
    *,
    since: str,
    composio: Any,
    account_id: str,
) -> list[CanonicalDoc]:
    raws: list[dict[str, Any]] = []
    cursor: str | None = None
    base = ""
    while len(raws) < MAX_ITEMS:
        args: dict[str, Any] = {
            "limit": min(50, MAX_ITEMS - len(raws)),
            "sort": "-modified-date",
            "status": "current",
            "body_format": "storage",
        }
        if cursor:
            args["cursor"] = cursor
        payload = tool_request(composio, account_id, "CONFLUENCE_GET_PAGES", args)
        links = as_dict(payload.get("_links"))
        base = str(links.get("base") or base).rstrip("/")
        for page in as_list(payload, "results"):
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            version = as_dict(page.get("version"))
            when = str(version.get("createdAt") or page.get("createdAt") or "")
            if since and when and when < since:
                continue
            body = _page_html(page)
            if not body:
                detail = tool_request(
                    composio,
                    account_id,
                    "CONFLUENCE_GET_PAGE_BY_ID",
                    {"id": page_id},
                )
                body = _page_html(detail) or detail.get("body")
                version = as_dict(detail.get("version")) or version
                when = str(version.get("createdAt") or detail.get("createdAt") or when)
                page_links = as_dict(detail.get("_links")) or as_dict(page.get("_links"))
            else:
                page_links = as_dict(page.get("_links"))
            webui = str(page_links.get("webui") or "")
            url = f"{base}{webui}" if base and webui else webui or None
            raws.append(
                {
                    "id": page_id,
                    "title": page.get("title"),
                    "body": body,
                    "author": page.get("authorId") or version.get("authorId"),
                    "space": page.get("spaceId"),
                    "when": when,
                    "parent_id": page.get("parentId"),
                    "url": url,
                }
            )
            if len(raws) >= MAX_ITEMS:
                break
        cursor = _cursor_from_links(payload)
        if not cursor:
            break
    expanded: list[dict[str, Any]] = []
    for raw in raws:
        expanded.extend(split_document_on_h2(raw))
    return adapt_many(CONFLUENCE_PAGE, expanded)
