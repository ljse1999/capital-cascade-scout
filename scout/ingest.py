"""Ingestion: pull Google News RSS (no API key) + optional plain feeds,
keyword pre-filter against the cascade vocabulary, dedupe. No LLM here —
this is the cheap deterministic tier."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import feedparser

# Cascade vocabulary used for the cheap pre-filter (counts distinct hits).
# Broad on purpose — the LLM does the precise judgement afterwards.
CASCADE_TERMS = [
    "capex", "capital expenditure", "capital spending", "investment plan",
    "buildout", "build-out", "expansion", "gigafactory", "megaproject",
    "data center", "data centre", "capacity", "backlog", "order book",
    "orders", "lead time", "sold out", "shortage", "bookings",
    "oversupply", "overcapacity", "glut", "price war", "cancelled",
    "canceled", "delayed", "writedown", "impairment", "spending cut",
    "capex cut", "distressed", "bankruptcy", "supplier", "equipment",
    "shipbuilding", "fleet order", "mine", "grid", "power plant",
    "generation", "utilities", "semiconductor", "chip", "foundry",
    "pricing power", "margins", "overbuild", "billion", "record",
]

_TERM_RE = [re.compile(rf"\b{re.escape(t)}\b", re.I) for t in CASCADE_TERMS]


@dataclass
class Item:
    headline: str
    url: str
    source: str
    published: str           # ISO string
    published_dt: datetime
    hits: int = 0
    matched: list = field(default_factory=list)

    def key(self) -> str:
        # Dedupe key: normalised headline (first 12 words) ignoring source.
        words = re.sub(r"[^a-z0-9 ]", "", self.headline.lower()).split()
        return " ".join(words[:12])


def _google_news_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _parse_dt(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _source_of(entry, fallback: str) -> str:
    src = getattr(entry, "source", None)
    if src and getattr(src, "title", None):
        return src.title
    # Google News prefixes the publisher after a " - " in the title.
    title = getattr(entry, "title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return fallback


def _clean_headline(title: str) -> str:
    # Strip the trailing " - Publisher" Google News appends.
    if " - " in title:
        head, tail = title.rsplit(" - ", 1)
        if len(tail) < 40:
            return head.strip()
    return title.strip()


def _score(text: str):
    matched = [t.pattern.strip("\\b") for t in _TERM_RE if t.search(text)]
    # Unescape the readable term back out of the regex pattern.
    matched = [CASCADE_TERMS[i] for i, t in enumerate(_TERM_RE) if t.search(text)]
    return len(matched), matched


def fetch(config: dict) -> list[Item]:
    lookback = config.get("lookback_days", 2)
    blocked = set(d.lower() for d in config.get("blocked_domains", []))
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback)

    feeds: list[str] = [_google_news_url(q) for q in config.get("google_news_queries", [])]
    feeds += list(config.get("extra_rss_feeds", []))

    items: dict[str, Item] = {}
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:  # network hiccup on one feed shouldn't kill the run
            print(f"  ! feed failed: {url[:60]}... ({e})")
            continue
        for entry in parsed.entries:
            dt = _parse_dt(entry)
            if dt < cutoff:
                continue
            headline = _clean_headline(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            if not headline or not link:
                continue
            if any(b in link.lower() for b in blocked):
                continue
            hits, matched = _score(headline)
            if hits < config.get("min_prefilter_hits", 1):
                continue
            item = Item(
                headline=headline,
                url=link,
                source=_source_of(entry, "news"),
                published=dt.isoformat(),
                published_dt=dt,
                hits=hits,
                matched=matched,
            )
            k = item.key()
            # Keep the higher-scoring / fresher of any duplicates.
            if k not in items or item.hits > items[k].hits:
                items[k] = item

    ranked = sorted(items.values(), key=lambda i: (i.hits, i.published_dt), reverse=True)
    return ranked[: config.get("max_candidates", 60)]


if __name__ == "__main__":
    import yaml, pathlib
    cfg = yaml.safe_load((pathlib.Path(__file__).parent.parent / "config.yaml").read_text())
    out = fetch(cfg)
    print(f"{len(out)} candidates after filter\n")
    for it in out[:25]:
        print(f"[{it.hits}] {it.headline}  ({it.source})")
