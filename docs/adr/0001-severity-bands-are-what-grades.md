# ADR-0001 — A tenant's issues are graded as severity bands

- **Status:** Accepted
- **Date:** 2026-08-14 — the decisions are the port's and are already in the code;
  this record is where they are written down for the people who receive it
- **Related:** little-sister **ADR-0036** (addressable members — what makes a band's
  line separately pinnable), little-sister **ADR-0050** (a slug is an identifier,
  never a position), little-sister **ADR-0025** (per-node display text, and a
  deployment's right to replace it), little-sister **ADR-0023** (secret references)

> Every reference to one of little-sister's records is written out as **little-sister
> ADR-00NN**, because the two numbering spaces overlap.

## Context

This check reads a **whole tenant** — every issue WIZ holds as open or in progress —
rather than one target. That is unusual for a check type, and it is what makes the
reporting shape a decision rather than a detail.

The predecessor emitted **one result per issue**. That is a defensible data dump and
poor monitoring: the severity ends up repeated on every line, nothing aggregates, and
an operator looking at forty amber lines cannot say whether the tenant is better or
worse than it was yesterday. The question a dashboard is asked about a security tenant
is *how bad, and is it moving* — which is a question about bands, not about issues.

The shape that replaced it is in this package's source and its knobs are in the README.
The README states each setting and its default; it does not state the argument for
them. That gap matters here more than in most packages, because `severity_map` exists
**in order to be overridden** — a deployment is invited to disagree with the grading,
and until this record there was nothing shipped for it to disagree with.

## Decision

### 1. The band grades; the issue does not

One leaf per severity band under the check's node, and the band's status is the whole
of what this check asserts. A band with findings takes its mapped status; an empty band
is `OK`. The check's own node declares nothing and rolls up worst-of its bands, so the
single glance at the top of the tree is the worst live band and not an average of forty
lines.

An issue therefore never carries a status of its own. It is an **entry on the band that
owns it** — which is what lets `severity_map` mean something: one setting regrades every
issue at that severity, in one place, without touching a line of text.

### 2. A watched band reports while it is empty

A band is emitted when it is named in `severity_map` **or** present in the data. So the
five default bands are always on screen, green when there is nothing in them.

The alternative — render a band only when it has findings — loses the difference between
*nothing critical today* and *the critical band stopped being produced*. A green band is
a reading; an absent one is a silence, and a monitoring tool that answers a question by
saying nothing has not answered it.

The corollary is that a severity **the data brings and nothing declares** still gets a
band, and grades `WARN` rather than being dropped. WIZ can add a severity without asking
us; a check that silently discarded it would under-report by exactly the amount nobody
would think to look for. `WARN` is the deliberate middle: loud enough to be seen, not so
loud that a vendor's taxonomy change pages somebody at night. A deployment that knows
what the new band means names it in its own `severity_map` and the guess stops applying.

### 3. A line is keyed by something WIZ minted

Each band's lines are **keyed entries** (little-sister ADR-0036), so an engineer who
opens a ticket for one finding can pin that line while the other nineteen keep
reporting. The key is built from an identifier the provider issued — the control ID
(`wiz-control-<control-id>`) or the issue ID (`wiz-<issue-id>`), depending on
`aggregation_level` — and never from the rendered text and never from a position in the
list (little-sister ADR-0050).

That is the decision with the longest reach, because **a key is stored somewhere else**:
in a deployment's maintenance pins, written against names this package publishes. Keying
on text would silently re-point every pin the first time a line was worded better;
keying on position would re-point them whenever WIZ returned the same issues in a
different order, which it may do at any time. An issue that arrives with no id has
nothing stable to key on and falls back to little-sister's content hash — a worse
identity, and still not a position.

### 4. An issue with no control ID gets its own bucket

Under `aggregation_level: id`, issues are grouped by control. An issue whose control has
no id is **not** merged with the others that lack one. Sharing an empty-string bucket
would put unrelated findings on a single line and, worse, move a maintenance pin made
for one of them onto work it was never made for.

### 5. TLS verification is not a knob

The original disabled certificate verification and silenced the warning that says so.
This package verifies, always, and offers no setting to stop. A monitoring tool that
accepts an unverified connection to a security vendor is asserting something it did not
check. A deployment behind a proxy with a private CA supplies that CA through the
environment, which is a statement about *which* authority is trusted rather than about
whether any is.

### 6. `api_url` is required and has no default

The WIZ GraphQL endpoint is region-specific. A default would be a guess that resolves,
authenticates against the wrong region and fails at the first run — or, worse, at the
first run that happens to matter. Required-with-no-default moves that failure to
**load**, where little-sister's refusal to start makes it one loud event instead of a
check that is quietly never green.

It is also the one value here that names a tenant, which is the type-vs-deployment line
arriving from the direction that proves it: it could not have travelled with the package
even if we had wanted a default.

### 7. `IN_PROGRESS` is a finding, not a hidden state

little-sister has no in-progress status and is not growing one for this. An issue WIZ
marks as in progress stays counted in its band and says *in progress* on its own line.

Hiding it was tried in the predecessor and had two engineers pick up the same finding on
the same afternoon. Somebody working on a thing is not the same as the thing being
fixed, and only the line is entitled to make that distinction — the band's status is
about the tenant's exposure, which has not changed.

### 8. One page, and the cap is a ceiling rather than an error

A run fetches a single page of `first` issues (default 500), ordered by severity
descending. Beyond that, findings are silently not seen.

This is stated rather than defended: it matches the original, no tenant here approaches
it, and pagination is real work for a bound nobody has hit. What makes it tolerable is
the ordering — a tenant over the cap loses its *least* severe findings first, so the
band this check exists to grade is the last one to go wrong. It is named here so that
the next person meets it as a known limit and not as a mystery, and raising `first` is
the answer until it is not.

## Consequences

- **`severity_map` is a supported disagreement.** A deployment that thinks `medium`
  should be amber rather than red says so in its own config, and this record is the case
  it is arguing against rather than a default it has to reverse-engineer.
- **A slug is a promise.** Because the keys are published identifiers, changing how one
  is composed is a breaking change for every deployment holding a pin, whatever the code
  says. That belongs at the top of the release notes when it ever happens.
- **A rewording is free**, which is the same decision seen from the other side, and is
  what makes it safe to improve a line's text at any time.
- **What a band renders as is not settled here.** The order the bands appear in, and
  whether a band's title should carry its severity as a glyph, are display questions this
  record deliberately does not answer — they depend on a library change that does not
  exist yet.
- **The provenance of the port** — where each piece came from, what travelled and what
  stayed behind — is a working note and stays on the working branch. What a consumer
  needs is the reasoning, which is this file.
