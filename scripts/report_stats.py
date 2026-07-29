"""
Prints size and stats for data/live.json and data/history.json.

Run locally:
    python scripts/report_stats.py

Or add as a step in .github/workflows/update-data.yml, right after fetch_data.py,
to get a report in the Actions log on every cron run.
"""

import json
import os

HISTORY_FILE = "data/history.json"
LIVE_FILE = "data/live.json"


def human_size(num_bytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def main():
    print("=" * 50)
    print("MANDI DATA — STORAGE REPORT")
    print("=" * 50)

    if os.path.exists(LIVE_FILE):
        size = os.path.getsize(LIVE_FILE)
        with open(LIVE_FILE) as f:
            live = json.load(f)
        print(f"\nlive.json")
        print(f"  size: {human_size(size)}")
        print(f"  records: {len(live.get('records', []))}")
        print(f"  arrival_date: {live.get('arrival_date')}")
        print(f"  fetched_at: {live.get('fetched_at')}")
    else:
        print("\nlive.json — not found")

    if os.path.exists(HISTORY_FILE):
        size = os.path.getsize(HISTORY_FILE)
        with open(HISTORY_FILE) as f:
            history = json.load(f)

        day_count = len(history)
        total_records = sum(len(v) for v in history.values())

        print(f"\nhistory.json")
        print(f"  size: {human_size(size)}")
        print(f"  days cached: {day_count}")
        print(f"  dates: {', '.join(sorted(history.keys()))}")
        print(f"  total records across all days: {total_records}")
        if day_count:
            print(f"  avg records/day: {total_records / day_count:.1f}")
    else:
        print("\nhistory.json — not found")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
