"""Periodic (monthly, not daily) sector-level Capital Cascade assessment.

This is the automated, no-LLM-needed cousin of the interactive
capital-cascade-classifier skill. That skill's data step depends on a
Bigdata MCP connector (find_companies / bigdata_company_tearsheet) which
isn't available to an unattended script — this module reproduces its
quantitative steps (parse metrics -> derived ratios -> archetype scoring ->
phase detection) using `yfinance` instead, which is a normal pip dependency
that runs fine in GitHub Actions.

What this deliberately does NOT do (left to the interactive skill, on
demand, for a specific sector when Lucian wants the fuller picture):
  - qualitative signals from earnings calls / news (FutureSearch)
  - positioning signal / implementation vehicles
  - per-company detail beyond the sector-level aggregate

Output: appended to data/sector_assessments.jsonl, one record per
(sector, run_date). Unlike sector_trends.jsonl (a derived, fully-rebuilt
view of seeds.jsonl), this file is append-only — each run reflects market
data AS OF that date, so historical assessments are genuine, non-reproducible
data points, not something to regenerate from scratch.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Sector baskets. Adapted from the capital-cascade-classifier skill's basket
# table, remapped onto the scout's own sector taxonomy (scout/rubric.md).
# `other_emerging` has no fixed basket by design — it's an ad-hoc catch-all,
# not a stable sector to score financially; watch it instead via the
# sector_note tally in the trend data.
# ---------------------------------------------------------------------------
SECTOR_BASKETS = {
    "semiconductors": ["NVDA", "AMD", "AVGO", "QCOM"],
    "data_centers_ai_infra": ["MSFT", "GOOGL", "AMZN", "META", "EQIX"],
    "power_utilities_grid": ["NEE", "DUK", "SO", "EXC"],
    "lng_gas": ["LNG", "OKE", "WMB"],
    "oil_gas_refining": ["XOM", "CVX", "VLO", "PSX"],
    "mining_metals": ["FCX", "NEM", "SCCO", "AA"],
    "industrial_materials": ["NUE", "STLD", "VMC", "MLM"],
    "chemicals_petrochemicals": ["LIN", "DD", "DOW", "LYB"],
    "battery_ev": ["TSLA", "ALB", "SQM"],
    "autos": ["GM", "F", "STLA"],
    "shipbuilding_shipping": ["HII", "FRO", "GOGL"],
    "aerospace_defence": ["LMT", "RTX", "NOC", "GD"],
    "pharma_biomanufacturing": ["LLY", "PFE", "TMO", "DHR"],
    "construction_homebuilding": ["DHI", "LEN", "NVR", "PHM"],
    "agriculture": ["ADM", "BG", "DE", "MOS"],
    "airlines": ["DAL", "UAL", "LUV", "AAL"],
    "telecom": ["T", "VZ", "TMUS", "CSCO"],
}

# Sector priors — a small, deliberately coarse nudge toward the archetype a
# sector usually plays, mirroring the classifier's "sector prior" points.
# Edit freely as your view of a sector's typical role changes.
INVESTOR_PRIOR_SECTORS = {
    "power_utilities_grid", "oil_gas_refining", "lng_gas", "telecom",
    "mining_metals", "data_centers_ai_infra", "aerospace_defence",
}
SUPPLIER_PRIOR_SECTORS = {
    "semiconductors", "industrial_materials", "chemicals_petrochemicals",
    "pharma_biomanufacturing", "shipbuilding_shipping",
}


def _row(df, name):
    if df is None or name not in df.index:
        return None
    vals = [v for v in df.loc[name].tolist() if v == v]  # drop NaN
    return vals or None


def fetch_company_metrics(ticker: str) -> dict | None:
    """Pull the raw per-year series needed for one company. Returns None
    (and the caller logs it as a gap) if the ticker has no usable data."""
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)
        inc, bs, cf = t.income_stmt, t.balance_sheet, t.cashflow
        rev = _row(inc, "Total Revenue")
        ebit = _row(inc, "EBIT")
        tax = _row(inc, "Tax Provision")
        pretax = _row(inc, "Pretax Income")
        ic = _row(bs, "Invested Capital")
        assets = _row(bs, "Total Assets")
        capex = _row(cf, "Capital Expenditure")
        if not (rev and ebit and ic and capex):
            return None
        capex = [abs(x) for x in capex]
        return {"rev": rev, "ebit": ebit, "tax": tax, "pretax": pretax,
                "ic": ic, "assets": assets, "capex": capex}
    except Exception as e:
        print(f"  ! {ticker} fetch failed: {e}")
        return None


def aggregate_sector(companies: list[dict]) -> dict:
    """Simple average of each metric at each year-index across companies
    that have data for that index (mirrors the classifier's approach)."""
    keys = ["rev", "ebit", "tax", "pretax", "ic", "assets", "capex"]
    max_years = max((len(c[k]) for c in companies for k in keys if c.get(k)), default=0)
    agg = {}
    for k in keys:
        series = []
        for i in range(max_years):
            vals = [c[k][i] for c in companies if c.get(k) and len(c[k]) > i]
            series.append(sum(vals) / len(vals) if vals else None)
        agg[k] = series
    return agg


def compute_derived(agg: dict) -> dict:
    rev, ebit, tax, pretax, ic, assets, capex = (
        agg["rev"], agg["ebit"], agg["tax"], agg["pretax"], agg["ic"],
        agg["assets"], agg["capex"])

    n = min(len(rev), len(ebit), len(ic), len(capex))
    capex_sales = [capex[i] / rev[i] * 100 for i in range(n) if rev[i]]
    tax_rate = []
    for i in range(n):
        if tax and pretax and i < len(tax) and i < len(pretax) and tax[i] is not None and pretax[i]:
            tax_rate.append(max(0.0, min(1.0, tax[i] / pretax[i])))
        else:
            tax_rate.append(0.21)  # rough US statutory fallback
    nopat = [ebit[i] * (1 - tax_rate[i]) for i in range(n)]
    roic = [nopat[i] / ic[i] * 100 for i in range(n) if ic[i]]
    ebit_margin = [ebit[i] / rev[i] * 100 for i in range(n) if rev[i]]

    capex_intensity_ratio = (
        capex_sales[0] / (sum(capex_sales[1:]) / len(capex_sales[1:]))
        if len(capex_sales) > 1 and sum(capex_sales[1:]) else None
    )
    capex_trend = (capex_sales[0] - capex_sales[2]) if len(capex_sales) > 2 else None
    roic_erosion = (roic[0] / max(roic)) if roic and max(roic) else None
    roic_base = min(roic) if roic else None
    roic_improvement = (roic[0] / roic_base) if roic_base and roic_base > 0 else None
    revenue_growth = ((rev[0] - rev[1]) / rev[1] * 100) if len(rev) > 1 and rev[1] else None
    revenue_growth_prior = ((rev[1] - rev[2]) / rev[2] * 100) if len(rev) > 2 and rev[2] else None
    ebit_margin_trend = (ebit_margin[0] - ebit_margin[-1]) if len(ebit_margin) > 1 else None

    overbuild_ratio = None
    asset_cagr = rev_cagr = None
    if assets and len(assets) > 2 and assets[2] and len(rev) > 2 and rev[2]:
        asset_cagr = (assets[0] / assets[2]) ** 0.5 - 1
        rev_cagr = (rev[0] / rev[2]) ** 0.5 - 1
        if rev_cagr > 0.005:  # guard: a flat/declining revenue base makes this ratio meaningless
            overbuild_ratio = asset_cagr / rev_cagr

    return {
        "capex_sales_pct": round(capex_sales[0], 2) if capex_sales else None,
        "capex_intensity_ratio": round(capex_intensity_ratio, 2) if capex_intensity_ratio else None,
        "capex_trend_pp": round(capex_trend, 2) if capex_trend is not None else None,
        "roic_pct": round(roic[0], 2) if roic else None,
        "roic_erosion": round(roic_erosion, 2) if roic_erosion else None,
        "roic_improvement": round(roic_improvement, 2) if roic_improvement else None,
        "revenue_growth_yoy_pct": round(revenue_growth, 2) if revenue_growth is not None else None,
        "revenue_growth_prior_yoy_pct": round(revenue_growth_prior, 2) if revenue_growth_prior is not None else None,
        "ebit_margin_pct": round(ebit_margin[0], 2) if ebit_margin else None,
        "ebit_margin_trend_pp": round(ebit_margin_trend, 2) if ebit_margin_trend is not None else None,
        "overbuild_ratio": round(overbuild_ratio, 2) if overbuild_ratio else None,
        "asset_cagr_2y_pct": round(asset_cagr * 100, 2) if asset_cagr is not None else None,
        "revenue_cagr_2y_pct": round(rev_cagr * 100, 2) if rev_cagr is not None else None,
    }


def score_archetypes(d: dict, sector: str) -> dict:
    inv = sup = ena = 0

    cir = d["capex_intensity_ratio"]
    if cir is not None:
        if cir > 1.5:
            inv += 3
        elif cir > 1.2:
            inv += 2
        if cir < 0.7:
            sup += 2

    if d["capex_trend_pp"] is not None and d["capex_trend_pp"] > 3:
        inv += 1

    cs = d["capex_sales_pct"]
    if cs is not None:
        if cs > 20:
            inv += 2
        elif cs > 12:
            inv += 1
        if cs < 5:
            sup += 2
            ena += 1

    ob = d["overbuild_ratio"]
    if ob is not None:
        if ob > 1.5:
            inv += 3
        elif ob > 1.2:
            inv += 2
        if ob < 0.8:
            sup += 1

    if d["roic_erosion"] is not None:
        if d["roic_erosion"] < 0.6:
            inv += 2
        elif d["roic_erosion"] < 0.8:
            inv += 1

    if d["ebit_margin_trend_pp"] is not None and d["ebit_margin_trend_pp"] < -10:
        inv += 1

    rg = d["revenue_growth_yoy_pct"]
    if rg is not None:
        if rg > 50:
            sup += 3
        elif rg > 25:
            sup += 2
        elif rg > 10:
            sup += 1

    ri = d["roic_improvement"]
    if ri is not None and d["roic_pct"] is not None and d["roic_pct"] > 15:
        if ri > 3:
            sup += 3
        elif ri > 1.8:
            sup += 2
        elif ri > 1.3:
            sup += 1

    emt = d["ebit_margin_trend_pp"]
    if emt is not None:
        if emt > 15:
            sup += 2
        elif emt > 7:
            sup += 1

    if (rg is not None and d["revenue_growth_prior_yoy_pct"] is not None
            and rg > d["revenue_growth_prior_yoy_pct"]):
        sup += 1

    em = d["ebit_margin_pct"]
    if em is not None:
        if em < 0:
            ena += 3
        elif em <= 5:
            ena += 2

    roic = d["roic_pct"]
    if roic is not None and roic < 5:
        ena += 2

    if sector in INVESTOR_PRIOR_SECTORS:
        inv += 1
    if sector in SUPPLIER_PRIOR_SECTORS:
        sup += 1

    return {"investor": inv, "supplier": sup, "enabler": ena}


def detect_phase(role: str, d: dict) -> str:
    if role == "investor":
        cs, cir, roic_er = d["capex_sales_pct"], d["capex_intensity_ratio"], d["roic_erosion"]
        if cir is not None and cir >= 1.2 and roic_er is not None and 0.6 <= roic_er <= 0.85:
            return "peak"
        if d["capex_trend_pp"] is not None and d["capex_trend_pp"] > 0 and roic_er is not None and roic_er > 0.8:
            return "boom"
        if roic_er is not None and roic_er < 0.6 and d["capex_trend_pp"] is not None and d["capex_trend_pp"] < 0:
            return "bust"
        if cir is not None and cir <= 0.85:
            return "trough"
        return "unclear"
    if role == "supplier":
        rg, rg_prior = d["revenue_growth_yoy_pct"], d["revenue_growth_prior_yoy_pct"]
        if rg is not None and rg < 0:
            return "bust"
        if rg is not None and rg > 20 and (rg_prior is None or rg >= rg_prior):
            return "boom"
        if rg is not None and rg >= 0:
            return "peak"
        return "unclear"
    # Enabler: phase is a function of the upstream Investor's cycle position,
    # which this automated pass doesn't cross-reference — flag for manual read.
    return "unclear"


def assess_sector(sector: str, tickers: list[str]) -> dict | None:
    companies, missing = [], []
    for tk in tickers:
        m = fetch_company_metrics(tk)
        if m:
            companies.append(m)
        else:
            missing.append(tk)
    if not companies:
        print(f"  ! {sector}: no usable data for any basket ticker, skipping")
        return None

    agg = aggregate_sector(companies)
    derived = compute_derived(agg)
    scores = score_archetypes(derived, sector)
    total = sum(scores.values()) or 1
    role = max(scores, key=scores.get)
    confidence_score = round(scores[role] / total, 2)
    confidence_label = ("high" if confidence_score > 0.7
                         else "medium" if confidence_score >= 0.5 else "low")
    phase = detect_phase(role, derived)

    return {
        "sector": sector,
        "role": role,
        "role_scores": scores,
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "phase": phase,
        "metrics": derived,
        "basket": tickers,
        "missing_tickers": missing,
    }


def load_existing_keys(path: pathlib.Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            keys.add((r.get("sector"), r.get("run_date")))
        except json.JSONDecodeError:
            continue
    return keys


def run(path: pathlib.Path, run_date: str | None = None) -> int:
    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = load_existing_keys(path)
    generated_at = datetime.now(timezone.utc).isoformat()

    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as f:
        for sector, tickers in SECTOR_BASKETS.items():
            if (sector, run_date) in existing:
                print(f"  - {sector}: already assessed for {run_date}, skipping")
                continue
            print(f"  assessing {sector} ({', '.join(tickers)})...")
            result = assess_sector(sector, tickers)
            if not result:
                continue
            result["run_date"] = run_date
            result["generated_at"] = generated_at
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            written += 1
    return written


if __name__ == "__main__":
    root = pathlib.Path(__file__).parent.parent
    n = run(root / "data" / "sector_assessments.jsonl")
    print(f"wrote {n} sector assessments")
