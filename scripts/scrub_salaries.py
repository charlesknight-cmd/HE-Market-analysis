"""One-off scrub of out-of-band stored salaries.

The salary parsers (`scraper.parser.parse_salary` and
`scraper.detail._parse_basesalary`) now reject any amount outside the plausible
annual band (`config.SALARY_FLOOR`..`config.SALARY_CEILING`). Rows inserted
before that guard existed can still hold junk — an hourly rate stored as annual
(£17), or a misparse like "£45,025" read as £4,502,500 — and a single such value
blows the y-axis on every box-plot / percentile / salary-range chart.

This script fixes only the offending rows. For each job whose stored
`salary_min` or `salary_max` falls outside the band, it re-derives the salary
from the persisted `salary_raw` using the now-band-aware `parse_salary` and
writes the corrected values back (often NULL, when the raw text has no
recoverable annual figure — the honest result, since the original number is
unrecoverable from a misparse).

Unlike `scripts.reparse` (which re-parses *every* row and would wipe ~20
legitimately-enriched salaries whose `salary_raw` doesn't parse), this touches
only the handful of genuinely out-of-band rows, leaving good data alone.

Usage:
    python -m scripts.scrub_salaries            # apply changes
    python -m scripts.scrub_salaries --dry-run  # report only, write nothing
"""

import argparse

from config import SALARY_CEILING, SALARY_FLOOR
from db.schema import get_connection
from scraper.parser import parse_salary


def _in_band(v: float | None) -> bool:
    """True if v is absent (nothing to police) or within the sane salary band."""
    return v is None or SALARY_FLOOR <= v <= SALARY_CEILING


def scrub_salaries(dry_run: bool = False) -> tuple[int, int]:
    """Correct rows whose stored salary falls outside the plausible band.

    Returns (rows_out_of_band, rows_changed).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT job_id, salary_raw, salary_min, salary_max FROM jobs "
            "WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL"
        ).fetchall()

        out_of_band = changed = 0
        for row in rows:
            if _in_band(row["salary_min"]) and _in_band(row["salary_max"]):
                continue
            out_of_band += 1

            new_min, new_max = parse_salary(row["salary_raw"])
            if new_min == row["salary_min"] and new_max == row["salary_max"]:
                continue  # nothing recoverable and already matches — leave it

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

    return out_of_band, changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrub out-of-band stored salaries")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the database",
    )
    args = parser.parse_args()

    out_of_band, changed = scrub_salaries(dry_run=args.dry_run)
    verb = "would be corrected" if args.dry_run else "corrected"
    print(
        f"\n{out_of_band} out-of-band row(s) found "
        f"(band £{SALARY_FLOOR:,}–£{SALARY_CEILING:,}); {changed} {verb}."
    )
    if args.dry_run and changed:
        print("Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
