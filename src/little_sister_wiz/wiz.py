"""The ``wiz`` check type: open cloud-security issues, one leaf per severity band.

Authenticates to WIZ with OAuth2 client credentials, queries open and in-progress
issues over GraphQL, and reports one leaf per severity band under the check's node,
from ``critical`` through ``informational``. Each band is graded by a configurable
``severity_map`` and lists its findings. Findings are grouped by WIZ control ID by
default; ``aggregation_level: entity`` gives one line per issue and affected entity.
Ported from an older in-house alerting dashboard; the mapping and what was
deliberately changed are in ``docs/migrating-security-checks.md``.

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

Everything imported from little-sister below is part of its **check-authoring
surface** (architecture.md §11), which is what the ``require_api(1)`` in this
package's ``__init__`` pins.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from little_sister.checks import (
    Check,
    CheckError,
    CheckResult,
    coerce_code,
    config_markdown,
    parse_secret_refs,
    parse_subnodes,
    plain,
    register,
    resolve_text,
)
from little_sister.reasons import derived_slug, slug
from little_sister.status import StatusCode

TOKEN_URL = "https://auth.app.wiz.io/oauth/token"
AGGREGATION_LEVELS = ("id", "entity")
DEFAULT_AGGREGATION_LEVEL = "id"

# Built-in display text for the severity-band leaves this check emits (little-sister
# ADR-0025). This text is type-inherent, so it is written once here rather than copied
# into every deployment config; a second tenant's check is then config only. A check
# config's `subnodes:` block replaces any of these, or extends one by writing
# `{default}` into its own text; `nodes.yaml` still wins over both, per node path.
SUBNODES: dict[str, dict[str, str]] = {
    "critical": {"title": "Critical",
                 "about": "Critical-severity WIZ issues — fix immediately.\n\n"
                          "{entry_note}"},
    "high": {"title": "High",
             "about": "High-severity WIZ issues — graded ERROR.\n\n{entry_note}"},
    "medium": {"title": "Medium",
               "about": "Medium-severity WIZ issues — graded ERROR.\n\n"
                        "{entry_note}"},
    "low": {"title": "Low",
            "about": "Low-severity WIZ issues — graded WARN, so they are visible "
                     "without shouting.\n\n{entry_note}"},
    "informational": {"title": "Informational",
                      "about": "Informational WIZ findings — graded OK.\n\n"
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

# Trimmed to the fields we use: ID, severity, control, and entity.
_ISSUES_QUERY = """
query Issues($first: Int, $filterBy: IssueFilters, $orderBy: IssueOrder) {
  issues(first: $first, filterBy: $filterBy, orderBy: $orderBy) {
    nodes { id severity status control { id name } entity { name type } }
    pageInfo { hasNextPage endCursor }
  }
}
"""


class WizError(Exception):
    """A WIZ API request failed (``status`` is the HTTP code, when known)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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


def _entity_text(issue: dict[str, Any]) -> str:
    """Render one affected entity without adding another WIZ link."""
    entity = issue.get("entity") or {}
    name = str(entity.get("name") or "")
    kind = str(entity.get("type") or "").replace("_", " ").lower()
    issue_id = str(issue.get("id") or "")

    if name:
        text = f"**{plain(name)}**"
        if kind:
            text += f" ({plain(kind)})"
    else:
        text = f"WIZ issue {plain(issue_id)}" if issue_id else "WIZ issue"
    if str(issue.get("status") or "").upper() == "IN_PROGRESS":
        text += " · *in progress*"
    return text


def _issue_entry(issue: dict[str, Any], severity: str) -> tuple[str, str]:
    """Render one entity-level issue as ``(slug, text)``.

    The text leads with the affected entity, because that is the thing an engineer
    has to change. The control that flagged it follows and carries the deep link. The
    earlier wording led with the control, which read as a policy name and left the
    actual subject, often a bare resource ID, trailing after a dash. The entity kind
    comes from the payload and makes a resource ID legible.
    """
    control = issue.get("control") or {}
    control_name = str(control.get("name") or control.get("id") or "issue")
    entity = issue.get("entity") or {}
    name = str(entity.get("name") or "")
    kind = str(entity.get("type") or "").replace("_", " ").lower()
    issue_id = str(issue.get("id") or "")

    flagged = f"[{plain(control_name)}]({_issue_link(issue_id, severity)})" \
        if issue_id else plain(control_name)
    if name:
        subject = f"**{plain(name)}**"
        if kind:
            subject += f" ({plain(kind)})"
        text = f"{subject} — {flagged}"
    else:
        text = flagged
    if str(issue.get("status") or "").upper() == "IN_PROGRESS":
        text += " · *in progress*"
    # Without an ID there is nothing stable to key on, so fall back to
    # little-sister's content hash rather than to a position (little-sister ADR-0036).
    return (slug("wiz", issue_id) if issue_id else derived_slug(text)), text


def _control_entry(control_id: str, issues: list[dict[str, Any]],
                   severity: str) -> tuple[str, str]:
    """Render one control-level aggregate with one representative WIZ link."""
    control = issues[0].get("control") or {}
    control_name = str(control.get("name") or control_id)
    issue_id = ""
    for issue in issues:
        issue_id = str(issue.get("id") or "")
        if issue_id:
            break

    control_text = f"**{plain(control_name)}**"
    if issue_id:
        control_text = f"[{control_text}]({_issue_link(issue_id, severity)})"
    affected = [_entity_text(issue) for issue in issues]
    text = f"{control_text} — {', '.join(affected)}"
    return slug("wiz", "control", control_id), text


def _id_entries(items: list[dict[str, Any]],
                severity: str) -> list[tuple[str, str]]:
    """Group one severity band's issues by WIZ ``control.id``.

    A missing control ID gets its own issue-level bucket. Missing IDs must not share
    an empty-string bucket because that would merge unrelated findings and move a
    maintenance pin onto the wrong work.
    """
    buckets: list[tuple[str | None, list[dict[str, Any]]]] = []
    positions: dict[str, int] = {}
    for issue in items:
        control = issue.get("control") or {}
        control_id = str(control.get("id") or "")
        if not control_id:
            buckets.append((None, [issue]))
            continue
        position = positions.get(control_id)
        if position is None:
            positions[control_id] = len(buckets)
            buckets.append((control_id, [issue]))
        else:
            buckets[position][1].append(issue)

    entries: list[tuple[str, str]] = []
    for bucket_control_id, grouped in buckets:
        if bucket_control_id is None:
            entries.append(_issue_entry(grouped[0], severity))
        else:
            entries.append(_control_entry(bucket_control_id, grouped, severity))
    return entries


class WizClient:
    """A minimal WIZ client over stdlib ``urllib`` (OAuth2 + GraphQL, TLS on)."""

    def __init__(self, client_id: str, client_secret: str, *, api_url: str,
                 token_url: str = TOKEN_URL, timeout: float = 60.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_url = api_url
        self._token_url = token_url
        self._timeout = timeout
        self._token: str | None = None

    def _post(self, url: str, body: bytes,
              headers: dict[str, str]) -> tuple[int, str]:
        request = urllib.request.Request(url, data=body, method="POST",
                                         headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace")
        except Exception as error:   # any transport failure
            raise WizError(f"request failed for {url}: {error}") from error

    def _get_token(self) -> str:
        if self._token:
            return self._token
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "audience": "wiz-api",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }).encode("utf-8")
        status, text = self._post(
            self._token_url, body,
            {"Content-Type": "application/x-www-form-urlencoded",
             "User-Agent": "little-sister-wiz"})
        if status != 200:
            raise WizError(f"WIZ auth failed: HTTP {status}: {text[:200]}",
                           status=status)
        token = str(json.loads(text)["access_token"])
        self._token = token
        return token

    def issues(self, first: int) -> list[dict[str, Any]]:
        """Open and in-progress issues, worst severity first (a single page of
        ``first``, matching the original — see the doc's cap note)."""
        token = self._get_token()
        payload = json.dumps({
            "query": _ISSUES_QUERY,
            "variables": {
                "first": first,
                "filterBy": {"status": ["OPEN", "IN_PROGRESS"]},
                "orderBy": {"field": "SEVERITY", "direction": "DESC"},
            },
        }).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {token}",
                   "User-Agent": "little-sister-wiz"}
        for _ in range(3):
            status, text = self._post(self._api_url, payload, headers)
            if status in (502, 503, 504):
                continue                       # transient — retry
            if status != 200:
                raise WizError(f"WIZ query failed: HTTP {status}: {text[:200]}",
                               status=status)
            body = json.loads(text)
            if body.get("errors"):
                raise WizError(f"WIZ GraphQL errors: {body['errors']}")
            issues = ((body.get("data") or {}).get("issues") or {}).get("nodes")
            return list(issues or [])
        raise WizError("WIZ query failed after retries (5xx)")


@register("wiz")
class WizCheck(Check):
    """Report open WIZ issues as severity-band leaves under the check's node."""

    def __init__(self, *, api_url: str, token_url: str = TOKEN_URL,
                 first: int = 500, severity_map: dict[str, StatusCode] | None = None,
                 ignore_control_ids: tuple[str, ...] = (),
                 aggregation_level: str = DEFAULT_AGGREGATION_LEVEL,
                 subnodes: dict[str, dict[str, str]] | None = None,
                 client_id_ref: str, client_secret_ref: str,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Resolved **once here** from the references the config's `secrets:`
        # block names (little-sister ADR-0023) — never re-read during a run. An
        # unresolvable reference leaves these empty and records the failure, and
        # the engine pins this check to a visible ERROR without calling run().
        self.client_id = self.resolve_secret(client_id_ref)
        self.client_secret = self.resolve_secret(client_secret_ref)
        self.api_url = api_url
        self.token_url = token_url
        self.first = first
        self.severity_map = {**DEFAULT_SEVERITY_MAP, **(severity_map or {})}
        self.ignore_control_ids = ignore_control_ids
        self.aggregation_level = _parse_aggregation_level(aggregation_level)
        # Per-band display text (title/about) from this check's own config
        # (`subnodes:`), carried onto each severity leaf (little-sister
        # ADR-0025).
        self.subnodes = subnodes or {}

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
            "first": int(config.get("first", 500)),
            "severity_map": severity_map,
            "ignore_control_ids": tuple(str(i) for i in ignore),
            "aggregation_level": _parse_aggregation_level(
                config.get("aggregation_level", DEFAULT_AGGREGATION_LEVEL)),
            "subnodes": parse_subnodes(config),
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
            "ignored controls": str(len(self.ignore_control_ids) or ""),
        })

    def _meta(self, name: str) -> tuple[str, str]:
        """The (title, about) for severity band `name`: this check type's built-in
        `SUBNODES` text, which the config's `subnodes:` block replaces — or extends,
        where it writes `{default}` into its own text (little-sister ADR-0025).
        `{entry_note}` expands in either case, so a deployment that rewrites one
        band's `about` can keep the shared explanation of the line format."""
        configured = self.subnodes.get(name, {})
        default = SUBNODES.get(name, {})
        tokens = {"entry_note": ENTRY_NOTES[self.aggregation_level]}
        return (resolve_text(configured.get("title", ""),
                             default.get("title", ""), tokens),
                resolve_text(configured.get("about", ""),
                             default.get("about", ""), tokens))

    def _make_client(self, client_id: str, client_secret: str) -> WizClient:
        """Build the API client. Overridden in tests to avoid live calls."""
        return WizClient(client_id, client_secret, api_url=self.api_url,
                         token_url=self.token_url, timeout=self.timeout_seconds)

    def run(self) -> CheckResult:
        try:
            client = self._make_client(self.client_id, self.client_secret)
            issues = client.issues(self.first)
        except WizError as error:
            return CheckResult(StatusCode.ERROR,
                               [f"WIZ query failed: {plain(str(error))}"])

        groups: dict[str, list[dict[str, Any]]] = {}
        for issue in issues:
            control = issue.get("control") or {}
            if str(control.get("id")) in self.ignore_control_ids:
                continue
            severity = str(issue.get("severity") or "unknown").lower()
            groups.setdefault(severity, []).append(issue)

        order = [*SEVERITY_ORDER,
                 *(s for s in groups if s not in SEVERITY_ORDER)]
        children: list[CheckResult] = []
        for severity in order:
            if severity not in self.severity_map and severity not in groups:
                continue                       # not monitored and nothing found
            items = groups.get(severity, [])
            code = (self.severity_map.get(severity, StatusCode.WARN) if items
                    else StatusCode.OK)
            # (slug, text) pairs, so the band's lines are **members** — each one
            # separately pinnable while the rest of the band keeps reporting
            # (little-sister ADR-0036). The configured aggregation level decides
            # whether that member is a control or one concrete issue for an entity.
            entries = (_id_entries(items, severity)
                       if self.aggregation_level == "id"
                       else [_issue_entry(issue, severity) for issue in items])
            title, about = self._meta(severity)
            children.append(CheckResult(
                code, entries, name=severity,
                description=f"{severity.capitalize()} WIZ issues",
                title=title, about=about))
        return CheckResult(StatusCode.OK, children=tuple(children))
