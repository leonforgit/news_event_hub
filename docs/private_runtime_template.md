# Private Runtime Template

This document describes a public-safe deployment template for operators who want
to run `News Event Hub` outside the repository.

The paths below are examples, not required infrastructure and not a record of a
specific private machine. Replace them with your own runtime root, service
manager, database path, and credential storage.

## Example Runtime Layout

```text
/opt/news-event-hub/
  config/
    news_event_hub.env          # private, not committed
    schema.sql
    source_registry_v1.yaml
  scripts/
  state/
    news_event.db               # private runtime database
    consumer_exports/           # generated exports
  runtime/
  logs/
  cache/
```

Keep these outside Git:

- `.env` files and service credentials
- cookies and browser storage state
- SQLite databases and backups
- generated consumer exports
- logs, caches, replay progress databases, and raw upstream payloads

## Example Service Responsibilities

A private runtime usually needs four independent jobs:

- live collection into `news_articles`
- event building from recent article windows
- consumer export generation
- optional structured macro import or browser-backed signal collection

The repository includes systemd-style templates under `config/systemd/`, but
operators should review and adapt paths, users, permissions, timers, and
environment files before deployment.

## Public-Safe Validation

Before deploying, run local checks from the repository root:

```bash
python3 -m compileall -q scripts
python3 scripts/smoke_test_event_layer.py
python3 scripts/smoke_test_consumer_views.py
python3 scripts/smoke_test_live_collector.py
python3 scripts/smoke_test_fred_us_macro_import.py
```

For runtime health checks, use your own private host and paths. Do not paste
private hostnames, IP addresses, ports, SSH commands, cookies, database excerpts,
or raw provider payloads into public issues.
