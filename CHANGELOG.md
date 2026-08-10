# Changelog

All notable changes to little-sister-wiz, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/). These notes are for the
deployments that install this package, not a work log.

Treat **a new or renamed `type:` name, a changed slug shape, or a removed config
key as a breaking change** and say so at the top: every deployment with
maintenance pins or dashboards built on those is affected, even though nothing in
the code says so.

## [Unreleased]

## [0.1.0] - 2026-08-10

### Added

- **First release: the `wiz` check type**, extracted from the private deployment
  it grew up in. The behavior is unchanged — same tree, same band codes, same
  entry slugs. Open and in-progress WIZ issues are fetched over GraphQL and
  reported as one leaf per severity band (`critical` through `informational`),
  each graded by a configurable `severity_map` and listing its findings.
- Every finding is an **individually addressable line**, slugged from WIZ's own
  identifiers, so one control can be put into maintenance while the rest of its
  band keeps reporting. `aggregation_level` chooses the identity: `id` (the
  default) groups by WIZ **control**, listing every affected entity on one line;
  `entity` keeps one line per issue.
- The **per-band display text ships with the type**, including the paragraph that
  explains the line format for the configured aggregation level, so it is not
  copied per tenant. A deployment replaces a label in its own `subnodes:` block,
  or extends the shipped text by writing `{default}` into its own.
- The credentials are little-sister **secret references** in the config's
  `secrets:` block, so each tenant's check carries its own OAuth2 client
  credentials.
- `api_url` is **required**: the WIZ GraphQL endpoint is region-specific, so a
  wrong default would fail at the first run instead of at load. `ignore_control_ids`
  skips controls entirely, and `first` bounds the issues read per run.

### Requires

- `little-sister >= 0.3.11` — the floor is 0.3.11, not the 0.3.0 that first
  promised the check-authoring surface this package imports: 0.3.0 was tagged but
  never uploaded, so it names no version a resolver can fetch, and it is 0.3.11
  that lowered the library's own Python floor to the one below.
  A **floor, never a pin**. The package declares
  check API epoch **1**; a library that has moved past that surface refuses at
  startup rather than failing as an import error from inside this package.
- **Python 3.11 or newer** — the library's floor, not a higher one of this
  package's own: a plugin that asked for more would mean somebody installs
  little-sister and then cannot install the package they came for. The claim is
  checked rather than declared — the type check runs against 3.11 on every commit
  and the whole suite against a real 3.11 on every release.
