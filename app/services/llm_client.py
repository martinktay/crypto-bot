"""Provider-agnostic LLM chat-completion client.

Supports three providers via the ``LLM_PROVIDER`` setting:

* ``openai``    — uses ``OPENAI_API_KEY`` and ``REASONING_MODEL`` by default.
* ``deepseek``  — DeepSeek's OpenAI-compatible endpoint at ``api.deepseek.com``.
* ``anthropic`` — Claude's native ``messages`` API.

If ``LLM_API_KEY`` is set it overrides ``OPENAI_API_KEY`` for chat. The
``LLM_BASE_URL`` and ``LLM_MODEL`` settings allow per-provider overrides
without code changes.

Embeddings deliberately stay on the OpenAI endpoint (DeepSeek does not
expose an embeddings model; Anthropic's is private beta). When you switch
chat to DeepSeek you can still set ``OPENAI_API_KEY`` purely for embeddings.

The single public entry point is ``chat_complete(prompt, **kwargs)`` which
returns the assistant's text or ``None`` on failure. Failures never raise —
callers fall back to deterministic rule-based output.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet-latest",
    },
}


def _resolve_provider() -> str:
    provider = (settings.llm_provider or "openai").strip().lower()
    if provider not in _PROVIDER_DEFAULTS:
        logger.warning("Unknown LLM_PROVIDER=%r; falling back to openai", provider)
        return "openai"
    return provider


def _resolve_api_key(provider: str) -> str:
    if settings.llm_api_key:
        return settings.llm_api_key
    if provider == "openai":
        return settings.openai_api_key
    return ""


def _resolve_base_url(provider: str) -> str:
    return settings.llm_base_url or _PROVIDER_DEFAULTS[provider]["base_url"]


def _resolve_model(provider: str) -> str:
    if settings.llm_model:
        return settings.llm_model
    if provider == "openai":
        return settings.reasoning_model or _PROVIDER_DEFAULTS[provider]["model"]
    return _PROVIDER_DEFAULTS[provider]["model"]


def configured_provider() -> dict[str, str]:
    provider = _resolve_provider()
    return {
        "provider": provider,
        "model": _resolve_model(provider),
        "base_url": _resolve_base_url(provider),
        "has_api_key": "true" if _resolve_api_key(provider) else "false",
    }


def chat_complete(
    prompt: str,
    *,
    max_tokens: int = 200,
    temperature: float = 0.3,
    system: str | None = None,
) -> str | None:
    """Send a single-turn chat completion. Returns assistant text or None.

    The function never raises — on any error it returns None and logs the
    error class. Callers should provide a deterministic fallback.
    """
    provider = _resolve_provider()
    api_key = _resolve_api_key(provider)
    if not api_key:
        return None

    base_url = _resolve_base_url(provider)
    model = _resolve_model(provider)
    timeout = settings.llm_request_timeout

    try:
        if provider == "anthropic":
            return _anthropic_chat(
                api_key=api_key,
                base_url=base_url,
                model=model,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
        return _openai_compatible_chat(
            api_key=api_key,
            base_url=base_url,
            model=model,
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning(
            "LLM chat failed (provider=%s, model=%s): %s",
            provider,
            model,
            exc.__class__.__name__,
        )
        return None


def _openai_compatible_chat(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    system: str | None,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> str | None:
    url = base_url.rstrip("/") + "/chat/completions"
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        logger.warning("LLM chat HTTP %d (provider=openai-compatible)", resp.status_code)
        return None
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        logger.warning("LLM chat returned unexpected payload shape")
        return None


def _anthropic_chat(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    system: str | None,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> str | None:
    url = base_url.rstrip("/") + "/messages"
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    resp = httpx.post(
        url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code != 200:
        logger.warning("LLM chat HTTP %d (provider=anthropic)", resp.status_code)
        return None
    data = resp.json()
    try:
        # Anthropic returns content as a list of blocks: [{"type":"text","text":"..."}]
        blocks = data.get("content", [])
        if isinstance(blocks, list) and blocks:
            text = blocks[0].get("text", "")
            return text.strip() or None
    except Exception:
        pass
    logger.warning("Anthropic chat returned unexpected payload shape")
    return None
