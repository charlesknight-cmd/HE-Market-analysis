"""Entry point for the scraper.

Usage:
    python -m scraper.run           # run once and exit
    python -m scraper.run --daemon  # run once then repeat daily at SCHEDULE_TIME
"""

import argparse
import sys
from datetime import datetime, timezone

import schedule
import time

from config import SCHEDULE_TIME
from db.queries import bulk_upsert, existing_job_ids, log_run
from db.schema import init_db
from scraper.fetcher import fetch_all
from scraper.detail import run_enrichment

# Cap detail-page fetches per scrape so a backlog can't hammer the site in one run.
ENRICH_LIMIT = 200


def run_once(enrich: bool = True) -> None:
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[{started}] Starting scrape...")

    # Listings are newest-first, so passing the IDs we already hold lets each
    # category stop paging as soon as it reaches jobs we've seen before.
    results = fetch_all(known_ids=existing_job_ids())

    total_new = total_updated = total_found = 0
    for slug, (jobs, error) in results.items():
        if error:
            print(f"  {slug}: ERROR — {error}")
            log_run(slug, 0, 0, 0, "error", error)
            continue

        new_count, updated_count = bulk_upsert(jobs)
        total_found   += len(jobs)
        total_new     += new_count
        total_updated += updated_count

        print(
            f"  {slug}: {len(jobs)} jobs fetched, "
            f"{new_count} new, {updated_count} updated"
        )
        log_run(slug, len(jobs), new_count, updated_count, "ok")

    print(
        f"\nDone — {total_found} total, {total_new} new, {total_updated} updated.\n"
    )

    if enrich:
        run_enrichment(limit=ENRICH_LIMIT)


def run_daemon() -> None:
    print(f"Daemon mode: running now, then daily at {SCHEDULE_TIME}.")
    init_db()
    run_once()
    schedule.every().day.at(SCHEDULE_TIME).do(run_once)
    while True:
        schedule.run_pending()
        time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser(description="HE job market scraper")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help=f"Keep running and re-scrape daily at {SCHEDULE_TIME}",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip the detail-page enrichment step (listing scrape + upsert only)",
    )
    args = parser.parse_args()

    init_db()

    if args.daemon:
        run_daemon()
    else:
        run_once(enrich=not args.no_enrich)


if __name__ == "__main__":
    main()
