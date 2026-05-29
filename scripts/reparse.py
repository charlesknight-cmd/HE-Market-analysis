"""Backfill re-parse of stored jobs.

Existing rows keep whatever salary the parser produced when they were first
inserted. `bulk_upsert` never re-derives salary on the UPDATE path, and most
jobs cycle out of the RSS top-20 before they're ever revisited — so an improved
parser does NOT retroactively fix old rows. This script walks every job, re-runs
the current `parse_salary` against the stored `salary_raw`, and writes back any
values that changed.

Only `salary_raw` is persisted (the raw HTML description is not), so salary is
the one field recoverable here. Run it once after any parser change.

Usage:
    python -m scripts.reparse            # apply changes
    python -m scripts.reparse --dry-run  # report what would change, write nothing
"""

import argparse

from db.schema import get_connection
from scraper.parser import parse_salary


def reparse_salaries(dry_run: bool = False) -> tuple[int, int]:
    """Re-derive salary_min/salary_max from salary_raw for every job.

    Returns (rows_examined, rows_changed).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT job_id, salary_raw, salary_min, salary_max FROM jobs"
        ).fetchall()

        changed = 0
        for row in rows:
            new_min, new_max = parse_salary(row["salary_raw"])
            if new_min == row["salary_min"] and new_max == row["salary_max"]:
                continue

            changed += 1
            print(
                f"  {row['job_id']}: "
                f"({row['salary_min']}, {row['salary_max']}) -> ({new_min}, {new_max})"
                f"  [{row['salary_raw']!r}]"
            )
            if not dry_run:
                conn.execute(
                    "UPDATE jobs SET salary_min = ?, salary_max = ? WHERE job_id = ?",
                    (new_min, new_max, row["job_id"]),
                )

        if not dry_run:
            conn.commit()

    return len(rows), changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-parse stored job salaries")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the database",
    )
    args = parser.parse_args()

    examined, changed = reparse_salaries(dry_run=args.dry_run)
    verb = "would change" if args.dry_run else "changed"
    print(f"\n{examined} jobs examined, {changed} {verb}.")
    if args.dry_run and changed:
        print("Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
