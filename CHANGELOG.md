# Changelog

All notable changes to little-sister-wiz, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/). These notes are for the
deployments that install this package, not a work log.

Treat **a new or renamed `type:` name, a changed slug shape, or a removed config
key as a breaking change** and say so at the top: every deployment with
maintenance pins or dashboards built on those is affected, even though nothing in
the code says so.

## [Unreleased]

## [0.1.1] - 2026-08-17

**Two behavior changes worth reading before you upgrade: `timeout:` now bounds the whole
run rather than each request, and a WIZ outage now reports amber rather than red.**
Neither needs a config edit; both change what you see
([ADR-0002](docs/adr/0002-a-read-failure-is-not-a-finding.md)).

### Fixed

- **An answer with no findings in it was reported as a clean tenant.** The issue list was
  read defensively enough to survive a payload that was not there — a 200 with no
  `data`, from a schema change or a partial response, became **zero issues**: every band
  green, and a security tenant reported as all clear by a check that had been told
  nothing. A missing payload is now a failure that grades and says so. An **empty** list
  of issues is unchanged and still means what it says: nothing open.
- **`timeout:` bounded nothing at all.** It is the check's one duration, and it was
  handed to the socket layer as the *per-request* timeout — so a run, which is an auth
  request plus up to three query attempts, could spend it several times over. Nothing
  else bounded it either, so a slow WIZ could hold a run past its own `frequency:`
  indefinitely, and a wedged check reports nothing at all. It is now the whole run's
  deadline, and each request is clamped to what is left of it.
  - **Re-read your `timeout:`** if you set it near one request's length. The shipped
    example uses `120s`, which is now a ceiling on the whole run.
- **The retry asked three times in the same millisecond, and skipped `500`.** There was
  no wait between attempts — an endpoint that had just failed was asked again
  immediately, which is the one thing certain not to help — and a plain 500, the
  commonest transient status there is, was treated as final on the first ask while
  502/503/504 were retried. There is a **1-second backoff** now, a 500 is retried like
  any other 5xx, and a `429` is understood as *not now* and honors the `Retry-After` WIZ
  sends. The wait is never longer than the run can afford: a ten-minute reset is reported
  rather than slept through, because when to ask again is your `frequency:`.
- **A transient failure on the auth endpoint ended the run.** The token exchange sat
  outside the retry, so a single 503 from it lost a run that the next second would have
  completed.
- **Two failures reached the engine as a crash rather than a reading.** An auth response
  without an `access_token`, and any answer that was not JSON, raised past this check's
  own error handling — so little-sister reported the whole check as a check error instead
  of saying what had happened.
- **A misdirected endpoint could fail as something unrecognizable.** Redirects were
  followed, and urllib turns a POST into a GET when it follows one, so the request body
  was silently dropped. A 3xx is now reported as what it is: the URL is wrong, which for
  a region-specific `api_url` is the useful thing to be told.

### Changed

- **A severity band wears a colored circle instead of its own name again.** Each
  band's title was `Critical`, `High`, `Medium` — the name back with a capital
  letter, twice the width of a chip for no second fact. The row now reads
  🔴 🟠 🟡 🔵 🟢, beside the names, which is the severity at a glance in one
  character.
  - **The colour is by name, never by rank.** Same severity, same circle, wherever
    it sits — a colour that meant *where this band is in this row* would move when a
    deployment changed the row, and nobody reads a red circle that way.
  - **`informational` is green, not white.** The bottom of a severity scale and
    *nothing to do here, and that is the thing being watched* are different
    statements, and this band renders while empty precisely to make the second one.
  - **A severity this package does not name gets `❓`**, never a borrowed colour. The
    band list is open: WIZ may add one, and your `severity_map` may name one.
  - **The word is not lost anywhere.** The name sits beside the title on every chip,
    and the two surfaces that draw a title *instead of* a name — the `/copy` hand-off
    and the hover card — now draw both, so a pasted ticket reads `critical 🔴` rather
    than a bare circle. That is the library's rule, not this package's
    (little-sister ADR-0061), and it is why the floor below matters for more than an
    import.
  - **It is a default.** A tenant that wants the word back writes one `subnodes:`
    line, as for any band label.
- **The band row reads worst-first.** It rendered
  `critical high informational low medium` — siblings sort by name, and a name sort
  destroys the one order a severity scale has, putting `informational`, the band that
  means *nothing to do*, third. Each band now declares its rank
  (little-sister ADR-0055) and the row reads
  `critical high medium low informational`, on the dashboard and in the JSON.
  - **A severity WIZ invents tomorrow sorts after every declared band**, by name among
    its own kind, rather than wherever the data happened to bring it.
  - **Your `nodes.yaml` still wins.** What this package declares is a default; an
    `order:` you set per node overrules it, as it already does for `title` and
    `about`. Worth knowing before you write one: `0` is the rank the *unranked* carry,
    so `order: 0` on one band moves it to the **front** of a ranked row, not back to
    its alphabetical place.
  - **The JSON `children` order moves with it**, which little-sister ADR-0055
    decision 5 accepts as a small incompatible change: a client rendering in received
    order will see the row change, and what it sees is better.
- **A band's page said what it was graded, and said it wrong.** Every band's shipped
  text named its own code in prose — `High-severity WIZ issues — graded ERROR`, and
  the same for the others — but that text is written into this package and cannot see
  your `severity_map`. **A deployment that graded `medium` as WARN read `graded ERROR`
  on the medium band's own page**, and nothing anywhere said otherwise.
  - **What a severity means stays in the prose; what it is graded moved to `config`.**
    A band's page now carries `graded: `WARN` when this band has findings` — expanded
    from the map actually in force, so an override shows — beside `when empty: `OK`,
    so a watched band's silence is visible`. A band with no `severity_map` entry says
    the fallback is what applied, which is the case a reader could not see at all.
  - **The check's own page carries the whole map**, in one line, as
    `` `critical` → **ERROR**, `high` → **ERROR**, … `` — collapsing to
    `**ERROR** for every band` where they agree. It is the one place every band's
    answer is visible together, and where you confirm an override took.
  - **Only display text changed.** No node path, no slug and no grading behavior moves,
    so maintenance pins and dashboards are untouched. If your `subnodes:` block already
    rewrote a band's `about`, yours still wins and is unaffected — and if it repeated a
    grade in your own words, it has the same drift problem this fixes.
- **A read failure is no longer a finding about your tenant.** *Could not ask WIZ* is a
  fact about WIZ, not about your cloud posture, so a 5xx, a throttle, a dropped
  connection or a spent budget now put the check's node at **WARN**, with a sentence
  saying so, where it used to be ERROR. What still grades ERROR is an answer WIZ gave —
  a rejected credential, a rejected query — and an answer this check cannot read: those
  are about your configuration or about the API, and somebody has to act on them.
  - The severity bands are **not** rewritten on a failed run. They keep their previous
    reading and go stale on freshness, which is the honest display of the last thing
    actually known rather than five bands invented from an answer that never arrived.
- **The request, the budgets and the retry are the library's now**, and only what is
  actually about WIZ stays here — the OAuth2 exchange, the GraphQL envelope and its own
  error channel. One visible effect: requests identify themselves as
  `little-sister/<version>` instead of an unversioned `little-sister-wiz`, which is a
  name a WIZ support thread can do something with. Certificate verification still cannot
  be switched off, now because the library offers no way to ask.

### Requires

- **`little-sister >= 0.3.12`**, up from 0.3.11, now for **two** reasons. This package
  imports `little_sister.transport` and `little_sister.fetch`, and 0.3.11 has neither —
  so a floor still naming it would let this install against a library missing every
  name it needs, and would say so only as an `ImportError` at startup.
  - The second reason is quieter and worth stating, because nothing would crash: the
    band glyphs above depend on 0.3.12 knowing that **a title with no word in it
    cannot stand in for a name** (little-sister ADR-0061). On an older library the
    check would run perfectly and every `/copy` would paste a bare 🔴. A floor that
    only ever guards imports would have missed this one.

  Still a **floor, never a pin**, and the check API epoch is still **1**: adding names
  to the surface does not move it.

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
