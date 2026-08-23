# little-sister-wiz

The **`wiz`** check type for [little-sister](https://github.com/m-31/little-sister):
open and in-progress issues from [WIZ](https://www.wiz.io/) cloud security, reported
as one leaf per severity band — `critical`, `high`, `medium`, `low`,
`informational` — under the node the check owns.

Every finding is an individually addressable line, so an operator who opens a
ticket for one control can put **that line** into maintenance and the rest of the
band keeps reporting.

## The contract

- **Requires** `little-sister >= 0.3.13` — a floor, never a pin.
- **Runs on** Python **3.11 or newer** — the library's floor, not a higher
  one of its own.
- **Registers** one check type: **`wiz`**.

## Install

```toml
# your deployment's pyproject.toml — both come from the index
[project]
# Pin them. A deployment names exact versions so an upgrade is a deliberate edit
# rather than drift; a plugin is the one that declares a floor, because two plugins
# that each pinned could not be installed together.
dependencies = ["little-sister==0.3.13", "little-sister-wiz==0.1.0"]
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
for its slug, never to a position in the list. The package has no dependency but
little-sister itself, and TLS verification is always on — there is no setting to
turn it off.

## When WIZ is the one having a bad day

A read that fails is not automatically a finding about your tenant, and this type tells
the two apart by **status**
([ADR-0002](docs/adr/0002-a-read-failure-is-not-a-finding.md)).

| what came back | what you see |
|---|---|
| **5xx**, a dropped connection, or a `429`, three times | the node at **WARN**: `could not ask WIZ this run: …` — your cloud posture is not being graded for WIZ's weather |
| **401 / 403** | **ERROR**: the client ID or secret is wrong or unauthorized, and only a person can fix it |
| **GraphQL `errors`** inside a 200 | **ERROR**: WIZ answered and rejected the query |
| an answer this check **cannot read** | **ERROR**: a missing payload, a changed schema. Waiting changes nothing |
| a **3xx** | **ERROR**: `api_url` is wrong. Redirects are not followed, because urllib turns a POST into a GET when it follows one |

A transient failure is **retried twice more**, one second apart, and a `429` waits as
long as WIZ's `Retry-After` asks — but never longer than the run can afford. A reset
twenty minutes out is reported rather than slept through: when to ask again is your
`frequency:`.

**The severity bands are not rewritten on a failed run.** They keep their previous
reading and go stale on freshness, which says *this is the last thing we actually knew*
rather than inventing five bands from an answer that never arrived.

## One budget: `timeout:`

`timeout:` is the **whole run's** deadline — the token exchange plus up to three query
attempts — and each request's socket timeout is clamped to whatever is left of it. There
is no separate per-request key: a run makes at most four requests, so the run's own
budget is a sane bound for one of them too.

**If you are upgrading, re-read your `timeout:`.** It used to be spent per request, so a
value chosen for one request now bounds the whole run. The shipped example uses `120s`.

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
little-sister = { git = "file:///path/to/little-sister" }
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
