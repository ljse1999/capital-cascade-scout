"""Cross-run dedup: remember the headline keys already emitted so the same
story doesn't reappear in later daily digests.

Headline-only by design. The normalised headline (ingest.Item.key(): first 12
words, lowercased, punctuation stripped) is stable for a given article across
days, whereas the source URL is not — the model sometimes returns a generic
Google News link — so we key on the headline alone and never on the URL.

State lives in digests/_seen.json as {headline_key: first_seen_date}. The daily
workflow already runs `git add digests/`, so the store is committed and restored
automatically with no workflow change. Entries older than RETENTION_DAYS are
pruned, keeping the file small and letting a story legitimately resurface much
later.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

RETENTION_DAYS = 30


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _cutoff() -> str:
    return (datetime.now(timezone.utc)
            - timedelta(days=RETENTION_DAYS)).date().isoformat()


def _load(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def load_seen(path: pathlib.Path) -> set[str]:
    """Headline keys emitted on a previous run, within the retention window."""
    cutoff = _cutoff()
    return {k for k, d in _load(path).items() if d >= cutoff}


def filter_unseen(items, seen: set[str]):
    """Drop items whose headline key was already emitted on a previous run."""
    return [it for it in items if it.key() not in seen]


def record(path: pathlib.Path, items) -> None:
    """Mark these items' headline keys as seen (keeping the earliest date),
    prune anything past the retention window, and persist.

    Call this ONLY after the digest has been written successfully, so a failed
    run never marks stories seen and loses them.
    """
    data = _load(path)
    today = _today()
    for it in items:
        data.setdefault(it.key(), today)
    cutoff = _cutoff()
    data = {k: d for k, d in data.items() if d >= cutoff}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=0, sort_keys=True), encoding="utf-8")
