"""
Fetches Karnataka mandi price data from data.gov.in and writes it to
data/latest.json (current snapshot) and data/history.json (rolling trend history).

Run via GitHub Actions on a schedule (see .github/workflows/update-data.yml),
or locally with:

    export DATA_GOV_API_KEY=your_key_here
    python scripts/fetch_data.py
"""

import json
import os
import sys
from datetime import datetime, timezone, date

import requests

API_KEY = os.environ.get("DATA_GOV_API_KEY")
if not API_KEY:
    print("ERROR: DATA_GOV_API_KEY environment variable is not set.")
    sys.exit(1)

CURRENT_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
HIST_URL = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"

DATA_DIR = "data"
LATEST_FILE = os.path.join(DATA_DIR, "latest.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

TREND_DAYS_KEPT = 14       # keep a bit more than 7 so the frontend has slicing headroom
MAX_NEW_COMBOS_PER_RUN = 30  # cap backfill work per cron run to stay within rate limits


def fetch_current():
    params = {
        "api-key": API_KEY,
        "format": "json",
        "filters[state]": "Karnataka",
        "limit": 2000,
    }
    resp = requests.get(CURRENT_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("records", [])


def fetch_historical_paginated(filters, sort_field=None, max_pages=50):
    """Paginate through the historical resource (hard-capped at 10 records/request)."""
    records = []
    offset = 0
    page_size = 10

    while offset < max_pages * page_size:
        params = {
            "api-key": API_KEY,
            "format": "json",
            "limit": page_size,
            "offset": offset,
            **filters,
        }
        if sort_field:
            params[f"sort[{sort_field}]"] = "desc"

        resp = requests.get(HIST_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("records", [])
        if not rows:
            break

        records.extend(rows)
        total = int(data.get("total", len(rows)))
        offset += len(rows)
        if offset >= total:
            break

    return records


def normalize_current(r):
    return {
        "state": r.get("state"),
        "district": r.get("district"),
        "market": r.get("market"),
        "commodity": r.get("commodity"),
        "variety": r.get("variety"),
        "grade": r.get("grade"),
        "arrival_date": r.get("arrival_date"),
        "min_price": r.get("min_price"),
        "max_price": r.get("max_price"),
        "modal_price": r.get("modal_price"),
    }


def normalize_hist(r):
    return {
        "state": r.get("State"),
        "district": r.get("District"),
        "market": r.get("Market"),
        "commodity": r.get("Commodity"),
        "variety": r.get("Variety"),
        "grade": r.get("Grade"),
        "arrival_date": r.get("Arrival_Date"),
        "min_price": r.get("Min_Price"),
        "max_price": r.get("Max_Price"),
        "modal_price": r.get("Modal_Price"),
    }


def combo_key(r):
    return f"{r['commodity']}|{r['market']}|{r['district']}"


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def parse_ddmmyyyy(ds):
    d, m, y = ds.split("/")
    return date(int(y), int(m), int(d))


def append_snapshot_to_history(history, records):
    for r in records:
        if not r.get("commodity") or not r.get("market") or not r.get("district"):
            continue
        key = combo_key(r)
        history.setdefault(key, {})
        history[key][r["arrival_date"]] = {
            "min_price": r["min_price"],
            "max_price": r["max_price"],
            "modal_price": r["modal_price"],
        }
        if len(history[key]) > TREND_DAYS_KEPT:
            sorted_dates = sorted(history[key].keys(), key=parse_ddmmyyyy)
            for old_date in sorted_dates[:-TREND_DAYS_KEPT]:
                del history[key][old_date]
    return history


def bootstrap_missing_combos(history, current_records, max_new_combos=MAX_NEW_COMBOS_PER_RUN):
    """For combos with no history yet, backfill a few recent days from the historical API.
    Capped per run so a large batch of brand-new combos doesn't blow the rate limit."""
    new_count = 0
    for r in current_records:
        if not r.get("commodity") or not r.get("market") or not r.get("district"):
            continue
        key = combo_key(r)
        if key in history:
            continue
        if new_count >= max_new_combos:
            break

        rows = fetch_historical_paginated(
            {
                "filters[State]": "Karnataka",
                "filters[District]": r["district"],
                "filters[Commodity]": r["commodity"],
                "filters[Market]": r["market"],
            },
            sort_field="Arrival_Date",
            max_pages=3,
        )
        if rows:
            history.setdefault(key, {})
            for row in rows:
                nr = normalize_hist(row)
                history[key][nr["arrival_date"]] = {
                    "min_price": nr["min_price"],
                    "max_price": nr["max_price"],
                    "modal_price": nr["modal_price"],
                }
        new_count += 1

    print(f"Bootstrapped history for {new_count} new combo(s)")
    return history


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_history()

    current_raw = fetch_current()

    if current_raw:
        current = [normalize_current(r) for r in current_raw]
        payload = {
            "records": current,
            "source": "current",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        history = append_snapshot_to_history(history, current)
        history = bootstrap_missing_combos(history, current)

    else:
        print("Current resource returned no rows — falling back to historical latest date")
        latest = fetch_historical_paginated(
            {"filters[State]": "Karnataka"}, sort_field="Arrival_Date", max_pages=1
        )
        if not latest:
            print("No fallback data available either — leaving existing data/*.json unchanged")
            sys.exit(0)

        latest_date = latest[0]["Arrival_Date"]
        full_day_raw = fetch_historical_paginated(
            {"filters[State]": "Karnataka", "filters[Arrival_Date]": latest_date},
            max_pages=100,
        )
        full_day = [normalize_hist(r) for r in full_day_raw]

        payload = {
            "records": full_day,
            "source": "historical_fallback",
            "fallback_date": latest_date,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        history = append_snapshot_to_history(history, full_day)

    with open(LATEST_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    save_history(history)

    print(f"Wrote {len(payload['records'])} records (source: {payload['source']})")
    print(f"history.json now tracks {len(history)} commodity/market/district combos")


if __name__ == "__main__":
    main()
