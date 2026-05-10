#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
IMPORT_SCRIPT = ROOT / "scripts" / "import_fred_us_macro_open_data.py"
EVENT_LAYER_SCRIPT = ROOT / "scripts" / "build_event_layer.py"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cpi_release = now - timedelta(hours=2)
    claims_release = now - timedelta(days=1)

    events_payload = {
        "generatedAt": iso(now),
        "sourceId": "fred-us-macro",
        "events": [
            {
                "id": "fred-CPIAUCNS-test",
                "createdAt": iso(cpi_release),
                "primaryCategory": "macro_inflation",
                "sourceId": "fred-us-macro",
                "sourceLabel": "FRED US Macro",
                "textEn": "U.S. CPI YoY (CPIAUCNS) released for 2026-03-01: actual 3.1%, previous 3.0%.",
                "textZh": "美国 CPI 年率（CPIAUCNS）公布：2026-03-01 实际 3.1%，前值 3.0%。",
                "url": "https://fred.stlouisfed.org/series/CPIAUCNS",
                "metadata": {
                    "seriesId": "CPIAUCNS",
                    "observationDate": "2026-03-01",
                    "releaseDateApproximate": False,
                    "value": 3.1,
                    "valueKind": "yoy_pct",
                    "valueUnit": "%",
                    "consensus": {
                        "actual": 3.1,
                        "forecast": 3.0,
                        "previous": 3.0,
                        "surprise": 0.1,
                        "unit": "%",
                        "sourceId": "investing-economic-calendar",
                    },
                },
            },
            {
                "id": "fred-ICSA-test",
                "createdAt": iso(claims_release),
                "primaryCategory": "macro_labor",
                "sourceId": "fred-us-macro",
                "sourceLabel": "FRED US Macro",
                "textEn": "U.S. Initial Jobless Claims (ICSA) released for 2026-04-18: actual 214,000, previous 208,000.",
                "textZh": "美国 初请失业金人数（ICSA）公布：2026-04-18 实际 214,000，前值 208,000。",
                "url": "https://fred.stlouisfed.org/series/ICSA",
                "metadata": {
                    "seriesId": "ICSA",
                    "observationDate": "2026-04-18",
                    "releaseDateApproximate": True,
                    "value": 214000,
                    "valueKind": "level",
                    "valueUnit": "Number",
                },
            },
        ],
    }
    metadata_payload = {
        "generatedAt": iso(now),
        "repoPurpose": "Core high-impact U.S. macro history and replay-ready market event data sourced from FRED.",
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "news_event.db"
        events_file = tmp_path / "events.json"
        metadata_file = tmp_path / "metadata.json"
        events_file.write_text(json.dumps(events_payload, ensure_ascii=False), encoding="utf-8")
        metadata_file.write_text(json.dumps(metadata_payload, ensure_ascii=False), encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(IMPORT_SCRIPT),
                "--db",
                str(db_path),
                "--events-file",
                str(events_file),
                "--metadata-file",
                str(metadata_file),
                "--lookback-days",
                "0",
            ],
            check=True,
            cwd=ROOT,
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            article_count = conn.execute("SELECT COUNT(*) FROM news_articles WHERE source_id = 'fred_us_macro_open_data'").fetchone()[0]
            assert_true(article_count == 2, "importer should persist both structured macro events as articles")
            qualities = {
                row["title"]: row["timestamp_quality"]
                for row in conn.execute(
                    "SELECT title, timestamp_quality FROM news_articles WHERE source_id = 'fred_us_macro_open_data'"
                )
            }
            assert_true(any(value == "exact" for value in qualities.values()), "exact release timestamps should be preserved")
            assert_true(any(value == "estimated" for value in qualities.values()), "approximate release timestamps should be marked estimated")
            body = conn.execute(
                "SELECT body_text FROM news_articles WHERE title LIKE '%CPI%' LIMIT 1"
            ).fetchone()[0]
            body_payload = json.loads(body)
            assert_true(
                body_payload["event"]["metadata"]["consensus"]["surprise"] == 0.1,
                "consensus surprise should remain in structured body_text JSON",
            )
        finally:
            conn.close()

        subprocess.run(
            [
                sys.executable,
                str(EVENT_LAYER_SCRIPT),
                "--db",
                str(db_path),
                "--lookback-days",
                "0",
            ],
            check=True,
            cwd=ROOT,
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            event_rows = conn.execute(
                "SELECT event_type, event_state, event_rank_flags FROM events ORDER BY event_title"
            ).fetchall()
            assert_true(len(event_rows) == 2, "event layer should convert imported macro articles into events")
            assert_true(all(row["event_type"] == "macro_data" for row in event_rows), "FRED releases should classify as macro_data")
            assert_true(
                any(json.loads(row["event_rank_flags"])["action_key"] == "macro_release" for row in event_rows),
                "structured macro releases should use macro_release action key",
            )
            macro_themes = {
                row["entity_name"]
                for row in conn.execute(
                    "SELECT entity_name FROM event_entity_links WHERE entity_type = 'macro_theme'"
                )
            }
            assert_true("通胀" in macro_themes, "CPI release should map to inflation macro theme")
            assert_true("美国就业" in macro_themes, "jobless claims release should map to labor macro theme")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
