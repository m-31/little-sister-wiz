# Changelog

All notable changes to little-sister-wiz, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/). These notes are for the
deployments that install this package, not a work log.

Treat **a new or renamed `type:` name, a changed slug shape, or a removed config
key as a breaking change** and say so at the top: every deployment with
maintenance pins or dashboards built on those is affected, even though nothing in
the code says so.

## [Unreleased]

## [0.1.5] - 2026-10-25

**This release installs only beside little-sister 0.3.22 or newer**, the release in
which a node says what it is on a card and at length in a handbook, so a deployment
moves the two pins together (*Requires*).

**Every band says what to do, its handbook says the rest, and every node links its
issues in WIZ.** Nothing to edit. A band's `about` is a sentence of what to do when it
holds issues, by the sign the band shows then under your `severity_map`, leading into
the **handbook** every band shows on its *Handbook* tab, which holds what the `about`
said at its end — how a line reads, and that each line can be pinned on its own — and
the grading in force, what to do and the configuration. A band's description says what
it reads, and its **details** link WIZ's list of its open issues, as the check's own
node's link the tenant's (*Added*, *Changed*). The `about` no longer says how soon a
severity is fixed: a deployment that wants *fix immediately* back writes it in its
`subnodes:` block, after `{default}`.

**On little-sister's wall the bands start as chips, and a band nothing waits on with its
issues folded** — what the wall draws today, kept when little-sister's built-in look
opens what nobody speaks for — **and a failing band's box shows ten lines** of its
issues whatever `reason_cap` your `settings.yaml` says, the rest under its *⌄ all N*:
four lines more than the library's default of six. Nothing to edit, and no name moves;
a deployment that wants them open, or another budget for the bands, says so in the
check's own file (*Changed*).

### Added

- **Each node links its issues in WIZ**, in its details (little-sister ADR-0133
  decision 6): a band WIZ's list of the open and in-progress issues of its severity, and
  the check's own node the tenant's whole list, on a run that failed as well — both on
  `app_url`. WIZ's list holds what no band lists too: a threat detection, and an issue
  of a control in `ignore_control_ids`.
- **A handbook every band shows**, a Markdown file this package ships: what the bands
  read; the grading in force, `{grading}`; how a line reads at the configured
  `aggregation_level`, `{line_note}`; what to do with an issue in WIZ; the configuration
  the check takes; and that each line can be pinned on its own, `{pin_note}`. A
  deployment's text may name the three tokens, beside `{entry_note}`, the last two
  together, as before.

### Changed

- **The bands start as chips, and a band nothing waits on folds its issues** — what this
  type proposes of the wall's first look, in little-sister's keys (its ADR-0128). The
  check's own node proposes its bands as chips, each with its count, and a band your
  `severity_map` grades OK — `informational` as shipped — its issues folded behind
  *✓ +N ok* wherever it is open, its own page among them; a band that fails opens its
  way as little-sister opens a failure a chip would hide, its box ten lines of its
  issues and the rest under its *⌄ all N* and on the band's page. The budget is the
  type's, above the one `settings.yaml` gives every box. A deployment that wants the
  bands open writes `chips: false` at the top of the check's file,
  `children: {reason_cap: 20}` beside it for another budget, and `fold_ok: false` under
  a band's name in its `subnodes:` block to show its issues; no name moves, so no pin
  does
  ([ADR-0006](docs/adr/0006-the-bands-start-as-chips-and-a-quiet-band-folds-its-lines.md)).
- **A band's `about` says what to do, by the sign the band shows** — `{error}: open each
  issue from its line and fix what WIZ found on the entity, setting the issue in
  progress in WIZ meanwhile — or ignore it there with its reason`, and a link into the
  handbook's section; for a band graded OK, as `informational` is, that nothing waits
  on it. The sign is taken from `severity_map` as configured, so a band your map grades
  WARN says `{warn}`, and a severity the map names that this package does not is
  declared as the five are, with its `about` and the handbook — as is the band of a
  severity WIZ invents, which nothing declares and whose run hands them over, at the
  sign of the fallback grading, `{warn}`. What the `about` said until now is the
  handbook's — how a line reads — or a deployment's policy — how soon a severity is
  fixed.
- A band's description says what it reads, *The open and in-progress WIZ issues of this
  severity that a Control or a configuration rule raised.*, where it said *Critical WIZ
  issues*.

### Requires

- **little-sister 0.3.22 or newer.** The floor rises from 0.3.21 because 0.3.22 is the
  first release in which a run writes a node's details, a type declares a band's
  handbook, and a label says a status by its sign and links a section of its node's
  handbook (little-sister ADR-0133) — what every band's text and every node this check
  writes are now made of. An older library cannot run it. Upgrade the library first; no
  configuration changes with it.

## [0.1.4] - 2026-10-18

**An issue's line is written from a form, and a deployment may re-word it.**
little-sister writes each issue's line from the form `issue`, over the issue's record,
and a check's `display:` block re-words it in its own file with no release of this
package; the README's *What its lines say* names the form, its words and its fields.
As shipped, it says what it said, and when WIZ detected the issue and when it is due.
Those names are **stored keys** from this release on: renaming one will be said here as
a breaking change. It installs only beside little-sister 0.3.21 or newer, the release
that writes a line from a form, so a deployment moves the two pins together
(*Requires*).

**Each entity on a control's line links to its own issue.** At the default
`aggregation_level: id` the control's name linked to one of the line's issues as if it
were all of them; it links nowhere now, and each entity links to its issue, so every
issue is one click from the line, where it is set in progress or ignored in WIZ. The
text of every control's line moves once. No slug moves but that of an issue WIZ sent
without an id, which its API does not do (*Changed*).

### Added

- `app_url`, the WIZ app's address every link is built on — `https://app.wiz.io` by
  default. One that is not an http(s) URL with a host, or that carries a query or a
  fragment, refuses to load ([ADR-0005](docs/adr/0005-an-issues-line-is-written-from-a-form.md)).
- The form `issue`, its four words — `kind`, `in_progress`, `url`, `control` — and the
  nine fields of an issue's record a template may name: `id`, `severity`, `status`,
  `control_id`, `control_name`, `entity_name`, `entity_type`, `created.at`, `due.at`.
  `/system/installed` lists each with its sentence and an example.
- An issue's record keeps when WIZ detected the issue, `created.at`, and when it is due,
  `due.at`, where the tenant's SLA rules give it a date — asked of WIZ as `createdAt` and
  `dueAt`, which answered the same issues with nothing else in the answer moving
  ([ADR-0004](docs/adr/0004-the-issues-are-asked-of-issuesv2.md)).

### Changed

- A control's line carries no record, made from one issue or from several, where one
  made from one issue carried that issue's: it has one shape whatever its count
  ([ADR-0003](docs/adr/0003-a-run-is-the-exposure-and-its-issues.md)). An issue's line
  carries its own, as before.
- An issue's line says when WIZ detected the issue and, where an SLA gives it a date,
  when it is due — `, detected 2026-09-01 12:00:00, due 2026-10-15 02:00:00` before
  *in progress*, on the configured clock — and `—` for a control with neither a name
  nor an id, where it said `issue`; the rest of it is word for word.
- An issue WIZ sent without an id is keyed by the content hash of its control and its
  entity, where its text was hashed, so that no wording moves its slug; the slug of such
  an issue moves once ([ADR-0001](docs/adr/0001-severity-bands-are-what-grades.md)).

### Requires

- **`little-sister >= 0.3.21`**, up from 0.3.18: the first release that writes a line
  from a form — `Check.line` and the `line_forms` a type declares — which every issue's
  line is now written through, and which no earlier release has. Still a **floor, never a
  pin**.

## [0.1.3] - 2026-09-27

**Breaking: this package speaks check API epoch 3, and needs the little-sister release
that does.** Beside an older library it refuses at startup, naming both epochs, so a
deployment moves both pins together. It asks WIZ's documented `issuesV2` query now, in
place of the `issues` query WIZ superseded, and reads the same issues. **One
configuration may have to change**: `first` refuses to load outside 1 to 1000, the range
that query takes. No slug moves, and the tree says what it said but for the cases under
*Changed* and *Fixed*.

### Added

- **A run records what it read**
  ([ADR-0003](docs/adr/0003-a-run-is-the-exposure-and-its-issues.md)): one reading of
  the tenant's exposure — the open issues per severity band, counted before
  `ignore_control_ids`, and whether the page was full — and then one reading per issue.
  With little-sister's `series_keep:` set, the check keeps the exposure's history, one
  record per change; issues keep none.
- **Every line made from one issue carries that issue's record** as its `data` — every
  line at `aggregation_level: entity`, a control's line at `id` only when one issue made
  it — so a line template or a client can read what the line read. It is weight in every
  envelope a client polls: about 150 KB per poll for five hundred open issues at
  `entity`.

### Changed

- **Breaking: check API epoch 3.** little-sister replaced a check's `run()` with
  `measure()` and `grade()` (little-sister ADR-0086), and this type is written as the two
  halves now.
- **The node the check owns is a container**: it declares nothing and rolls up its
  bands, where it declared `OK`. What it rolls up to is unchanged but for one case — with
  every band in maintenance it reads `MAINTENANCE`, where it read `OK`.
- **A name past 300 characters, or past 600 bytes as JSON writes it — which emoji reach
  far sooner — is shortened once**, and its line says the shortened name. So is a failure
  sentence past the same length, such as a GraphQL error quoted whole.
- **The check asks WIZ's `issuesV2`**, the query WIZ documents, in place of `issues`,
  which WIZ superseded in 2023 and no longer documents
  ([ADR-0004](docs/adr/0004-the-issues-are-asked-of-issuesv2.md)). It reads the same
  issues — those a Control or a configuration rule raised, types `TOXIC_COMBINATION` and
  `CLOUD_CONFIGURATION` — and still no threat detection. A line is keyed by the control
  the issue's rules name, a configuration rule's issue by the rule's parent control, so
  no slug moves; an issue whose rules name several controls goes under the one with the
  smallest id.
- **Breaking for a `first` outside 1 to 1000: it must be an integer from 1 to 1000**,
  the most issues one `issuesV2` query may ask for, and a configuration outside that
  refuses to load with a sentence naming the range, rather than asking WIZ on every run
  for what its documented query does not take. A value that is not an integer is refused
  the same way; it used to stop the load with a bare `ValueError`, naming neither the
  file nor the key.

### Fixed

- **An issue on an object deleted since it was raised still names what it was raised
  on**, where its line used to name nothing but *WIZ issue* and an id. The entity comes
  from `entitySnapshot` now, which keeps what the issue was raised on after the object is
  gone, where the old query read the object as it is now; the few lines this changes are
  such issues.

### Requires

- **`little-sister >= 0.3.18`**, up from 0.3.13: the first release that speaks check API
  epoch 3. Still a **floor, never a pin**.

## [0.1.2] - 2026-08-23

### Changed

- **Breaking: this package speaks check API epoch 2.** little-sister reads the
  whole `subnodes:` block itself now, for every check type, and a type only
  **declares** what it ships (little-sister ADR-0025). So this check no longer parses that
  block or layers its own defaults: it declares the band prose and the
  `{entry_note}` token beside the band's glyph, and the library resolves and
  applies them. **A deployment's configuration does not change** — the same
  `subnodes:` entries, the same `{default}` extension, the same precedence under
  `nodes.yaml` — and the block now works for every installed branch type rather
  than for the ones that chose to read it. Installed beside an older library this
  package refuses at startup, naming both epochs.
- A band that appears **only in a run's findings** — a severity WIZ invents — is
  the one whose glyph still rides its result, because nothing could have declared
  a name that did not exist yet. A severity named by `severity_map` is declared
  like the rest, prose or no prose, so it wears its circle and `{default}` in a
  configured title still gives that circle back.

### Fixed

- **`little_sister_wiz.__version__` reports the installed version again.** It was a
  literal, frozen at `0.1.0` since the first release, so an installation of 0.1.1
  answered `0.1.0` to anything that asked — a second source of a fact `pyproject.toml`
  already owns. It is read from the installed distribution's metadata now, the way
  little-sister reads its own, so it cannot disagree with the package that carries it;
  in a source tree with no install it reads `0+unknown` rather than a number that
  would be wrong.

### Requires

- **`little-sister >= 0.3.13`**, up from 0.3.12: that is the release which reads the
  `subnodes:` block for every check type, and therefore the first that speaks epoch 2.
  Both reasons the floor already carried still hold — this package imports
  `little_sister.transport` and `little_sister.fetch`, and the band glyphs depend on
  the library knowing that a title with no word in it cannot stand in for a name.
  Still a **floor, never a pin**.

## [0.1.1] - 2026-08-16

**Two behavior changes worth reading before you upgrade: `timeout:` now bounds the whole
run rather than each request, and a WIZ outage now reports amber rather than red.**
Neither needs a config edit; both change what you see
([ADR-0002](docs/adr/0002-a-read-failure-is-not-a-finding.md)).

### Changed

- **A severity band wears a colored circle instead of its own name again.** Each
  band's title was `Critical`, `High`, `Medium` — the name back with a capital
  letter, twice the width of a chip for no second fact. The row now reads
  🔴 🟠 🟡 🔵 🟢, beside the names, which is the severity at a glance in one
  character.
  - **The color is by name, never by rank.** Same severity, same circle, wherever
    it sits — a color that meant *where this band is in this row* would move when a
    deployment changed the row, and nobody reads a red circle that way.
  - **`informational` is green, not white.** The bottom of a severity scale and
    *nothing to do here, and that is the thing being watched* are different
    statements, and this band renders while empty precisely to make the second one.
  - **A severity this package does not name gets `❓`**, never a borrowed color. The
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

## [0.1.0] - 2026-08-09

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
