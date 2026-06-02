"""One-off backfill of detail-page enrichment for historical jobs.

The day-to-day scraper (`python -m scraper.run`) enriches up to ENRICH_LIMIT new
jobs each run. This script walks the whole backlog of un-enriched jobs so existing
rows get their closing date, contract type, hours, and location populated too.

It is just a thin, unbounded wrapper around `scraper.detail.run_enrichment`, so it
shares the same politeness (sequential, delayed, skip-already-enriched) behaviour.

Usage:
    python -m scripts.enrich_backfill                 # process all pending jobs
    python -m scripts.enrich_backfill --limit 50      # cap this run
    python -m scripts.enrich_backfill --delay 2.0     # slower / more polite
"""

import argparse

from db.schema import init_db
from scraper.detail import run_enrichment


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill detail-page enrichment")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max jobs to enrich this run (default: all pending)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds to wait between requests (default: 1.5)")
    parser.add_argument("--all", action="store_true",
                        help="Re-fetch jobs missing date_posted (one-off field backfill), "
                             "not just never-enriched ones")
    args = parser.parse_args()

    init_db()  # ensure the enrichment columns exist
    stats = run_enrichment(limit=args.limit, delay=args.delay, reenrich=args.all)
    print(f"\n{stats['attempted']} attempted, "
          f"{stats['enriched']} enriched, {stats['failed']} failed.")


if __name__ == "__main__":
    main()
