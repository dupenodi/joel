"""§13's third surface, after web and Slack: a minimal MCP server exposing
one tool, "ask". Authenticated by API key (`joel_sk_…`) or OAuth access
token (`joel_at_…`), both mapping to exactly one person's normal Actor --
`AskContext` is built server-side from that Actor, never from anything
the MCP client sends, same discipline `/api/ask` already applies to the
session cookie.

Scope, honestly: `ask` reuses the exact same `answer_question` retrieval
and synthesis pipeline `/api/ask` uses, but not (yet) the follow-up
rewriting or live-lookup layers wrapped around it there -- each call is
a standalone question, answered from memory alone. Extending those is a
later increment, not a redesign, same "N of M implemented" shape as
CP10's live lookup.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from mcp.server.mcpserver import MCPServer

from joel import identity

_actor_ctx: contextvars.ContextVar[identity.Actor | None] = contextvars.ContextVar(
    "mcp_actor", default=None
)

AskFn = Callable[[identity.Actor, str], Awaitable[dict[str, Any]]]
ActorResolver = Callable[[str], identity.Actor | None]


class _BearerAuthASGI:
    """Wraps the MCP Streamable HTTP app with joel's own bearer auth,
    entirely outside the SDK's OAuth-oriented `token_verifier`/
    `AuthSettings` machinery for the *stream* path — so streaming
    responses pass through unbuffered. Accepts API keys (`joel_sk_`)
    and OAuth access tokens (`joel_at_`). Unauthenticated MCP calls
    get RFC 9728 `WWW-Authenticate` pointing at protected-resource
    metadata so Cursor can start the sign-in flow."""

    def __init__(
        self,
        app: Any,
        actor_resolver: ActorResolver,
        resource_metadata_url: str = "",
    ) -> None:
        self.app = app
        self._resolve = actor_resolver
        self._resource_metadata_url = resource_metadata_url

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        actor = self._resolve(token) if token else None
        if actor is None:
            www = 'Bearer error="invalid_token", error_description="Authentication required"'
            if self._resource_metadata_url:
                www += f', resource_metadata="{self._resource_metadata_url}"'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", www.encode("latin-1")),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"error":"missing or invalid token"}',
                }
            )
            return
        reset = _actor_ctx.set(actor)
        try:
            await self.app(scope, receive, send)
        finally:
            _actor_ctx.reset(reset)


@dataclass
class McpMount:
    """`asgi_app` is what gets `app.mount()`ed. `session_manager` is the
    Streamable HTTP transport's task-group owner -- FastAPI's `Mount()`
    does NOT chain a sub-app's `lifespan` into the outer app's, so its
    task group is never started/stopped unless something does that
    explicitly. `run_forever()` is that something: enter it from the
    outer app's own startup hook, exit it from shutdown."""

    asgi_app: Any
    session_manager: Any

    def run_forever(self) -> AsyncIterator[None]:
        return self.session_manager.run()


def build_mcp_app(
    *,
    ask_fn: AskFn,
    actor_resolver: ActorResolver,
    resource_metadata_url: str = "",
) -> McpMount:
    server = MCPServer(
        name="joel",
        version="1.0",
        instructions=(
            "Ask joel's company memory a question. Answers are grounded in the "
            "company's own ingested data, cite their sources, and honestly say "
            "'not in memory' rather than guessing. Scoped to your own workspace "
            "permissions -- you'll never see something you couldn't see in the app."
        ),
    )

    @server.tool(
        description=(
            "Ask joel's company memory a question. Returns a grounded, cited "
            "answer or an honest 'not in memory' -- never a guess."
        )
    )
    async def ask(question: str) -> str:
        actor = _actor_ctx.get()
        if actor is None:
            return "Not authenticated."
        result = await ask_fn(actor, question)
        answer = str(result.get("answer") or "")
        citations = result.get("citations") or []
        lines = [
            f"- {c['title']} ({c['url']})" if c.get("url") else f"- {c['title']}"
            for c in citations
            if c.get("title")
        ]
        if lines:
            answer = f"{answer}\n\nSources:\n" + "\n".join(lines)
        return answer

    # streamable_http_path="/": this whole app is mounted at /mcp in the
    # outer FastAPI app already; the default '/mcp' here would otherwise
    # make the real reachable path /mcp/mcp.
    inner = server.streamable_http_app(streamable_http_path="/")
    session_manager = server.session_manager
    return McpMount(
        asgi_app=_BearerAuthASGI(
            inner, actor_resolver, resource_metadata_url=resource_metadata_url
        ),
        session_manager=session_manager,
    )


__all__ = ["McpMount", "build_mcp_app"]
