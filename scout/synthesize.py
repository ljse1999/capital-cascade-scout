"""Synthesis: send pre-filtered candidates to the cheap LLM with the cascade
rubric, get back scored/tagged seeds. One batched call per run."""

from __future__ import annotations

import json
import pathlib

from . import llm

RUBRIC = (pathlib.Path(__file__).parent / "rubric.md").read_text(encoding="utf-8")


def score_candidates(items) -> list[dict]:
    """items: list[ingest.Item]. Returns list of scored dicts (score >= 2)."""
    if not items:
        return []

    payload = [
        {"headline": i.headline, "url": i.url, "source": i.source,
         "published": i.published}
        for i in items
    ]
    user = (
        "Here are today's candidate headlines as JSON. Triage them per your "
        "instructions and return ONLY a JSON array of the items worth keeping "
        "(score >= 2), each with the fields specified.\n\n"
        + json.dumps(payload, indent=2)
    )

    scored = llm.complete_json(RUBRIC, user)
    if isinstance(scored, dict):
        scored = scored.get("items", [scored])
    # Normalise + guard.
    out = []
    for s in scored:
        try:
            s["score"] = int(s.get("score", 0))
        except (TypeError, ValueError):
            s["score"] = 0
        if s["score"] >= 2:
            s.setdefault("tickers", [])
            s.setdefault("data_to_pull", [])
            out.append(s)
    out.sort(key=lambda s: s["score"], reverse=True)
    return out
