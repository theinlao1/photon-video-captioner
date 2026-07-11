"""
A single client for OpenAI-compatible chat completions APIs.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger("llm_client")

REQUEST_TIMEOUT_S = 45
MAX_RETRIES = 2
RETRY_BACKOFF_S = 2.0


@dataclass
class ProviderConfig:
    label: str
    base_url: str
    api_key: str
    model: str


def _load_provider(prefix: str, kind: str) -> ProviderConfig | None:
    """kind: 'vision' or 'text'. If {PREFIX}_TEXT_MODEL is not set, fall back to
    {PREFIX}_VISION_MODEL (the same VLM usually writes text fine too)."""
    api_key = os.environ.get(f"{prefix}_API_KEY", "").strip()
    base_url = os.environ.get(f"{prefix}_BASE_URL", "").strip()
    if not api_key or not base_url:
        return None
    model = (
        os.environ.get(f"{prefix}_{kind.upper()}_MODEL", "").strip()
        or os.environ.get(f"{prefix}_VISION_MODEL", "").strip()
    )
    if not model:
        return None
    return ProviderConfig(label=f"{prefix.lower()}:{kind}", base_url=base_url, api_key=api_key, model=model)


def _post_chat(
    cfg: ProviderConfig,
    messages: list[dict],
    *,
    response_format: dict | None,
    max_tokens: int,
    temperature: float,
) -> str:
    """A single request to /chat/completions. Raises on a network/HTTP error or an
    unexpected response shape — the caller (chat_with_fallback) decides whether to
    retry or switch to another provider."""
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    # Reasoning models (Qwen 3.x Plus etc.) emit "thoughts" by default. Fireworks
    # lets you turn them off via reasoning_effort. Controlled by the DISABLE_REASONING
    # env var (on by default — we want clean descriptions, not deliberations).
    if os.environ.get("DISABLE_REASONING", "1") == "1":
        payload["reasoning_effort"] = "none"

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{cfg.label}: empty content in response")
    return content


def chat_with_fallback(
    messages: list[dict],
    *,
    kind: str = "text",
    response_format: dict | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    Tries PRIMARY with retries (exponential backoff), and on a full failure falls
    back to FALLBACK (if set). This way a single transient failure/rate-limit
    during judging does not zero out the result for the clip — it only costs time.
    """
    providers = [p for p in (_load_provider("PRIMARY", kind), _load_provider("FALLBACK", kind)) if p is not None]
    if not providers:
        raise RuntimeError(
            "No provider found: set PRIMARY_API_KEY / PRIMARY_BASE_URL / "
            "PRIMARY_VISION_MODEL (and optionally PRIMARY_TEXT_MODEL, FALLBACK_*) in .env"
        )

    last_error: Exception | None = None
    for cfg in providers:
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                return _post_chat(
                    cfg, messages,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as e:  # network, timeout, HTTP 4xx/5xx, unexpected response shape
                last_error = e
                logger.warning("%s: attempt %d/%d failed (%s)", cfg.label, attempt, MAX_RETRIES + 1, e)
                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_S * attempt)
        logger.warning("%s exhausted all attempts, switching to the next", cfg.label)

    raise RuntimeError(f"All providers unavailable, last error: {last_error}")
