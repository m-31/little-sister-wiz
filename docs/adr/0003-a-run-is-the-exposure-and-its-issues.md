# ADR-0003 — A run is the tenant's exposure and its issues, and only the exposure has a history

- **Status:** Accepted
- **Date:** 2026-09-26
- **Related:** [ADR-0001](0001-severity-bands-are-what-grades.md) (the bands, their
  lines and their slugs, which this keeps exactly),
  [ADR-0002](0002-a-read-failure-is-not-a-finding.md) (what a failed read means, which
  this keeps exactly), little-sister **ADR-0086** (a check measures and then grades what
  it measured — the split this is the conversion to), little-sister **ADR-0087** (a
  subject's readings kept as its series, and the identity or state that says whether a
  reading is a new record), little-sister **ADR-0085** (one shape for every reading),
  little-sister **ADR-0023** (a secret reference is a name), little-sister **ADR-0050**
  (an identifier is never invented from text), `little-sister-github` ADR-0014 (the
  first package through the split — its estate, its readings and its configuration
  split, taken here in this vocabulary)

> Every reference to one of little-sister's records is written out as **little-sister
> ADR-00NN**, because the two numbering spaces overlap.

## Context

little-sister ADR-0086 replaced a check's `run()` with two halves. `measure()` reads
the world and hands back `Measurement`s — records, and the objects they were read from
— and `grade(measurements, now)` builds the tree a check has always returned out of
those records and nothing else: not the world again, not the clock, not anything the
measuring half left behind. The check API epoch moved to 3 with it, and a type written
for 2 refuses at import. Until this record, this one did.

The split asks three questions of every vocabulary, and a check that reads a whole
tenant answers them differently from one that reads a single object:

- **What is one reading?** A `wiz` run reads one answer — up to `first` issues, worst
  first — and writes up to five bands of lines out of it. The grading may read only
  records, and a record is bounded by `record_limit`, 2 KB by default.
- **Which readings name a subject?** A subject is what gives a reading a history
  (little-sister ADR-0087 decision 2), so the answer is a decision about what is to have
  one.
- **What event is a reading of?** Nothing in a tenant's open issues is an event. An
  issue WIZ keeps reporting names nothing that happened, and neither does the tenant's
  exposure; little-sister ADR-0087 decision 3 says what a reading of such a frozen state
  names.

## Decision

### 1. A run hands back the estate first, then one reading per issue

**The estate** is the run's own reading: the tenant's exposure, and whether the read
worked.

```
{"kind": "estate",
 "bands": {"critical": 3, "high": 12, "medium": 40, "low": 7, "informational": 2},
 "page_full": false,
 "failure": null}
```

`bands` counts the issues on the page per severity band. The five declared severities
are always keys, at zero when empty; a severity WIZ invents becomes a key in the run it
appears, after them and by name, and an issue WIZ sent without a severity counts as
`unknown`, the band it has always landed in. `page_full` is WIZ's own
`pageInfo.hasNextPage` — the query always asked for it and never read it — and where it
is set, the counts are a floor under the tenant's exposure rather than the whole of it
(ADR-0001 decision 8). `failure` is null on a run that read.

**An issue's reading** carries exactly what its line says, and nothing else:

```
{"kind": "issue", "id": "…", "severity": "CRITICAL", "status": "IN_PROGRESS",
 "control_id": "…", "control_name": "…", "entity_name": "…", "entity_type": "BUCKET"}
```

— the values as WIZ sent them, bounded as decision 7 says, and **null** where WIZ sent
nothing, so every reading has one shape (little-sister ADR-0085 decision 3). There is
one reading per issue on the page, in the order WIZ returned them, the ignored ones
included (decision 2).

**Two things are deliberately not readings.** The **band** is derived: the estate and
the issues rendered as five children, and a sixth for a severity WIZ invents, the way
one `host-metrics` reading is rendered as five nodes. And the **control's line** is a
grading choice: under `aggregation_level: id` it gathers every issue of one control, and
may list more entities than any one record can hold.

The two refused shapes are refused for the grading's sake. **The estate alone** cannot
carry the lines: one band's lines at the default `first` do not fit in 2 KB, and the
grading could write them from nothing else. **The issues alone** leave two runs with
nothing to say. A clean tenant would hand back an empty sequence, which clears the
node's last reading, when *read, and nothing open* is the reading most worth keeping.
And a failed read would have to raise for anything to be recorded — the engine then
records the attempt itself (little-sister ADR-0086 decision 5), but it grades that run
`ERROR`, where ADR-0002 decision 5 says a transient failure and a spent budget only
warn. So a failed read hands back the estate alone, its `failure` saying which fault —
`transient`, `answered`, `malformed` or `deadline` — and the sentence, and its counts
**null**: never zero, which would keep, as a series, the tenant reported clean by a
check that was told nothing (ADR-0002 decision 6). The grading reads the fault and says
what it always said.

### 2. The configuration is split by what it spares

`little-sister-github` ADR-0014 §5's rule, in this vocabulary: a setting that spares a
request stays in the measuring half, because the reading it saves is never taken; a
setting that only chooses what is said moves to the grading, because a reading that
left something out would be a reading of the configuration rather than of WIZ.
**`first`** is the query, and stays. **`severity_map`**, **`aggregation_level`** and
**`ignore_control_ids`** spare nothing — the query is one query whatever they say — and
go to the grading.

So **the counts are WIZ's, taken before the ignore list**, while the bands still show
what the deployment grades. A curve of the exposure does not jump the day somebody edits
`ignore_control_ids`, and what the deployment graded is kept beside it anyway, as the
code that stood where the estate landed (decision 5).

### 3. Only the estate names a subject: `<api host>;credential=<client_id reference>`

**The estate is the object this check watches**, declared at construction out of its
configuration (little-sister ADR-0086 decision 4), so a run that raises is still
recorded against the estate it failed to reach. The endpoint alone is not the estate:
two checks can read one endpoint with two credentials — two teams, a service account
each — and each sees what its own credential sees. WIZ names no tenant in anything this
package reads, and the object is needed at construction anyway, before any answer. What
draws the estate is the endpoint and the credential, and the credential's value may not
travel. **Its reference may**: a reference is a name, and the value is resolved once
(little-sister ADR-0023), whose decision 4 already puts a reference into a visible
failure reason — so a reference in a subject exposes nothing new. The host is the
`api_url`'s, and the reference is kept **whole, scheme included**, because two teams'
references may differ in nothing but their scheme: one resolver per team, the same path
in each.

**A spelling longer than a subject may be is refused at load**, with a sentence that
names its parts and its length — never cut, because a cut name could be another
estate's. The sentence does not quote the reference, which could be a credential pasted
where its reference belongs; refusing that is the resolver's, and it quotes nothing.

The costs are the ones a renamed branch has in `little-sister-github`: moving or
renaming the secret starts a new history, and two references to one secret split one
estate in two — the harmless direction.

**No issue names a subject**, so none has a history. The curve this check exists for is
the estate's — *how bad, and is it moving* is a question about bands (ADR-0001) — and it
has it either way. `series_keep` is one number per check, so a deployment asking for the
estate's curve would otherwise buy a series for every open finding with it. Findings
churn, and a resolved finding's series is never trimmed by its count: it waits for the
ceiling on everything held, where each eviction turns the engine's node red
(little-sister ADR-0087 decision 10). And WIZ keeps an issue's lifecycle itself.
`little-sister-github` decided its findings the same way (its ADR-0014 §2), and granting
a history later is additive: a subject on a reading that already exists.

### 4. The estate names the state it is in

little-sister ADR-0087 decision 3, for an object whose source keeps no event: a reading
names the source's own last-changed field where the source has one that moves with the
state, and otherwise the state itself. WIZ keeps no such field for an estate — the query
answers issues, not a tenant — and the issues' own timestamps cannot stand in, since a
resolved issue leaves the query and no maximum over those still in it moves when the
exposure falls. So the estate names its **state**, spelled from what constitutes the
exposure: each band's count in the record's order, and `page=full` where the page was
full —

```
critical=3;high=12;medium=40;low=7;informational=2
critical=0;high=0;medium=0;low=0;informational=0;page=full
failed=transient
```

— and never from the failure's sentence, whose words change from one message to the next
while the state does not. A state is bounded like a subject and compared by equality
alone, so where the spelling would not travel — longer than a subject may be, a control
character, or a `;` or `=` inside a severity WIZ invented, which would let two exposures
spell alike — it is `sha256:` and 32 hex digits of the same fields in an unambiguous
form. Refusing is not available here, as it is for the subject: this is decided at run
time, from WIZ's answer, and a refusal would be an error on every poll.

What a deployment that sets `series_keep` then keeps is **spells of exposure**: one
record per change, placed where the spell began, the newest always the exposure now. A
failed read is a spell of its own, so the series says how often WIZ could not be read,
and for how long. Two costs, stated. A spell keeps the code that stood at its latest
poll, since the same state replaces its record whole, so a `severity_map` edited in the
middle of an unchanged spell rewrites the code that spell keeps — the state rule's cost
for every check, not this one's. And a spell does not show this process's own gaps: an
instance down for a day comes back to an unchanged exposure and continues the spell,
which is the engine's history to tell and not the tenant's.

### 5. The node is a container

On a run that read, the check's own node declares `UNDEFINED` and says nothing, as
`host-metrics` does, where it declared `OK`. ADR-0001 decision 1 always said the node
declares nothing and rolls up worst-of its bands; the `OK` was the old shape's way of
saying nothing, and now it would be said on the record. For the reading that names the
check's own object and that no line carried, the engine keeps what stood on the node:
the root's own code and texts — or, where the root declares `UNDEFINED` with no text,
what the run's result rolls up to (little-sister ADR-0087 decision 8). With `OK` the
estate would have entered its series as `OK` on every run, whatever the bands said; with
the container it keeps the tenant's worst band.

The node rolls up to exactly what it did, with one exception: when every band is pinned,
nothing under it is counted, and it reads `MAINTENANCE` where it read `OK`. A failed read
still declares its `WARN` or `ERROR` with its sentence, and writes no band.

### 6. A line made from one reading carries it

`little-sister-github` ADR-0014 §7's rule: a line the grading writes out of **one**
reading carries that reading's record as its `data`, and a line written out of several
carries none, since no one record is what it read. So at `aggregation_level: entity`
every line carries its issue, and at `id` a control's line carries its issue when one
issue made it and nothing when several did. An issue names no subject, so neither does
its line. The bands' lines carry no code of their own — the band does — so a band says
`entries=True`, which keeps each line a member a pin can hold, as the `(slug, text)`
pairs said by their shape.

### 7. Free text is clipped once, and every field is bounded

A control's name, an entity's name and a failure's sentence are clipped **once**, in the
measuring half, to 300 characters and then to 600 of the bytes the seam weighs a record
in (little-sister ADR-0086 decision 7), and the line is written from the clipped value —
so a name longer than that is shorter on its line than it was, and the sentence written
today can always be written again from the reading. A severity, a status and an entity's
kind are held to 100 bytes; an identifier is kept whole, or, past 100 bytes, as
`sha256:` and 32 hex digits of it, because a clipped identifier could meet another one
and a digest cannot. WIZ mints all of these short — an issue's id is a UUID — so these
bounds are not met in practice. They exist so that no answer makes a record the seam
refuses: the heaviest issue reading possible, every field at its bound in the characters
JSON escapes the most, weighs 1819 bytes against the default 2048.

**One record can still be refused**, and it is stated rather than engineered away: an
estate whose answer invents so many severities that its counts pass `record_limit`.
WIZ's severities are five.

## Consequences

- **The package speaks check API epoch 3**, and installed beside an older library it
  refuses at startup, naming both epochs. Its floor rises with it.
- **The tree says what it said.** Measured rather than argued: the module as it was, on
  the library it was written for, and this one, run over one set of fixtures — mixed
  severities, controls shared and missing, issues without ids or entities, in-progress
  lines at both levels, invented severities, the ignore list, a custom grading map, both
  aggregation levels, duplicate ids, every failure — agreed on every band, code, slug,
  line and label, and differed in exactly three ways: the node's declared code
  (decision 5), its rolled-up code with every band pinned (decision 5), and a name or a
  failure sentence past the clip budget (decision 7).
- **No configuration key changes and no slug moves**, so every maintenance pin still
  matches (ADR-0001 decision 3).
- **Lines carry what they read.** At `aggregation_level: entity` every line carries its
  issue's record — about 200 to 350 bytes of JSON with ordinary names — in the tree and in
  every envelope a client polls, so five hundred open issues are some 150 KB more per
  poll. At `id` only a control with one affected entity carries one.
- **The records' field names are keys now**, as a slug is: a deployment's line template
  or grading will read them, so renaming one breaks what this package cannot see. They
  are the ones in decision 1.
- **With `series_keep` set, a deployment keeps the tenant's exposure** as spells, and
  nothing per issue. Without it — the default — nothing is kept beyond the node.
- **A failure sentence longer than 300 characters is shorter than it was.** The case
  that shows it is a GraphQL error quoted whole.

## Alternatives considered

- **The estate alone**, one reading per run carrying the counts. Refused in decision 1:
  it cannot carry the lines.
- **The issues alone.** Refused in decision 1: a clean tenant records nothing, and a
  failed read would grade `ERROR` through the engine where it should warn.
- **One reading per control.** Its line lists every affected entity, so a control with
  many of them passes `record_limit`; and the reading would depend on
  `aggregation_level`, which is configuration.
- **The counts after the ignore list.** Refused in decision 2: a reading of the
  configuration, and a curve that jumps when the list is edited.
- **The endpoint alone as the estate's subject.** Two credentials on one endpoint would
  be one object.
- **The client id's value, or a digest of it.** The value may not travel; a digest is
  opaque, and it is the kind of value `little-sister-github` keeps precisely because it
  is never published.
- **A new `tenant:` key.** A stored key; optional, it leaves the collision wherever it
  is unset, and required, it breaks every configuration.
- **The token's claims.** Undocumented, and ADR-0002 already declines to read a vendor
  dialect nobody has verified.
- **The reference without its scheme.** Two teams' references can differ in the scheme
  alone.
- **A subject cut to fit.** A cut name could be another estate's.
- **Each issue's id as its subject**, a history per finding. Refused in decision 3, for
  what it costs every deployment that wants the estate's curve, and because WIZ keeps an
  issue's lifecycle itself.
- **Appending the estate on every poll**, as `little-sister-github`'s estate does, whose
  record is a sample of per-run facts. This one is a state: its record would repeat every
  poll while nothing changed, and `series_keep` would count polls rather than changes.
- **An issue timestamp as the estate's identity.** A resolved issue leaves the query, so
  no maximum over the rest moves when the exposure falls.
- **Keeping the root's `OK`.** Refused in decision 5: the estate would be kept as `OK`
  on every run.

