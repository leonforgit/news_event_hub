# Contributing

Thanks for helping improve News Event Hub.

The project is an event-first news infrastructure layer. It collects source
outputs, normalizes articles, builds structured events, maps entities, and
exports consumer views. Contributions should keep that boundary clear:
repository code, schemas, small fixtures, and public-safe docs are public;
credentials, private runtime configuration, generated state, and raw upstream
payloads stay outside the repository.

## Development Setup

Use a local Python environment and install only the dependencies needed for the
area you are changing.

Typical local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Optional connectors may need additional packages such as `akshare` or
`playwright`. Keep connector credentials in your local environment, never in
Git.

## Validation

Run the checks relevant to your change:

```bash
python3 -m compileall -q scripts
python3 scripts/smoke_test_event_layer.py
python3 scripts/smoke_test_consumer_views.py
python3 scripts/smoke_test_live_collector.py
python3 scripts/smoke_test_fred_us_macro_import.py
```

Some integration checks require optional dependencies, credentials, browser
state, or a private runtime configured outside this repository. When those are
unavailable, describe the skipped check and run the closest synthetic smoke
fixture instead.

## Contribution Rules

- Keep changes focused and reviewable.
- Prefer existing schemas, source registry entries, contracts, and fixtures over
  new parallel abstractions.
- Add or update tests when changing ingestion, event merging, ranking, exports,
  source registry semantics, or security boundaries.
- Use synthetic sample data for fixtures. Do not add proprietary data dumps,
  paid-source archives, browser traces, cookies, raw-news corpora, generated
  feeds, or runtime databases.
- Do not commit credentials, SSH material, private hostnames, private ports,
  local absolute paths, or deployment-specific overrides.
- Update `README.md` and relevant docs when changing project structure,
  contracts, or operator workflow.

## Pull Request Checklist

Before opening a pull request:

- Run the relevant validation commands.
- Confirm that new files are intentionally tracked.
- Confirm that public docs do not expose private infrastructure, personal
  paths, credentials, or source terms that cannot be redistributed.
- Describe any skipped integration checks and why they were skipped.
