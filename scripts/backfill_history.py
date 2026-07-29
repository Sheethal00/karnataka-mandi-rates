"""
Manual, offline backfill of data/history.json from a folder of manually
downloaded per-district CSVs (same columns as the government's data
exports: Arrival_Date, Commodity, District, Market, Max_Price, Min_Price,
Modal_Price, ...).

This never calls any data.gov.in API -- it only reads local CSV files. It
exists because the pipeline itself (scripts/fetch_data.py) intentionally
never calls the rate-limited, 10-records-per-request historical API, so if
history.json is ever missing days (e.g. after a long outage), the only way
to fill the gap is a manual CSV import like this one.

Merges into the same {iso_date: [full day's records]} shape that
fetch_data.py maintains -- upserting each CSV's date (overwriting if that
date is already present), then trimming to the most recent 7 days. Safe to
run any time; running it again with the same CSVs is a no-op.

Run locally:
    python scripts/backfill_history.py /path/to/csv/dir
"""

import csv
import glob
import json
import os
import sys
from datetime import date

DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HISTORY_DAYS = 7


def parse_ddmmyyyy(ds):
    d, m, y = ds.split("/")
    return date(int(y), int(m), int(d))


def to_iso(ddmmyyyy):
    return parse_ddmmyyyy(ddmmyyyy).isoformat()


def normalize_row(r):
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


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def trim_to_last_n_days(history, n=HISTORY_DAYS):
    if len(history) <= n:
        return history
    keep = sorted(history.keys())[-n:]
    return {d: history[d] for d in keep}


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/backfill_history.py /path/to/csv/dir")
        sys.exit(1)

    csv_dir = sys.argv[1]
    csv_files = sorted(glob.glob(os.path.join(csv_dir, "*.csv")))
    if not csv_files:
        print(f"No CSV files found in {csv_dir}")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_history()

    by_date = {}
    rows_seen = 0
    skipped = 0
    for path in csv_files:
        with open(path, newline="") as f:
            for raw in csv.DictReader(f):
                rows_seen += 1
                r = normalize_row(raw)
                if not r["commodity"] or not r["market"] or not r["district"] or not r["arrival_date"]:
                    skipped += 1
                    continue
                iso = to_iso(r["arrival_date"])
                by_date.setdefault(iso, []).append(r)

    for iso, records in by_date.items():
        history[iso] = records  # upsert: overwrite this date wholesale, no de-dup needed

    history = trim_to_last_n_days(history)
    save_history(history)

    print(f"Processed {len(csv_files)} CSV file(s), {rows_seen} row(s), skipped {skipped} incomplete row(s)")
    print(f"history.json now holds {len(history)} day(s): {', '.join(sorted(history.keys()))}")


if __name__ == "__main__":
    main()
