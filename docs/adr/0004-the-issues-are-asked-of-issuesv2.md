# ADR-0004 — The issues are asked of `issuesV2`, for the two types the old query answered

- **Status:** Accepted
- **Date:** 2026-09-26
- **Related:** [ADR-0001](0001-severity-bands-are-what-grades.md) (the bands, and a
  line keyed by its control — decisions 2, 3, 4, 6 and 8, which this keeps, the last
  with WIZ's ceiling), [ADR-0002](0002-a-read-failure-is-not-a-finding.md) (what a
  refused or unreadable answer means, which this keeps exactly),
  [ADR-0003](0003-a-run-is-the-exposure-and-its-issues.md) (the readings, their field
  names and their bounds, which this keeps exactly), little-sister **ADR-0050** (a key
  is an identifier, never a position), little-sister **ADR-0036** (a line is a member a
  pin can hold)

> Every reference to one of little-sister's records is written out as **little-sister
> ADR-00NN**, because the two numbering spaces overlap.

## Context

This package asked WIZ's `issues` query and read `control` and `entity` off each issue,
and WIZ's developer changelog says what became of all three. `entity` was removed from
the Issues API on `2022-08-31`. `control` was deprecated on `2023-05-15` in favor of the
rules that raised an issue. On `2023-06-07` the query itself became `issuesV2`, which
*can return Issues created from Controls, Cloud Configuration Rules, and Threat Detection
Rules* — *We highly recommend updating your query to `issuesV2`* — and WIZ's *Get Risk
Issues* page documents it alone. On `2025-04-02` WIZ announced that it is limiting API
access to documented APIs, so that undocumented queries *will no longer work*, with a
warning in the response first. The announcement is addressed to the partners of its
integration network and does not say whether a tenant's own service account is held to
it.

The old query still answered, which was WIZ's leniency and not its contract, and two
things made waiting on it worse than moving. A warning in the answer would reach nobody:
this package reads nothing of an answer but `data` and `errors`. And a retired field does
not always end loudly. A field gone from the schema is a validation error, which grades
ERROR (ADR-0002 decision 3), but WIZ has retired Issues fields that went on answering
with `null` — and `control` answering `null` would move no count and change no code,
while every control's line came apart into one line per issue and every maintenance pin
on it stopped applying.

The documented query is not a rename, and three of its differences are decisions:

- **The rules that raised an issue are an array**, `sourceRules`, of three kinds: a
  `Control`; a `CloudConfigurationRule`, which names its parent `control` as well; and a
  `CloudEventRule`, a threat detection rule. The old query named one control per issue,
  and a line's key, `wiz-control-<control-id>`, is a stored key: a deployment's
  maintenance pins are held against it (ADR-0001 decision 3).
- **An issue has one of three types** — `TOXIC_COMBINATION`, raised by a Control;
  `CLOUD_CONFIGURATION`, raised by a configuration rule; `THREAT_DETECTION`, raised by a
  threat detection rule, which a Wiz Defend license brings — and `issuesV2` answers all
  three unless a `type` filter narrows it. So replacing the query is also choosing what
  the check reads.
- **`first` is from 1 to 1000** on WIZ's page, where this package accepted any integer.

**What was measured, and how.** Before the query was written, both queries were asked
side by side for each of two configured checks, exactly as each check asks — its
endpoint, its credential and so its project scope, its `first`, its status filter and its
order — once with no type filter and once with each filter this record could name, and
the answers were compared in both directions. The two queries answered the same issues,
none of either that the other lacked, with either filter. Every issue was a
`TOXIC_COMBINATION` naming exactly one rule, a `Control`, whose id was the old
`control.id` — 248 of 248 — and the keys a line is slugged by matched in every band.
Neither estate held a single `CLOUD_CONFIGURATION` or `THREAT_DETECTION` issue.

The one field that did not agree was the entity's name: the old query returned 19 of the
248 issues without one, 15 in one estate and 4 in the other, where `entitySnapshot` names
each. Run in the deployment that watches both estates, the new query still counted those
issues at its first runs, and within the hour they had left the estate — from 133 to 118
in one and from 115 to 111 in the other, both at the same run. The objects had been
deleted: the old `entity` reads the object as it is now, so a deleted one has no
name, and WIZ resolved the issues on its next pass. WIZ's own record of one of them
gives `OBJECT_DELETED` as the reason, between the run that still counted it and the
next. Where a decision below rests on these measurements it says so, and where it rests
on WIZ's word it says that.

## Decision

### 1. The query is the one WIZ documents, and the readings keep their names

The check asks `issuesV2` under WIZ's own alias, `issues:`, as its page writes it, so the
answer is `data.issues.nodes` as it always was and ADR-0002 decision 6 reads it
unchanged: an empty list is zero issues, a missing one is no answer. It asks for what a
line reads and nothing else — each issue's id, severity and status; the `Control`s and
configuration rules among its `sourceRules`, a configuration rule by its parent
`control`; and the `entitySnapshot`'s name and type. The variables are the old ones, one
page of `first`, open and in progress, worst severity first, with a `type` filter
(decision 2).

**The readings keep their shape and the names of their fields** (ADR-0003 decision 1):
`control_id` and `control_name` are the control decision 3 names, and `entity_name` and
`entity_type` are the `entitySnapshot`'s. Those names are stored keys — a deployment's
line template or grading reads them — so the new source fills the old names rather than
renaming them. The fields keep their bounds as well, so ADR-0003 decision 7's heaviest
reading is what it was.

### 2. The check reads today's estate, and the filter names it

The `type` filter names `TOXIC_COMBINATION` and `CLOUD_CONFIGURATION`: the issues a
Control or a configuration rule raised, which are the ones the old query answered. The
estate is named rather than left to whatever `issuesV2` answers by default, so what the
check reads is a stated choice a reader can find; and it is **today's**, because a change
of query is not the moment to change what the bands grade. Widening it is a decision of
its own.

**`TOXIC_COMBINATION` is measured**: every issue both queries returned was one.

**`CLOUD_CONFIGURATION` is WIZ's word, not a measurement** — neither measured estate held
one, so the old query had none to return — and it is named for two reasons. WIZ's
changelog of `2023-05-15` says configuration rules raised issues before cloud event rules
could, and that the old `control` could be null only for an issue a cloud event rule
raised; so the old query answered a configuration rule's issue, with its parent control.
And the two ways of being wrong are not alike. Named on an account that turned out wrong,
such issues would arrive at the upgrade, where a reader sees them. Left out on an account
that was right, they would leave the bands without a word — the silence ADR-0001 decision
2 argues against, an under-report by exactly the amount nobody would think to look for.

**`THREAT_DETECTION` is not read.** WIZ's account does not settle whether the old query
answered it — its changelog of `2023-05-15` has the old `control` null for an issue a
cloud event rule raised, that of `2023-06-07` has `issuesV2` made to answer the issues of
every rule — and reading detections is a decision about what the bands grade: a
detection is an incident with a lifecycle of its own, where the bands grade a tenant's
posture. Neither measured estate held one.

### 3. A line is keyed by the control the issue's rules name

A `Control`'s own id, or a configuration rule's parent control's id: the control the old
query named, so `wiz-control-<control-id>` does not move and every pin still holds. The
first is measured, 248 of 248; the second rests on WIZ's word, as decision 2 does. The
line names that control, and `ignore_control_ids` matches it — for a configuration rule's
issue its parent's id, not the rule's own.

**An issue whose rules name no control** keeps a line of its own, keyed by the issue, as
an issue with no control id always has (ADR-0001 decision 4): no rules at all, a cloud
event rule, a configuration rule whose parent is null. A control that comes without an id
keys nothing either, and its name still reaches the issue's line, as it did.

**An issue whose rules name more than one control is filed under the one with the
smallest id**, compared as text. None of the 248 did, and WIZ's page shows several rules
only on a threat detection, which decision 2 leaves out, so this is the answer for a case
not yet seen, chosen for what it does if it comes:

- **Not the first WIZ lists.** That keys the line by a position in an array, which moves
  when WIZ reorders it, and a pin moves with it — little-sister ADR-0050's reason a key is
  an identifier and never a position, and ADR-0001 decision 3's reason a line is never
  keyed by its place in the list of issues.
- **Not a line of its own.** It never guesses between controls, but the reading carries
  one control, so the line would name none: `[issue]` where a control's name stood.
- **Not a line under each.** One issue on several lines: a pin quiets it on one and not
  on the others, and a band's lines no longer add up to its issues.

The smallest id is stable whatever WIZ's order, and it still names a control. What it
costs is stated: the issue shows once, under one of the controls that raised it, and
`ignore_control_ids` skips it only when that control is the one listed.

### 4. The entity is WIZ's `entitySnapshot`

Its name and its type, where the old query read `entity`, which WIZ removed from the
Issues API on `2022-08-31`. WIZ's page gives `entitySnapshot` as the entity that triggered
the issue, and a snapshot keeps what the issue was raised on after the object is gone,
which is what a line should name. An issue on an object deleted since it was raised still
names what it was raised on, where the old query read the object as it is now and had
nothing to name, so its line said *WIZ issue* and the issue's id. The 19 issues the
measurement found without a name in the old query were such issues.

### 5. `first` is from 1 to 1000, and a value outside that refuses to load

WIZ's page takes `first` from 1 to 1000. A query that asks outside that asks for what
the documented API does not take, and what comes back — a refusal, which grades ERROR
(ADR-0002 decision 3) on every run, or a page quietly cut to what WIZ allows — is WIZ's
to choose. So the check refuses such a value once, at load, with a sentence that names
the range — ADR-0001 decision 6's argument for `api_url`: a wrong value is one loud
event where it can be fixed, not a red node on every poll, and the configuration never
says more than the check can ask. A value that is not an integer is refused the same
way, where it used to stop the load with a bare `ValueError` that named neither the file
nor the key; the check is the one `little-sister-github` already makes of such a count,
with WIZ's ceiling on it. The key keeps its name, its default of 500 and its meaning:
one page, worst first (ADR-0001 decision 8), whose ceiling is now WIZ's.

Two other answers were weighed. **Clamping to 1000** would ask for less than the
configuration says and say so nowhere. **Paging past 1000**, with `after` and
`pageInfo.endCursor`, would lift ADR-0001 decision 8's ceiling, but a run would then
make several queries against one budget, a read could fail between two pages, and the
estate's `page_full` would change its meaning — real work for a bound no measured estate
is near.

## Consequences

- **No slug moves, and no configuration key is renamed or removed**, so every
  maintenance pin still matches (ADR-0001 decision 3) — measured on two estates, and by
  the comparison below.
- **The tree says what it said.** Measured rather than argued: the module as it was and
  this one, each over one set of fixtures written in its own query's shape — mixed
  severities, a missing and an invented one, controls shared and missing, a control
  without an id, a configuration rule's issue, issues without ids or entities, duplicate
  ids, in-progress lines, names past the clip budget, a full page and failed reads, under
  the default configuration, both aggregation levels, the ignore list and a custom
  grading map — agreed on every band, code, slug, line, label and reading.
- **An issue on an object deleted since it was raised still names what it was raised
  on**, where its line named nothing but *WIZ issue* and the issue's id, so a few lines
  say more than they did.
- **One configuration can refuse to load**: a `first` above 1000, below 1, or not an
  integer. The refusal names the range.
- **A configuration rule's issue reads as a Control's**, under its parent control and
  named by it. None has been seen yet; if one ever keys differently from what the old
  query would have said, it is decision 2's account of WIZ that was wrong.
- **What this does not do.** It reads no threat detection, pages past no 1000, and still
  reads no GraphQL error's code. Each is a decision of its own.

## Alternatives considered

- **Every type WIZ raises.** The fuller reading of *open issues*, and what ADR-0001
  decision 2 argues for in general. Refused in decision 2: it changes what the bands grade
  at a moment meant to change nothing, and it needs keys and texts for a rule that is not
  a control.
- **`TOXIC_COMBINATION` alone**, all that was measured. Refused in decision 2: it drops,
  without a word, what WIZ's account says the old query answered.
- **No filter, the estate being whatever `issuesV2` answers.** The estate would change
  whenever WIZ added a type, and nothing here would say so.
- **A configuration rule's own id as the key.** The old query named the parent control;
  the rule's own id would move the key of every such issue it answered.
- **The first control WIZ lists, a line of its own, or a line under each**, for an issue
  whose rules name several. Refused in decision 3.
- **Clamping `first`, or paging past 1000.** Refused in decision 5.

