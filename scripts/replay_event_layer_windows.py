#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "runtime" / "news_event.db"
DEFAULT_PROGRESS_DB = ROOT / "runtime" / "event_layer_replay_progress.db"
DEFAULT_BUILDER = ROOT / "scripts" / "build_event_layer.py"
DEFAULT_CONSUMER_EXPORT = ROOT / "scripts" / "export_consumer_views.py"
DEFAULT_EXCLUDED_SOURCE_IDS = ("akshare_stock_notice_report",)
METRIC_RE = re.compile(r"^(article_candidates|articles_processed|events_built|events_ranked_positive|window_snapshots_written):\s*(\d+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ReplayWindow:
    granularity: str
    label: str
    start: date
    end: date

    @property
    def start_arg(self) -> str:
        return self.start.isoformat()

    @property
    def end_arg(self) -> str:
        return self.end.isoformat()

    @property
    def as_of_arg(self) -> str:
        return datetime.combine(self.end, datetime.min.time(), tzinfo=timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay event-layer windows into durable window snapshots.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite news_event.db path.")
    parser.add_argument("--progress-db", type=Path, default=DEFAULT_PROGRESS_DB, help="SQLite progress database for resumable replay.")
    parser.add_argument("--builder", type=Path, default=DEFAULT_BUILDER, help="Path to build_event_layer.py.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Exclusive end date, YYYY-MM-DD.")
    parser.add_argument("--cadence", choices=("day", "rolling3", "week", "month", "year"), required=True)
    parser.add_argument("--max-article-count", type=int, default=50000, help="Abort a window before writing when article candidates exceed this count.")
    parser.add_argument("--limit-articles", type=int, default=0, help="Optional builder-side article limit; 0 disables.")
    parser.add_argument("--include-source-id", action="append", default=[], help="Only include this source_id. Repeatable.")
    parser.add_argument("--exclude-source-id", action="append", default=[], help="Exclude this source_id. Repeatable.")
    parser.add_argument("--include-stock-notice", action="store_true", help="Do not apply the default stock-notice exclusion.")
    parser.add_argument("--mutate-core", action="store_true", help="Also update core events/article links. Only allowed for day cadence.")
    parser.add_argument("--rerun", action="store_true", help="Rerun windows already marked ok.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned windows and builder commands without running them.")
    parser.add_argument("--max-windows", type=int, default=0, help="Run at most this many windows; 0 disables.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Sleep between windows.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first failed window.")
    parser.add_argument("--run-consumer-export", action="store_true", help="Run export_consumer_views.py after successful replay.")
    parser.add_argument("--consumer-export-script", type=Path, default=DEFAULT_CONSUMER_EXPORT)
    return parser.parse_args()


def parse_date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"invalid date: {value}") from exc


def month_start(value: date) -> date:
    return value.replace(day=1)


def next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def next_year(value: date) -> date:
    return date(value.year + 1, 1, 1)


def iter_windows(cadence: str, start: date, end: date) -> Iterable[ReplayWindow]:
    if start >= end:
        return
    if cadence == "day":
        cursor = start
        while cursor < end:
            window_end = cursor + timedelta(days=1)
            yield ReplayWindow("day", f"day:{cursor.isoformat()}", cursor, min(window_end, end))
            cursor = window_end
        return
    if cadence == "rolling3":
        cursor = start
        while cursor < end:
            window_start = max(start, cursor - timedelta(days=2))
            window_end = min(cursor + timedelta(days=1), end)
            yield ReplayWindow("rolling3", f"rolling3:{cursor.isoformat()}", window_start, window_end)
            cursor += timedelta(days=1)
        return
    if cadence == "week":
        cursor = start - timedelta(days=start.weekday())
        while cursor < end:
            window_start = max(cursor, start)
            window_end = min(cursor + timedelta(days=7), end)
            iso_year, iso_week, _ = cursor.isocalendar()
            yield ReplayWindow("week", f"week:{iso_year}-W{iso_week:02d}", window_start, window_end)
            cursor += timedelta(days=7)
        return
    if cadence == "month":
        cursor = month_start(start)
        while cursor < end:
            window_start = max(cursor, start)
            window_end = min(next_month(cursor), end)
            yield ReplayWindow("month", f"month:{cursor:%Y-%m}", window_start, window_end)
            cursor = next_month(cursor)
        return
    if cadence == "year":
        cursor = date(start.year, 1, 1)
        while cursor < end:
            window_start = max(cursor, start)
            window_end = min(next_year(cursor), end)
            yield ReplayWindow("year", f"year:{cursor:%Y}", window_start, window_end)
            cursor = next_year(cursor)
        return
    raise ValueError(f"unsupported cadence: {cadence}")


def ensure_progress_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_windows (
            run_key              TEXT PRIMARY KEY,
            db_path              TEXT NOT NULL,
            cadence              TEXT NOT NULL,
            window_granularity   TEXT NOT NULL,
            window_label         TEXT NOT NULL,
            window_start         TEXT NOT NULL,
            window_end           TEXT NOT NULL,
            status               TEXT NOT NULL,
            attempts             INTEGER NOT NULL DEFAULT 0,
            started_at           TEXT,
            finished_at          TEXT,
            returncode           INTEGER,
            article_candidates   INTEGER,
            articles_processed   INTEGER,
            events_built         INTEGER,
            events_ranked_positive INTEGER,
            window_snapshots_written INTEGER,
            stdout_tail          TEXT,
            stderr_tail          TEXT,
            command              TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_windows_status ON replay_windows (status, cadence, window_start)")
    conn.commit()


def run_key_for(db: Path, cadence: str, window: ReplayWindow, include_sources: list[str], exclude_sources: list[str], mutate_core: bool) -> str:
    payload = "|".join(
        [
            str(db.resolve()),
            cadence,
            window.granularity,
            window.label,
            window.start_arg,
            window.end_arg,
            ",".join(sorted(include_sources)),
            ",".join(sorted(exclude_sources)),
            "mutate_core" if mutate_core else "snapshot_only",
        ]
    )
    return "erw_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def existing_status(conn: sqlite3.Connection, run_key: str) -> tuple[str, int] | None:
    row = conn.execute("SELECT status, attempts FROM replay_windows WHERE run_key = ?", (run_key,)).fetchone()
    if not row:
        return None
    return str(row[0]), int(row[1] or 0)


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mark_started(conn: sqlite3.Connection, run_key: str, db: Path, cadence: str, window: ReplayWindow, attempts: int, command: list[str]) -> None:
    conn.execute(
        """
        INSERT INTO replay_windows (
            run_key, db_path, cadence, window_granularity, window_label, window_start, window_end,
            status, attempts, started_at, command
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
        ON CONFLICT(run_key) DO UPDATE SET
            status = 'running',
            attempts = excluded.attempts,
            started_at = excluded.started_at,
            finished_at = NULL,
            returncode = NULL,
            command = excluded.command
        """,
        (
            run_key,
            str(db),
            cadence,
            window.granularity,
            window.label,
            window.start_arg,
            window.end_arg,
            attempts,
            utc_now_text(),
            " ".join(command),
        ),
    )
    conn.commit()


def parse_metrics(stdout: str) -> dict[str, int]:
    return {key: int(value) for key, value in METRIC_RE.findall(stdout)}


def tail(value: str, max_chars: int = 4000) -> str:
    return value[-max_chars:] if len(value) > max_chars else value


def mark_finished(conn: sqlite3.Connection, run_key: str, status: str, proc: subprocess.CompletedProcess[str]) -> dict[str, int]:
    metrics = parse_metrics(proc.stdout or "")
    conn.execute(
        """
        UPDATE replay_windows
        SET status = ?,
            finished_at = ?,
            returncode = ?,
            article_candidates = ?,
            articles_processed = ?,
            events_built = ?,
            events_ranked_positive = ?,
            window_snapshots_written = ?,
            stdout_tail = ?,
            stderr_tail = ?
        WHERE run_key = ?
        """,
        (
            status,
            utc_now_text(),
            int(proc.returncode),
            metrics.get("article_candidates"),
            metrics.get("articles_processed"),
            metrics.get("events_built"),
            metrics.get("events_ranked_positive"),
            metrics.get("window_snapshots_written"),
            tail(proc.stdout or ""),
            tail(proc.stderr or ""),
            run_key,
        ),
    )
    conn.commit()
    return metrics


def source_filters(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    include_sources = [item.strip() for item in args.include_source_id if item.strip()]
    exclude_sources = [item.strip() for item in args.exclude_source_id if item.strip()]
    if not args.include_stock_notice:
        for source_id in DEFAULT_EXCLUDED_SOURCE_IDS:
            if source_id not in exclude_sources:
                exclude_sources.append(source_id)
    return include_sources, exclude_sources


def build_command(args: argparse.Namespace, window: ReplayWindow, include_sources: list[str], exclude_sources: list[str]) -> list[str]:
    command = [
        sys.executable,
        str(args.builder),
        "--db",
        str(args.db),
        "--window-start",
        window.start_arg,
        "--window-end",
        window.end_arg,
        "--as-of",
        window.as_of_arg,
        "--window-granularity",
        window.granularity,
        "--window-label",
        window.label,
        "--slice-safe",
        "--max-article-count",
        str(max(args.max_article_count, 0)),
    ]
    if not args.mutate_core:
        command.append("--snapshot-only")
    if args.limit_articles > 0:
        command.extend(["--limit-articles", str(args.limit_articles)])
    for source_id in include_sources:
        command.extend(["--include-source-id", source_id])
    for source_id in exclude_sources:
        command.extend(["--exclude-source-id", source_id])
    return command


def run_consumer_export(args: argparse.Namespace) -> None:
    command = [sys.executable, str(args.consumer_export_script), "--db", str(args.db)]
    proc = subprocess.run(command, text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"consumer export failed rc={proc.returncode}\n{tail(proc.stderr or proc.stdout)}")
    print("consumer_export: ok")


def main() -> None:
    args = parse_args()
    start = parse_date_arg(args.start_date)
    end = parse_date_arg(args.end_date)
    if start >= end:
        raise SystemExit("--start-date must be earlier than --end-date")
    if args.max_article_count < 0:
        raise SystemExit("--max-article-count must be non-negative")
    if args.limit_articles < 0:
        raise SystemExit("--limit-articles must be non-negative")
    if args.sleep_seconds < 0:
        raise SystemExit("--sleep-seconds must be non-negative")
    if args.mutate_core and args.cadence != "day":
        raise SystemExit("--mutate-core is only allowed for day cadence")

    include_sources, exclude_sources = source_filters(args)
    windows = list(iter_windows(args.cadence, start, end))
    if args.max_windows > 0:
        windows = windows[: args.max_windows]
    if not windows:
        print("windows_planned: 0")
        return

    args.progress_db.parent.mkdir(parents=True, exist_ok=True)
    progress_conn = sqlite3.connect(args.progress_db)
    ensure_progress_schema(progress_conn)

    try:
        print(f"windows_planned: {len(windows)}")
        ok_count = 0
        skipped_count = 0
        failed_count = 0
        for index, window in enumerate(windows, start=1):
            run_key = run_key_for(args.db, args.cadence, window, include_sources, exclude_sources, bool(args.mutate_core))
            status_attempts = existing_status(progress_conn, run_key)
            if status_attempts and status_attempts[0] == "ok" and not args.rerun:
                skipped_count += 1
                print(f"[{index}/{len(windows)}] skip ok {window.label} {window.start_arg}->{window.end_arg}")
                continue
            attempts = (status_attempts[1] if status_attempts else 0) + 1
            command = build_command(args, window, include_sources, exclude_sources)
            print(f"[{index}/{len(windows)}] run {window.label} {window.start_arg}->{window.end_arg}")
            if args.dry_run:
                print("  " + " ".join(command))
                continue
            mark_started(progress_conn, run_key, args.db, args.cadence, window, attempts, command)
            proc = subprocess.run(command, text=True, capture_output=True)
            status = "ok" if proc.returncode == 0 else "error"
            metrics = mark_finished(progress_conn, run_key, status, proc)
            if proc.returncode == 0:
                ok_count += 1
                print(
                    "  ok "
                    f"articles={metrics.get('articles_processed', 0)} "
                    f"events={metrics.get('events_built', 0)} "
                    f"snapshots={metrics.get('window_snapshots_written', 0)}"
                )
            else:
                failed_count += 1
                print(f"  error rc={proc.returncode} {tail(proc.stderr or proc.stdout, 1000)}")
                if args.stop_on_error:
                    break
            if args.sleep_seconds > 0 and index < len(windows):
                time.sleep(args.sleep_seconds)
        print(f"summary: ok={ok_count} skipped={skipped_count} failed={failed_count}")
        if failed_count == 0 and args.run_consumer_export and not args.dry_run:
            run_consumer_export(args)
    finally:
        progress_conn.close()


if __name__ == "__main__":
    main()
