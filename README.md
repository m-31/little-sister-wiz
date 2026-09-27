# little-sister-wiz

The **`wiz`** check type for [little-sister](https://github.com/m-31/little-sister):
open and in-progress issues from [WIZ](https://www.wiz.io/) cloud security, reported
as one leaf per severity band — `critical`, `high`, `medium`, `low`,
`informational` — under the node the check owns.

Every finding is an individually addressable line, so an operator who opens a
ticket for one control can put **that line** into maintenance and the rest of the
band keeps reporting.

## The contract

- **Requires** `little-sister >= 0.3.18` — a floor, never a pin.
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
dependencies = ["little-sister==0.3.18", "little-sister-wiz==0.1.3"]
```

```python
# wsgi.py — registrations first, the app last. The order is load-bearing: the
# server's start, right after little_sister.app is imported, builds the engine from
# the check configs, so every check type must already be registered. `isort: off`
# keeps an import sorter from quietly reversing that.
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
| **Issues** | `POST <api_url>` — `issuesV2(first: <first>)`, status `OPEN` and `IN_PROGRESS`, type `TOXIC_COMBINATION` and `CLOUD_CONFIGURATION`, ordered by severity |

Each returned issue carries its id, severity and status, the rules that raised it — a
Control's `id` and `name`, or a configuration rule's parent control — and the affected
entity (`name`, `type`); nothing else is requested. The issues a Control or a
configuration rule raised are read; a threat detection (`THREAT_DETECTION`, which a Wiz
Defend license brings) is not
([ADR-0004](docs/adr/0004-the-issues-are-asked-of-issuesv2.md)).

| Config | Decides |
|---|---|
| `severity_map` | what a band with findings grades as. Defaults: `critical` / `high` / `medium` → **ERROR**, `low` → **WARN**, `informational` → **OK**. An empty band is always OK |
| `aggregation_level` | `id` (default) — one line per WIZ **control**, listing every affected entity, slugged `wiz-control-<control-id>`: a configuration rule's issue under the rule's parent control, and an issue whose rules name several controls under the one with the smallest id; `entity` — one line per issue, slugged `wiz-<issue-id>` |
| `ignore_control_ids` | WIZ control IDs to skip entirely |
| `first` | issues fetched per run, from 1 to 1000 — WIZ's limit for one query — and 500 by default. A single page, so raise it rather than expecting pagination; a value outside 1 to 1000 refuses to load |

A band with findings takes its mapped status; the check's own node rolls up
worst-of its bands. An issue with no id falls back to little-sister's content hash
for its slug, never to a position in the list. The package has no dependency but
little-sister itself, and TLS verification is always on — there is no setting to
turn it off.

## What a run records

Each run records what it read: one reading of the tenant's **exposure** — how many open
issues each band holds, counted before `ignore_control_ids`, and whether the page was
full — and then one reading per issue. Every line made from one issue carries that
issue's record as its `data` (every line at `aggregation_level: entity`; a control's
line at `id` only when one issue made it), so a line template or a client can read what
the line read.

`series_keep:` — little-sister's setting, **0 by default** — keeps the exposure's
history: one record each time a band's count changes, or the read starts or stops
failing, the oldest out. Issues keep none. Why it is shaped this way is
[ADR-0003](docs/adr/0003-a-run-is-the-exposure-and-its-issues.md).

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
this package imports — and a release resolves it **from the index**, like any
other dependency: a released tree carries no `[tool.uv.sources]` table, and its
`uv.lock` names the index. Working against a library that is not on the index yet
takes a redirect to the checkout beside this one:

```toml
# pyproject.toml — while the library is unreleased, and never in a release
[tool.uv.sources]
little-sister = { path = "../little-sister", editable = true }
```

The redirect leaves a second trace by itself — the next `uv run`, and the pre-commit
gate is one, rewrites `uv.lock` to name the directory — and the two go together:
while the library is unreleased both may be committed, and neither may reach a
release. uv reads the sources table of a dependency it resolves from a path or a
checkout, so a released one would be imposed on every deployment that installs this
package that way; an install from the index is unaffected. The comment on the sources
table in `pyproject.toml` says what the window costs.

```bash
uv sync
uv run ruff check
uv run shellcheck $(git ls-files -- '*.sh' 'hooks/pre-commit')
uv run mypy
uv run mypy --python-version 3.11   # against the floor, not the interpreter you have
uv run pytest -q
# The same gate runs before every commit once the hook is enabled:
git config core.hooksPath hooks
```

The tests are fixture-based; nothing in this repository calls WIZ.

## License

MIT — see [LICENSE](LICENSE).
