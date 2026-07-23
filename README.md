# Mandi Rates · Karnataka

A live dashboard of daily agricultural mandi (market) prices for Karnataka — commodity, market, district, and min/max/modal prices per quintal — with 7-day price trend charts, sourced from the Ministry of Agriculture & Farmers Welfare's data via [data.gov.in](https://data.gov.in).

ಇಂದಿನ ದರ · ಕರ್ನಾಟಕ ಮಾರುಕಟ್ಟೆ

## How it works

Rather than calling the government API directly from the browser (which exposes the API key, hits shared rate limits, and breaks during the morning data-refresh gap), this project fetches data **server-side on a schedule** via GitHub Actions and serves static JSON files to the frontend.

```
┌─────────────────────┐     hourly cron      ┌──────────────────┐
│  data.gov.in APIs    │ ───────────────────► │  GitHub Actions   │
│  (current + hist.)   │                      │  fetch_data.py    │
└─────────────────────┘                      └────────┬─────────┘
                                                        │ commits
                                                        ▼
                                              ┌──────────────────┐
                                              │  data/latest.json │
                                              │  data/history.json│
                                              └────────┬─────────┘
                                                        │ served via
                                                        │ GitHub Pages
                                                        ▼
                                              ┌──────────────────┐
                                              │   index.html      │
                                              │  (this frontend)  │
                                              └──────────────────┘
```

### Data sources
- **Current daily prices**: [`9ef84268-d588-465a-a308-a864a43d0070`](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi) — near-real-time snapshot, refreshed by the ministry through the day. Does *not* retain history; if queried during the morning refresh gap it can return zero rows.
- **Historical daily prices**: [`35985678-0d79-46b4-9ed6-6f13308a1d24`](https://www.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24) — used for (a) falling back to the most recent available date when the current-price feed is empty, and (b) bootstrapping trend history for new commodity/market combos. Capped at 10 records per request by the API, so pagination is required for bulk pulls.

### Why static JSON instead of client-side API calls
- **No exposed API key** — the key lives only in a GitHub Actions secret, never shipped to the browser.
- **No per-visitor rate limiting** — only the hourly cron job talks to data.gov.in; visitors just read a static file.
- **Morning-gap resilience** — if the current-price feed is empty when the cron runs, it automatically falls back to the most recent historical date instead of publishing an empty snapshot.
- **Fast trend charts** — `history.json` accumulates a rolling ~14-day window per commodity/market/district combo from each hourly snapshot, so opening a trend chart is an instant local read with zero live API calls.

## Project structure

```
.
├── index.html                  # frontend (static, no build step)
├── scripts/
│   ├── fetch_data.py            # pulls current + historical data, writes data/*.json
│   ├── backfill_history.py      # one-time seed of data/history.json from manually downloaded CSVs
│   └── report_stats.py          # prints size/growth stats for data/history.json
├── data/
│   ├── latest.json              # current snapshot consumed by index.html
│   └── history.json             # rolling per-combo price history for trend charts
└── .github/
    └── workflows/
        └── update-data.yml      # hourly cron: runs fetch_data.py, commits data/*.json
```

## Setup

1. **Get a data.gov.in API key**
   Register at [data.gov.in](https://data.gov.in), then generate a personal API key from your account page. A personal key avoids the shared/public demo key's rate limits.

2. **Add the key as a GitHub secret**
   Repo → **Settings → Secrets and variables → Actions → New repository secret**
   Name: `DATA_GOV_API_KEY`
   Value: *(your key)*

3. **Enable GitHub Pages**
   Repo → **Settings → Pages** → deploy from the branch this code lives on (root, or `/docs` if you move `index.html` there).

4. **Run the workflow once manually** to generate the first `data/latest.json` and `data/history.json`
   Repo → **Actions → Update mandi data → Run workflow**

After that, the workflow runs hourly on its own (`cron: "0 * * * *"` in `update-data.yml`) and keeps the data fresh.

## Local development

```bash
pip install requests
export DATA_GOV_API_KEY=your_key_here
python scripts/fetch_data.py     # generates data/latest.json and data/history.json
python scripts/report_stats.py   # check file sizes / combo counts
```

To seed `data/history.json` from a folder of manually downloaded per-district CSVs (same columns as the historical API — useful for bootstrapping trend history faster than the per-run bootstrap cap allows):
```bash
python scripts/backfill_history.py /path/to/csv/dir
```

Then open `index.html` directly, or serve it locally:
```bash
python -m http.server 8000
```

## Data notes

- Prices are per quintal (100 kg), as reported by APMC market committees. They may lag actual trading by a day.
- `history.json` keeps roughly the last 14 reported days per commodity/market/district combination, trimmed automatically by `fetch_data.py` — this bounds file growth while keeping enough headroom for 7-day trend charts.
- New commodity/market combinations are backfilled from the historical API automatically (capped at 30 new combos per cron run to stay within rate limits).

## License / attribution

Price data is published by the Ministry of Agriculture and Farmers Welfare, Department of Agriculture and Farmers Welfare, via the AGMARKNET portal, released under the Open Government Data Platform India (data.gov.in). This project is not affiliated with the Government of India.
