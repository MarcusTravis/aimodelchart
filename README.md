# AI Model Chart

Free, ad-free tracker of the most popular AI models and how smart they are: https://aimodelchart.pages.dev

One static page (`index.html`) that reads `data/latest.json`. No client-side API calls, no build step.

## Sources (each shown separately, never combined into one score)

| Column | Source | License |
|---|---|---|
| Popularity, token share, rank change | OpenRouter daily rankings (openrouter.ai/rankings), top 50 by tokens, `other` aggregate ignored | CC BY 4.0 |
| ECI, maker, open/closed | Epoch AI, Epoch Capabilities Index (epoch.ai/eci), `eci_scores.csv`. The CSV `date` is the model release date, not a score date | CC BY 4.0 |
| Arena Score, Arena rank | LMArena text leaderboard, `text_style_control`, category `overall` (huggingface.co/datasets/lmarena-ai/leaderboard-dataset). Arena Score is a Bradley-Terry rating, not Elo | CC BY 4.0 |

## How the update works

`.github/workflows/update-data.yml` runs daily at 00:00 UTC (and on manual dispatch), runs `scripts/update_data.py`, and commits `data/` to `main` only if something changed.

The script:
1. Fetches OpenRouter rankings for yesterday (complete UTC day) and the day before, for rank deltas. Needs the `OPENROUTER_API_KEY` repository secret.
2. Downloads the ECI CSV and the Arena parquet.
3. Merges by normalized model name (`aliases.json` holds manual overrides). Arena variants such as `(High)` are collapsed: the plain entry is used if present, otherwise the best-rated variant. Unmatched cells are `null` and render as "—".
4. Row set: the OpenRouter top 50, plus up to 20 top-ECI and 20 top-Arena models not already present, capped at 60 rows.
5. Writes `data/latest.json` (page data), `data/sources_cache.json` (last-good copy of each source) and `data/history.json` (14 days of top-20 OpenRouter ranks).

If a source fails, its last-good data from `sources_cache.json` is reused and the failure is logged. Without `OPENROUTER_API_KEY` the popularity columns are empty and the table is ordered by ECI. The OpenRouter response parser is tolerant of field names (`model_permaslug`/`model`, `total_tokens`/`tokens`, `date`); if the dataset schema differs, adjust `fetch_openrouter`.

## Search engines and AI assistants

`scripts/prerender.py` (run by the workflow right after `update_data.py`, no network) bakes `data/latest.json` into static files so crawlers that don't run JavaScript still see the data:

- `index.html`: table rows, the "Last updated" line and a JSON-LD block (WebSite, WebPage, Dataset, FAQPage), between `<!-- X:START -->`/`<!-- X:END -->` markers. `app.js` re-renders the table in the browser, so visitors see no change. Don't hand-edit inside the markers.
- `llms.txt`: plain-text summary (top 10 by usage, ECI and Arena Score, plus definitions and sources).
- `sitemap.xml`: `<lastmod>` = data date.

It only rewrites a file when its content changes.

## Run locally

```
pip install -r requirements.txt
OPENROUTER_API_KEY=... python scripts/update_data.py
python scripts/prerender.py
python -m http.server 8000   # then open http://localhost:8000
```

(Browsers block `fetch` on `file://`, so use a local server.)

## Hosting

Cloudflare Pages, git-connected, empty build command, root output directory. `_headers` sets security headers and a short cache TTL for `data/*`.
