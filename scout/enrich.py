"""Finance enrichment via yfinance (no API key). Attaches a quick price +
trailing-1y change snapshot so a 'boom narrative' can be cross-checked
against what the tape is actually doing."""

from __future__ import annotations


def _snapshot(ticker: str):
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty:
            return None
        last = float(hist["Close"].iloc[-1])
        first = float(hist["Close"].iloc[0])
        chg = (last / first - 1.0) * 100 if first else 0.0
        return {"ticker": ticker, "price": round(last, 2), "chg_1y_pct": round(chg, 1)}
    except Exception as e:
        print(f"  ! enrich failed for {ticker}: {e}")
        return None


def watchlist_context(tickers: list[str]) -> list[dict]:
    out = []
    for tk in tickers:
        snap = _snapshot(tk)
        if snap:
            out.append(snap)
    return out


def enrich_items(items: list[dict], enabled: bool) -> list[dict]:
    """items: list of LLM-scored dicts each possibly carrying a 'tickers' list.
    Mutates each item to add 'ticker_snaps'."""
    if not enabled:
        return items
    cache: dict[str, dict] = {}
    for it in items:
        snaps = []
        for tk in (it.get("tickers") or [])[:5]:
            tk = tk.strip().upper()
            if not tk:
                continue
            if tk not in cache:
                cache[tk] = _snapshot(tk) or {}
            if cache[tk]:
                snaps.append(cache[tk])
        it["ticker_snaps"] = snaps
    return items


if __name__ == "__main__":
    print(watchlist_context(["SMH", "XLU"]))
