"""
One-time backfill of data/history.json from manually downloaded per-district
CSVs (same shape as the historical-price API: Arrival_Date, Commodity,
District, Market, Max_Price, Min_Price, Modal_Price, ...).

Merges into the same combo_key (commodity|market|district) -> {date: prices}
shape that fetch_data.py maintains, last-row-wins per combo/date -- so it's
safe to run once to seed history ahead of the hourly cron, which will then
keep appending and trimming as usual.

Run locally:
    python scripts/backfill_history.py /path/to/csv/dir
"""

import csv
import glob
import json
import os
import sys

DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


def normalize_row(r):
    return {
        "district": r.get("District"),
        "market": r.get("Market"),
        "commodity": r.get("Commodity"),
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
                key = combo_key(r)
                history.setdefault(key, {})
                history[key][r["arrival_date"]] = {
                    "min_price": r["min_price"],
                    "max_price": r["max_price"],
                    "modal_price": r["modal_price"],
                }

    save_history(history)
    print(f"Processed {len(csv_files)} CSV file(s), {rows_seen} row(s), skipped {skipped} incomplete row(s)")
    print(f"history.json now tracks {len(history)} commodity/market/district combos")


if __name__ == "__main__":
    main()
