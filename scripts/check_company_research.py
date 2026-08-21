"""Company website research — LLM-free same-origin crawl."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.company_research import (  # noqa: E402
    ResearchError,
    assert_public_url,
    html_to_text,
    normalize_start_url,
    parse_sitemap_urls,
    research_website,
    web_fetch_allowed,
)


def check_normalize_and_ssrf() -> None:
    assert normalize_start_url("hydradb.com") == "https://hydradb.com/"
    assert normalize_start_url("https://HydraDB.com/docs").startswith("https://hydradb.com/docs")
    try:
        normalize_start_url("")
        raise AssertionError("empty should fail")
    except ResearchError:
        pass
    try:
        assert_public_url("http://127.0.0.1/")
        raise AssertionError("loopback should fail")
    except ResearchError:
        pass
    try:
        assert_public_url("http://localhost/x")
        raise AssertionError("localhost should fail")
    except ResearchError:
        pass
    print("ok  cr.1: normalize + SSRF rejects private/loopback")


def check_html_and_sitemap() -> None:
    title, meta, body, hrefs = html_to_text(
        """<!doctype html><html><head>
        <title>HydraDB</title>
        <meta name="description" content="Graph memory for agents">
        </head><body>
        <script>evil()</script>
        <a href="/hack/hydra">Hack</a>
        <a href="https://other.com/x">Nope</a>
        <p>We build graph memory.</p>
        </body></html>"""
    )
    assert title == "HydraDB"
    assert "Graph memory" in meta
    assert "evil" not in body
    assert "We build graph memory." in body
    assert any(h.endswith("/hack/hydra") or h == "/hack/hydra" for h in hrefs)

    locs = parse_sitemap_urls(
        """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://hydradb.com/docs/hydra</loc></url>
          <url><loc>https://evil.example/x</loc></url>
        </urlset>""",
        site_host="hydradb.com",
    )
    assert locs == ["https://hydradb.com/docs/hydra"]
    print("ok  cr.2: html_to_text strips scripts; sitemap stays same-host")


def check_research_fake_site() -> None:
    pages = {
        "https://acme.test/": (
            200,
            "https://acme.test/",
            b"""<!doctype html><html><head><title>Acme</title>
            <meta name="description" content="Widgets for teams"></head>
            <body><a href="/docs/guide">Docs</a><a href="/hack/acme">Hack</a>
            <p>Acme builds widgets.</p></body></html>""",
            "text/html",
        ),
        "https://acme.test/llms.txt": (
            200,
            "https://acme.test/llms.txt",
            b"# Acme\n\nWe make widgets.\nhttps://acme.test/docs/guide\n",
            "text/plain",
        ),
        "https://acme.test/docs/guide": (
            200,
            "https://acme.test/docs/guide",
            b"""<!doctype html><html><head><title>Guide</title></head>
            <body><h1>Guide</h1><p>How to use Acme widgets day to day.</p></body></html>""",
            "text/html",
        ),
        "https://acme.test/hack/acme": (
            200,
            "https://acme.test/hack/acme",
            b"""<!doctype html><html><head><title>Hack</title></head>
            <body><p>Weekend hack notes for Acme.</p></body></html>""",
            "text/html",
        ),
    }

    def fake_get(url: str) -> tuple[int, str, bytes, str]:
        # Seeds may 404
        key = url.rstrip("/") or url
        # normalize lookup
        for candidate in (url, url.rstrip("/"), url + "/"):
            if candidate in pages:
                return pages[candidate]
        if url.endswith("/sitemap.xml") or url.endswith("/about") or url.endswith("/product"):
            return 404, url, b"missing", "text/plain"
        raise ResearchError(f"unexpected fetch {url}")

    # Bypass DNS SSRF for .test — inject by monkeypatching assert on research path:
    # research_website calls assert_public_url which will try to resolve acme.test.
    # Use a host that resolves publicly... better: patch assert_public_url in module.
    import joel.company_research as cr

    original = cr.assert_public_url
    cr.assert_public_url = lambda url: None  # type: ignore[assignment]
    try:
        result = research_website("https://acme.test/", http_get=fake_get)
    finally:
        cr.assert_public_url = original

    assert result.pages_fetched >= 3, result.as_dict()
    assert "widgets" in result.about.lower()
    urls = {s["url"] for s in result.sources}
    assert any("/docs/guide" in u for u in urls)
    assert any("/hack/acme" in u for u in urls)
    assert any("llms.txt" in u for u in urls)
    print("ok  cr.3: research follows home links + llms.txt (no LLM)")


def check_kill_switch() -> None:
    prev = os.environ.get("JOEL_ALLOW_WEB_FETCH")
    os.environ["JOEL_ALLOW_WEB_FETCH"] = "0"
    try:
        assert web_fetch_allowed() is False
        try:
            research_website("https://example.com")
            raise AssertionError("should be disabled")
        except ResearchError as err:
            assert err.status == 403
    finally:
        if prev is None:
            os.environ.pop("JOEL_ALLOW_WEB_FETCH", None)
        else:
            os.environ["JOEL_ALLOW_WEB_FETCH"] = prev
    print("ok  cr.4: JOEL_ALLOW_WEB_FETCH=0 blocks research")


def main() -> None:
    check_normalize_and_ssrf()
    check_html_and_sitemap()
    check_research_fake_site()
    check_kill_switch()
    print("\nCompany research: all automated checks passed.")


if __name__ == "__main__":
    main()
