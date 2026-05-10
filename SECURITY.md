# Security Policy

This repository is open-source event infrastructure. It is intentionally
source-only: credentials, browser state, runtime databases, generated exports,
and deployment overrides must stay outside the repository.

## Supported Versions

The current supported line is `main`. Security fixes normally land on `main`
unless a future tagged release policy says otherwise.

## Reporting a Vulnerability

Please do not open a public issue that contains exploit details, API keys,
tokens, private server names, SSH material, personal paths, paid-source data, or
unpublished runtime outputs.

Use GitHub private vulnerability reporting or GitHub Security Advisories when
available. If that route is not available, contact the maintainers through a
private channel and share only the minimum reproduction details needed to
confirm the issue.

Useful reports include:

- A concise description of the affected component.
- The repository revision or release tag.
- Minimal steps to reproduce the issue with synthetic data.
- Whether the issue exposes credentials, private infrastructure, personal data,
  paid data, browser state, or raw upstream payloads.

## Secret and Infrastructure Boundary

This repository must not contain real credentials or private infrastructure
details. In particular, do not commit:

- API keys, access tokens, cookies, browser storage state, service account
  files, SMTP credentials, or `.env` files.
- SSH keys, SSH config, known-host files, hostnames, private IP addresses,
  private ports, jump-host details, or operator-specific deployment aliases.
- Local absolute paths, private runtime roots, production database files,
  generated state, logs, caches, exported feeds, or raw-news dumps.

Use environment variables or private runtime configuration outside the
repository for deployment-specific values. Public examples should stay generic
and synthetic.

Repository-level GitHub secret scanning and push protection should remain
enabled. Maintainers may also run private local checks outside this repository,
but operator-specific detection rules and personal infrastructure patterns
should not be committed here.

## Source and Data Notes

The project integrates optional APIs, public sources, browser-backed sources,
and generated event exports. Contributors must respect each source's terms, rate
limits, and redistribution limits. Do not add paid-source payloads, browser
session artifacts, or bulk raw-news corpora to the repository.
