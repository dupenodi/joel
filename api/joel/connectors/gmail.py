"""Gmail REST fetcher via an injected HTTP caller (Composio proxy in prod)."""

from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from joel.adapters import GMAIL, adapt_many
from joel.connectors.http import RequestFn
from joel.models import CanonicalDoc


class GmailAPIError(RuntimeError):
    def __init__(self, error: str, *, status: int | None = None) -> None:
        super().__init__(f"Gmail API error: {error}")
        self.error = error
        self.status = status


_HTML_BLOCK = re.compile(r"(?is)<(script|style).*?>.*?</\1>")
_BR = re.compile(r"(?is)<br\s*/?>")
_P_END = re.compile(r"(?is)</p>")
_TAG = re.compile(r"(?s)<[^>]+>")


def _b64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", "replace")


def _strip_html(raw: str) -> str:
    text = _HTML_BLOCK.sub(" ", raw)
    text = _BR.sub("\n", text)
    text = _P_END.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def gmail_plain_body(payload: dict[str, Any]) -> str:
    """Prefer text/plain; fall back to stripped HTML."""
    mime = str(payload.get("mimeType") or "")
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    data = body.get("data") if isinstance(body, dict) else None
    if mime.startswith("text/plain") and isinstance(data, str) and data:
        return _b64url(data)
    if mime.startswith("text/html") and isinstance(data, str) and data:
        return _strip_html(_b64url(data))
    plains: list[str] = []
    htmls: list[str] = []
    for part in payload.get("parts") or []:
        if not isinstance(part, dict):
            continue
        extracted = gmail_plain_body(part)
        child_mime = str(part.get("mimeType") or "")
        if child_mime.startswith("text/html"):
            htmls.append(extracted)
        elif extracted:
            plains.append(extracted)
    if plains:
        return "\n".join(plains)
    return "\n".join(htmls)


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in payload.get("headers") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").lower()
        value = item.get("value")
        if name and isinstance(value, str):
            out[name] = value
    return out


def _split_addresses(value: str) -> list[str]:
    parts: list[str] = []
    for chunk in value.split(","):
        display, addr = parseaddr(chunk)
        token = addr or display or chunk.strip()
        if token:
            parts.append(token)
    return parts


def _as_dict(data: Any) -> dict[str, Any]:
    return data if isinstance(data, dict) else {}


class GmailClient:
    def __init__(self, request: RequestFn) -> None:
        self.request = request

    def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        data, _headers = self.request("GET", endpoint, params)
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            err = data["error"]
            message = str(err.get("message") or err.get("status") or "error")
            raise GmailAPIError(message, status=int(err.get("code") or 0) or None)
        return _as_dict(data)


def fetch_gmail_docs(
    *,
    after: datetime,
    request: RequestFn,
) -> list[CanonicalDoc]:
    client = GmailClient(request)
    profile = client.get("/gmail/v1/users/me/profile")
    mailbox = str(profile.get("emailAddress") or "me")
    after_day = after.astimezone(timezone.utc).strftime("%Y/%m/%d")
    query = f"-in:spam -in:trash after:{after_day}"

    stubs: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"q": query, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        listed = client.get("/gmail/v1/users/me/messages", **params)
        stubs.extend(
            item
            for item in (listed.get("messages") or [])
            if isinstance(item, dict) and item.get("id")
        )
        page_token = str(listed.get("nextPageToken") or "") or None
        if not page_token:
            break

    raws: list[dict[str, Any]] = []
    for stub in stubs:
        message_id = str(stub["id"])
        try:
            message = client.get(
                f"/gmail/v1/users/me/messages/{message_id}",
                format="full",
            )
        except GmailAPIError as exc:
            if exc.status in {404, 410}:
                continue
            raise
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        headers = _header_map(payload)
        from_raw = headers.get("from") or ""
        _display, from_addr = parseaddr(from_raw)
        raws.append(
            {
                "id": message.get("id") or message_id,
                "threadId": message.get("threadId") or message_id,
                "subject": headers.get("subject") or "(no subject)",
                "from": from_addr or from_raw or None,
                "to": _split_addresses(headers.get("to") or ""),
                "cc": _split_addresses(headers.get("cc") or ""),
                "labels": message.get("labelIds") or [],
                "internalDate": message.get("internalDate"),
                "body": gmail_plain_body(payload),
                "mailbox": mailbox,
                "url": (
                    f"https://mail.google.com/mail/u/0/#all/{message.get('threadId')}"
                    if message.get("threadId")
                    else None
                ),
            }
        )
    return adapt_many(GMAIL, raws)


__all__ = ["GmailAPIError", "GmailClient", "fetch_gmail_docs", "gmail_plain_body"]
