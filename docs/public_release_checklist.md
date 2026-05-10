# Public Release Checklist

This checklist must pass before changing the GitHub repository from private to
public.

## Repository Visibility

- Keep the repository private until every item below is complete.
- Enable GitHub secret scanning and push protection where available.
- Confirm the default branch only contains sanitized public-ready history.

## Secret Hygiene

GitHub secret scanning and push protection must be enabled before release.
Maintainers should run any operator-specific local scans outside this
repository, because private detection rules can themselves expose personal
infrastructure details if committed.

Review current files and reachable Git history for credentials, cookies,
browser state, runtime state, production databases, SSH material, private
hosts, private IP addresses, private ports, personal paths, or deployment
aliases. Any finding is a release blocker.

## Private Runtime Review

Review the current tree and reachable history for private infrastructure terms
before release. The public repository should not expose:

- SSH keys, SSH config, known-host files, hostnames, private IP addresses,
  private ports, jump-host details, or operator-specific aliases.
- Local absolute paths, real private runtime roots, production database paths,
  or machine-specific service templates. Generic example paths such as
  `/opt/news-event-hub` are acceptable only when they are clearly documented as
  operator-replaceable templates and contain no hostname, IP address, SSH
  detail, account name, secret, or production output.
- Browser auth state, cookies, generated event exports, logs, caches, or raw
  upstream payloads.

If these details are needed for operations, move them to private deployment
notes or template them with generic placeholders before public release.

## Documentation and Governance

- `README.md` explains the public value proposition and security boundary.
- `LICENSE` is present and matches the intended open-source license.
- `SECURITY.md` explains private vulnerability reporting and the no-secrets
  issue policy.
- `CONTRIBUTING.md` explains development checks and data boundaries.
- Runtime docs and service templates are public-safe or clearly separated into
  private-only deployment material.

## Functional Smoke Checks

Run public-safe smoke checks:

```bash
python3 -m compileall -q scripts
python3 scripts/smoke_test_event_layer.py
python3 scripts/smoke_test_consumer_views.py
python3 scripts/smoke_test_live_collector.py
python3 scripts/smoke_test_fred_us_macro_import.py
```

If an integration check requires private upstream services, credentials, browser
state, or optional packages, document the skip and run the closest synthetic
fixture instead.

## Final Review

- Review the GitHub repository page while it is still private.
- Review Actions logs for accidental path, host, token, or source-term exposure.
- Check that issues, pull request templates, and examples do not invite users to
  paste secrets into public threads.
- Only switch visibility after the maintainers agree that both current content
  and reachable history are public-safe.
