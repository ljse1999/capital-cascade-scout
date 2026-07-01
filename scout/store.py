"""Persistent structured store: appends every scored seed to a JSONL file
(one JSON object per line) so seeds accumulate into a queryable history,
instead of living only in that day's throwaway markdown digest.

This is the source of truth for the future Capital Cascade tracker/dashboard.
The daily markdown digest is just a same-day rendering of what gets written
here; `data/seeds.jsonl` is what should eventually feed aggregation scripts
and a dashboard.
"""

from __future__ import annotations

import hashlib
import json
import pathlib


FIELDS = [
    "id", "date_seen", "published", "headline", "source", "url",
    "role", "sector", "sector_note", "phase", "score", "why",
    "data_to_pull", "tickers",
]


def stable_id(item: dict) -> str:
    """Deterministic id so the same story always gets the same id, even if
    re-scored on a later run. Keyed on URL when present (most stable),
    falling back to source+headline."""
    key = (item.get("url") or "").strip().lower()
    if not key:
        key = f"{item.get('source', '')}|{item.get('headline', '')}".strip().lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _to_record(item: dict, date_seen: str) -> dict:
    rec = {"id": stable_id(item), "date_seen": date_seen}
    for f in FIELDS:
        if f in ("id", "date_seen"):
            continue
        rec[f] = item.get(f, "" if f not in ("data_to_pull", "tickers") else [])
    return rec


def load_ids(path: pathlib.Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line).get("id"))
        except json.JSONDecodeError:
            continue
    return ids


def append_records(path: pathlib.Path, scored: list[dict], date_seen: str) -> int:
    """Append newly-scored seeds to the JSONL store. Skips anything whose id
    is already present (belt-and-suspenders against a rerun on the same day —
    the daily 'seen' store is the primary guard against reprocessing).
    Returns the number of records actually written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_ids(path)
    new_lines = []
    for item in scored:
        rec = _to_record(item, date_seen)
        if rec["id"] in existing:
            continue
        existing.add(rec["id"])
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    if new_lines:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")
    return len(new_lines)
