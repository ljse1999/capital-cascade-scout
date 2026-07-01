"""Provider-swappable cheap-LLM call. Pick the provider with the env var
LLM_PROVIDER (minimax | glm | deepseek). Each uses its cheapest capable
model by default; override with LLM_MODEL. Only ONE API key is needed.

Cost note: this is the only paid step in the whole pipeline. We send one
batched request per day, so the daily cost is fractions of a cent on any of
these models.
"""

from __future__ import annotations

import json
import os

DEFAULT_MODELS = {
    "glm": "glm-5.2",
    "deepseek": "deepseek-v4-pro",
    "minimax": "MiniMax-M3",
    
}

# OpenAI-compatible providers: same SDK, different base_url + key env var.
OPENAI_COMPATIBLE = {
    "glm":      {"base_url": "https://api.z.ai/api/paas/v4",  "key": "ZAI_API_KEY"},
    "deepseek": {"base_url": "https://api.deepseek.com",      "key": "DEEPSEEK_API_KEY"},
    "minimax": {"base_url": "https://api.minimax.io/v1",      "key": "MINIMAX_API_KEY"},
}


def _extract_json(text: str):
    """Pull the first JSON array/object out of a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start == -1:
        raise ValueError(f"No JSON found in model output:\n{text[:300]}")
    depth, end, opener = 0, None, text[start]
    closer = "]" if opener == "[" else "}"
    for i in range(start, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(text[start:end])


def complete(system: str, user: str) -> str:
    # Use `or` so an empty env var (e.g. an unset GitHub Actions variable that
    # still exports LLM_MODEL="") falls back to the default rather than sending
    # an empty/invalid model string to the API.
    provider = (os.environ.get("LLM_PROVIDER") or "minimax").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(
            f"Unknown LLM_PROVIDER {provider!r}. Choose one of: "
            f"{', '.join(DEFAULT_MODELS)}."
        )
    model = (os.environ.get("LLM_MODEL") or "").strip() or DEFAULT_MODELS[provider]

    if provider in OPENAI_COMPATIBLE:
        from openai import OpenAI
        spec = OPENAI_COMPATIBLE[provider]
        # LLM_BASE_URL overrides the default endpoint if you ever need to.
        base_url = os.environ.get("LLM_BASE_URL", spec["base_url"])
        client = OpenAI(api_key=os.environ[spec["key"]], base_url=base_url, timeout=600,