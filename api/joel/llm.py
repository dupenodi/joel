"""Generic JSON-mode LLM caller shared by every prompted stage (§18: distill,
extract, resolve, plan, rerank, answer). One call shape, one repair retry on
a parse failure, then a loud raise — callers decide what "give up" means for
their own stage (skip the thread, fall back to lexical-only, etc).

Mirrors the `RequestFn` seam in `connectors/http.py`: production binds a real
HTTP call via `make_openrouter_caller`, tests inject a fake `LLMCallFn`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Callable, Iterator

from openai import OpenAI, OpenAIError

LLMCallFn = Callable[[str, str, str], str]  # (stage, system_prompt, user_prompt) -> raw text
# (stage, system_prompt, user_prompt) -> content deltas
LLMStreamFn = Callable[[str, str, str], Iterator[str]]


class LLMError(RuntimeError):
    pass


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def strip_fences(text: str) -> str:
    """Strip markdown code fences an LLM added despite being told not to."""
    return _JSON_FENCE.sub("", text).strip()


def parse_json_response(text: str) -> Any:
    return json.loads(strip_fences(text))


@lru_cache(maxsize=8)
def _client(base_url: str, api_key: str, timeout: float) -> OpenAI:
    """One client per (endpoint, key, timeout). The SDK holds a connection
    pool, so rebuilding it per call would throw away keep-alive on every
    stage of every question."""
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2)


def _guard(base_url: str, api_key: str, model: str) -> None:
    if not api_key:
        raise LLMError("LLM API key not set — add one in Settings")
    if not model:
        raise LLMError("no model configured for this stage")


def openrouter_call(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 60,
) -> str:
    """One OpenAI-compatible chat completion call. Returns raw text content.

    Every failure mode raises `LLMError`, including transport-level ones,
    and never lets the SDK's own exception types escape. Every caller in
    this codebase (`plan_query`, `rerank_candidates`, `synthesize_answer`,
    `distill_thread`) only catches `LLMError` and degrades gracefully
    (fallback plan, empty rerank, "absent" answer); a raw `APIError`
    slipping through instead crashes the whole SSE stream mid-response on
    a transient network blip, which is exactly the kind of outage this is
    supposed to degrade honestly through, not crash on.
    """
    _guard(base_url, api_key, model)
    try:
        resp = _client(base_url.rstrip("/"), api_key, float(timeout)).chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except OpenAIError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc
    try:
        return str(resp.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected LLM response shape: {resp!r}"[:500]) from exc


def openrouter_stream(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 120,
) -> Iterator[str]:
    """Same call as `openrouter_call`, but yields content deltas as the model
    produces them instead of returning once it is done.

    Failure modes match `openrouter_call` exactly -- every one raises
    `LLMError` -- because callers degrade on `LLMError` and a transport
    exception escaping mid-stream would kill the SSE response rather than
    abstain honestly. A chunk carrying no content delta (role-only openers,
    keepalives, usage trailers) is skipped rather than fatal."""
    _guard(base_url, api_key, model)
    try:
        stream = _client(base_url.rstrip("/"), api_key, float(timeout)).chat.completions.create(
            model=model,
            temperature=0,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is not None and delta.content:
                yield str(delta.content)
    except OpenAIError as exc:
        raise LLMError(f"LLM stream broke: {exc}") from exc


class JSONFieldStreamer:
    """Pulls one top-level string field out of a JSON document as it streams.

    The answer stage asks for a JSON object (answer, citations, status,
    conflicts) because the post-gate has to inspect the citations before the
    answer is trusted. That structure is why the endpoint used to wait for
    the whole completion and then fake tokens by splitting the finished text
    on spaces -- the user saw one burst after the full model latency.

    Feeding the raw stream through here recovers real token-by-token
    delivery without giving up the structured response: characters inside
    the target field are emitted as they arrive, everything else is
    buffered, and the caller still parses the complete JSON at the end.
    Escapes are decoded so the UI never sees a literal `\\n` or a half-
    written `\\u` sequence.
    """

    def __init__(self, field: str = "answer") -> None:
        self._needle = f'"{field}"'
        self.raw = ""
        self._state = "seek"  # seek -> colon -> inside -> done
        self._escape = False
        self._unicode = ""

    def feed(self, chunk: str) -> str:
        """Absorb a delta; return the decoded text of the target field that
        became available in it (empty string when nothing did)."""
        out: list[str] = []
        for ch in chunk:
            self.raw += ch
            if self._state == "done":
                continue
            if self._state == "seek":
                if self.raw.endswith(self._needle):
                    self._state = "colon"
                continue
            if self._state == "colon":
                # Between the key and its value there may be whitespace and
                # the colon; the opening quote starts the value.
                if ch == '"':
                    self._state = "inside"
                continue
            # inside the string value
            if self._unicode is not None and len(self._unicode) > 0:
                self._unicode += ch
                if len(self._unicode) == 5:  # "u" + 4 hex digits
                    try:
                        out.append(chr(int(self._unicode[1:], 16)))
                    except ValueError:
                        pass
                    self._unicode = ""
                continue
            if self._escape:
                self._escape = False
                if ch == "u":
                    self._unicode = "u"
                else:
                    out.append(
                        {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}.get(ch, ch)
                    )
                continue
            if ch == "\\":
                self._escape = True
                continue
            if ch == '"':
                self._state = "done"
                continue
            out.append(ch)
        return "".join(out)


def call_json(call: LLMCallFn, stage: str, system_prompt: str, user_prompt: str) -> Any:
    """Call an LLM and parse ONE JSON value out of the response.

    One repair retry on a parse failure, telling the model exactly what
    broke and showing it its own broken output, then raises `LLMError`.
    """
    raw = call(stage, system_prompt, user_prompt)
    try:
        return parse_json_response(raw)
    except json.JSONDecodeError as exc:
        repair_prompt = (
            f"{user_prompt}\n\n---\nYour previous response could not be parsed as "
            f"JSON: {exc}. Respond again with ONLY the corrected JSON. No prose, "
            f"no markdown fences.\n\nYour previous response was:\n{raw}"
        )
        raw2 = call(stage, system_prompt, repair_prompt)
        try:
            return parse_json_response(raw2)
        except json.JSONDecodeError as exc2:
            raise LLMError(f"[{stage}] LLM returned unparseable JSON twice: {exc2}") from exc2


def make_openrouter_caller(settings: dict[str, str]) -> LLMCallFn:
    """Bind an `LLMCallFn` to the org's stored settings (`llm_base_url`,
    `llm_api_key`, `llm_model_{stage}`). Model is resolved per-stage so
    /settings can repoint one stage at a cheaper model without a restart.
    """
    base_url = settings.get("llm_base_url") or "https://openrouter.ai/api/v1"
    api_key = settings.get("llm_api_key") or ""

    def _call(stage: str, system_prompt: str, user_prompt: str) -> str:
        model = settings.get(f"llm_model_{stage}") or ""
        return openrouter_call(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    return _call


def make_openrouter_streamer(settings: dict[str, str]) -> LLMStreamFn:
    """Streaming counterpart of `make_openrouter_caller`, same per-stage
    model resolution."""
    base_url = settings.get("llm_base_url") or "https://openrouter.ai/api/v1"
    api_key = settings.get("llm_api_key") or ""

    def _stream(stage: str, system_prompt: str, user_prompt: str) -> Iterator[str]:
        model = settings.get(f"llm_model_{stage}") or ""
        return openrouter_stream(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    return _stream


__all__ = [
    "LLMCallFn",
    "LLMStreamFn",
    "LLMError",
    "JSONFieldStreamer",
    "strip_fences",
    "parse_json_response",
    "openrouter_call",
    "openrouter_stream",
    "call_json",
    "make_openrouter_caller",
    "make_openrouter_streamer",
]
