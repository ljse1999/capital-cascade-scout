# Capital Cascade Scout

A cheap daily robot that scans the news for things that fit the **Capital Cascade**
framework and writes you a dated digest of *idea seeds* — capex commitments, supplier
backlogs, oversupply/cancellation signals, distressed-asset (enabler) angles — each tagged
by role (investor / supplier / enabler) and cascade phase (boom / peak / bust / trough),
with specific data points worth pulling.

## How it keeps cost near zero

Two tiers. The expensive part (an LLM) only runs **once per day** on a pre-filtered shortlist:

1. **Free, no LLM:** Google News RSS (no key) → keyword pre-filter against cascade
   vocabulary → dedupe. This does ~95% of the work for £0.
2. **One cheap LLM call/day:** the shortlist goes to a small model (Gemini Flash by
   default) which scores and tags each item against the framework rubric. Pennies, or free
   on Gemini's free tier.
3. **Free enrichment:** `yfinance` attaches a price + 1-year move to any tickers flagged,
   plus a bellwether watchlist, so a "boom narrative" can be checked against the tape.

The output is `digests/seeds-YYYY-MM-DD.md`. Keep Cowork/Opus for actually *writing the
articles* — that's where premium tokens earn their keep.

---

## One-time setup (about 15 minutes)

### 1. Get one API key
Default is **GLM (z.ai)** — use your existing z.ai key. (DeepSeek, OpenAI, Gemini and
Anthropic also supported — see "Swapping providers".)

### 2. Create a GitHub repo
- Make a **new repository** on GitHub (private is fine), e.g. `capital-cascade-scout`.
- Upload the entire contents of this `capital-cascade-scout` folder into it (drag-and-drop
  in the GitHub web UI works — keep the folder structure, including `.github/`).

### 3. Add your key as a secret
In the repo: **Settings → Secrets and variables → Actions → New repository secret**
- Name: `ZAI_API_KEY`  ·  Value: *(your z.ai key)*

### 4. Turn it on
The schedule (06:30 UTC daily) is already defined in `.github/workflows/daily-scout.yml`.
To check it works now, go to the **Actions** tab → *Capital Cascade Daily Scout* →
**Run workflow**. After a minute it commits a digest into `digests/`.

> First-time note: GitHub disables scheduled Actions on brand-new repos until you've
> enabled Actions once (the Actions tab will prompt you). A manual "Run workflow" both
> tests it and satisfies that.

### 5. Get digests into your Capital Cascade folder (OneDrive sync)
A cloud Action can't write to your PC directly, so do this once:
- Install GitHub Desktop (easiest) or Git.
- **Clone the repo into your OneDrive folder**, e.g. to
  `…/OneDrive/Documents/Capital Cascade/capital-cascade-scout-repo`.
- Each morning, open GitHub Desktop and hit **Fetch/Pull** (or let it auto-fetch). The new
  `digests/seeds-*.md` files land in that folder and OneDrive syncs them to all your devices.

Prefer it fully hands-off? Say the word and I'll switch the workflow to **email** each
digest to you instead of (or as well as) committing it — no cloning needed.

---

## Running it locally (optional, for testing)
```bash
cd capital-cascade-scout
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
setx GEMINI_API_KEY "your-key"      # then reopen the terminal
python -m scout.run                 # writes digests/seeds-<today>.md

# Just see what the free filter catches, no LLM/key needed:
python -m scout.ingest
```

## Tuning it
Everything lives in **`config.yaml`** — no code changes needed:
- `google_news_queries` — add/remove search angles (broad scan by default).
- `lookback_days`, `max_candidates`, `min_prefilter_hits` — recall vs. cost.
- `context_watchlist` — the bellwether tickers shown at the foot of each digest.

The framework rubric the LLM scores against is **`scout/rubric.md`** — edit this to sharpen
what counts as a good seed as your thinking on the framework develops.

## Swapping providers
Default is **MiniMax (`minimax`)**. To switch, set a repo **variable** `LLM_PROVIDER` (Settings →
Secrets and variables → Actions → *Variables*) and add the matching secret:

| `LLM_PROVIDER` | Secret name | Default model | Endpoint |
|---|---|---|---|
| `minimax` (default) | `MINIMAX_API_KEY` | `MiniMax-M3` | api.minimax.io/v1 (OpenAI-compatible) |
| `glm` | `ZAI_API_KEY` | `glm-5.2` | z.ai (OpenAI-compatible) |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-v4-pro` | api.deepseek.com (OpenAI-compatible) |

Override the model with an `LLM_MODEL` variable (e.g. set it to your exact model string).
All three providers use the `openai` SDK already in `requirements.txt`, so no dependency
change is needed to move between them.

## What's deliberately *not* in v1
Social media (X is costly, Reddit/StockTwits are v2) and macro series from FRED. Both are
easy add-ons once the core is earning its keep.

## Files
```
config.yaml                     sources, keywords, watchlist (edit this)
requirements.txt
.github/workflows/daily-scout.yml   the daily schedule
scout/rubric.md                 the Capital Cascade scoring rubric (edit this)
scout/ingest.py                 free RSS fetch + keyword filter + dedupe
scout/synthesize.py             the one cheap LLM triage call
scout/llm.py                    provider-swappable LLM wrapper
scout/enrich.py                 yfinance price context
scout/run.py                    orchestrator -> digests/seeds-<date>.md
```
