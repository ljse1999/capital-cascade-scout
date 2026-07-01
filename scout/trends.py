"""Sector trend time series: turns the accumulating data/seeds.jsonl into a
weekly per-sector history (count, score-weighted intensity, role mix, phase
mix) so a future dashboard can chart a sector moving through the cascade
over time, not just see today's snapshot.

Unlike seeds.jsonl (an append-only log of individual articles), this file is
a DERIVED, fully-rebuilt materialized view: every run reads the full seed
history and regenerates data/sector_trends.jsonl from scratch. That avoids
any incremental-patch drift — the current (incomplete) week's numbers simply
get recomputed each day until the week closes.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROLE_KEYS = ["investor", "supplier", "enabler", "macro", "unclear"]
PHASE_KEYS = ["boom", "peak", "bust", "trough", "unclear"]

TOP_SEEDS_PER_PERIOD = 5


def _parse_date(s: str):
    """Best-effort parse of an ISO-ish date/datetime string to a date."""
    if not s:
        return None
    s = s.strip()
    try:
        # Handle both "2026-07-01" and full ISO datetimes, with or without Z.
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _week_bounds(d):
    """Monday..Sunday ISO week containing date d, as ISO strings."""
    monday = d.fromordinal(d.toordinal() - d.weekday())
    sunday = monday.fromordinal(monday.toordinal() + 6)
    return monday.isoformat(), sunday.isoformat()


def load_seeds(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def build_trends(seeds: list[dict]) -> list[dict]:
    # Bucket by (sector, week), preferring the article's published date
    # (when the news actually happened) with date_seen as a fallback for
    # anything the LLM returned without a usable published date.
    buckets: dict[tuple[str, str], dict] = {}

    for s in seeds:
        d = _parse_date(s.get("published") or "") or _parse_date(s.get("date_seen") or "")
        if d is None:
            continue
        period_start, period_end = _week_bounds(d)
        sector = s.get("sector") or "other_emerging"
        key = (sector, period_start)

        b = buckets.setdefault(key, {
            "sector": sector,
            "period_start": period_start,
            "period_end": period_end,
            "count": 0,
            "score_sum": 0,
            "role_counts": {k: 0 for k in ROLE_KEYS},
            "phase_counts": {k: 0 for k in PHASE_KEYS},
            "_seeds": [],
        })

        score = int(s.get("score", 0) or 0)
        role = (s.get("role") or "unclear").lower()
        phase = (s.get("phase") or "unclear").lower()

        b["count"] += 1
        b["score_sum"] += score
        b["role_counts"][role] = b["role_counts"].get(role, 0) + 1
        b["phase_counts"][phase] = b["phase_counts"].get(phase, 0) + 1
        b["_seeds"].append({
            "id": s.get("id"), "headline": s.get("headline"),
            "url": s.get("url"), "score": score,
        })

    rows = []
    for (sector, period_start), b in buckets.items():
        top = sorted(b["_seeds"], key=lambda x: x["score"], reverse=True)[:TOP_SEEDS_PER_PERIOD]
        rows.append({
            "sector": b["sector"],
            "period_start": b["period_start"],
            "period_end": b["period_end"],
            "count": b["count"],
            "score_sum": b["score_sum"],
            "avg_score": round(b["score_sum"] / b["count"], 2) if b["count"] else 0.0,
            "role_counts": b["role_counts"],
            "phase_counts": b["phase_counts"],
            "top_seeds": top,
        })

    rows.sort(key=lambda r: (r["sector"], r["period_start"]))
    return rows


def write_trends(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = []
    for r in rows:
        r = dict(r)
        r["generated_at"] = generated_at
        lines.append(json.dumps(r, ensure_ascii=False))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_and_write(seeds_path: pathlib.Path, trends_path: pathlib.Path) -> int:
    seeds = load_seeds(seeds_path)
    rows = build_trends(seeds)
    write_trends(trends_path, rows)
    return len(rows)


if __name__ == "__main__":
    root = pathlib.Path(__file__).parent.parent
    n = build_and_write(root / "data" / "seeds.jsonl", root / "data" / "sector_trends.jsonl")
    print(f"wrote {n} sector-week rows")
