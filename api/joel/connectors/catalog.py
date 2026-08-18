"""Proxy fetchers for Linear, Notion, Google Drive, and HubSpot."""

from __future__ import annotations

from typing import Any
import re

from joel.adapters import adapt_many
from joel.adapters.manifests import (
    GDRIVE_FILE,
    HUBSPOT_DEAL,
    LINEAR_COMMENT,
    LINEAR_ISSUE,
    NOTION_PAGE,
)
from joel.connectors.http import ProviderAPIError, RequestFn, as_dict, as_list
from joel.models import CanonicalDoc

# Lookback is the real bound. This is a safety cap until poll/backfill cursors exist.
MAX_ITEMS = 250
_PDF_MIME = "application/pdf"


def _as_bytes(payload: Any) -> bytes | None:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        if text.startswith("%PDF"):
            return text.encode("latin-1", "replace")
        compact = re.sub(r"\s+", "", text)
        if re.fullmatch(r"[A-Za-z0-9+/]+=*", compact) and len(compact) >= 32:
            try:
                import base64

                decoded = base64.b64decode(compact, validate=False)
                if decoded.startswith(b"%PDF") or len(decoded) > 8:
                    return decoded
            except Exception:
                pass
        return text.encode("latin-1", "replace")
    if isinstance(payload, dict):
        for key in ("content", "body", "data"):
            nested = payload.get(key)
            raw = _as_bytes(nested)
            if raw:
                return raw
    return None


def _pdf_text(payload: Any) -> str:
    raw = _as_bytes(payload)
    if not raw:
        return ""
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(BytesIO(raw))
    except Exception:
        return ""
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8", "replace")
    bag = as_dict(payload)
    for key in ("body", "content", "text"):
        value = bag.get(key)
        if isinstance(value, str) and value:
            return value
    return str(payload or "")


def _gdrive_file_body(
    request: RequestFn, file_id: str, mime: str, file: dict[str, Any]
) -> str:
    del file
    try:
        if mime == "application/vnd.google-apps.document":
            exported, _ = request(
                "GET",
                f"/files/{file_id}/export",
                {"mimeType": "text/plain"},
            )
            return _payload_text(exported)
        if mime.startswith("text/"):
            exported, _ = request(
                "GET", f"/files/{file_id}", {"alt": "media"}
            )
            return _payload_text(exported)
        if mime == _PDF_MIME:
            exported, _ = request(
                "GET", f"/files/{file_id}", {"alt": "media"}
            )
            return _pdf_text(exported)
    except ProviderAPIError as exc:
        if exc.status in {403, 404}:
            return ""
        raise
    return ""


def _graphql(
    request: RequestFn,
    endpoint: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data, _headers = request(
        "POST", endpoint, {}, {"query": query, "variables": variables or {}}
    )
    payload = as_dict(data)
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        raise ProviderAPIError(str(first.get("message") or "graphql error"))
    inner = payload.get("data")
    return as_dict(inner) if inner is not None else payload


def _plain_rich(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("plain_text") or "")
            for item in value
            if isinstance(item, dict)
        )
    return ""


def fetch_linear_docs(*, since: str, request: RequestFn) -> list[CanonicalDoc]:
    query = """
    query JoelIssues($after: String) {
      issues(first: 50, after: $after, orderBy: updatedAt) {
        nodes {
          id identifier title description createdAt url priority updatedAt
          state { name }
          assignee { name }
          creator { name }
          team { key }
          comments {
            nodes { id body createdAt url user { name } }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    issues: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(issues) < MAX_ITEMS:
        data = _graphql(
            request, "/graphql", query, {"after": cursor} if cursor else {}
        )
        conn = as_dict(data.get("issues"))
        nodes = as_list(conn, "nodes")
        if not nodes:
            break
        for issue in nodes:
            updated = str(issue.get("updatedAt") or issue.get("createdAt") or "")
            if since and updated and updated < since:
                continue
            team = as_dict(issue.get("team"))
            team_key = str(team.get("key") or "")
            state = as_dict(issue.get("state"))
            creator = as_dict(issue.get("creator")) or as_dict(issue.get("assignee"))
            row = dict(issue)
            row["team"] = team
            row["state"] = state.get("name")
            row["creator"] = creator
            if not row.get("description"):
                row["description"] = row.get("title")
            issues.append(row)
            for comment in as_list(as_dict(issue.get("comments")), "nodes"):
                item = dict(comment)
                item["identifier"] = issue.get("identifier")
                item["team_key"] = team_key
                comments.append(item)
            if len(issues) >= MAX_ITEMS:
                break
        page = as_dict(conn.get("pageInfo"))
        if not page.get("hasNextPage"):
            break
        cursor = str(page.get("endCursor") or "") or None
        if not cursor:
            break
    docs = adapt_many(LINEAR_ISSUE, issues)
    docs.extend(adapt_many(LINEAR_COMMENT, comments))
    return docs


def _notion_title(page: dict[str, Any]) -> str:
    props = as_dict(page.get("properties"))
    for value in props.values():
        if isinstance(value, dict) and value.get("type") == "title":
            title = _plain_rich(value.get("title"))
            if title:
                return title
    return str(page.get("id") or "Untitled")


def _notion_blocks(request: RequestFn, block_id: str, *, depth: int = 0) -> str:
    if depth > 2:
        return ""
    parts: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 50}
        if cursor:
            params["start_cursor"] = cursor
        try:
            data, _ = request("GET", f"/v1/blocks/{block_id}/children", params)
        except ProviderAPIError as exc:
            if exc.status in {404, 400}:
                break
            raise
        payload = as_dict(data)
        for block in as_list(payload, "results"):
            btype = str(block.get("type") or "")
            inner = as_dict(block.get(btype))
            text = _plain_rich(inner.get("rich_text") or inner.get("text"))
            if btype.startswith("heading") and text:
                level = btype[-1] if btype[-1].isdigit() else "2"
                parts.append("#" * max(1, int(level)) + " " + text)
            elif text:
                parts.append(text)
            if block.get("has_children") and block.get("id"):
                nested = _notion_blocks(request, str(block["id"]), depth=depth + 1)
                if nested:
                    parts.append(nested)
        if not payload.get("has_more"):
            break
        cursor = str(payload.get("next_cursor") or "") or None
        if not cursor:
            break
    return "\n".join(parts)


def fetch_notion_docs(*, since: str, request: RequestFn) -> list[CanonicalDoc]:
    raws: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(raws) < MAX_ITEMS:
        body: dict[str, Any] = {
            "page_size": 25,
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        }
        if cursor:
            body["start_cursor"] = cursor
        data, _ = request("POST", "/v1/search", {}, body)
        payload = as_dict(data)
        for page in as_list(payload, "results"):
            edited = str(page.get("last_edited_time") or "")
            if since and edited and edited < since:
                continue
            parent = as_dict(page.get("parent"))
            created = as_dict(page.get("created_by"))
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            title = _notion_title(page)
            body = _notion_blocks(request, page_id) or title
            raws.append(
                {
                    "id": page_id,
                    "title": title,
                    "body": body,
                    "author": created.get("name") or created.get("id"),
                    "parent": parent.get("page_id")
                    or parent.get("database_id")
                    or parent.get("type"),
                    "last_edited_time": page.get("last_edited_time"),
                    "url": page.get("url"),
                    "doc_type": "notes",
                }
            )
            if len(raws) >= MAX_ITEMS:
                break
        if not payload.get("has_more"):
            break
        cursor = str(payload.get("next_cursor") or "") or None
        if not cursor:
            break
    return adapt_many(NOTION_PAGE, raws)


def fetch_gdrive_docs(*, since: str, request: RequestFn) -> list[CanonicalDoc]:
    query = "trashed = false"
    if since:
        query += f" and modifiedTime > '{since}'"
    raws: list[dict[str, Any]] = []
    token: str | None = None
    while len(raws) < MAX_ITEMS:
        params: dict[str, Any] = {
            "q": query,
            "pageSize": 50,
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,owners,webViewLink,size,parents)",
            "orderBy": "modifiedTime desc",
        }
        if token:
            params["pageToken"] = token
        data, _ = request("GET", "/files", params)
        payload = as_dict(data)
        for file in as_list(payload, "files"):
            mime = str(file.get("mimeType") or "")
            if mime in {
                "application/vnd.google-apps.folder",
                "application/vnd.google-apps.spreadsheet",
                "application/vnd.google-apps.presentation",
            }:
                continue
            try:
                size = int(file.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            if size > 500_000:
                continue
            file_id = str(file.get("id") or "")
            if not file_id:
                continue
            body = _gdrive_file_body(request, file_id, mime, file)
            if not body.strip():
                continue
            owners = file.get("owners") if isinstance(file.get("owners"), list) else []
            owner = owners[0] if owners and isinstance(owners[0], dict) else {}
            parents = file.get("parents") if isinstance(file.get("parents"), list) else []
            raws.append(
                {
                    "id": file_id,
                    "name": file.get("name"),
                    "body": body,
                    "author": owner.get("displayName") or owner.get("emailAddress"),
                    "folder": str(parents[0]) if parents else None,
                    "modifiedTime": file.get("modifiedTime"),
                    "url": file.get("webViewLink"),
                }
            )
            if len(raws) >= MAX_ITEMS:
                break
        token = str(payload.get("nextPageToken") or "") or None
        if not token:
            break
    return adapt_many(GDRIVE_FILE, raws)


def fetch_hubspot_docs(*, since: str, request: RequestFn) -> list[CanonicalDoc]:
    raws: list[dict[str, Any]] = []
    after: str | None = None
    while len(raws) < 100:
        params: dict[str, Any] = {
            "limit": 50,
            "properties": "dealname,dealstage,amount,pipeline,closedate,hubspot_owner_id,description",
        }
        if after:
            params["after"] = after
        data, _ = request("GET", "/crm/v3/objects/deals", params)
        payload = as_dict(data)
        for deal in as_list(payload, "results"):
            updated = str(deal.get("updatedAt") or deal.get("createdAt") or "")
            if since and updated and updated < since:
                continue
            props = as_dict(deal.get("properties"))
            raws.append(
                {
                    "id": deal.get("id"),
                    "properties": props,
                    "updatedAt": deal.get("updatedAt") or deal.get("createdAt"),
                    "url": f"https://app.hubspot.com/contacts/deals/{deal.get('id')}",
                    "owner": props.get("hubspot_owner_id"),
                }
            )
            if len(raws) >= 100:
                break
        paging = as_dict(as_dict(payload.get("paging")).get("next"))
        after = str(paging.get("after") or "") or None
        if not after:
            break
    return adapt_many(HUBSPOT_DEAL, raws)


__all__ = [
    "ProviderAPIError",
    "fetch_linear_docs",
    "fetch_notion_docs",
    "fetch_gdrive_docs",
    "fetch_hubspot_docs",
]
