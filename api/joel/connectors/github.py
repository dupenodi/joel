"""GitHub REST fetcher via an injected HTTP caller (Composio proxy in prod)."""

from __future__ import annotations

import base64
from typing import Any, Iterator
from urllib.parse import urlsplit

from joel.adapters import (
    GITHUB_CODE,
    GITHUB_ISSUE,
    GITHUB_ISSUE_COMMENT,
    GITHUB_PR,
    GITHUB_PR_REVIEW,
    adapt_many,
)
from joel.adapters.code_chunk import chunk_code, first_symbol
from joel.connectors.http import RequestFn
from joel.models import CanonicalDoc

MAX_REPOS = 80
MAX_CODE_REPOS = 8
MAX_CODE_FILES = 30
MAX_FILE_BYTES = 200_000
GITHUB_ACCEPT = "application/vnd.github+json"
_SKIP_DIRS = {
    "node_modules",
    "dist",
    "build",
    "vendor",
    ".git",
    "__pycache__",
    ".next",
    "coverage",
}
_SKIP_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
}
_CODE_EXT = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cs",
    ".php",
    ".md",
    ".sql",
    ".sh",
    ".toml",
    ".yml",
    ".yaml",
}


class GitHubAPIError(RuntimeError):
    def __init__(self, error: str, *, status: int | None = None) -> None:
        super().__init__(f"GitHub API error: {error}")
        self.error = error
        self.status = status


def _next_link(headers: dict[str, str]) -> str | None:
    link = headers.get("Link") or headers.get("link") or ""
    for part in link.split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start < 0 or end <= start:
            continue
        url = part[start + 1 : end]
        parsed = urlsplit(url)
        if parsed.path:
            return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
        return url
    return None


def _as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "data", "repos", "issues", "comments"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


class GitHubClient:
    def __init__(self, request: RequestFn) -> None:
        self.request = request

    def get(self, endpoint: str, **params: Any) -> tuple[Any, dict[str, str]]:
        data, headers = self.request("GET", endpoint, params)
        return data, headers

    def pages(self, endpoint: str, **params: Any) -> Iterator[list[dict[str, Any]]]:
        path = endpoint
        query = dict(params)
        query.setdefault("per_page", 100)
        while path:
            data, headers = self.get(path, **query)
            yield _as_list(data)
            nxt = _next_link(headers)
            path = nxt or ""
            query = {}

    def items(self, endpoint: str, **params: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            for page in self.pages(endpoint, **params):
                out.extend(page)
        except GitHubAPIError as exc:
            if exc.status in {404, 410}:
                return []
            raise
        return out


def _with_repo(raw: dict[str, Any], full_name: str) -> dict[str, Any]:
    out = dict(raw)
    out["repository"] = {"full_name": full_name}
    return out


def _number_from_url(url: Any, kind: str) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    marker = f"/{kind}/"
    if marker not in url:
        return None
    tail = url.rsplit(marker, 1)[-1]
    number = tail.split("#", 1)[0].split("?", 1)[0].strip("/")
    return number or None


def _skip_code_path(path: str) -> bool:
    parts = path.split("/")
    if any(part in _SKIP_DIRS for part in parts):
        return True
    name = parts[-1].lower() if parts else ""
    if name in _SKIP_NAMES:
        return True
    if "." not in name:
        return True
    ext = "." + name.rsplit(".", 1)[-1]
    return ext not in _CODE_EXT


def _decode_blob(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    encoding = str(data.get("encoding") or "")
    content = data.get("content")
    if encoding == "base64" and isinstance(content, str) and content:
        try:
            raw = base64.b64decode(content)
        except (ValueError, TypeError):
            return None
        if b"\x00" in raw[:1024]:
            return None
        return raw.decode("utf-8", "replace")
    if isinstance(content, str):
        return content
    return None


def _fetch_pr_reviews(
    client: GitHubClient,
    owner: str,
    name: str,
    full_name: str,
    pr_numbers: set[str],
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for number in pr_numbers:
        for review in client.items(f"/repos/{owner}/{name}/pulls/{number}/reviews"):
            review_id = review.get("id")
            if review_id is None:
                continue
            row = _with_repo(review, full_name)
            row["thread_key"] = f"pr_{full_name}#{number}"
            body = row.get("body")
            state = str(row.get("state") or "COMMENTED")
            if not isinstance(body, str) or len(body.strip()) < 20:
                row["body"] = (body.strip() + "\n" if isinstance(body, str) and body.strip() else "") + f"Review {state}."
            reviews.append(row)
    return reviews


def _fetch_repo_code(
    client: GitHubClient,
    owner: str,
    name: str,
    full_name: str,
    repo: dict[str, Any],
) -> list[dict[str, Any]]:
    branch = str(repo.get("default_branch") or "HEAD")
    try:
        tree, _headers = client.get(
            f"/repos/{owner}/{name}/git/trees/{branch}", recursive="1"
        )
    except GitHubAPIError as exc:
        if exc.status in {404, 409, 422}:
            return []
        raise
    entries = tree.get("tree") if isinstance(tree, dict) else None
    if not isinstance(entries, list):
        return []
    raws: list[dict[str, Any]] = []
    taken = 0
    for entry in entries:
        if taken >= MAX_CODE_FILES:
            break
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = str(entry.get("path") or "")
        sha = str(entry.get("sha") or "")
        if not path or not sha or _skip_code_path(path):
            continue
        try:
            size = int(entry.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size > MAX_FILE_BYTES:
            continue
        try:
            blob, _ = client.get(f"/repos/{owner}/{name}/git/blobs/{sha}")
        except GitHubAPIError as exc:
            if exc.status in {404, 403}:
                continue
            raise
        src = _decode_blob(blob)
        if not src:
            continue
        html = f"https://github.com/{full_name}/blob/{branch}/{path}"
        for index, chunk in enumerate(chunk_code(path, src)):
            raws.append(
                {
                    "_qualified_id": f"{full_name}:{path}:c{index}",
                    "body": chunk,
                    "title": f"{path} — {first_symbol(chunk, path)}",
                    "repository": {"full_name": full_name},
                    "html_url": html,
                }
            )
        taken += 1
    return raws


def fetch_github_docs(
    *,
    since: str | None = None,
    request: RequestFn,
) -> list[CanonicalDoc]:
    client = GitHubClient(request)
    repos = client.items(
        "/user/repos",
        sort="pushed",
        affiliation="owner,collaborator,organization_member",
    )
    kept_repos: list[dict[str, Any]] = []
    for repo in repos:
        if repo.get("fork") or repo.get("archived"):
            continue
        full_name = str(repo.get("full_name") or "")
        if not full_name or "/" not in full_name:
            continue
        kept_repos.append(repo)
        if len(kept_repos) >= MAX_REPOS:
            break

    issues_raw: list[dict[str, Any]] = []
    prs_raw: list[dict[str, Any]] = []
    comments_raw: list[dict[str, Any]] = []
    reviews_raw: list[dict[str, Any]] = []
    code_raw: list[dict[str, Any]] = []
    since_params = {"since": since} if since else {}
    code_repos = 0

    for repo in kept_repos:
        full_name = str(repo["full_name"])
        owner, name = full_name.split("/", 1)
        issue_params: dict[str, Any] = {
            "state": "all",
            "sort": "updated",
            **since_params,
        }
        listed = client.items(f"/repos/{owner}/{name}/issues", **issue_params)
        pr_numbers: set[str] = set()
        for item in listed:
            number = item.get("number")
            if number is None:
                continue
            payload = _with_repo(item, full_name)
            if isinstance(item.get("pull_request"), dict):
                payload["draft"] = bool(item.get("draft", False))
                payload["merged"] = bool(item.get("merged", False))
                prs_raw.append(payload)
                pr_numbers.add(str(number))
            else:
                issues_raw.append(payload)

        for comment in client.items(
            f"/repos/{owner}/{name}/issues/comments", **since_params
        ):
            number = _number_from_url(comment.get("issue_url") or comment.get("html_url"), "issues")
            if not number:
                continue
            row = _with_repo(comment, full_name)
            kind = "pr" if number in pr_numbers else "issue"
            row["thread_key"] = f"{kind}_{full_name}#{number}"
            comments_raw.append(row)
        for comment in client.items(
            f"/repos/{owner}/{name}/pulls/comments", **since_params
        ):
            number = _number_from_url(
                comment.get("pull_request_url") or comment.get("html_url"), "pulls"
            )
            if not number:
                continue
            row = _with_repo(comment, full_name)
            row["thread_key"] = f"pr_{full_name}#{number}"
            comments_raw.append(row)

        reviews_raw.extend(_fetch_pr_reviews(client, owner, name, full_name, pr_numbers))
        if code_repos < MAX_CODE_REPOS:
            files = _fetch_repo_code(client, owner, name, full_name, repo)
            if files:
                code_raw.extend(files)
                code_repos += 1

    docs: list[CanonicalDoc] = []
    docs.extend(adapt_many(GITHUB_ISSUE, issues_raw))
    docs.extend(adapt_many(GITHUB_PR, prs_raw))
    docs.extend(adapt_many(GITHUB_ISSUE_COMMENT, comments_raw))
    docs.extend(adapt_many(GITHUB_PR_REVIEW, reviews_raw))
    docs.extend(adapt_many(GITHUB_CODE, code_raw))
    return docs


def fetch_github_item(
    *, request: RequestFn, owner: str, repo: str, number: int
) -> CanonicalDoc | None:
    """§13.2 live mode: the CURRENT state of ONE issue/PR by number -- a
    single request, never `fetch_github_docs`'s full-account, every-repo
    scan. Returns `None` for a 404/410 (deleted, wrong number, no access)
    rather than raising, matching live lookup's "nothing found" shape."""
    client = GitHubClient(request)
    full_name = f"{owner}/{repo}"
    try:
        data, _headers = client.get(f"/repos/{full_name}/issues/{number}")
    except GitHubAPIError as exc:
        if exc.status in {404, 410}:
            return None
        raise
    if not isinstance(data, dict) or data.get("number") is None:
        return None
    payload = _with_repo(data, full_name)
    is_pr = isinstance(data.get("pull_request"), dict)
    if is_pr:
        payload["draft"] = bool(data.get("draft", False))
        payload["merged"] = bool(data.get("merged", False))
        docs = adapt_many(GITHUB_PR, [payload])
    else:
        docs = adapt_many(GITHUB_ISSUE, [payload])
    return docs[0] if docs else None


__all__ = [
    "GitHubAPIError",
    "GitHubClient",
    "fetch_github_docs",
    "fetch_github_item",
    "GITHUB_ACCEPT",
]
