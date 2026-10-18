# ADR-0005 — An issue's line is written from a form, and a control's line links every issue

- **Status:** Accepted
- **Date:** 2026-10-11
- **Related:** little-sister **ADR-0126** (a line is a template over its record: the
  forms, words and fields a type declares, `Check.line`, and the `display:` block),
  [ADR-0001](0001-severity-bands-are-what-grades.md) (decision 3, a line keyed by what
  WIZ minted; decision 6, the endpoint without a default; decision 7, *in progress*
  on the line), [ADR-0003](0003-a-run-is-the-exposure-and-its-issues.md) (decision 6,
  the line that carries its reading),
  [ADR-0004](0004-the-issues-are-asked-of-issuesv2.md) (the query, held to what WIZ
  documents), `little-sister-github` ADR-0017 (the package that adopted first, whose
  round this one follows), little-sister **ADR-0018** (escaping is a render-time step)

> Every reference to one of little-sister's records is written out as **little-sister
> ADR-00NN**, because the two numbering spaces overlap.

## Context

An issue's line was a sentence this package wrote: a Markdown link it built, `plain()`
around each name, `**` around the entity. little-sister ADR-0126 makes a line made from
one reading a template over its record. A type declares the forms its grading names and
the words and fields a template may name; its grading asks the library for each line,
`Check.line`; and a deployment re-words a form in its check's `display:` block.
`little-sister-github` adopted first, and this package adopts beside it, on Lex's word,
after a round of four questions with him, one at a time.

Lex asked one more: whether a line's link reaches one issue, since the point of the
click is to set that issue in progress, or ignore it, in WIZ. The link's shape opens one
issue — its fragment's `issue~'<id>` opens the issue's panel over the issue list, the
shape Roadie's Backstage plugin for WIZ moved its own links to in its 2.4.1, *so they
open the issue in Wiz* — and what the panel lets a reader change is their WIZ role's.
But at the default `aggregation_level: id` a line is one control and every entity it
flagged, and only the control's name linked, to one of those issues: the first WIZ
answered with an id. A click reached one issue of several, and setting it in progress
or ignoring it left the rest of the line's issues as they were. And every link's host
was `https://app.wiz.io`, where Roadie's plugin takes the app's address from its
configuration.

## Decision

### 1. An issue's line is the form `issue`

At `aggregation_level: entity`, and at `id` for an issue whose rules name no control
(ADR-0001 decision 4), an issue's line is written by `Check.line` from the form `issue`:

`{?entity_name:**{entity_name}**{? ({line.kind})} — }[{line.control}]({line.url}){?, detected {created.at}}{?, due {due.at}}{?line.in_progress: · *in progress*}`

— the entity and its kind, the control that flagged it linked to the issue, when WIZ
detected the issue and when it is due (§7), and *in progress* where WIZ has it so
(ADR-0001 decision 7). Beside the two times it says what the code said, word for word,
but for one value (§6), and it carries the issue's record (ADR-0003 decision 6).
The names of the form, of its words and of the record's fields are **stored keys**: a
deployment's `display:` block writes them, so renaming one is a breaking change, said at
the top of a release's notes. `/system/installed` lists every one with its sentence and
an example, and a line's page names its form.

### 2. What a line derives from the record is a word

Four words, built when the line is written and never stored: `kind`, the entity's type
as a reader says it — `STORAGE_BUCKET` as *storage bucket*; `in_progress`, a flag;
`url`, the issue's page, named as `little-sister-github` names a link it builds; and
`control`, the control's name or, where it has none, its id. The record stays as WIZ
sent it and stores no fact twice.

### 3. A control's line carries no record, and each entity on it links to its issue

A control's line, made from every issue of one control in the band, keeps its sentence
and carries no record, however many issues made it — one among them. **Each entity on
it links to its own issue**, and the control's name, which led to one of them as if it
were all, links nowhere: every issue is one click from the line, and one line per
control stays. A control's line has one shape whatever its count, and its list of
links is what no template writes, since a list is a word and a word carries no link
(ADR-0003 decision 6).

### 4. The app's address is a setting

`app_url`, by default `https://app.wiz.io`, is the address every link is built on — an
issue's line's, and each entity's on a control's line. One that is not an http(s) URL
with a host, or that carries a query or a fragment, refuses to load: a link no browser
opens would leave every line's words without one, and nothing would say why. Unlike
`api_url` (ADR-0001 decision 6) it has a default: one address serves every tenant WIZ
does not serve from another, where every endpoint of its API is a region's.

### 5. An issue without an id is keyed by what it is about

Its slug was little-sister's content hash of its text, which a deployment's template now
re-words. It is the content hash of what the issue is about: its record's `control_id`,
`entity_type` and `entity_name`, so that no wording, this package's or a deployment's,
moves its slug or a pin held on it. Its status and severity are left out, since they
change without it becoming another issue. WIZ's API always sends an issue's id, so this
is a guard, and it moves such a slug once (ADR-0001 decision 3).

### 6. A value that is not there is `—`

A form is written as the notation writes it, as `little-sister-github`'s round settled:
a control with neither a name nor an id, which the code said as `issue`, is `—`.

### 7. The line says when WIZ detected the issue, and when it is due

As `little-sister-github`'s round settled for its findings, this release improves the
wording where a fact the record does not keep yet makes the line clearly better, and a
line says a time and never an age: a time stays true between two runs, and the grading
reads no clock. An issue's line says when WIZ detected it and, where the tenant's SLA
rules give it a date, when it is due —
`, detected 2026-09-01 12:00:00, due 2026-10-15 02:00:00` before its *in progress* — in
the configured zone and format. The two are fields of the record, `created.at` and
`due.at`, asked of WIZ as `createdAt` and `dueAt` once WIZ's own answer showed both to
be part of the query it documents
([ADR-0004](0004-the-issues-are-asked-of-issuesv2.md) decision 1). A
control's line keeps its wording, but for each entity's link (§3).

## Consequences

- **The floor rises** to the little-sister release that brings `Check.line` and the
  `display:` block.
- **A control's line moves once**, every one at the default `aggregation_level: id`: its
  name loses its link and each entity gains one. No slug moves but an id-less issue's,
  and a control's line made from one issue no longer has `data` in the envelope.
- **A deployment re-words an issue's line without a release of this package**, and may
  say what no default does — its severity, a field. A template that names what the type
  does not declare stops the start, naming the check's file.
- **The sentences that were an issue's are gone from the code**, and with them the
  `plain()` around its names: the escaping is the library's, at render.
- **An issue's record grows by two times**, `created.at` and `due.at`, and the heaviest
  issue reading with them, to 1915 bytes (ADR-0003 decisions 1 and 7). The query asks
  WIZ for two fields more (ADR-0004 decision 1).

## Alternatives considered

- **`kind` and `in_progress` as fields** beside `entity_type` and `status`. Rejected in
  §2: the record would store a fact twice.
- **Two forms for a control's line while one issue makes it** — an entity without a name
  said as *WIZ issue* and the issue's id, which a segment cannot say without an else.
  Rejected in §3: a deployment's template would re-word the line only until a second
  issue joined.
- **The control's name linking to one issue**, as before. Rejected in §3: a click
  reached one issue of several.
- **One line per issue at every level.** Rejected: that is `aggregation_level: entity`,
  which a deployment chooses; a control's line with every issue one click away keeps the
  band short and loses no issue.
- **An id-less issue keyed by the hash of its text**, which any template moves, or of
  the default form's text, which this package's own wording would still move. Rejected
  in §5.
- **Today's lines word for word**, the release only moving their wording onto forms.
  Rejected in §7, as `little-sister-github`'s round rejected it.
- **The entity's cloud account beside its kind**, one more field, which serves an estate
  of many accounts. Declined in the same round.
