"""One-off backfill of subject-area (discipline) tags for existing jobs.

`jobs.category` only records the discipline facet a job was first scraped under,
so multi-discipline jobs were attributed to a single facet. The detail page lists
every subject area a job is tagged with; the daily enrichment now captures them
for new jobs. This script walks every job whose tags haven't been captured yet
(`jobs.disciplines_at IS NULL`) and fills `job_disciplines`.

jobs.ac.uk keeps a detail page for roughly 45 days after a job closes, then
answers with a redirect to /search/ whose query string still names the job's
discipline facets (minus display names). Jobs are processed newest-closing
first so the ones still serving a full page are captured before they age out.

Network failures leave a job unstamped (retried next run); a page that loads
but has no Subject Area(s) block is stamped with zero tags so it isn't
refetched forever.

Usage:
    python -m scripts.backfill_disciplines                # everything pending
    python -m scripts.backfill_disciplines --limit 500    # cap this run
    python -m scripts.backfill_disciplines --delay 2.0    # slower / more polite
    python -m scripts.backfill_disciplines --status       # coverage only, no fetching
"""

import argparse
import time

import requests

from db.queries import discipline_coverage, jobs_needing_disciplines, set_disciplines
from db.schema import init_db
from scraper.detail import enrich_url


def run_backfill(limit: int | None = None, delay: float = 1.0, verbose: bool = True) -> dict:
    pending = jobs_needing_disciplines(limit=limit)
    stats = {"attempted": 0, "detail": 0, "redirect": 0, "empty": 0, "failed": 0}
    total = len(pending)
    if not total:
        if verbose:
            print("Discipline backfill: nothing pending.")
        return stats
    if verbose:
        print(f"Discipline backfill: {total} job(s) to process (delay {delay}s)...")

    session = requests.Session()
    for i, job in enumerate(pending, 1):
        stats["attempted"] += 1
        data = enrich_url(job["url"], session=session)
        if data is None:
            stats["failed"] += 1
            tag = "FAIL"
        else:
            tags = data.get("disciplines") or []
            source = data.get("discipline_source", "detail")
            set_disciplines(job["job_id"], tags, source)
            if not tags:
                stats["empty"] += 1
            else:
                stats[source] += 1
            tag = f"{source}:{len(tags)}"
        if verbose and (i % 25 == 0 or i == total or tag == "FAIL"):
            print(f"  [{i}/{total}] {job['job_id']} -> {tag}", flush=True)
        if i < total:
            time.sleep(delay)

    if verbose:
        print(f"Discipline backfill done: {stats}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill job discipline tags from detail pages")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max jobs to fetch this run (default: all pending)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds to wait between requests (default: 1.0)")
    parser.add_argument("--status", action="store_true",
                        help="Print coverage and exit without fetching")
    args = parser.parse_args()

    init_db()  # ensures job_disciplines, disciplines_at and the views exist
    if not args.status:
        run_backfill(limit=args.limit, delay=args.delay)
    cov = discipline_coverage()
    print(f"\nCoverage: {cov['stamped']}/{cov['total_jobs']} jobs captured "
          f"({cov['pending']} pending); jobs by best source {cov['jobs_by_source']}; "
          f"{cov['multi_discipline_jobs']} jobs carry more than one academic discipline.")


if __name__ == "__main__":
    main()
