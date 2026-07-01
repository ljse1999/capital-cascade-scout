"""Orchestrator. Run with:  python -m scout.run
Pipeline: ingest (free) -> LLM triage (one cheap call) -> enrich (free)
-> write a dated digest markdown into ../digests/."""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import yaml

from . import ingest, synthesize, enrich

ROOT = pathlib.Path(__file__).parent.parent
DIGEST_DIR = ROOT / "digests"

ROLE_EMOJI = {"investor": "🏗️", "supplier": "⛏️", "enabler": "🎟️",
              "macro": "🌐", "unclear": "❔"}
PHASE_LABEL = {"boom": "Boom", "peak": "Peak ⚠️", "bust": "Bust",
               "trough": "Trough", "unclear": "—"}


def _fmt_item(s: dict) -> str:
    role = (s.get("role") or "unclear").lower()
    phase = (s.get("phase") or "unclear").lower()
    stars = "★" * int(s.get("score", 0))
    lines = [
        f"### {ROLE_EMOJI.get(role, '❔')} {s.get('headline', '(no headline)')}",
        f"**{stars}** · _{role}_ · _{PHASE_LABEL.get(phase, phase)}_ · "
        f"{s.get('source', '')} · {s.get('published', '')[:10]}",
        "",
        s.get("why", ""),
    ]
    data = s.get("data_to_pull") or []
    if data:
        lines += ["", "*Data to pull:* " + "; ".join(str(d) for d in data)]
    snaps = s.get("ticker_snaps") or []
    if snaps:
        tape = ", ".join(f"{x['ticker']} {x['price']} ({x['chg_1y_pct']:+.0f}% 1y)"
                         for x in snaps)
        lines += ["", f"*Tape:* {tape}"]
    url = s.get("url")
    if url:
        lines += ["", f"[source]({url})"]
    lines.append("")
    return "\n".join(lines)


def build_digest(scored: list[dict], context: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hdr = [f"# Capital Cascade — Idea Seeds · {today}", ""]
    if not scored:
        hdr += ["_No qualifying seeds today._", ""]
    else:
        top = [s for s in scored if s.get("score", 0) >= 4]
        hdr += [f"**{len(scored)} seeds** "
                f"({len(top)} strong). Roles below: 🏗️ investor · ⛏️ supplier · "
                f"🎟️ enabler. ⚠️ = peak/danger phase.", ""]
    body = [_fmt_item(s) for s in scored]

    ctx = ""
    if context:
        rows = "\n".join(
            f"| {c['ticker']} | {c['price']} | {c['chg_1y_pct']:+.1f}% |"
            for c in context)
        ctx = ("\n---\n\n## Cascade bellwethers (1y)\n\n"
               "| Ticker | Last | 1y |\n|---|---|---|\n" + rows + "\n")

    return "\n".join(hdr) + "\n".join(body) + ctx


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    print("1/4 ingesting news…")
    candidates = ingest.fetch(cfg)
    print(f"     {len(candidates)} candidates after pre-filter")

    print("2/4 LLM triage…")
    scored = synthesize.score_candidates(candidates)
    print(f"     {len(scored)} seeds kept (score >= 2)")

    print("3/4 finance enrichment…")
    scored = enrich.enrich_items(scored, cfg.get("enrich_tickers", True))
    context = enrich.watchlist_context(cfg.get("context_watchlist", [])) \
        if cfg.get("enrich_tickers", True) else []

    print("4/4 writing digest…")
    DIGEST_DIR.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DIGEST_DIR / f"seeds-{today}.md"
    out_path.write_text(build_digest(scored, context), encoding="utf-8")
    print(f"     wrote {out_path}")


if __name__ == "__main__":
    main()
