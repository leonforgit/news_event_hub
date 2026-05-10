<!-- codex-workspace-bootstrap:managed -->
# AGENTS.md

This directory contains the stable entrypoints and helper scripts for the workspace.

## Stable Entry Points

- `check_git_hygiene.py`: audit working tree cleanliness and in-progress Git operations.
- `checkpoint_commit.py`: create a scoped checkpoint commit without sweeping unrelated dirty paths.
- `close_git_thread.py`: fast-forward back to the base branch after the temporary branch is clean.
- `init_unified_news_db.py`: initialize `news_event.db` and seed `source_registry`.
- `backfill_tracker_articles.py`: backfill article-layer content from legacy `investment_tracker.db`.
- `backfill_historical_news_sources.py`: backfill date-addressable article sources. For large runs, keep A-share announcement/CNINFO sources separate from slow `akshare_news_cctv`, and pause event-layer rebuilds while article backfill is active.
- `build_event_layer.py`: build online events from a bounded article window. Keep the systemd service on the small online profile (`--lookback-days 1 --exclude-source-id akshare_stock_notice_report --max-article-count 50000 --slice-safe`); use `--window-start/--window-end` only through stable replay wrappers when possible.
- `replay_event_layer_windows.py`: resumable event-layer replay for `day / rolling3 / week / month / year`. Default behavior writes `event_window_snapshots` without mutating the online `events` table; use `--mutate-core` only for short `day` windows that intentionally repair core event links.
- `import_fred_us_macro_open_data.py`: import structured FRED U.S. macro release events into the shared article/event pipeline without committing upstream JSON data.
- `deploy_runtime_fred_macro_import.sh`: deploy the FRED macro importer and its systemd timer to `private runtime`.
- `deploy_runtime_unified_news_db.sh`: deploy schema / source registry / init script to `private runtime`.
- Add stable wrappers here for the workflows you want Codex to use first.

## Validation Expectations

- Default to no-send, no-publish, and no-payment flows while testing.
