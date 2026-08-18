"""Jira fetcher via Composio tools (generic REST proxy returns 401)."""

from __future__ import annotations

from typing import Any

from joel.adapters import adapt_many
from joel.adapters.manifests import JIRA_COMMENT, JIRA_ISSUE
from joel.connectors.http import as_dict, as_list, tool_request
from joel.models import CanonicalDoc


def fetch_jira_docs(
    *,
    since: str,
    composio: Any,
    account_id: str,
) -> list[CanonicalDoc]:
    day = since[:10] if since else "1970-01-01"
    jql = f'updated >= "{day}" ORDER BY updated DESC'

    issues_raw: list[dict[str, Any]] = []
    comments_raw: list[dict[str, Any]] = []
    next_page_token: str | None = None

    while len(issues_raw) < 250:
        args: dict[str, Any] = {
            "jql": jql,
            "max_results": min(100, 250 - len(issues_raw)),
        }
        if next_page_token:
            args["next_page_token"] = next_page_token
        payload = tool_request(composio, account_id, "JIRA_SEARCH_ISSUES", args)
        for issue in as_list(payload, "issues"):
            key = str(issue.get("key") or "")
            if not key:
                continue
            project = as_dict(issue.get("project"))
            status = as_dict(issue.get("status"))
            priority = as_dict(issue.get("priority"))
            assignee = as_dict(issue.get("assignee"))
            reporter = as_dict(issue.get("reporter"))
            issues_raw.append(
                {
                    "key": key,
                    "summary": issue.get("summary"),
                    "description": issue.get("description"),
                    "body": issue.get("description") or issue.get("summary"),
                    "created": issue.get("created"),
                    "status": status.get("name"),
                    "priority": priority.get("name"),
                    "assignee": assignee.get("display_name")
                    or assignee.get("email_address"),
                    "project": project.get("key") or project.get("name"),
                    "author": reporter.get("display_name")
                    or reporter.get("email_address"),
                    "url": issue.get("browser_url"),
                }
            )
            comments = tool_request(
                composio,
                account_id,
                "JIRA_LIST_ISSUE_COMMENTS",
                {"issue_id_or_key": key},
            )
            for comment in as_list(comments, "comments"):
                author = as_dict(comment.get("author"))
                comments_raw.append(
                    {
                        "id": comment.get("id"),
                        "body": comment.get("body"),
                        "created": comment.get("created"),
                        "author": author.get("display_name")
                        or author.get("email_address"),
                        "key": key,
                        "project": project.get("key") or project.get("name"),
                        "url": comment.get("self"),
                    }
                )
        next_page_token = str(payload.get("next_page_token") or "") or None
        if not next_page_token:
            break

    docs = adapt_many(JIRA_ISSUE, issues_raw)
    docs.extend(adapt_many(JIRA_COMMENT, comments_raw))
    return docs
