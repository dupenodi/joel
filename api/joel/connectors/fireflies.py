"""Fireflies fetcher via Composio tools (generic GraphQL proxy doubles the path)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from joel.adapters import adapt_many
from joel.adapters.manifests import FIREFLIES_CHUNK
from joel.connectors.http import as_dict, as_list, tool_request
from joel.models import CanonicalDoc


def fetch_fireflies_docs(
    *,
    after: datetime,
    composio: Any,
    account_id: str,
) -> list[CanonicalDoc]:
    payload = tool_request(
        composio,
        account_id,
        "FIREFLIES_GET_TRANSCRIPTS",
        {
            "limit": 30,
            "from_date": after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "include_sentences": True,
            "include_summary": True,
        },
    )
    transcripts = as_list(payload, "transcripts")
    raws: list[dict[str, Any]] = []
    for meeting in transcripts:
        meeting_id = str(meeting.get("id") or "")
        if not meeting_id:
            continue
        sentences = meeting.get("sentences") or []
        if not isinstance(sentences, list):
            sentences = []
        summary = as_dict(meeting.get("summary"))
        turns = [
            item
            for item in sentences
            if isinstance(item, dict) and (item.get("text") or item.get("raw_text"))
        ]
        if not turns:
            continue
        title = str(meeting.get("title") or "Meeting")
        host = str(meeting.get("host_email") or "")
        date_value = meeting.get("date")
        url = meeting.get("transcript_url") or meeting.get("url")
        chunk_size = 40
        for index in range(0, len(turns), chunk_size):
            chunk = turns[index : index + chunk_size]
            lines = []
            for turn in chunk:
                speaker = str(
                    turn.get("speaker") or turn.get("speaker_name") or "Speaker"
                )
                text = str(turn.get("text") or turn.get("raw_text") or "").strip()
                if text:
                    lines.append(f"{speaker}: {text}")
            raw: dict[str, Any] = {
                "id": f"{meeting_id}_c{index // chunk_size}",
                "thread_id": meeting_id,
                "title": title,
                "body": "\n".join(lines),
                "host": host,
                "date": date_value,
                "url": url,
            }
            if index == 0:
                overview = summary.get("overview")
                actions = summary.get("action_items")
                if overview:
                    raw["summary"] = overview
                if actions:
                    raw["action_items"] = actions
            raws.append(raw)
    return adapt_many(FIREFLIES_CHUNK, raws)
