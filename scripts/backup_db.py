"""Nightly backup of the SQLite job database.

The GitHub repo backs up the *code*; the collected data lives only in
`data/jobs.db` on the production server. This script takes a consistent,
compressed snapshot of it and rotates old snapshots.

It uses SQLite's online backup API (`Connection.backup`), which produces a
sound copy even while the scraper is writing and correctly folds in the WAL —
so it's safe to run against the live database (unlike a plain file copy).

Usage:
    python -m scripts.backup_db                  # snapshot + prune (>30 days)
    python -m scripts.backup_db --retain-days 60
    python -m scripts.backup_db --out /mnt/backups   # write elsewhere

Backups are named `jobs-YYYY-MM-DD.db.gz` in `backups/` (gitignored). Re-running
on the same day overwrites that day's file, so a daily cron keeps one per day.
"""

import argparse
import gzip
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config import DB_PATH

DEFAULT_DIR = Path(__file__).parent.parent / "backups"
DEFAULT_RETAIN_DAYS = 30


def _snapshot(src: Path, dest_gz: Path) -> int:
    """Write a consistent gzipped snapshot of `src` to `dest_gz`. Returns bytes written."""
    # Back up to a temp file first so a crash mid-write can't leave a half file
    # where the real backup should be.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp_path = Path(tmp.name)
    try:
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        try:
            dest_conn = sqlite3.connect(tmp_path)
            try:
                src_conn.backup(dest_conn)  # online, consistent, WAL-aware
            finally:
                dest_conn.close()
        finally:
            src_conn.close()

        dest_gz.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "rb") as f_in, gzip.open(dest_gz, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return dest_gz.stat().st_size
    finally:
        tmp_path.unlink(missing_ok=True)


def _prune(backup_dir: Path, retain_days: int) -> list[Path]:
    """Delete backups older than `retain_days`. Returns the removed paths."""
    cutoff = datetime.now(timezone.utc).timestamp() - retain_days * 86400
    removed = []
    for f in backup_dir.glob("jobs-*.db.gz"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed.append(f)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the SQLite job database")
    parser.add_argument("--out", type=Path, default=DEFAULT_DIR,
                        help=f"Directory for snapshots (default: {DEFAULT_DIR})")
    parser.add_argument("--retain-days", type=int, default=DEFAULT_RETAIN_DAYS,
                        help=f"Delete snapshots older than this (default: {DEFAULT_RETAIN_DAYS})")
    args = parser.parse_args()

    if not Path(DB_PATH).exists():
        raise SystemExit(f"Database not found at {DB_PATH} — nothing to back up.")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = args.out / f"jobs-{stamp}.db.gz"

    size = _snapshot(Path(DB_PATH), dest)
    print(f"Backed up {DB_PATH} -> {dest} ({size / 1024:.0f} KiB)")

    removed = _prune(args.out, args.retain_days)
    kept = sorted(args.out.glob("jobs-*.db.gz"))
    print(f"Retention: {len(kept)} snapshot(s) kept, {len(removed)} pruned "
          f"(>{args.retain_days} days).")


if __name__ == "__main__":
    main()
