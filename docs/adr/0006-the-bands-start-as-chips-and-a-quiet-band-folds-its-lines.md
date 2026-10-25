# ADR-0006 — The bands start as chips, and a band nothing waits on folds its lines

- **Status:** Accepted
- **Date:** 2026-10-25 (accepted 2026-10-24)
- **Related:** little-sister **ADR-0128** (where a node's first look comes from: its
  keys, the layers that state them), little-sister **ADR-0127** (the wall as a tree: a
  chip, a click that opens a node, the failure budget, *✓ +N ok*),
  [ADR-0001](0001-severity-bands-are-what-grades.md) (a band per severity, graded by
  `severity_map`; a line per issue, pinned on its own), little-sister **ADR-0133** (a
  band's `about`, which says by the map in force whether anything waits on it)

> Every reference to one of little-sister's records is written out as **little-sister
> ADR-00NN**, because the two numbering spaces overlap.

## Context

little-sister's wall is a tree whose nodes start open or closed (its ADR-0127), and a
check type proposes how the levels it writes first look (its ADR-0128): whether a
node's children start as chips, whether its healthy children and lines start folded
behind *✓ +N ok*, and its box's line budget. A deployment takes a proposal back in its
check's own file, by name, or per path in `nodes.yaml`. A level nobody speaks for keeps
the density the page drew before the tree — a quiet leaf a chip — until little-sister's
built-in look becomes *open, its healthy shown*, after the family's types have declared
theirs.

This check writes a band per severity beneath its own node: a ladder of five leaves,
each read by its count, whose lines are its open issues (ADR-0001). The band nothing
waits on — `informational`, which the shipped map grades OK — holds the most: on one
deployment's own tree, anonymized, seventeen issues, four of them over a thousand
characters, and a tenant's state has held 148. Drawn open, that band is a card's height
of lines that ask for no work.

A band whose issues the map grades WARN or ERROR opens wherever its look closes it, by
little-sister's failure budget, to say why it is red, and its box shows as many lines as
`settings.yaml` gives every box: six by default, thirty on that deployment. A failing
band's issues are written as `informational`'s are and may run as long, so at thirty
lines one failing band can stand a card's height, where its first few issues say why.

The look little-sister's interactive wall was measured with, on Lex's word, has the
bands as chips and `informational`'s lines folded; on his word of 2026-10-25 a failing
band's box shows ten lines, as GitHub's bands do in `little-sister-github`.

## Decision

### 1. The bands start as chips

The check's own node proposes it — `OWN_LOOK`, handed to little-sister as
`node_defaults`, `chips: true` — since a band's name reaches the band and not the node
it hangs beneath. A band that fails opens its way as little-sister opens a failure a
chip would hide, the first three of each card, and the check's own page draws every band
open, as a page opens its node's children.

### 2. A band the map grades OK folds its lines

`_band_labels` declares `fold_ok: true` beside the labels of each band the map in force
grades OK: by the map, as the band's `about` is, so `informational` under the shipped
map, and a band a deployment grades OK beside it. Open, such a band shows its issues as
*✓ +N ok*, and a click shows them; a band graded WARN or ERROR declares no fold, its
lines being its work.

### 3. A band's box shows ten lines

`OWN_LOOK` says it of the check's own node's children, `children: {reason_cap: 10}`
from `BAND_LINES`, so that a band only WIZ's findings name takes it too. A band that
fails says why with its first few issues, and the rest stand under its *⌄ all N* and on
the band's page, which lists them all. The budget is the type's, above the one
`settings.yaml` gives every box; the check's own box keeps the deployment's.

### 4. A deployment takes it back in its own file

`chips: false` at the top of the check's file opens the bands,
`children: {reason_cap: 20}` there gives a band's box twenty lines, and `fold_ok: false`
under a band's name in its `subnodes:` block shows its lines; `nodes.yaml` speaks per
path, above them. The keys are little-sister's (its ADR-0128 decision 1), read in the
same entries as the labels, and none is a key of this type's own.

## Consequences

- **Once the built-in look changes, the card stays a row of chips.** Drawn as it will
  be then, on that tree mounted as the deployment mounts it, the card is 129 pixels
  tall at 1,920 where its bands open would stand it at 1,044, and the check's own page
  one screen of 900 pixels at 1,280 where `informational`'s seventeen issues open stand
  it at 1,314.
- **The wall is laid out from the proposal now.** little-sister's planner prices the
  first look, so with GitHub's and AWS's proposals standing the card is priced as the
  row of chips it is drawn as: at 1,920 pixels it takes one track and the AWS card one,
  the wall 1,703 pixels tall where AWS's proposal alone laid it out at 1,472; at 2,560
  1,328 where 1,339; at 1,280 1,741 where 1,849; on a phone as it was.
- **A failing band's box is ten lines tall at most, whatever `settings.yaml` says**:
  shorter than a deployment's thirty, four lines taller than the library's default of
  six. On little-sister's wall-cost harness nothing moves, since that tree's failing
  bands hold one issue each.
- **It draws once a deployment runs a library that reads it**, little-sister 0.3.21,
  which this package requires already.
- **No name moves**, so a pin or a `nodes.yaml` entry on a band holds.

## Alternatives considered

- **`informational` folded by its name**: the measured look's words, and the same under
  the shipped map; but whether anything waits on a band is the map's to say, as its
  `about` says it, and a deployment that grades `low` OK would see its issues open.
- **The deployment's budget for the bands**, what a band took before: thirty lines on
  that deployment, a card several issues deep for one failing band, where the first few
  say why it is red.
- **Ten lines by each band's name**: a band only WIZ's findings name would keep the
  deployment's budget.
- **The bands open**: five boxes, most of them empty while the tenant is well, where a
  chip says the same with its count.
