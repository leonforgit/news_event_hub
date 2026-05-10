# STATUS

Updated: 2026-05-10

## Public Status

`News Event Hub` is public-ready open-source infrastructure for turning mixed
news feeds, official releases, optional API-backed sources, and early signal
sources into structured events and consumer exports.

The repository is source-only. It does not contain real API keys, cookies,
browser storage state, SSH material, production SQLite databases, generated
consumer exports, raw upstream payloads, or private deployment overrides.

## What Is In Place

- Open-source governance: `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, and
  `docs/public_release_checklist.md`.
- Secret boundary: source-only repository policy, `.gitignore`, public-safe
  smoke tests, and GitHub secret scanning / push protection.
- Source registry, SQLite schema, collector catalog, event builder, consumer
  export layer, replay helpers, and public-safe smoke tests.
- Optional connector support for API-backed and browser-backed sources, gated
  by local runtime configuration.
- Public-safe deployment templates. Paths under `/opt/...` are example
  conventions and must be overridden by operators for their own environments.

## Current Boundaries

- This project is not a newsletter generator, news reader, or investment
  decision system.
- Runtime databases, caches, logs, generated exports, browser auth state, and
  credentials belong outside Git.
- Optional sources must respect provider terms, rate limits, and redistribution
  limits.
- Public examples should use placeholders or synthetic fixtures.

## Validation

Recommended public-safe checks:

```bash
python3 -m compileall -q scripts
python3 scripts/smoke_test_event_layer.py
python3 scripts/smoke_test_consumer_views.py
python3 scripts/smoke_test_live_collector.py
python3 scripts/smoke_test_fred_us_macro_import.py
```

Integration checks that require private upstream services, credentials, browser
state, or generated production outputs should be run in the operator's private
runtime, not in this repository.
