# Mandi Rates · Karnataka

A live dashboard of daily agricultural mandi (market) prices for Karnataka — commodity, market, district, and min/max/modal prices per quintal — with 7-day price trend charts, sourced from the Ministry of Agriculture & Farmers Welfare's data via [data.gov.in](https://data.gov.in).

ಇಂದಿನ ದರ · ಕರ್ನಾಟಕ ಮಾರುಕಟ್ಟೆ

## How it works

Rather than calling the government API directly from the browser (which exposes the API key, hits shared rate limits, and breaks during the morning data-refresh gap), this project fetches data **server-side on a schedule** via GitHub Actions and serves static JSON files to the frontend.

```
┌─────────────────────┐     hourly cron      ┌──────────────────┐
│  data.gov.in API     │ ───────────────────► │  GitHub Actions   │
│  (current price)     │                      │  fetch_data.py    │
└─────────────────────┘                      └────────┬─────────┘
                                                        │ commits
                                                        ▼
                                              ┌──────────────────┐
                                              │  data/live.json   │
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

### Data source
- **Current daily prices**: [`9ef84268-d588-465a-a308-a864a43d0070`](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi) — near-real-time snapshot, refreshed by the ministry through the day. Does *not* retain history; if queried before the ministry has published for the day it returns `count: 0`.

This is the **only** API this project calls. The government's separate "historical daily prices" resource is deliberately never used — it caps responses at 10 records/request, so reconstructing even one full day for Karnataka (~200–700 records) would take dozens of paginated calls and risks the API's rate limiter. Instead, `history.json` is built up incrementally, one day at a time, purely from this same daily current-price pull.

### Why static JSON instead of client-side API calls
- **No exposed API key** — the key lives only in a GitHub Actions secret, never shipped to the browser.
- **No per-visitor rate limiting** — only the hourly cron job talks to data.gov.in; visitors just read a static file.
- **Morning-gap resilience** — the API's `count` field is checked explicitly. When `count === 0` (today's data isn't published yet), the script does nothing and leaves `live.json`/`history.json` untouched, so the site keeps serving the most recently fetched day indefinitely, with no extra API calls, until the next real update arrives.
- **Fast trend charts & date picker** — `history.json` keys each of the last 7 days to that day's full record list, built from ordinary hourly snapshots, so opening a trend chart or picking an earlier date is an instant local read with zero live API calls.

## Project structure

```
.
├── index.html                  # frontend (static, no build step)
├── scripts/
│   ├── fetch_data.py            # pulls current-day data, writes data/live.json + data/history.json
│   ├── backfill_history.py      # manual/offline seed of data/history.json from downloaded CSVs
│   └── report_stats.py          # prints size stats for data/live.json and data/history.json
├── data/
│   ├── live.json                # most recent successfully fetched day, consumed by index.html
│   └── history.json             # rolling 7-day window {iso_date: [that day's records]}
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

4. **Run the workflow once manually** to generate the first `data/live.json` and `data/history.json`
   Repo → **Actions → Update mandi data → Run workflow**

After that, the workflow runs hourly on its own (`cron: "0 * * * *"` in `update-data.yml`) and keeps the data fresh.

## Local development

```bash
pip install requests
export DATA_GOV_API_KEY=your_key_here
python scripts/fetch_data.py     # generates data/live.json and data/history.json
python scripts/report_stats.py   # check file sizes / cached days
```

To seed or repair `data/history.json` from a folder of manually downloaded per-district CSVs (same columns as the government's data exports) — useful if a day is missing, since the pipeline itself never backfills from a live API:
```bash
python scripts/backfill_history.py /path/to/csv/dir
```

Then open `index.html` directly, or serve it locally:
```bash
python -m http.server 8000
```

## Data notes

- Prices are per quintal (100 kg), as reported by APMC market committees. They may lag actual trading by a day.
- `history.json` keeps exactly the most recent 7 days seen from the current-price feed, trimmed automatically by `fetch_data.py` on each run. Fewer days may be present until the cache has had a week to fill up.
- The date picker on the homepage only ever offers dates present in `history.json` — there's no way to request a date outside that window, since none is fetched.

## License / attribution

Price data is published by the Ministry of Agriculture and Farmers Welfare, Department of Agriculture and Farmers Welfare, via the AGMARKNET portal, released under the Open Government Data Platform India (data.gov.in). This project is not affiliated with the Government of India.
