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

The API's own `total` field is the signal for whether today's data has been
published yet. total == 0 means "not published" -- in that case this script
does nothing and leaves live.json / history.json exactly as they are, so the
site keeps serving the last successfully fetched day indefinitely until the
next real update arrives.

A day's data is NOT published all at once: markets report in through the
day, so an early-morning pull sees only a fraction of the eventual total
(e.g. 162 rows at 07:00 UTC vs 435+ by evening). So every cron run re-pulls
the current day rather than stopping once that date is present -- and the
stored day is replaced only when the fresh pull has *more* records than
what's already on disk. That "only grows" rule is what keeps a partial
morning snapshot from clobbering a fuller set (including one written by
hand via backfill_from_api.py), while still letting the day fill out.

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

import requests

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

# The API silently caps `limit` per request, so a single call can come back
# short even when it reports a larger `total` -- always page until `total`
# rows are collected rather than trusting one response to hold everything.
PAGE_SIZE = 1000
MAX_PAGES = 10

session = requests.Session()
session.headers.update(HEADERS)


def fetch_page(offset, retries=3):
    """Returns (records, total) for one page, or (None, 0) if every retry
    failed. `total` is the API's own count of all rows matching the filter,
    which is what tells us whether today's data has been published at all."""
    params = {
        "api-key": API_KEY,
        "format": "json",
        "filters[state]": "Karnataka",
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    for attempt in range(retries):
        try:
            resp = session.get(CURRENT_URL, params=params, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("records", [])
            total = int(data.get("total", len(records)) or 0)
            return records, total
        except requests.exceptions.RequestException as e:
            print(f"fetch page at offset {offset}, attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    return None, 0


def fetch_current():
    """Returns (records, total) for the whole current-price result set."""
    records = []
    total = 0
    for page in range(MAX_PAGES):
        rows, page_total = fetch_page(len(records))
        if rows is None:
            # A mid-pagination failure would hand back a truncated day that
            # could still look "bigger" than a real earlier pull, so bail out
            # entirely and let the next cron run retry from scratch.
            print("fetch_current: request failed, treating as not-yet-published")
            return [], 0
        total = max(total, page_total)
        records.extend(rows)
        if not rows or len(records) >= total:
            break
    else:
        print(f"fetch_current: hit the {MAX_PAGES}-page ceiling with {len(records)}/{total} records")
    return records, total


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


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_json(HISTORY_FILE) or {}

    raw_records, total = fetch_current()

    if total == 0:
        print("Current resource has not published today's data yet (total=0) -- leaving live.json and history.json untouched")
        return

    day_records = [normalize_current(r) for r in raw_records]
    dated_records = [r for r in day_records if r.get("arrival_date")]
    if not dated_records:
        print("Current resource reported total>0 but returned no usable records -- leaving live.json and history.json untouched")
        return

    arrival_date_iso = to_iso(dated_records[0]["arrival_date"])

    # Markets report in through the day, so re-running is how a day fills
    # out -- but only ever upward, never replacing a fuller set with a
    # partial one.
    have = len(history.get(arrival_date_iso, []))
    if have >= len(dated_records):
        print(f"Already have {have} record(s) for {arrival_date_iso}; fetch returned {len(dated_records)} -- leaving live.json and history.json untouched")
        return

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

    print(f"Wrote {len(day_records)} records for {arrival_date_iso} to live.json (was {have})")
    print(f"history.json now holds {len(history)} day(s): {', '.join(sorted(history.keys()))}")


if __name__ == "__main__":
    main()
