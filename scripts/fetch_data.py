"""
Fetches Karnataka mandi price data from data.gov.in's "current daily price"
resource and writes it to data/live.json (today's snapshot) and
data/history.json (a rolling 7-day window, keyed by ISO date, each holding
that day's full list of records).

The historical-price resource is intentionally never called here: it caps
responses at 10 records/request, so reconstructing one full day (~500+
records for Karnataka) would take dozens of paginated calls and risk the
API's rate limiter. Instead, history.json is built up incrementally, one day
at a time, purely from this daily current-price pull. If older days are ever
missing, backfilling is a manual/offline step (see backfill_history.py) --
not something this script does automatically.

The API's own `count` field is the signal for whether today's data has been
published yet. count == 0 means "not published" -- in that case this script
does nothing and leaves live.json / history.json exactly as they are, so the
site keeps serving the last successfully fetched day indefinitely until the
next real update arrives.

If today's (IST) date is already the newest entry in history.json, the
script skips calling the API at all -- there's nothing left to find until
the date rolls over, so there's no point spending a request just to confirm
that. This is what lets the cron poll hourly without hammering the API: once
a day's data is found, every remaining run that day is a free no-op.

Run via GitHub Actions on a schedule (see .github/workflows/update-data.yml),
or locally with:

    export DATA_GOV_API_KEY=your_key_here
    python scripts/fetch_data.py
"""

import json
import os
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import requests

IST = ZoneInfo("Asia/Kolkata")

API_KEY = os.environ.get("DATA_GOV_API_KEY")
if not API_KEY:
    print("ERROR: DATA_GOV_API_KEY environment variable is not set.")
    sys.exit(1)

CURRENT_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

# Some gov-hosted APIs silently stall requests without a browser-like
# User-Agent instead of rejecting them cleanly -- this header avoids that.
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"}

DATA_DIR = "data"
LIVE_FILE = os.path.join(DATA_DIR, "live.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

HISTORY_DAYS = 7

session = requests.Session()
session.headers.update(HEADERS)


def fetch_current(retries=3):
    """Returns (records, count). `count` is the API's own explicit signal
    for whether today's data has been published -- trusted over an empty
    records list, since that's the field the API actually uses to mean it."""
    params = {
        "api-key": API_KEY,
        "format": "json",
        "filters[state]": "Karnataka",
        "limit": 2000,
    }
    for attempt in range(retries):
        try:
            resp = session.get(CURRENT_URL, params=params, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            count = int(data.get("count", data.get("total", 0)) or 0)
            return data.get("records", []), count
        except requests.exceptions.RequestException as e:
            print(f"fetch_current attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    print("fetch_current: all retries failed, treating as not-yet-published")
    return [], 0


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


def parse_ddmmyyyy(ds):
    d, m, y = ds.split("/")
    return date(int(y), int(m), int(d))


def to_iso(ddmmyyyy):
    return parse_ddmmyyyy(ddmmyyyy).isoformat()


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def atomic_write(path, obj):
    """Write via a temp file + rename so a crash mid-write can never leave a
    truncated/corrupt JSON file in place."""
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def trim_to_last_n_days(history, n=HISTORY_DAYS):
    if len(history) <= n:
        return history
    keep = sorted(history.keys())[-n:]
    return {d: history[d] for d in keep}


def today_ist_iso():
    return datetime.now(IST).date().isoformat()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_json(HISTORY_FILE) or {}

    today = today_ist_iso()
    if today in history:
        print(f"Already have {today}'s data in history.json -- skipping API call")
        return

    raw_records, count = fetch_current()

    if count == 0:
        print("Current resource has not published today's data yet (count=0) -- leaving live.json and history.json untouched")
        return

    day_records = [normalize_current(r) for r in raw_records]
    dated_records = [r for r in day_records if r.get("arrival_date")]
    if not dated_records:
        print("Current resource reported count>0 but returned no usable records -- leaving live.json and history.json untouched")
        return

    arrival_date_iso = to_iso(dated_records[0]["arrival_date"])

    live_payload = {
        "records": day_records,
        "source": "current",
        "arrival_date": arrival_date_iso,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(LIVE_FILE, live_payload)

    history[arrival_date_iso] = dated_records
    history = trim_to_last_n_days(history)
    atomic_write(HISTORY_FILE, history)

    print(f"Wrote {len(day_records)} records for {arrival_date_iso} to live.json")
    print(f"history.json now holds {len(history)} day(s): {', '.join(sorted(history.keys()))}")


if __name__ == "__main__":
    main()
