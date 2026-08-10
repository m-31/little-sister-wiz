# little-sister-wiz

The **`wiz`** check type for [little-sister](https://github.com/m-31/little-sister):
open and in-progress issues from [WIZ](https://www.wiz.io/) cloud security, reported
as one leaf per severity band — `critical`, `high`, `medium`, `low`,
`informational` — under the node the check owns.

Every finding is an individually addressable line, so an operator who opens a
ticket for one control can put **that line** into maintenance and the rest of the
band keeps reporting.

## The contract

- **Requires** `little-sister >= 0.3.11` — a floor, never a pin.
- **Runs on** Python **3.11 or newer** — the library's floor, not a higher
  one of its own.
- **Registers** one check type: **`wiz`**.

## Install

```toml
# your deployment's pyproject.toml
[project]
dependencies = ["little-sister", "little-sister-wiz"]

# Only while *this* one comes from git: little-sister resolves from the index.
# Delete the table once this package is on an index too — nothing else changes.
[tool.uv.sources]
little-sister-wiz = { git = "…/little-sister-wiz.git", tag = "v0.1.0" }
```

```python
# wsgi.py — registrations first, the app last. The order is load-bearing:
# importing little_sister.app builds the engine and loads the check configs, so
# every check type must already be registered. `isort: off` keeps an import
# sorter from quietly reversing that.
# isort: off
import little_sister_wiz               # noqa: F401  registers the `wiz` type
from little_sister.app import app
# isort: on

__all__ = ["app"]                      # without it, lint calls the app import unused
```

## Configure

Copy [`examples/wiz.yaml`](examples/wiz.yaml) into your deployment's
`config/checks/`, set `api_url` and the two credential references, and you are
done — one file per tenant. The credentials are **references**, never values:

```yaml
type: wiz
path: /platform/wiz
secrets:
  client_id: env://PLATFORM_WIZ_CLIENT_ID
  client_secret: env://PLATFORM_WIZ_CLIENT_SECRET
api_url: https://api.<region>.app.wiz.io/graphql
```

`api_url` is **required and has no default**: the WIZ GraphQL endpoint is
region-specific, and guessing it would fail at the first run rather than at load.
Each tenant's check carries its own client credentials, so a second tenant is a
second config file rather than a code change.

The per-band display text ships **with the type**, so it is not copied per tenant.
Your deployment's own policy — a remediation deadline, who to page — goes in that
config's `subnodes:` block, appended to the shipped text with `{default}`.

## What it reads

One OAuth2 client-credentials token exchange, then one GraphQL query per run:

| | |
|---|---|
| **Token** | `POST https://auth.app.wiz.io/oauth/token` (`token_url:` overrides it) |
| **Issues** | `POST <api_url>` — `issues(first: <first>)`, status `OPEN` and `IN_PROGRESS`, ordered by severity |

Each returned issue carries its id, severity, status, control (`id`, `name`) and
affected entity (`name`, `type`) — nothing else is requested.

| Config | Decides |
|---|---|
| `severity_map` | what a band with findings grades as. Defaults: `critical` / `high` / `medium` → **ERROR**, `low` → **WARN**, `informational` → **OK**. An empty band is always OK |
| `aggregation_level` | `id` (default) — one line per WIZ **control**, listing every affected entity, slugged `wiz-control-<control-id>`; `entity` — one line per issue, slugged `wiz-<issue-id>` |
| `ignore_control_ids` | WIZ control IDs to skip entirely |
| `first` | issues fetched per run — a single page, so raise it rather than expecting pagination |

A band with findings takes its mapped status; the check's own node rolls up
worst-of its bands. An issue with no id falls back to little-sister's content hash
for its slug, never to a position in the list. Only stdlib `urllib` is used — the
package has no dependency but little-sister itself, and TLS verification is always
on.

## Develop

little-sister is declared as a **floor** — the release that promised the surface
this package imports — and it resolves **from the index**, like any other
dependency. There is no `[tool.uv.sources]` table here, and the committed
`uv.lock` is what a release runs against. To work against a local library
checkout, add the redirect and **do not commit it**: uv reads the sources table of
a dependency it resolves from a path or a checkout, so a committed line would
follow this package into every deployment that installs it.

```toml
# pyproject.toml — locally, never committed
[tool.uv.sources]
little-sister = { path = "../little-sister" }
```

Restore `uv.lock` with it. The next `uv run` — the pre-commit gate is one — rewrites
the lock to `source = { directory = … }`, so a redirect kept out of `pyproject.toml`
can still reach a commit through the lock beside it.

```bash
uv sync
uv run ruff check
uv run mypy
uv run mypy --python-version 3.11   # against the floor, not the interpreter you have
uv run pytest -q
# The same gate runs before every commit once the hook is enabled:
git config core.hooksPath hooks
```

The tests are fixture-based; nothing in this repository calls WIZ.

## License

MIT — see [LICENSE](LICENSE).
