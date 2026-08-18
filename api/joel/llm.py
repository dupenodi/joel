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
from typing import Any, Callable

import requests

LLMCallFn = Callable[[str, str, str], str]  # (stage, system_prompt, user_prompt) -> raw text


class LLMError(RuntimeError):
    pass


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def strip_fences(text: str) -> str:
    """Strip markdown code fences an LLM added despite being told not to."""
    return _JSON_FENCE.sub("", text).strip()


def parse_json_response(text: str) -> Any:
    return json.loads(strip_fences(text))


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

    Every failure mode raises `LLMError` — including raw network exceptions
    (`requests.RequestException`: DNS, timeout, connection reset, TLS) —
    never lets `requests`' own exception types escape. Every caller in this
    codebase (`plan_query`, `rerank_candidates`, `synthesize_answer`,
    `distill_thread`) only catches `LLMError` and degrades gracefully
    (fallback plan, empty rerank, "absent" answer); a raw `ConnectionError`
    slipping through instead crashes the whole SSE stream mid-response on
    a transient network blip, which is exactly the kind of outage this is
    supposed to degrade honestly through, not crash on."""
    if not api_key:
        raise LLMError("LLM API key not set — add one in Settings")
    if not model:
        raise LLMError("no model configured for this stage")
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise LLMError(f"LLM API error: HTTP {resp.status_code} {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError as exc:  # requests raises simplejson/json's JSONDecodeError, a ValueError subclass
        raise LLMError(f"LLM response was not valid JSON: {resp.text[:300]!r}") from exc
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected LLM response shape: {data!r}"[:500]) from exc


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


__all__ = [
    "LLMCallFn",
    "LLMError",
    "strip_fences",
    "parse_json_response",
    "openrouter_call",
    "call_json",
    "make_openrouter_caller",
]
