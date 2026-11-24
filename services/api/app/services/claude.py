"""Claude (Anthropic) client: the in-app help assistant and edit planning."""

from __future__ import annotations

import json
from typing import Any, Iterator

import anthropic

from ..config import settings
from .ai_keys import AiError, require_key

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens (input, output) for the spend meter. Unknown models -> 0.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.1, 0.5),
}


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=require_key("anthropic"))


def estimate_cost(usage: Any) -> float:
    """Rough cost of one response from its usage block (cache reads at 5%)."""
    price_in, price_out = PRICES.get(settings.anthropic_model, (0.0, 0.0))
    fresh = (getattr(usage, "input_tokens", 0) or 0) + 1.25 * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return (fresh * price_in + cached * price_in * 0.05 + out * price_out) / 1_000_000


def _explain(exc: Exception) -> AiError:
    if isinstance(exc, anthropic.AuthenticationError):
        return AiError("Claude rejected the Anthropic API key — check it on the AI settings page.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AiError("This Anthropic API key is not allowed to use the configured Claude model.")
    if isinstance(exc, anthropic.NotFoundError):
        return AiError(f"Claude model '{settings.anthropic_model}' was not found — set ANTHROPIC_MODEL to one your key can use.")
    if isinstance(exc, anthropic.RateLimitError):
        return AiError("Claude is rate-limiting this key right now — wait a moment and try again.")
    if isinstance(exc, anthropic.APIStatusError):
        return AiError(f"Claude request failed ({exc.status_code}): {exc.message}")
    if isinstance(exc, anthropic.APIConnectionError):
        return AiError("Could not reach the Claude API — check the server's internet connection.")
    return AiError(f"Claude request failed: {exc}")


def plan_json(system: str, user: str) -> tuple[dict[str, Any], float]:
    """Ask Claude for one JSON object. Returns (object, estimated cost in USD)."""
    try:
        response = _client().beta.messages.create(
            model=settings.anthropic_model,
            max_tokens=8000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError as exc:
        raise _explain(exc) from exc
    if response.stop_reason == "refusal":
        raise AiError("Claude declined to plan this edit.")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        parsed = json.loads(text[start : end + 1]) if start >= 0 and end > start else None
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        raise AiError("Claude did not return a valid edit plan — try again.")
    return parsed, estimate_cost(response.usage)


def stream_chat(system: list[dict[str, Any]], messages: list[dict[str, str]]) -> Iterator[dict[str, Any]]:
    """Stream a chat reply as events: {"text": ...}* then {"done": cost} or {"error": ...}."""
    try:
        with _client().beta.messages.stream(
            model=settings.anthropic_model,
            max_tokens=8000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "low"},
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield {"text": text}
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield {"error": "I can't help with that one. Ask me anything about using Pro Clipper."}
            return
        yield {"done": estimate_cost(final.usage)}
    except AiError as exc:
        yield {"error": str(exc)}
    except anthropic.APIError as exc:
        yield {"error": str(_explain(exc))}
