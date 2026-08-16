# ADR-0002 — A read failure is not a finding about the tenant

- **Status:** Accepted
- **Date:** 2026-08-15
- **Related:** [ADR-0001](0001-severity-bands-are-what-grades.md) (the band is what
  grades — this record is what happens when there is no band to grade),
  little-sister **ADR-0058** (one transport policy for the family, and any client —
  the vocabulary this record adopts), little-sister **ADR-0040** (a failing check is
  all-or-nothing — the shape this record works around), little-sister **ADR-0033**
  (the budgeted failure retry — whose realm this deliberately does not enter),
  `little-sister-github` ADR-0002, which decided the same question for a different
  API and named this package as the place the rule would have to be settled next

> Every reference to one of little-sister's records is written out as **little-sister
> ADR-00NN**, because the two numbering spaces overlap.

## Context

[ADR-0001](0001-severity-bands-are-what-grades.md) settled what this check *asserts*:
one leaf per severity band, the band's status is the whole claim, and an issue is an
entry on the band that owns it. It says nothing at all about the case where there is
**nothing to assert** — where WIZ did not answer — and neither did the code, which is
how three defects lived side by side in one client nobody had ever tested.

**None of them were reachable by the suite.** Every test in this package stubbed
`_make_client` and handed the check a fake, so the OAuth2 exchange, the GraphQL
envelope, the status handling and the retry loop were asserted by nobody. That is the
context for all three findings below: they are not subtle, and the reason they survived
is that the one seam the tests never crossed was the only place they lived.

### 1. Nothing bounded a run

`timeout:` is the check's one duration. It was handed to the socket layer as the
**per-request** timeout, so an auth request plus up to three query attempts each got
the whole of it — a 30-second budget could spend two minutes, and the example config's
`timeout: 120s` could spend eight. Nothing else bounded it either: the engine calls
`run()` with no deadline of its own, on the stated understanding that honouring
`timeout:` is the check's job. A slow WIZ could hold a run past its own `frequency:`
indefinitely, and a wedged check reports **nothing at all**, which is worse than any
reading it could have produced.

### 2. The retry asked three times in the same millisecond, and skipped the commonest
transient status

The loop was `for _ in range(3)` with `continue` on 502/503/504 and **no wait between
attempts** — an endpoint that had just failed was asked again immediately, which is the
one thing certain not to help. A plain **500** was not retried at all; a `429` was not
recognised; and the sentence at the end of the loop was
`WIZ query failed after retries (5xx)`, which threw away the status and the body it had
just been handed three times. The token exchange sat outside the loop entirely, so one
503 from the auth endpoint ended a run that the next second would have completed.

### 3. An answer with no payload in it read as a clean tenant

The issue list was read as
`((body.get("data") or {}).get("issues") or {}).get("nodes")`, handed to
`list(… or [])`. So a 200 with no `data` — a schema change, a partial response, a
gateway's own JSON — became **zero issues**: every band green, and a security tenant
reported as clean by a check that had been told nothing. This is the one defect here
that is not about timing, and it is the worst of the three: a monitoring tool that
answers *all clear* when it has no answer has failed in the only way that matters.

Two smaller faults sat beside it. `json.loads(text)["access_token"]` and
`json.loads(text)` raised `KeyError` and `JSONDecodeError` **past** `run()`'s
`except WizError`, so the engine turned the whole check into an all-or-nothing check
error (little-sister ADR-0040) instead of a reading. And `_post` returned
`(status, text)` while swallowing `HTTPError` into a normal return, which is what left
every caller responsible for remembering to look at the status.

## Decision

### 1. The vocabulary is the library's, and the client keeps only WIZ

`WizError` is a `RemoteError` subclass (little-sister ADR-0058), so `fault` is required
and has no default: the classification is the decision this package must not take by
accident. `fetch` replaces the hand-rolled `urlopen`, `Deadline` bounds the run, and
`ask` replaces the retry loop.

What stays is what only a WIZ client can know: the OAuth2 client-credentials exchange,
the GraphQL envelope, and reading that envelope's own error channel. TLS verification
is still not a knob (ADR-0001 §5) — now because `fetch` offers no way to make it one,
which is a stronger guarantee than this package refusing to add a setting.

### 2. Two budgets, and `timeout:` is the run's

`timeout:` becomes the whole run's deadline, checked before every request, and each
request's socket timeout is **clamped to what is left of it**. Without the clamp a
120-second request could start with two seconds of budget left and overrun the run by a
hundred and eighteen, which would make the deadline a suggestion rather than a bound.

**There is no separate `request_timeout:` key**, unlike the sister package, and that is
a decision rather than an omission. `timeout_seconds` is passed as *both* the run's
budget and one request's bound, so **no single request is tightened by this change** —
which matters because a deployment already runs with `timeout: 120s`, and a new
per-request default would have quietly halved or quartered it. At four requests a run
the run's own budget is a defensible per-request bound too; the sister package needs the
split because it makes hundreds. The key can be added the day a deployment's region is
slow enough that one request genuinely wants a different number from the run.

### 3. A failure is transient, an answer, or unreadable — and the status decides

| what came back | fault | what it means |
|---|---|---|
| **5xx**, or a transport failure | `TRANSIENT` | we could not ask |
| **429** | `TRANSIENT` | we asked too often — *not now* |
| **401**, **403** | `ANSWERED` | this credential is wrong or unauthorized |
| any other 4xx, a **3xx** | `ANSWERED` | WIZ answered, and the answer is no |
| **GraphQL `errors`** inside a 200 | `ANSWERED` | the query was rejected |
| a payload we cannot read | `MALFORMED` | it arrived and it cannot be used |

By status and by the envelope, **never by message text**. Two rows are worth their own
sentence:

**A `429` is transient here, and the library keeps it *answered*.** That divergence is
deliberate. `fault_for` is cautious because a 429 in the general case may be crawler
protection with no stated end; this is an authenticated API with a documented rate
limit, and being over it is a *not now*. Knowing whose 429 it is, is exactly the
knowledge little-sister ADR-0058 says belongs in the vendor's package.

**A `401`/`403` is not, and this package needs no dialect reader because of it.** The
sister package has to read GitHub's headers to tell a throttled 403 from a permission
403; here there is nothing to disambiguate, because this check holds **one credential
for a whole tenant** — a refusal means the client ID or secret is wrong, and no amount
of asking again will make it right. So the **standard `Retry-After` is the whole of
what is read**. A WIZ-specific header set nobody here has verified is not something to
invent: guessing a dialect is worse than not reading one, because a wrong guess waits
the wrong length of time and looks like it worked.

### 4. Only a transient failure is retried, and the wait is bounded by the run

Three attempts, which is the count the old loop already made — what was wrong with it
was not its length. Now with a **1-second backoff between them**, spent only while the
deadline can still afford it, and with a wait WIZ named replacing that backoff when it
sends one. The auth request is inside the retry too.

**A wait longer than the run has left is refused and the error re-raised.** A
ten-minute `Retry-After` inside a thirty-second run is not slept through: the line says
how long WIZ asked for, and the run reports what it has. When to ask again is
`frequency:` and the engine's business (little-sister ADR-0033) — **a check and an HTTP
request are different realms**, and a request layer does not reschedule anything.

### 5. *We could not ask* warns; an answer, and an unreadable answer, still grade

This is `little-sister-github` ADR-0002's rule arriving at the second check type, as
that record predicted it would have to. A `TRANSIENT` failure means the check could not
look, which is a fact about **WIZ** and not about this tenant's cloud posture — so the
node says `could not ask WIZ this run: …` at **WARN** rather than ERROR.

`ANSWERED` and `MALFORMED` keep grading **ERROR**. A rejected credential and a changed
schema are both real, both about this deployment rather than about WIZ's weather, and
both need a person. Reading them as *we could not ask* would be the mirror of the
defect in §3 of the Context: a check that shrugs at its own misconfiguration.

**The shape is simpler here than in the sister package, and only because this check has
one call.** There is no per-repository line to protect and nothing partial to keep, so
there is no `UNDEFINED` entry and no coverage sentence: the whole reading either arrived
or did not. The band leaves are **not** rewritten on a failed run — they keep their
previous reading and go stale on freshness (little-sister ADR-0005), which is the honest
display of *this is the last thing we actually knew* and is what ADR-0001 §2's argument
about absent bands asks for.

### 6. An empty `nodes` list is zero issues; a missing one is no answer

The distinction §3 of the Context lost. `data.issues` must be an object and its `nodes`
must be a list; anything else is `MALFORMED` and grades. An empty list stays what it has
always been — a tenant with nothing open, which is a real and common answer and the one
this check exists to be able to give.

### 7. Redirects are not followed

`urlopen` followed them. On a redirect urllib turns a POST into a GET, so a
misconfigured endpoint could silently drop the request body and fail as something else
entirely. A 3xx from an API endpoint means the URL is wrong — which for a
region-specific `api_url` with no default (ADR-0001 §6) is precisely the thing a reader
needs to be told, and following it hides.

## Consequences

- **A WIZ outage is amber, not red.** This is the operator-visible change and it is
  intended. If a deployment wants to be paged when its security tenant cannot be read,
  that is a `severity_map`-shaped wish this record does not grant — the node's code is
  not configurable, and making it so is a separate decision.
- **Re-read your `timeout:`.** It used to be spent per request and now bounds the whole
  run. A value chosen for one request will cut runs short; the example config's `120s`
  is now a ceiling on the auth request and up to three query attempts together.
- **No config key changes and no slug moves**, so every maintenance pin still matches
  (ADR-0001 §3's promise is untouched).
- **A test's claim was overturned**, not patched: `test_query_error_is_error` asserted
  ERROR for a 500, which is the case that now warns. It is replaced by one that pins the
  new reading, alongside a test for each of the other two faults.
- **The client has tests now** — its first. They stub the opener *below* `fetch`, so what
  runs is the shipped status handling, the shipped classification and the shipped retry,
  rather than a fake standing where the decision lives. Coverage of this module went from
  77% to 97%, and the eight lines still uncovered are all older than this record.
- **Requests identify themselves as `little-sister/<version>`**, the library's own, in
  place of an unversioned `little-sister-wiz`. A version is what makes the string useful
  in a vendor support thread.
- **The install floor rises**, because the names above are promised by a little-sister
  release. That release, this one and the sister package's go out together.
- **What this does not do.** It adds no pagination (ADR-0001 §8's cap is untouched), no
  per-request config key (§2), and no vendor throttle dialect (§3). Each is named so the
  next person meets it as a bounded decision rather than as an oversight.
