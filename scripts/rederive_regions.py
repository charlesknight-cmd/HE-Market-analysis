"""One-off re-derivation of `region` for jobs enrichment left NULL.

Enrichment used to read location only from the JobPosting JSON-LD. Enhanced
"campaign-site" adverts (employer microsites: XJTLU, UNNC, Auckland, UWS, BCU,
Rosalind Franklin ...) have no JSON-LD at all, so every one of them was stamped
enriched with region (and contract type / hours) NULL, and the International
count undercounted overseas employers. `scraper.detail.parse_detail` now falls
back to the advert's "Advert Details" table; this script applies that to the
rows already in the DB.

Two passes over jobs with region NULL (plus any --job-id given, e.g. a
multi-location advert whose region was taken from the wrong jobLocation entry):

1. Re-fetch the detail page (politely, sequentially) and re-parse it. Fills
   region, and contract_type / hours only where those are still NULL.
2. Jobs still unresolved (advert expired, fetch failed) take their
   institution's region when every other resolved advert from that institution
   shares one value (at least 2 of them) — e.g. all XJTLU adverts are
   International.

Dry run by default: prints every change and a summary, writes nothing.

Usage:
    python -m scripts.rederive_regions                    # dry run
    python -m scripts.rederive_regions --apply            # write changes
    python -m scripts.rederive_regions --job-id DSP263    # also re-check these
    python -m scripts.rederive_regions --db /tmp/snap.db  # run against a copy
"""

import argparse
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

import db.schema
from scraper.detail import enrich_url

MIN_SIBLINGS = 2


def _targets(conn, job_ids: list[str]) -> list[dict]:
    marks = ",".join("?" * len(job_ids))
    extra = f" OR job_id IN ({marks})" if job_ids else ""
    rows = conn.execute(
        "SELECT job_id, url, institution, region, contract_type, hours, date_posted "
        f"FROM jobs WHERE region IS NULL{extra} ORDER BY first_seen DESC",
        job_ids,
    ).fetchall()
    return [dict(r) for r in rows]


def _refetch(targets: list[dict], delay: float) -> dict[str, dict]:
    """Pass 1: job_id -> parsed page fields, for pages that yielded a region."""
    found, session = {}, requests.Session()
    for i, job in enumerate(targets, 1):
        data = enrich_url(job["url"], session=session)
        if data is None:
            tag = "FETCH FAILED"
        elif data["expired"]:
            tag = "expired"
        elif data["region"] is None:
            tag = "no location on page"
        else:
            found[job["job_id"]] = data
            tag = data["region"]
        print(f"  [{i}/{len(targets)}] {job['job_id']} {job['institution']}: {tag}")
        if i < len(targets):
            time.sleep(delay)
    return found


def _institution_consensus(conn, planned: dict[str, str]) -> dict[str, str]:
    """institution -> region, where all its resolved adverts agree (>= MIN_SIBLINGS)."""
    regions: dict[str, Counter] = defaultdict(Counter)
    rows = conn.execute("SELECT job_id, institution, region FROM jobs").fetchall()
    for r in rows:
        region = planned.get(r["job_id"], r["region"])
        if region is not None:
            regions[r["institution"]][region] += 1
    return {inst: next(iter(c)) for inst, c in regions.items()
            if len(c) == 1 and sum(c.values()) >= MIN_SIBLINGS}


def rederive_regions(job_ids: list[str], delay: float, apply: bool) -> Counter:
    with db.schema.get_connection() as conn:
        targets = _targets(conn, job_ids)
    print(f"{len(targets)} job(s) to re-derive (delay {delay}s)...")
    found = _refetch(targets, delay)

    with db.schema.get_connection() as conn:
        planned = {jid: d["region"] for jid, d in found.items()}
        consensus = _institution_consensus(conn, planned)

        summary: Counter = Counter()
        for job in targets:
            data = found.get(job["job_id"])
            if data:
                method, region = "page", data["region"]
                contract, hours = data["contract_type"], data["hours"]
            elif job["region"] is None and job["institution"] in consensus:
                method, region = "institution", consensus[job["institution"]]
                contract = hours = None
            else:
                summary["unresolved"] += 1
                print(f"  unresolved: {job['job_id']} {job['institution']}")
                continue
            if region == job["region"]:
                summary["unchanged"] += 1
                continue

            summary[f"via {method}"] += 1
            summary[f"-> {region}"] += 1
            if "2026-07-23" <= (job["date_posted"] or "") <= "2026-10-22":
                summary["in 2026-07-23..2026-10-22 window"] += 1
            if job["contract_type"] is None and contract:
                summary["contract_type filled"] += 1
            if job["hours"] is None and hours:
                summary["hours filled"] += 1
            print(f"  {job['job_id']} {job['institution']}: "
                  f"{job['region']} -> {region} ({method})")
            if apply:
                conn.execute(
                    "UPDATE jobs SET region = ?, "
                    "contract_type = COALESCE(contract_type, ?), "
                    "hours = COALESCE(hours, ?) WHERE job_id = ?",
                    (region, contract, hours, job["job_id"]),
                )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-derive NULL job regions")
    parser.add_argument("--apply", action="store_true",
                        help="Write the changes (default: dry run)")
    parser.add_argument("--job-id", action="append", default=[],
                        help="Also re-check this job even if its region is set (repeatable)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds to wait between requests (default: 1.5)")
    parser.add_argument("--db", type=Path, default=None,
                        help="Database file to use instead of config.DB_PATH")
    args = parser.parse_args()

    if args.db is not None:
        db.schema.DB_PATH = args.db
    summary = rederive_regions(args.job_id, args.delay, args.apply)
    print(f"\n{'APPLIED' if args.apply else 'DRY RUN (nothing written)'}:")
    for key, n in sorted(summary.items()):
        print(f"  {key}: {n}")


if __name__ == "__main__":
    main()
