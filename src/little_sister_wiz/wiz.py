"""The ``wiz`` check type: open cloud-security issues, one leaf per severity band.

Authenticates to WIZ with OAuth2 client credentials, asks WIZ's ``issuesV2`` query
for the open and in-progress issues a Control or a configuration rule raised, and
reports one leaf per severity band under the check's node, from ``critical`` through
``informational``. Each band is graded by a configurable
``severity_map`` and lists its findings. Findings are grouped by WIZ control ID by
default; ``aggregation_level: entity`` gives one line per issue and affected entity.
Ported from an older in-house alerting dashboard. Why it is shaped this way — the
band as the unit that grades, and what a line is keyed by — is
``docs/adr/0001-severity-bands-are-what-grades.md``; which issues are read, and which
control a line is keyed by now that WIZ names the rules that raised an issue, is
``docs/adr/0004-the-issues-are-asked-of-issuesv2.md``.

A band's lines are **keyed entries** rather than plain strings (little-sister
ADR-0036), slugged by the identity of the configured aggregation level — a WIZ
control ID or a WIZ issue ID: an engineer who opens a ticket for one finding pins
that line, and the other nineteen keep reporting. The parts are identifiers the
provider minted, never the rendered text and never a position (little-sister
ADR-0050).

Registered in little-sister's ``CHECK_TYPES`` on import — importing
``little_sister_wiz`` is the one line a deployment's ``wsgi.py`` adds, before
``little_sister.app``, so the ``wiz`` type is known when the engine loads the check
configs. The OAuth2 credentials are named by the config's ``secrets:`` block and
resolved once at construction (little-sister ADR-0023).

A run is two halves (little-sister ADR-0086). :meth:`WizCheck.measure` reads WIZ and
hands back the **estate** — the tenant's exposure per severity band, and whether the
read worked — and then one reading per issue; :meth:`WizCheck.grade` builds the bands
and their lines out of those readings and nothing else. What each reading is, which of
them has a history and what that history is of are
``docs/adr/0003-a-run-is-the-exposure-and-its-issues.md``.

Everything imported from little-sister below is part of its **check-authoring
surface** (architecture.md §11), which is what the ``require_api(3)`` in this
package's ``__init__`` pins.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from little_sister.checks import (
    Check,
    CheckError,
    CheckResult,
    Measurement,
    coerce_code,
    config_markdown,
    parse_secret_refs,
    plain,
    register,
)
from little_sister.fetch import Response, fault_for, fetch, retry_after
from little_sister.reasons import (
    MAX_SUBJECT_LENGTH,
    Entry,
    clip,
    derived_slug,
    slug,
)
from little_sister.status import StatusCode
from little_sister.transport import (
    Deadline,
    DeadlineExceeded,
    Fault,
    RemoteError,
    ask,
)

#: This package's own logger. little-sister does not promise its ``logger`` to check
#: authors and does not need to: the library configures the root handlers, so an
#: ordinary module logger's records land in the same place, under a name that says
#: which package emitted them.
logger = logging.getLogger(__name__)

_T = TypeVar("_T")

TOKEN_URL = "https://auth.app.wiz.io/oauth/token"
AGGREGATION_LEVELS = ("id", "entity")
DEFAULT_AGGREGATION_LEVEL = "id"

#: How many extra attempts a **transient** failure gets. Two, which is the three
#: attempts the hand-rolled loop this replaced already made — the count is preserved
#: deliberately, because what was wrong with that loop was not its length: it asked
#: three times with **no wait at all**, and it retried ``502``/``503``/``504`` while
#: letting the plainest transient status of all, a bare ``500``, through as final.
TRANSIENT_RETRIES = 2

#: The wait before each of those attempts. A retry with no backoff asks an endpoint
#: that just failed again in the same millisecond, which is the one thing certain not
#: to help — and it is spent only while the run's deadline can still afford it.
RETRY_BACKOFF_SECONDS = 1.0

#: Free text a reading keeps — a control's name, an entity's name, a failure's
#: sentence — clipped **once**, in the measuring half, to this many characters and
#: then to this many of the bytes the seam weighs a record in (little-sister ADR-0086
#: decision 7). The line is written from the clipped value, so what a grading says
#: today can always be said again from the reading stored beside it. The numbers are
#: little-sister-github's, and for the same reason: two names and a sentence stay far
#: inside a 2 KB record however they are spelled.
_TEXT_CHARS = 300
_TEXT_BYTES = 600

#: What an identifier or a short field WIZ sends is held to — an issue's id, a
#: control's id, a severity, a status, an entity's kind. WIZ mints these short (an
#: issue id is a UUID), so the bound is not met in practice; it exists so that no
#: answer, however strange, makes a record the seam refuses (ADR-0003 decision 7).
_SHORT_BYTES = 100

# Built-in display text for the severity-band leaves this check emits (little-sister
# ADR-0025). This text is type-inherent, so it is written once here rather than copied
# into every deployment config; a second tenant's check is then config only. It is
# **declared, not applied** — `_band_labels` hands it to little-sister as
# `subnode_defaults` and the library resolves a deployment's `subnodes:` block over
# it, replacing one of these or extending it where the config writes `{default}`, and
# the engine writes the result per band name. `nodes.yaml` still wins over both, per
# node path, and `{entry_note}` is a `label_tokens` entry expanded in either text.
#
# **None of them names a code, and that is the rule rather than an omission.** These
# texts used to read `graded ERROR` / `graded WARN` / `graded OK`, which is a setting
# written as prose: `severity_map` is what decides a band's code, this constant cannot
# see it, and a deployment that graded `medium` as WARN read `graded ERROR` on the
# medium band's own page. What a severity *means* belongs here; what it is *graded*
# belongs in the band's `config` card, where a reader expects what the check ran with
# and where it is expanded from the map in force (`_band_config`).
#
# **No `title` here either**, and for a related reason: a band's title is derived
# from its severity (`band_glyph`) rather than written per band, so the row cannot
# grow a sixth entry whose color nobody chose. What is authored here is prose;
# `_band_labels` is where the derived half joins it.
SUBNODES: dict[str, dict[str, str]] = {
    "critical": {"about": "Critical-severity WIZ issues — fix immediately.\n\n"
                          "{entry_note}"},
    "high": {"about": "High-severity WIZ issues — fix on the current sprint.\n\n"
                      "{entry_note}"},
    "medium": {"about": "Medium-severity WIZ issues — needs fixing, not only "
                        "knowing.\n\n{entry_note}"},
    "low": {"about": "Low-severity WIZ issues — worth knowing, and still work "
                     "somebody has to schedule.\n\n{entry_note}"},
    "informational": {"about": "Informational WIZ findings — nothing to do, watched "
                               "so that a quiet band is visibly quiet.\n\n"
                               "{entry_note}"},
}

# The paragraph every band's `about` ends with, selected for the configured
# aggregation level and referenced as `{entry_note}` so it is written once
# (little-sister ADR-0025). It explains the line format and the operationally
# important fact that a line is individually pinnable.
ENTRY_NOTES = {
    "id": (
        "Each line is one WIZ **control**, linked to one concrete WIZ issue ID and "
        "followed by every affected entity and its kind. A finding marked "
        "*in progress* is already being worked on in WIZ. Because the line carries "
        "the control ID, each control is separately addressable: put **that one "
        "line** into maintenance while you work on it and the rest of the band "
        "keeps reporting."
    ),
    "entity": (
        "Each line is one WIZ issue: the **affected entity** and its kind, then "
        "the control that flagged it, linked into WIZ. A line marked *in progress* "
        "is already being worked on in WIZ. Because a WIZ issue carries its own "
        "ID, each line is separately addressable: put **that one line** into "
        "maintenance while you work on it and the rest of the band keeps reporting."
    ),
}
# Backwards-compatible name for callers that display the default band's note.
ENTRY_NOTE = ENTRY_NOTES[DEFAULT_AGGREGATION_LEVEL]

# Standard WIZ severities, worst first. This is the order the bands render in.
SEVERITY_ORDER = ("critical", "high", "medium", "low", "informational")


def band_rank(severity: str) -> int:
    """Where this band sorts among its siblings (little-sister ADR-0055).

    The declared severities take `SEVERITY_ORDER`'s own sequence, worst first, and
    anything else — a severity WIZ invents tomorrow, or one a `severity_map` names
    that this package does not declare — lands after **all** of them and sorts by
    name among its own kind.

    **The ranks start at 1, and that is the whole subtlety.** `0` is not a neutral
    value here: it is the rank the unranked carry, so it sorts *before* every
    positive one (little-sister ADR-0055 decision 4). Leaving an undeclared band at
    the default would put an unknown severity at the **front** of the row, which is
    the opposite of what this is for.
    """
    try:
        return SEVERITY_ORDER.index(severity) + 1
    except ValueError:
        return len(SEVERITY_ORDER) + 1

#: A severity band's title: a colored circle, **by name and never by rank**.
#:
#: The band's name sits directly beside the title on every chip, so the circle costs
#: a chip's width less than the word *Critical* and says the same thing faster —
#: and where a surface draws the title *instead of* the name, little-sister now
#: draws both (little-sister ADR-0061), so the word is never lost.
#:
#: **By name** was the decision, and the sister package is why. Ranking the ramp
#: would make a color mean *where this band sits in this row* rather than *how bad
#: this is*: over there a deployment configures which severities are watched, so the
#: same `high` is rank 1 in one aspect and rank 2 in the next, and would wear a
#: different circle in each on one dashboard. Nobody reads a red circle that way. The
#: rank still orders the row (little-sister ADR-0055); the color is a different
#: question with a different answer.
#:
#: `informational` is **green and not white**: the bottom of a severity scale is not
#: the same statement as *nothing to do here, and that is the thing being watched*,
#: which is what this band means and why it renders even while empty.
BAND_GLYPHS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "informational": "🟢",
}

#: What a severity this package does not name gets. The band list is **open** — WIZ
#: may add a severity tomorrow, and a `severity_map` may name one this package has
#: never heard of — and a band with no color must not borrow one. Worth keeping
#: precisely because it is rare enough to mean something.
UNKNOWN_BAND_GLYPH = "❓"


def band_glyph(severity: str) -> str:
    """The circle this severity wears, or `❓` where this package does not name it."""
    return BAND_GLYPHS.get(severity, UNKNOWN_BAND_GLYPH)


def _band_labels(severities: Iterable[str]) -> dict[str, dict[str, str]]:
    """What this type **declares** for each band it can name at construction —
    `name -> {title, about}`, little-sister's `subnode_defaults` (its ADR-0025).

    Two halves meet here: the authored prose of :data:`SUBNODES`, and the derived
    `title` — the band's glyph, which is a function of the severity rather than a
    line somebody wrote. A band with no prose still declares its circle, so a
    severity a `severity_map` names and this package does not describe is
    labeled rather than bare, and a deployment writing `{default}` into a title
    for it still gets that circle back.

    What this cannot cover is a severity that appears **only in a run's
    findings** — WIZ inventing one tomorrow. That band is named by the data, so
    its glyph rides its `CheckResult`, which is the channel little-sister leaves
    open for exactly that child.
    """
    return {severity: {"title": band_glyph(severity),
                       **({"about": about} if (about := SUBNODES.get(
                           severity, {}).get("about", "")) else {})}
            for severity in sorted({*severities, *SUBNODES})}

# Default severity to status mapping when the config does not override it. `low` is
# WARN rather than OK: a low finding is still work somebody has to schedule, and a
# band graded OK is dimmed on the dashboard, which is indistinguishable from "no
# findings". `medium` is ERROR beside `high`: the split that earns a color is "needs
# fixing" against "worth knowing", and medium sits on the fixing side.
DEFAULT_SEVERITY_MAP = {
    "critical": StatusCode.ERROR,
    "high": StatusCode.ERROR,
    "medium": StatusCode.ERROR,
    "low": StatusCode.WARN,
    "informational": StatusCode.OK,
}

#: The issue types this check reads: an issue a Control raised and one a configuration
#: rule raised — the two the superseded ``issues`` query answered. A threat detection
#: rule's, ``THREAT_DETECTION``, is not read (ADR-0004 decision 2).
ISSUE_TYPES = ("TOXIC_COMBINATION", "CLOUD_CONFIGURATION")

#: The most issues one query may ask for. WIZ's *Get Risk Issues* page takes ``first``
#: from 1 to 1000, and what a query outside that gets back is WIZ's to choose on every
#: run — so a configuration outside it refuses to load instead (ADR-0004 decision 5).
MAX_FIRST = 1000

# WIZ's documented query (*Get Risk Issues*, ``IssuesTable``) under WIZ's own
# ``issues:`` alias, so the answer is ``data.issues.nodes`` as it always was. Trimmed
# to what a line reads: the id, the severity and the status; the Controls and the
# configuration rules among the rules that raised the issue, a configuration rule by
# its parent control; and the affected entity (ADR-0004 decision 1).
_ISSUES_QUERY = """
query IssuesTable($filterBy: IssueFilters, $first: Int, $orderBy: IssueOrder) {
  issues: issuesV2(filterBy: $filterBy, first: $first, orderBy: $orderBy) {
    nodes {
      id
      severity
      status
      sourceRules {
        __typename
        ... on Control { id name }
        ... on CloudConfigurationRule { control { id name } }
      }
      entitySnapshot { name type }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class WizError(RemoteError):
    """A WIZ API request failed (``status`` is the HTTP code, when known).

    A :class:`~little_sister.transport.RemoteError` subclass, which is what that class
    is for: the vocabulary is the library's while the messages and every
    ``except WizError`` here stay ours. ``fault`` is inherited and **required** — a
    default would be the one decision this package must not take by accident
    (little-sister ADR-0058), and it is what decides both whether a failure is worth
    asking again and whether the node grades (ADR-0002).
    """


def _fault_and_wait(response: Response) -> tuple[Fault, float | None]:
    """WIZ's answer, read as one of the three faults, plus any wait it asked for.

    Almost all of this is :func:`~little_sister.fetch.fault_for`: a **5xx** means WIZ
    failed to answer, and anything else *is* an answer. Two departures, and both are
    about knowing whose API this is:

    * **A ``429`` is transient here.** The library keeps it *answered*, because a 429
      in general may be crawler protection with no stated end; this endpoint is an
      authenticated API with a documented rate limit, and being over it is a *not now*.
    * **A ``401``/``403`` is not.** Unlike the sister package there is no ambiguity to
      resolve: this check holds one OAuth2 credential for a whole tenant, so a refusal
      means the client ID or secret is wrong or unauthorized, and no amount of asking
      again will change it. That is why this package needs **no vendor dialect reader**
      — the standard ``Retry-After`` is the whole of what is read, and a header set we
      have not verified is not something to invent.
    """
    asked = retry_after(response.headers)
    if response.status == 429:
        return Fault.TRANSIENT, asked
    return fault_for(response.status), asked


def _issue_link(issue_id: str, severity: str) -> str:
    """The WIZ app deep-link for one issue (ported from the original)."""
    if not issue_id:
        return ""
    sev = severity.upper()
    return ("https://app.wiz.io/issues#~(filters~(status~(equals~(~'OPEN~'IN_PROGRESS))"
            f"~severity~(equals~(~'{sev})))~issue~'{issue_id})")


def _parse_aggregation_level(value: object) -> str:
    """Normalize one configured aggregation level, rejecting typos at load."""
    if not isinstance(value, str):
        raise CheckError("wiz 'aggregation_level' must be 'id' or 'entity'")
    level = value.strip().lower()
    if level not in AGGREGATION_LEVELS:
        raise CheckError("wiz 'aggregation_level' must be 'id' or 'entity'")
    return level


def _first(value: object) -> int:
    """``first`` as WIZ takes it — an integer from 1 to :data:`MAX_FIRST` — or a
    refusal at load that says so (ADR-0004 decision 5). The shape of
    little-sister-github's ``_positive_int``, with WIZ's ceiling: a ``bool`` is not a
    count, and a string of digits is read as the number it spells."""
    refusal = (f"wiz 'first' must be an integer from 1 to {MAX_FIRST}, the most "
               f"issues one WIZ query may ask for")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CheckError(refusal)
    try:
        parsed = int(value)
    except ValueError as error:
        raise CheckError(refusal) from error
    if not 1 <= parsed <= MAX_FIRST:
        raise CheckError(refusal)
    return parsed


def _text_bytes(text: str) -> int:
    """What one string weighs inside a record, in the bytes the seam counts — the
    JSON the record is weighed as, which escapes to ASCII."""
    return len(json.dumps(text).encode("utf-8"))


def _kept(value: object) -> str | None:
    """Free text as a reading keeps it and as the line will say it — clipped once,
    in the measuring half (little-sister ADR-0086 decision 7) — and ``None`` where
    WIZ sent nothing, so that every reading has one shape (its decision 6)."""
    if not value:
        return None
    return clip(str(value), chars=_TEXT_CHARS, budget=_TEXT_BYTES)


def _short(value: object) -> str | None:
    """A short field WIZ sends — a severity, a status, an entity's kind — held to
    :data:`_SHORT_BYTES`, and ``None`` where WIZ sent nothing."""
    if not value:
        return None
    return clip(str(value), chars=_SHORT_BYTES, budget=_SHORT_BYTES)


def _ident(value: object) -> str | None:
    """An identifier WIZ minted, kept whole — or, past :data:`_SHORT_BYTES`, as
    ``sha256:`` and 32 hex digits of it, because a clipped identifier could meet
    another one and a digest cannot. ``None`` where WIZ sent none; an empty one
    stays empty, since the lines read the two alike."""
    if value is None:
        return None
    text = str(value)
    if _text_bytes(text) <= _SHORT_BYTES:
        return text
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def band_of(severity: object) -> str:
    """The band a severity lands in: its name in lower case, and ``unknown`` where
    WIZ sent none. One function for the counts the estate keeps and for the bands
    the grading builds, so the two cannot disagree about a name."""
    return str(severity or "unknown").lower()


def _control_of(issue: Mapping[str, Any]) -> Mapping[str, Any]:
    """The control an issue's rules name — its ``id`` and ``name`` as WIZ sent them —
    and an empty mapping where they name none (ADR-0004 decision 3).

    A ``Control`` names itself. A configuration rule names its parent ``control``,
    which is the control the superseded query answered such an issue with. Any other
    rule names none. Where the rules name more than one control, the one with the
    smallest id, compared as text — never the first WIZ lists, because a key taken
    from a position in an array moves when WIZ reorders it, and a maintenance pin
    moves with it (little-sister ADR-0050). A control without an id is only named
    where no control has one, so its name still reaches the line while the issue is
    keyed by itself (ADR-0001 decision 4).
    """
    rules = issue.get("sourceRules")
    named: list[Mapping[str, Any]] = []
    for rule in rules if isinstance(rules, list) else ():
        if not isinstance(rule, Mapping):
            continue
        kind = rule.get("__typename")
        control = (rule if kind == "Control"
                   else rule.get("control") if kind == "CloudConfigurationRule"
                   else None)
        if isinstance(control, Mapping):
            named.append(control)
    identified = [control for control in named if control.get("id")]
    if identified:
        return min(identified, key=lambda control: str(control["id"]))
    return named[0] if named else {}


def _issue_reading(issue: Mapping[str, Any]) -> Measurement:
    """One issue as the grading will read it: exactly what its line says, and
    nothing else (ADR-0003 decision 1). It names no subject — an issue has no
    history (decision 3) — so it is the grading's input and nothing more.

    The control is the one the issue's rules name (:func:`_control_of`) and the
    entity is WIZ's ``entitySnapshot`` (ADR-0004 decisions 3 and 4); the fields keep
    the names they had while the query answered ``control`` and ``entity`` (its
    decision 1)."""
    control = _control_of(issue)
    entity = issue.get("entitySnapshot")
    if not isinstance(entity, Mapping):
        entity = {}
    return Measurement(record={
        "kind": "issue",
        "id": _ident(issue.get("id")),
        "severity": _short(issue.get("severity")),
        "status": _short(issue.get("status")),
        "control_id": _ident(control.get("id")),
        "control_name": _kept(control.get("name")),
        "entity_name": _kept(entity.get("name")),
        "entity_type": _short(entity.get("type")),
    })


def _band_counts(readings: Sequence[Measurement]) -> dict[str, int]:
    """How many issues each band holds, **before** the ignore list: the tenant's
    exposure as WIZ reports it, not the deployment's grading of it (ADR-0003
    decision 2). Every declared severity is a key, at zero when it is empty; a
    severity WIZ invents becomes one in the run it appears, after the declared ones
    and by name."""
    counts: dict[str, int] = {}
    for reading in readings:
        band = band_of(reading.record["severity"])
        counts[band] = counts.get(band, 0) + 1
    return {**{severity: counts.get(severity, 0) for severity in SEVERITY_ORDER},
            **{severity: counts[severity] for severity in sorted(counts)
               if severity not in SEVERITY_ORDER}}


def _estate_state(record: Mapping[str, Any]) -> str:
    """The state the estate is in — what its series keeps one record per spell of
    (little-sister ADR-0087 decision 3; ADR-0003 decision 4).

    Spelled from what constitutes the exposure and nothing else: each band's count,
    the declared five first, and ``page=full`` where WIZ held more than the page —
    ``critical=3;high=12;medium=40;low=7;informational=2``. A failed read is a state
    of its own, ``failed=<fault>``. Never the failure's sentence, whose words change
    from one message to the next while the state does not.

    A state is bounded like a subject and compared by equality alone, so where the
    spelling would not travel — too long, a control character, or a ``;`` or ``=``
    inside a severity WIZ invented, which would let two exposures spell alike — it is
    ``sha256:`` and 32 hex digits of the same fields in an unambiguous form. Refusing
    is not available here, as it is for the subject: this is decided at run time,
    from WIZ's answer, and a refusal would turn one strange answer into an error on
    every poll.
    """
    failure = record["failure"]
    bands: Mapping[str, int | None] = record["bands"]
    names: list[str] = []
    if failure is not None:
        spelled = f"failed={failure['fault']}"
    else:
        names = list(bands)
        spelled = ";".join(f"{name}={bands[name]}" for name in names)
        if record["page_full"]:
            spelled += ";page=full"
    if (len(spelled) <= MAX_SUBJECT_LENGTH
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in spelled)
            and not any(";" in name or "=" in name for name in names)):
        return spelled
    fields = json.dumps({"bands": list(bands.items()),
                         "page_full": record["page_full"],
                         "fault": None if failure is None else failure["fault"]},
                        separators=(",", ":"))
    return "sha256:" + hashlib.sha256(fields.encode("utf-8")).hexdigest()[:32]


def _estate_subject(api_url: str, client_id_ref: str) -> str:
    """The object this check watches — the **estate** — as its configuration draws
    it: ``<api host>;credential=<client_id reference>`` (ADR-0003 decision 3).

    The endpoint alone is not the estate: two checks can read one endpoint with two
    credentials, and each sees what its own credential sees. The credential's value
    may not travel, and its reference may, because a reference is a name and the
    value is resolved once (little-sister ADR-0023). It is kept whole, scheme and
    all, since two references may differ in nothing else.
    """
    try:
        host = urllib.parse.urlsplit(api_url).hostname or api_url
    except ValueError:
        host = api_url
    return f"{host};credential={client_id_ref}"


def _entity_text(record: Mapping[str, Any]) -> str:
    """Render one affected entity without adding another WIZ link."""
    name = str(record["entity_name"] or "")
    kind = str(record["entity_type"] or "").replace("_", " ").lower()
    issue_id = str(record["id"] or "")

    if name:
        text = f"**{plain(name)}**"
        if kind:
            text += f" ({plain(kind)})"
    else:
        text = f"WIZ issue {plain(issue_id)}" if issue_id else "WIZ issue"
    if str(record["status"] or "").upper() == "IN_PROGRESS":
        text += " · *in progress*"
    return text


def _issue_entry(record: Mapping[str, Any], severity: str) -> Entry:
    """Render one entity-level issue as its line.

    The text leads with the affected entity, because that is the thing an engineer
    has to change. The control that flagged it follows and carries the deep link. The
    earlier wording led with the control, which read as a policy name and left the
    actual subject, often a bare resource ID, trailing after a dash. The entity kind
    comes from the payload and makes a resource ID legible.

    The line is made from one reading, so it carries it: the issue's record is the
    line's ``data`` (ADR-0003 decision 6).
    """
    control_name = str(record["control_name"] or record["control_id"] or "issue")
    name = str(record["entity_name"] or "")
    kind = str(record["entity_type"] or "").replace("_", " ").lower()
    issue_id = str(record["id"] or "")

    flagged = f"[{plain(control_name)}]({_issue_link(issue_id, severity)})" \
        if issue_id else plain(control_name)
    if name:
        affected = f"**{plain(name)}**"
        if kind:
            affected += f" ({plain(kind)})"
        text = f"{affected} — {flagged}"
    else:
        text = flagged
    if str(record["status"] or "").upper() == "IN_PROGRESS":
        text += " · *in progress*"
    # Without an ID there is nothing stable to key on, so fall back to
    # little-sister's content hash rather than to a position (little-sister ADR-0036).
    return Entry(slug("wiz", issue_id) if issue_id else derived_slug(text), text,
                 data=dict(record))


def _control_entry(control_id: str, records: list[Mapping[str, Any]],
                   severity: str) -> Entry:
    """Render one control-level aggregate with one representative WIZ link.

    A line made from **one** issue carries that issue's reading; a line made from
    several carries none, because no one record is what it read (ADR-0003
    decision 6)."""
    control_name = str(records[0]["control_name"] or control_id)
    issue_id = ""
    for record in records:
        issue_id = str(record["id"] or "")
        if issue_id:
            break

    control_text = f"**{plain(control_name)}**"
    if issue_id:
        control_text = f"[{control_text}]({_issue_link(issue_id, severity)})"
    affected = [_entity_text(record) for record in records]
    text = f"{control_text} — {', '.join(affected)}"
    return Entry(slug("wiz", "control", control_id), text,
                 data=dict(records[0]) if len(records) == 1 else None)


def _id_entries(records: list[Mapping[str, Any]], severity: str) -> list[Entry]:
    """Group one severity band's issues by WIZ ``control.id``.

    A missing control ID gets its own issue-level bucket. Missing IDs must not share
    an empty-string bucket because that would merge unrelated findings and move a
    maintenance pin onto the wrong work.
    """
    buckets: list[tuple[str | None, list[Mapping[str, Any]]]] = []
    positions: dict[str, int] = {}
    for record in records:
        control_id = str(record["control_id"] or "")
        if not control_id:
            buckets.append((None, [record]))
            continue
        position = positions.get(control_id)
        if position is None:
            positions[control_id] = len(buckets)
            buckets.append((control_id, [record]))
        else:
            buckets[position][1].append(record)

    entries: list[Entry] = []
    for bucket_control_id, grouped in buckets:
        if bucket_control_id is None:
            entries.append(_issue_entry(grouped[0], severity))
        else:
            entries.append(_control_entry(bucket_control_id, grouped, severity))
    return entries


def _failed(failure: Mapping[str, Any]) -> CheckResult:
    """What a failed read means, from the fault it recorded (ADR-0002 decision 5).

    **A read failure is not a finding about the tenant.** *We could not ask* warns —
    a transient failure, and the run's own budget running out; an answer WIZ gave,
    and an answer that cannot be read, still grade ERROR — a rejected credential and
    a changed schema are both real, and both are somebody's to fix. No band is
    written, so each keeps its previous reading and goes stale on freshness, which
    says *this is the last thing we actually knew* rather than inventing five bands
    from an answer that never arrived.
    """
    error = plain(str(failure["error"]))
    if failure["fault"] == "deadline":
        return CheckResult(StatusCode.WARN, [error])
    if failure["fault"] == Fault.TRANSIENT.name.lower():
        return CheckResult(StatusCode.WARN,
                           [f"could not ask WIZ this run: {error}"])
    return CheckResult(StatusCode.ERROR, [f"WIZ query failed: {error}"])


@dataclass(frozen=True)
class IssuePage:
    """What one query answered: the issues on its page, and whether WIZ holds more.

    ``more`` is the answer's ``pageInfo.hasNextPage``, and ``None`` where the answer
    did not say. The query asks for one page of ``first`` issues, worst first, so
    with ``more`` set the page is a floor under the tenant's exposure rather than the
    whole of it (ADR-0001 decision 8)."""
    nodes: list[dict[str, Any]]
    more: bool | None


class WizClient:
    """A minimal WIZ client: OAuth2 client credentials, then one GraphQL query.

    **Two budgets, and they are not the same one** (ADR-0002). ``timeout`` bounds one
    request; ``deadline``, when given, bounds **the whole run** and is checked before
    every request — which matters here even though a run makes at most four of them,
    because before it existed ``timeout:`` was handed to the socket layer per request
    and so bounded nothing at all.

    What is ours here is WIZ: the OAuth2 exchange, the GraphQL envelope and reading
    that envelope's own error channel. The request, the budgets and the retry are the
    library's (little-sister ADR-0058), which is what removed the hand-rolled loop
    below — and TLS verification is still not a knob (ADR-0001 §5), now because
    :func:`~little_sister.fetch.fetch` offers no way to make it one.
    """

    def __init__(self, client_id: str, client_secret: str, *, api_url: str,
                 token_url: str = TOKEN_URL, timeout: float = 60.0,
                 deadline: Deadline | None = None,
                 retries: int = TRANSIENT_RETRIES,
                 backoff: float = RETRY_BACKOFF_SECONDS,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_url = api_url
        self._token_url = token_url
        self._timeout = timeout
        self._deadline = deadline
        self._retries = retries
        self._backoff = backoff
        self._sleep = sleep
        self._token: str | None = None

    def _post(self, url: str, body: bytes, headers: dict[str, str], *,
              what: str) -> Response:
        """One POST, and **every status comes back as an answer**.

        That inversion is the point of :func:`~little_sister.fetch.fetch`: only a
        request that never reached a status raises. It replaces a hand-rolled
        ``urlopen`` whose ``except Exception`` was the widest clause in this package,
        and whose ``(status, text)`` return left each caller to remember to look at the
        status. No ``User-Agent`` is set: the library's own
        ``little-sister/<version>`` is a name a WIZ support thread can do something
        with, unlike the unversioned string this used to send.

        Redirects are **not** followed, deliberately. ``urlopen`` followed them, and on
        a redirect urllib turns a POST into a GET — so a misconfigured endpoint could
        silently drop the request body and fail as something else. A 3xx from an API
        endpoint means the URL is wrong, which for a region-specific ``api_url``
        (ADR-0001 §6) is exactly what a reader needs to be told.
        """
        try:
            return fetch(url, timeout=self._timeout, follow_redirects=False,
                         method="POST", data=body, headers=headers,
                         deadline=self._deadline)
        except RemoteError as error:
            # `fetch` attaches urllib's own exception as `__cause__`, so the sentence a
            # reader gets is ours rather than a list of proxy paths and certificate
            # directories. `DeadlineExceeded` is **not** a `RemoteError` and is not
            # caught: it is about the run, not about this request.
            raise WizError(f"{what} could not be sent to {url}: "
                           f"{error.__cause__ or error}",
                           status=error.status, fault=error.fault) from error

    def _refusal(self, response: Response, what: str) -> WizError:
        """A status WIZ refused with, read as one of the three faults."""
        fault, wait = _fault_and_wait(response)
        return WizError(f"{what}: HTTP {response.status}: {response.text()[:200]}",
                        status=response.status, fault=fault, retry_after=wait)

    def _ask(self, operation: Callable[[], _T]) -> _T:
        """Run one request under the library's retry policy and nothing of our own.

        `ask` retries only a `TRANSIENT` fault, only while attempts remain, and only
        while the deadline can still afford the wait — and it spends a wait WIZ named
        in place of the backoff. A wait longer than the run has left is refused and the
        error re-raised: **pausing past the check's budget is not a request layer's
        decision** (little-sister ADR-0058). When to ask again is `frequency:`.
        """
        return ask(operation, deadline=self._deadline, retries=self._retries,
                   backoff=self._backoff, sleep=self._sleep)

    def _token_request(self) -> str:
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "audience": "wiz-api",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }).encode("utf-8")
        response = self._post(
            self._token_url, body,
            {"Content-Type": "application/x-www-form-urlencoded"},
            what="WIZ auth")
        if response.status != 200:
            raise self._refusal(response, "WIZ auth failed")
        try:
            token = str(json.loads(response.body)["access_token"])
        except (ValueError, KeyError, TypeError) as error:
            # **It arrived and it cannot be used.** This used to escape as a bare
            # `KeyError` or `JSONDecodeError` — past the run's `except WizError`, so
            # the engine turned the whole check into a traceback rather than a reading
            # (little-sister ADR-0040). Not transient: the same request returns the
            # same shape.
            raise WizError(
                f"WIZ auth answered {response.status} without a usable "
                f"'access_token': {error}",
                status=response.status, fault=Fault.MALFORMED) from error
        return token

    def _get_token(self) -> str:
        """The bearer token, fetched once per client and then reused.

        A transient failure here is retried like any other. It was not before: the
        token exchange sat outside the retry loop, so a single 503 from the auth
        endpoint ended a run that the very next second would have completed.
        """
        if self._token:
            return self._token
        self._token = self._ask(self._token_request)
        return self._token

    def _query(self, payload: bytes, headers: dict[str, str]) -> IssuePage:
        """One GraphQL POST, and the three ways it can fail to be a page of issues."""
        response = self._post(self._api_url, payload, headers, what="WIZ query")
        if response.status != 200:
            raise self._refusal(response, "WIZ query failed")
        try:
            body = json.loads(response.body)
        except ValueError as error:
            raise WizError(f"WIZ answered the query with something that is not JSON: "
                           f"{error}", status=response.status,
                           fault=Fault.MALFORMED) from error
        if not isinstance(body, dict):
            raise WizError("WIZ answered the query with a JSON value that is not an "
                           "object", status=response.status, fault=Fault.MALFORMED)
        if body.get("errors"):
            # GraphQL's own error channel, inside a 200. WIZ answered, and the answer
            # is no — a rejected query, a field this credential may not read. Read as
            # `ANSWERED` and never retried, and deliberately not by looking at the
            # message text: a backend timeout can arrive this way too, and telling the
            # two apart by prose is the rule this family does not break.
            raise WizError(f"WIZ GraphQL errors: {body['errors']}",
                           status=response.status, fault=Fault.ANSWERED)
        issues = (body.get("data") or {}).get("issues")
        if not isinstance(issues, dict) or not isinstance(issues.get("nodes"), list):
            # **Green-when-blind, and it shipped.** This used to read
            # `((data or {}).get("issues") or {}).get("nodes")` and hand back
            # `list(… or [])`, so an answer with no payload in it — a schema change, a
            # partial response — became *zero issues*, which is every band green and a
            # tenant reported as clean. An empty `nodes` list is still zero issues; a
            # missing one is no answer.
            raise WizError("WIZ answered the query without a 'data.issues.nodes' "
                           "list — nothing to read", status=response.status,
                           fault=Fault.MALFORMED)
        page_info = issues.get("pageInfo")
        more = page_info.get("hasNextPage") if isinstance(page_info, dict) else None
        return IssuePage(nodes=list(issues["nodes"]),
                         more=more if isinstance(more, bool) else None)

    def issues(self, first: int) -> IssuePage:
        """Open and in-progress issues of the types this check reads
        (:data:`ISSUE_TYPES`), worst severity first (a single page of ``first``,
        matching the original — see ADR-0001 §8's cap note), and whether WIZ holds
        more than the page."""
        token = self._get_token()
        payload = json.dumps({
            "query": _ISSUES_QUERY,
            "variables": {
                "first": first,
                "filterBy": {"status": ["OPEN", "IN_PROGRESS"],
                             "type": list(ISSUE_TYPES)},
                "orderBy": {"field": "SEVERITY", "direction": "DESC"},
            },
        }).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {token}"}
        return self._ask(lambda: self._query(payload, headers))


@register("wiz")
class WizCheck(Check):
    """Report open WIZ issues as severity-band leaves under the check's node."""

    def __init__(self, *, api_url: str, token_url: str = TOKEN_URL,
                 first: int = 500, severity_map: dict[str, StatusCode] | None = None,
                 ignore_control_ids: tuple[str, ...] = (),
                 aggregation_level: str = DEFAULT_AGGREGATION_LEVEL,
                 client_id_ref: str, client_secret_ref: str,
                 **kwargs: Any) -> None:
        # Both declarations are computed **before** the base constructor runs,
        # because that is where little-sister resolves them against the
        # deployment's `subnodes:` block (its ADR-0025) — and
        # both are made of arguments rather than of attributes for the same
        # reason. `self.severity_map` and `self.aggregation_level` are set from
        # the same two values below, so nothing is read twice.
        severities = {**DEFAULT_SEVERITY_MAP, **(severity_map or {})}
        level = _parse_aggregation_level(aggregation_level)
        # Refused here as well as at load, so that a check built in code asks WIZ
        # for no page it would refuse either (ADR-0004 decision 5).
        first = _first(first)
        # The estate, declared here as little-sister ADR-0086 decision 4 asks, so a
        # run that raises is still recorded against the estate it failed to reach.
        # **Refused, never cut**, when it will not fit a subject, because a cut name
        # could be another estate's (ADR-0003 decision 3). The sentence names the
        # parts and not the reference, which may not be one yet: a credential pasted
        # where its reference belongs is the resolver's to refuse, without quoting it.
        subject = _estate_subject(api_url, client_id_ref)
        if len(subject) > MAX_SUBJECT_LENGTH:
            raise CheckError(
                f"wiz: the estate this check reads is named by the api_url's host "
                f"and the client_id reference, {len(subject)} characters together "
                f"— past the {MAX_SUBJECT_LENGTH} a subject may have. It is refused "
                f"rather than cut, because a cut name could be another estate's; a "
                f"shorter client_id reference fits")
        super().__init__(subject=subject,
                         subnode_defaults=_band_labels(severities),
                         label_tokens={"entry_note": ENTRY_NOTES[level]},
                         **kwargs)
        # Resolved **once here** from the references the config's `secrets:`
        # block names (little-sister ADR-0023) — never re-read during a run. An
        # unresolvable reference leaves these empty and records the failure, and
        # the engine pins this check to a visible ERROR without calling measure().
        self.client_id = self.resolve_secret(client_id_ref)
        self.client_secret = self.resolve_secret(client_secret_ref)
        self.api_url = api_url
        self.token_url = token_url
        self.first = first
        self.severity_map = severities
        self.ignore_control_ids = ignore_control_ids
        self.aggregation_level = level

    @classmethod
    def _extra_from_config(cls, config: dict[str, Any],
                           base_dir: Path) -> dict[str, Any]:
        api_url = config.get("api_url")
        if not api_url:
            raise CheckError("wiz check requires an 'api_url' (the region-specific "
                             "WIZ GraphQL endpoint)")
        raw_map = config.get("severity_map") or {}
        if not isinstance(raw_map, dict):
            raise CheckError("wiz 'severity_map' must be a mapping")
        severity_map = {str(k).lower(): coerce_code(v) for k, v in raw_map.items()}
        ignore = config.get("ignore_control_ids") or []
        if not isinstance(ignore, list):
            raise CheckError("wiz 'ignore_control_ids' must be a list")
        return {
            "api_url": str(api_url),
            "token_url": str(config.get("token_url", TOKEN_URL)),
            "first": _first(config.get("first", 500)),
            "severity_map": severity_map,
            "ignore_control_ids": tuple(str(i) for i in ignore),
            "aggregation_level": _parse_aggregation_level(
                config.get("aggregation_level", DEFAULT_AGGREGATION_LEVEL)),
            # `secrets: {client_id: …, client_secret: …}` — required, so two
            # checks of this type can each carry their own credentials
            # (little-sister ADR-0023).
            **{f"{name}_ref": reference for name, reference
               in parse_secret_refs(config, "client_id", "client_secret").items()},
        }

    def config_summary(self) -> str:
        return config_markdown({
            "api": self.api_url,
            "aggregation": f"{self.aggregation_level} level",
            "grading": self._grading_summary(),
            "ignored controls": str(len(self.ignore_control_ids) or ""),
        })

    def _grading_summary(self) -> str:
        """The whole map **in force**, for the check's own `config` card.

        Here rather than in any `about` text because it is a setting, and because a
        deployment that overrode `severity_map` has to be able to read *its* answer
        somewhere; the band pages carry one row each, and this is the one place all
        of them are visible together."""
        codes = [self.severity_map[name] for name in self._band_order()
                 if name in self.severity_map]
        if not codes:
            return "nothing graded"
        if len(set(codes)) == 1:
            # One answer for every band is worth saying once. Five identical arrows
            # are a wall a reader skips, and skipping is how the setting stays
            # invisible — which is the whole complaint this line answers.
            return f"**{codes[0].name}** for every band"
        return ", ".join(
            f"`{name}` → **{self.severity_map[name].name}**"
            for name in self._band_order() if name in self.severity_map)

    def _band_order(self) -> list[str]:
        """The declared severities first, then any a config added, by name.

        The run's own loop orders by the severities *the data* brought as well, which
        this cannot see; what it shares with that loop is the part that is a decision
        rather than an observation — `SEVERITY_ORDER` first."""
        return [*SEVERITY_ORDER,
                *sorted(s for s in self.severity_map if s not in SEVERITY_ORDER)]

    def _band_config(self, severity: str) -> str:
        """What this band ran with — the two facts a reader needs on its page.

        `graded` is the code this severity maps to, and it says when the fallback is
        what applied: a severity WIZ invents tomorrow reaches a band with no
        `severity_map` entry, and a band quietly taking the fallback is the case a
        reader cannot otherwise see. `when empty` is there because an empty green
        band reads as *nothing found* when it means *nothing found, and that is the
        thing being watched*."""
        mapped = self.severity_map.get(severity)
        return config_markdown({
            "graded": (f"`{mapped.name}` when this band has findings"
                       if mapped is not None else
                       "`WARN` when this band has findings — no `severity_map` "
                       "entry, so the fallback applies"),
            "when empty": "`OK`, so a watched band's silence is visible",
        })

    def _new_deadline(self) -> Deadline:
        """This run's budget. Overridden in tests, so a deadline can be spent without
        a test spending one."""
        return Deadline(self.timeout_seconds)

    def _make_client(self, client_id: str, client_secret: str,
                     deadline: Deadline | None = None) -> WizClient:
        """Build the API client. Overridden in tests to avoid live calls.

        ``timeout_seconds`` is handed over **twice, and it means two things**. As
        ``timeout`` it bounds one request, exactly as before, so no single request is
        tightened by this change. As the ``deadline`` it bounds the whole run, which
        nothing did before: a run makes an auth request and then up to three query
        attempts, and each of them used to be allowed the full budget. There is no
        separate `request_timeout:` key here, unlike the sister package — at four
        requests a run the run's own budget is a sane per-request bound too, and the
        clamp does the rest (ADR-0002).
        """
        return WizClient(client_id, client_secret, api_url=self.api_url,
                         token_url=self.token_url, timeout=self.timeout_seconds,
                         deadline=deadline)

    def _estate(self, *, bands: Mapping[str, int | None] | None = None,
                page_full: bool | None = None,
                failure: Mapping[str, str] | None = None) -> Measurement:
        """The run's own reading: the tenant's exposure, and whether the read worked
        (ADR-0003 decision 1).

        **One shape on every run** (little-sister ADR-0085 decision 3): every
        declared band is a key, its count **null** when the read failed — never zero,
        which would bring the tenant reported clean by a check told nothing back as
        a series (ADR-0002 decision 6) — ``page_full`` null with it, and ``failure``
        null on a run that read. It names the estate this check declared, so it is
        the reading the engine places when it is the only one, and it names the state
        the exposure is in (ADR-0003 decision 4).
        """
        record: dict[str, Any] = {
            "kind": "estate",
            "bands": (dict(bands) if bands is not None
                      else dict.fromkeys(SEVERITY_ORDER)),
            "page_full": page_full,
            "failure": None if failure is None else dict(failure),
        }
        return Measurement(record=record, subject=self.subject,
                           state=_estate_state(record))

    def measure(self) -> list[Measurement]:
        """Read WIZ: the estate first, then one reading per issue on the page
        (ADR-0003 decision 1).

        The token and the query are the whole of what a run asks, so a failure of
        either is the run's: the estate is then the only reading, carrying the fault
        and the sentence, and the grading says what that means. Nothing here decides
        a code or writes a line, and nothing is left out — the ignore list, the
        grading map and the aggregation level are the grading's (ADR-0003
        decision 2), because a reading that left something out would be a reading of
        the configuration rather than of WIZ.
        """
        # `timeout:` is the whole run's budget and this is where it starts ticking.
        deadline = self._new_deadline()
        try:
            client = self._make_client(self.client_id, self.client_secret, deadline)
            page = client.issues(self.first)
        except DeadlineExceeded as cut:
            # The run's own budget, not WIZ's fault and not the tenant's. Nothing was
            # read, so unlike the sister package there is nothing partial to keep:
            # this check's whole reading comes from one query.
            return [self._estate(failure={"fault": "deadline",
                                          "error": _kept(str(cut)) or ""})]
        except WizError as error:
            if error.fault is Fault.TRANSIENT:
                logger.warning("%s: could not ask WIZ (%s)", self.path, error)
            return [self._estate(failure={"fault": error.fault.name.lower(),
                                          "error": _kept(str(error)) or ""})]
        readings = [_issue_reading(issue) for issue in page.nodes]
        return [self._estate(bands=_band_counts(readings), page_full=page.more),
                *readings]

    def grade(self, measurements: Sequence[Measurement],
              now: datetime) -> CheckResult:
        """The bands and their lines, from the readings alone (little-sister
        ADR-0086 decision 6): the estate says whether the read worked, and the
        issues are what the bands list. ``now`` is not read — nothing this check
        says depends on when it is said.
        """
        estate: Mapping[str, Any] | None = None
        issues: list[Mapping[str, Any]] = []
        for measurement in measurements:
            kind = measurement.record.get("kind")
            if kind == "estate":
                estate = measurement.record
            elif kind == "issue":
                issues.append(measurement.record)
        if estate is None:
            # Only a failure record the engine wrote has no estate reading, and the
            # engine grades that run itself; this is the guard for a caller handing
            # over something no measurement of ours produced.
            return CheckResult(StatusCode.ERROR,
                               ["no estate reading to grade — nothing was read"])
        if estate["failure"] is not None:
            return _failed(estate["failure"])

        groups: dict[str, list[Mapping[str, Any]]] = {}
        for record in issues:
            if str(record["control_id"]) in self.ignore_control_ids:
                continue
            groups.setdefault(band_of(record["severity"]), []).append(record)

        # Named `band_order` and not `order`: `order` is now a `CheckResult` field
        # meaning a node's rank, and one name for the build sequence and the
        # declared rank in one function is how the two drift apart.
        band_order = [*SEVERITY_ORDER,
                      *(s for s in groups if s not in SEVERITY_ORDER)]
        children: list[CheckResult] = []
        for severity in band_order:
            if severity not in self.severity_map and severity not in groups:
                continue                       # not monitored and nothing found
            items = groups.get(severity, [])
            code = (self.severity_map.get(severity, StatusCode.WARN) if items
                    else StatusCode.OK)
            # The band's lines are **members** — each one separately pinnable while
            # the rest of the band keeps reporting (little-sister ADR-0036). They
            # carry no code of their own, the band does, so `entries=True` says what
            # `(slug, text)` pairs used to say by their shape. The configured
            # aggregation level decides whether a member is a control or one
            # concrete issue for an entity.
            lines = (_id_entries(items, severity)
                     if self.aggregation_level == "id"
                     else [_issue_entry(record, severity) for record in items])
            children.append(CheckResult(
                code, lines, entries=True, name=severity,
                description=f"{severity.capitalize()} WIZ issues",
                # A band this check could name at construction is **declared**,
                # and the library writes its label; what is left here is the band
                # a run *discovered* — a severity WIZ invented — which nothing
                # could have declared and which would otherwise wear no circle.
                title=("" if severity in self.subnode_labels
                       else band_glyph(severity)),
                order=band_rank(severity),
                config=self._band_config(severity)))
        # A container, not a claim (ADR-0003 decision 5). The node declares nothing
        # and rolls up worst-of its bands, as ADR-0001 decision 1 always said — and
        # so the estate a series keeps carries the tenant's worst band as the code
        # that stood, where an `OK` here would have kept `OK` on every run.
        return CheckResult(StatusCode.UNDEFINED, children=tuple(children))
