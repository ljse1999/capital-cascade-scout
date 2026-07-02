# Capital Cascade Scout

An automated research pipeline that scans daily news for signals fitting the
**Capital Cascade** framework — a lens for tracking how one industry's capex
becomes another industry's revenue, and eventually someone's oversupply. The
scout turns that framework into a running, structured dataset: a daily
LLM-triaged news feed, a monthly quantitative sector read, and a public
dashboard that visualizes both.

Built to run unattended on GitHub Actions for pennies a day.

**Live dashboard:** [ljse1999.github.io/capital-cascade-scout](https://ljse1999.github.io/capital-cascade-scout/)

---

## What it does

The pipeline has three layers that run on independent schedules and write
into a shared, append-only data store.

```
Google News RSS + yfinance              (free, no key)
        │  keyword pre-filter, dedupe
        ▼
One batched LLM call / day              (~$0.05–0.10)
        │  scores + tags each candidate: role, phase, sector
        ▼
data/seeds.jsonl                        (raw log, one line per kept article)
        │
        ├─► data/sector_trends.jsonl    weekly rollup, rebuilt each run
        │
        └─► data/sector_assessments.jsonl   monthly quantitative sector read
                                             (yfinance-derived, no LLM)
                        │
                        ▼
              docs/  (GitHub Pages dashboard)
```

**1. Daily scout** (`scout/run.py`, runs 06:30 UTC via
`.github/workflows/daily-scout.yml`)
Pulls Google News RSS across a three-tier query set (durable mechanism
queries, a sweep across 17 capex-heavy sectors, and an "emerging cycle" radar
for new booms forming outside the known list), keyword-filters for free, then
sends the shortlist to a small LLM in a single batched call. The model scores
each item against `scout/rubric.md` — tagging it by **role** (investor /
supplier / enabler), **cascade phase** (boom / peak / bust / trough), and
**sector** — and flags tickers for price enrichment via `yfinance`. Output:
a markdown digest (`digests/seeds-YYYY-MM-DD.md`) and a structured append to
`data/seeds.jsonl`.

**2. Monthly sector assessment** (`scout/sector_assessment.py`, runs on the
1st via `.github/workflows/monthly-assessment.yml`)
A separate, no-LLM quantitative read on all 17 taxonomy sectors — reproducing
a capital-cycle classification methodology (CapEx intensity, ROIC, EBIT
margin trend, revenue growth, overbuild ratio → phase) purely from `yfinance`
fundamentals across a basket of ~65 tickers. Appends one row per
sector/month to `data/sector_assessments.jsonl`.

**3. Dashboard** (`docs/`, static site on GitHub Pages)
A framework-free HTML/CSS/JS site that reads the three JSONL files directly
client-side: a sector overview (phase, trend direction, recent activity), a
per-sector drill-down (Chart.js trend chart + assessment history + filtered
seed feed), and a searchable timeline of every seed ever kept.

---

## Design goals

- **Near-zero marginal cost.** The only paid step is one batched LLM call per
  day (~$0.05–0.10 at `max_candidates: 150`). Everything else — ingestion,
  enrichment, the monthly assessment, the dashboard — is free.
- **Provider-agnostic LLM layer.** `scout/llm.py` swaps between GLM (z.ai,
  current default), MiniMax, and DeepSeek via one environment variable, all
  through the OpenAI-compatible SDK — no code changes to switch.
- **No database.** Three flat JSONL files (one append-only raw log, one
  derived/rebuilt rollup, one append-only monthly log) are the entire data
  layer, read directly by a static dashboard. Sufficient at this scale, easy
  to reason about, and git-versioned for free.
- **Idempotent by design.** `scout/store.py` hashes each URL into a stable
  id and skips anything already logged, so re-runs and overlapping lookback
  windows never duplicate data.

---

## Repo layout

```
scout/
  ingest.py                free RSS fetch + keyword pre-filter + dedupe
  synthesize.py            the one paid LLM triage call
  llm.py                   provider-swappable LLM client (minimax | glm | deepseek)
  enrich.py                yfinance price context for flagged tickers
  store.py                 appends scored seeds -> data/seeds.jsonl (stable-id dedupe)
  trends.py                rebuilds data/sector_trends.jsonl from seeds.jsonl
  sector_assessment.py     monthly yfinance-based sector role/phase read
  run.py                   daily orchestrator -> digest + data/
  rubric.md                the Capital Cascade scoring rubric + sector taxonomy
data/                      seeds.jsonl, sector_trends.jsonl, sector_assessments.jsonl
digests/                   dated markdown digests (human-readable daily output)
docs/                      static dashboard, served via GitHub Pages
.github/workflows/         daily-scout.yml, monthly-assessment.yml
config.yaml                queries, cost guardrails, watchlist
```

---

## Running it locally

```bash
git clone https://github.com/ljse1999/capital-cascade-scout.git
cd capital-cascade-scout
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt

export LLM_PROVIDER=glm
export ZAI_API_KEY=your-key
python -m scout.run                 # writes digests/seeds-<today>.md + data/

# Free filter only, no LLM/key needed:
python -m scout.ingest

# Monthly sector read (no LLM, no key):
python -m scout.sector_assessment
```

## Configuration

Everything tunable lives in `config.yaml` — no code changes needed:

- `google_news_queries` — the three-tier search set (durable / sector sweep / emerging).
- `lookback_days`, `max_candidates`, `min_prefilter_hits` — recall vs. LLM cost.
- `context_watchlist` — bellwether ETF tickers shown as macro context in each digest.

The classification logic itself — role/phase definitions, what makes a good
seed, the sector taxonomy, output schema — lives in `scout/rubric.md` and is
the part most worth reading to understand how the framework is operationalized.

## Swapping LLM providers

| `LLM_PROVIDER` | Secret | Default model | Endpoint |
|---|---|---|---|
| `glm` (current default) | `ZAI_API_KEY` | `glm-5.2` | api.z.ai (OpenAI-compatible) |
| `minimax` | `MINIMAX_API_KEY` | `MiniMax-M3` | api.minimax.io/v1 |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-v4-pro` | api.deepseek.com |

The live GitHub Actions runs are pinned to GLM via the `LLM_PROVIDER` repo
variable in **Settings → Secrets and variables → Actions**; change that
variable (and the matching secret) to switch providers. Override the model
with an `LLM_MODEL` variable. All three run through the `openai` SDK, so no
dependency changes are needed to move between them.

## What's deliberately out of scope (v1)

Social media (X/Reddit/StockTwits) and FRED macro series — both are natural
follow-ons once the core pipeline has a track record.

## Roadmap

- Sector-specific overrides for the monthly assessment (a handful of sectors —
  e.g. cyclical autos — currently mis-classify on pure margin data alone).
- Tighter phase-detection thresholds for the "capex still rising while ROIC
  has eroded" late-cycle case, currently bucketed as `unclear`.
- Linking the live dashboard from the Capital Cascade blog once it launches.

---

Built and maintained by [Lucian Ellis](https://github.com/ljse1999) as the
data backbone for the Capital Cascade research project.
