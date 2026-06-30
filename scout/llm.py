"""Provider-swappable cheap-LLM call. Pick the provider with the env var
LLM_PROVIDER (gemini | openai | anthropic). Each uses its cheapest capable
model by default; override with LLM_MODEL. Only ONE API key is needed.

Cost note: this is the only paid step in the whole pipeline. We send one
batched request per day, so the daily cost is fractions of a cent on any of
these models. Gemini Flash also has a free tier that often covers it entirely.
"""

from __future__ import annotations

import json
import os

DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "glm": "glm-5.2",
    "deepseek": "deepseek-chat",
}

# OpenAI-compatible providers: same SDK, different base_url + key env var.
OPENAI_COMPATIBLE = {
    "openai":   {"base_url": None,                            "key": "OPENAI_API_KEY"},
    "glm":      {"base_url": "https://api.z.ai/api/paas/v4",  "key": "ZAI_API_KEY"},
    "deepseek": {"base_url": "https://api.deepseek.com",      "key": "DEEPSEEK_API_KEY"},
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
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    model = os.environ.get("LLM_MODEL", DEFAULT_MODELS[provider])

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        gm = genai.GenerativeModel(model, system_instruction=system)
        resp = gm.generate_content(user)
        return resp.text

    if provider in OPENAI_COMPATIBLE:
        from openai import OpenAI
        spec = OPENAI_COMPATIBLE[provider]
        # LLM_BASE_URL overrides the default endpoint if you ever need to.
        base_url = os.environ.get("LLM_BASE_URL", spec["base_url"])
        client = OpenAI(api_key=os.environ[spec["key"]], base_url=base_url,
                        timeout=90, max_retries=1)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=model, max_tokens=4096, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def complete_json(system: str, user: str):
    return _extract_json(complete(system, user))
