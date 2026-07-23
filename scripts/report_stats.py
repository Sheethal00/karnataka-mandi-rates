"""
Prints size and growth stats for data/latest.json and data/history.json.

Run locally:
    python scripts/report_stats.py

Or add as a step in .github/workflows/update-data.yml, right after fetch_data.py,
to get a report in the Actions log on every cron run.
"""

import json
import os

HISTORY_FILE = "data/history.json"
LATEST_FILE = "data/latest.json"


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

    if os.path.exists(LATEST_FILE):
        size = os.path.getsize(LATEST_FILE)
        with open(LATEST_FILE) as f:
            latest = json.load(f)
        print(f"\nlatest.json")
        print(f"  size: {human_size(size)}")
        print(f"  records: {len(latest.get('records', []))}")
        print(f"  source: {latest.get('source')}")
        print(f"  fetched_at: {latest.get('fetched_at')}")
    else:
        print("\nlatest.json — not found")

    if os.path.exists(HISTORY_FILE):
        size = os.path.getsize(HISTORY_FILE)
        with open(HISTORY_FILE) as f:
            history = json.load(f)

        combo_count = len(history)
        total_day_entries = sum(len(days) for days in history.values())
        avg_days_per_combo = total_day_entries / combo_count if combo_count else 0

        combo_sizes = [(k, len(v)) for k, v in history.items()]
        combo_sizes.sort(key=lambda x: x[1])

        print(f"\nhistory.json")
        print(f"  size: {human_size(size)}")
        print(f"  unique combos: {combo_count}")
        print(f"  total (combo x day) entries: {total_day_entries}")
        print(f"  avg days tracked per combo: {avg_days_per_combo:.1f}")

        if combo_sizes:
            print(f"  least history: {combo_sizes[0][0]} ({combo_sizes[0][1]} days)")
            print(f"  most history: {combo_sizes[-1][0]} ({combo_sizes[-1][1]} days)")

        if avg_days_per_combo > 0 and avg_days_per_combo < 14:
            projected_full_size = size * (14 / avg_days_per_combo)
            print(f"  projected size once all combos reach 14 days: ~{human_size(projected_full_size)}")
    else:
        print("\nhistory.json — not found")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
