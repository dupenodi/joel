"""LLM-free company profile seed: crawl a website the operator typed.

Same-origin only. Pulls homepage, llms.txt, sitemap URLs, and links
discovered on fetched pages (e.g. /docs, /hack/hydra). No LLM, no
third-party search. Soft-fails when egress is blocked or
JOEL_ALLOW_WEB_FETCH=0 (air-gapped OSS).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlparse, urlunparse

import requests

MAX_PAGES = 12
MAX_BYTES_PER_PAGE = 200_000
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = 12
TOTAL_BUDGET_SECONDS = 45
ABOUT_CHAR_CAP = 8_000
PAGE_CHAR_CAP = 2_500
USER_AGENT = "joel-company-research/1.0 (+https://meetjoel.xyz; self-host ok)"

SEED_PATHS = (
    "/llms.txt",
    "/llms-full.txt",
    "/sitemap.xml",
    "/about",
    "/about-us",
    "/product",
    "/products",
    "/docs",
    "/documentation",
    "/pricing",
)

_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "iframe"})
_HREF_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


class ResearchError(Exception):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class FetchedPage:
    url: str
    title: str
    text: str
    kind: str  # html | text | llms | sitemap


@dataclass
class ResearchResult:
    start_url: str
    about: str
    sources: list[dict[str, str]] = field(default_factory=list)
    pages_fetched: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_url": self.start_url,
            "about": self.about,
            "sources": self.sources,
            "pages_fetched": self.pages_fetched,
            "warnings": self.warnings,
        }


def web_fetch_allowed() -> bool:
    raw = os.getenv("JOEL_ALLOW_WEB_FETCH", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def normalize_start_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ResearchError("Enter a website URL")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ResearchError("URL must be http or https")
    if not parsed.hostname:
        raise ResearchError("URL needs a host")
    # Drop fragment; keep path if operator pointed at a docs page.
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, ""))


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _same_site(host: str, other: str) -> bool:
    a = (host or "").lower().rstrip(".")
    b = (other or "").lower().rstrip(".")
    if not a or not b:
        return False
    if a == b:
        return True
    if a.startswith("www.") and a[4:] == b:
        return True
    if b.startswith("www.") and b[4:] == a:
        return True
    return False


def assert_public_url(url: str) -> None:
    """Reject non-http(s) and literal/private hosts (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ResearchError("URL must be http or https")
    host = parsed.hostname
    if not host:
        raise ResearchError("URL needs a host")
    if host.lower() in {"localhost", "metadata.google.internal"}:
        raise ResearchError("That host isn't allowed")
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise ResearchError("That host isn't allowed")
        return
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ResearchError(f"Couldn't resolve {host}") from exc
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise ResearchError("That host isn't allowed")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description = ""
        self.text_parts: list[str] = []
        self.hrefs: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._capture = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}
        if name in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if name == "title":
            self._in_title = True
        if name == "meta":
            prop = (attr.get("name") or attr.get("property") or "").lower()
            if prop in {"description", "og:description"} and not self.meta_description:
                self.meta_description = attr.get("content", "").strip()
        if name == "a":
            href = attr.get("href", "").strip()
            if href:
                self.hrefs.append(href)
        if name in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "section"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        chunk = data.strip()
        if not chunk:
            return
        if self._in_title:
            self.title_parts.append(chunk)
        else:
            self.text_parts.append(chunk)


def html_to_text(html: str) -> tuple[str, str, str, list[str]]:
    """Returns (title, meta_description, body_text, hrefs)."""
    parser = _PageParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Malformed HTML still often yields partial text.
        pass
    title = " ".join(parser.title_parts).strip()
    body = re.sub(r"[ \t]+", " ", " ".join(parser.text_parts))
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, parser.meta_description, body, parser.hrefs


def _strip_url(url: str) -> str:
    parsed = urlparse(url)
    # Drop query noise for dedupe except on the start URL path identity.
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", "", ""))


def extract_urls_from_text(text: str, *, base: str, site_host: str) -> list[str]:
    found: list[str] = []
    for match in _HREF_RE.findall(text or ""):
        cleaned = match.rstrip(".,);]")
        absolute = urljoin(base, cleaned)
        if _same_site(site_host, _hostname(absolute)):
            found.append(_strip_url(absolute))
    return found


def parse_sitemap_urls(xml_text: str, *, site_host: str) -> list[str]:
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return urls
    # Handle default and prefixed namespaces by localname.
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag != "loc" or not (el.text or "").strip():
            continue
        loc = el.text.strip()
        if _same_site(site_host, _hostname(loc)):
            urls.append(_strip_url(loc))
    return urls


HttpGet = Callable[[str], tuple[int, str, bytes, str]]


def _default_http_get(url: str) -> tuple[int, str, bytes, str]:
    """Returns (status, final_url, body, content_type). Manual redirects."""
    current = url
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(current)
        response = session.get(
            current,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location") or ""
            response.close()
            if not location:
                break
            current = urljoin(current, location)
            continue
        # Cap body size
        chunks: list[bytes] = []
        total = 0
        for block in response.iter_content(8192):
            if not block:
                continue
            total += len(block)
            if total > MAX_BYTES_PER_PAGE:
                chunks.append(block[: max(0, MAX_BYTES_PER_PAGE - (total - len(block)))])
                break
            chunks.append(block)
        body = b"".join(chunks)
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        final = str(response.url or current)
        status = int(response.status_code)
        response.close()
        return status, final, body, content_type
    raise ResearchError("Too many redirects")


def research_website(
    raw_url: str,
    *,
    http_get: HttpGet | None = None,
) -> ResearchResult:
    if not web_fetch_allowed():
        raise ResearchError(
            "Website research is disabled (JOEL_ALLOW_WEB_FETCH=0).",
            status=403,
        )

    start = normalize_start_url(raw_url)
    assert_public_url(start)
    site_host = _hostname(start)
    getter = http_get or _default_http_get

    queued: list[str] = []
    seen: set[str] = set()
    pages: list[FetchedPage] = []
    warnings: list[str] = []

    def enqueue(url: str) -> None:
        cleaned = _strip_url(url)
        host = _hostname(cleaned)
        if not _same_site(site_host, host):
            return
        path = urlparse(cleaned).path.lower()
        if any(path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".zip", ".css", ".js", ".woff", ".woff2")):
            return
        if cleaned in seen:
            return
        seen.add(cleaned)
        queued.append(cleaned)

    enqueue(start)
    # Seed common paths from origin root (not from a deep start path).
    origin = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
    for path in SEED_PATHS:
        enqueue(urljoin(origin + "/", path.lstrip("/")))

    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS

    while queued and len(pages) < MAX_PAGES:
        if time.monotonic() > deadline:
            warnings.append("Stopped early — time budget.")
            break
        url = queued.pop(0)
        try:
            status, final_url, body, content_type = getter(url)
        except ResearchError as err:
            if url == start or urlparse(url).path in {"/", ""}:
                raise
            warnings.append(f"Skipped {url}: {err}")
            continue
        except requests.RequestException as exc:
            if url == _strip_url(start):
                raise ResearchError(f"Couldn't fetch {url}: {exc}") from exc
            warnings.append(f"Skipped {url}: network error")
            continue

        final_host = _hostname(final_url)
        if not _same_site(site_host, final_host):
            warnings.append(f"Skipped redirect off-site from {url}")
            continue
        if status >= 400:
            if url == _strip_url(start):
                raise ResearchError(f"Site returned HTTP {status}")
            continue

        # Decode
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("utf-8", errors="replace")

        path_l = urlparse(final_url).path.lower()
        if path_l.endswith("sitemap.xml") or (
            "xml" in content_type and "<urlset" in text[:2000].lower()
        ):
            for loc in parse_sitemap_urls(text, site_host=site_host):
                enqueue(loc)
            pages.append(FetchedPage(url=final_url, title="sitemap", text="", kind="sitemap"))
            continue

        if path_l.endswith("llms.txt") or path_l.endswith("llms-full.txt") or content_type.startswith("text/plain"):
            kind = "llms" if "llms" in path_l else "text"
            for link in extract_urls_from_text(text, base=final_url, site_host=site_host):
                enqueue(link)
            pages.append(
                FetchedPage(
                    url=final_url,
                    title=path_l.rsplit("/", 1)[-1] or "text",
                    text=text.strip()[: PAGE_CHAR_CAP * 2],
                    kind=kind,
                )
            )
            continue

        if "html" in content_type or text.lstrip()[:32].lower().startswith("<!doctype") or "<html" in text[:500].lower():
            title, meta, body_text, hrefs = html_to_text(text)
            for href in hrefs:
                absolute = urljoin(final_url, href)
                if _same_site(site_host, _hostname(absolute)):
                    enqueue(absolute)
            combined = body_text
            if meta and meta not in combined[:500]:
                combined = f"{meta}\n\n{combined}"
            pages.append(
                FetchedPage(
                    url=final_url,
                    title=title or urlparse(final_url).path or final_url,
                    text=combined[: PAGE_CHAR_CAP * 2],
                    kind="html",
                )
            )
            continue

        # Other text-ish
        if content_type.startswith("text/") or not content_type:
            pages.append(
                FetchedPage(
                    url=final_url,
                    title=urlparse(final_url).path or final_url,
                    text=text.strip()[: PAGE_CHAR_CAP * 2],
                    kind="text",
                )
            )

    content_pages = [p for p in pages if p.kind != "sitemap" and p.text.strip()]
    if not content_pages:
        raise ResearchError("Nothing readable at that URL")

    about = _build_about(content_pages)
    sources = [{"url": p.url, "title": p.title, "kind": p.kind} for p in content_pages]
    return ResearchResult(
        start_url=start,
        about=about,
        sources=sources,
        pages_fetched=len(content_pages),
        warnings=warnings,
    )


def _build_about(pages: list[FetchedPage]) -> str:
    # Prefer llms.txt, then the start-ish html page, then the rest.
    ordered = sorted(
        pages,
        key=lambda p: (
            0 if p.kind == "llms" else 1 if p.kind == "html" else 2,
            len(p.url),
        ),
    )
    parts: list[str] = []
    used = 0
    for page in ordered:
        chunk = page.text.strip()
        if not chunk:
            continue
        header = f"## {page.title}\nSource: {page.url}\n\n"
        body = chunk[:PAGE_CHAR_CAP].strip()
        block = header + body
        if used + len(block) > ABOUT_CHAR_CAP:
            remain = ABOUT_CHAR_CAP - used
            if remain < 200:
                break
            block = block[:remain].rstrip() + "\n…"
            parts.append(block)
            break
        parts.append(block)
        used += len(block) + 2
    return "\n\n".join(parts).strip()


__all__ = [
    "ABOUT_CHAR_CAP",
    "MAX_PAGES",
    "FetchedPage",
    "ResearchError",
    "ResearchResult",
    "assert_public_url",
    "extract_urls_from_text",
    "html_to_text",
    "normalize_start_url",
    "parse_sitemap_urls",
    "research_website",
    "web_fetch_allowed",
]
