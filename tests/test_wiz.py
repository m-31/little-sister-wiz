"""Fixture-based tests for the ``wiz`` check type — no live WIZ calls."""
from __future__ import annotations

import contextlib
from email.message import Message
from unittest import mock

import pytest
from little_sister import fetch as ls_fetch
from little_sister.checks import CheckError
from little_sister.status import StatusCode
from little_sister.transport import Deadline, DeadlineExceeded, Fault

from little_sister_wiz import wiz as mod_wiz
from little_sister_wiz.wiz import (
    BAND_GLYPHS,
    ENTRY_NOTE,
    RETRY_BACKOFF_SECONDS,
    SEVERITY_ORDER,
    SUBNODES,
    WizCheck,
    WizClient,
    WizError,
    band_glyph,
    band_rank,
)


class _Clock:
    """A hand-wound monotonic clock, so a deadline can be spent without waiting."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _about(band):
    """The band's shipped `about` as the check renders it — `{entry_note}` is a
    token the type expands, not literal text (little-sister ADR-0025)."""
    return SUBNODES[band]["about"].replace("{entry_note}", ENTRY_NOTE)


class FakeWiz:
    """Stands in for WizClient.issues()."""

    def __init__(self, issues=None, error=None):
        self._issues = issues or []
        self._error = error

    def issues(self, first):
        if self._error:
            raise self._error
        return self._issues


def _issue(sev, control_id="wc-1", name="Public bucket", entity="bucket-a",
           issue_id="i1"):
    return {"id": issue_id, "severity": sev, "status": "OPEN",
            "control": {"id": control_id, "name": name},
            "entity": {"name": entity, "type": "BUCKET"}}


def _check(**over):
    cfg = {"path": "/wiz", "api_url": "https://api.example.app.wiz.io/graphql",
           "client_id_ref": "env://WIZ_CLIENT_ID",
           "client_secret_ref": "env://WIZ_CLIENT_SECRET"}
    cfg.update(over)
    return WizCheck(**cfg)


def _run(check, fake, monkeypatch):
    monkeypatch.setattr(check, "_make_client",
                        lambda cid, sec, deadline=None: fake)
    return check.run()


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    """The references resolve at construction now, so every check built here
    needs its environment (little-sister ADR-0023)."""
    monkeypatch.setenv("WIZ_CLIENT_ID", "id")
    monkeypatch.setenv("WIZ_CLIENT_SECRET", "sec")


def test_severity_bands_and_grading(monkeypatch):
    check = _check()
    fake = FakeWiz([_issue("CRITICAL", issue_id="c1"),
                    _issue("MEDIUM", issue_id="m1")])
    result = _run(check, fake, monkeypatch)
    bands = {c.name: c.code for c in result.children}
    assert bands["critical"] is StatusCode.ERROR      # has an issue
    assert bands["medium"] is StatusCode.ERROR        # has an issue
    assert bands["high"] is StatusCode.OK             # in map, no issues
    assert bands["low"] is StatusCode.OK              # in map, no issues
    assert [c.name for c in result.children][:2] == ["critical", "high"]  # order


def test_findings_remain_uncoded_inside_their_severity_band(monkeypatch):
    """little-sister ADR-0042 uses WIZ as the banded reference shape: severity
    stays on the leaf and does not migrate onto its entries."""
    result = _run(_check(), FakeWiz([_issue("CRITICAL")]), monkeypatch)
    critical = next(child for child in result.children
                    if child.name == "critical")
    assert critical.code is StatusCode.ERROR
    assert critical.reason_entries[0].code is None
    assert critical.reason_entries[0].running is False


def test_issue_listed_with_link(monkeypatch):
    check = _check()
    fake = FakeWiz([_issue("CRITICAL", name="Exposed DB", entity="db-1")])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.code is StatusCode.ERROR
    assert "Exposed DB" in critical.reason_texts[0]
    assert "app.wiz.io" in critical.reason_texts[0]


def test_ignore_control_ids(monkeypatch):
    check = _check(ignore_control_ids=("wc-2",))
    fake = FakeWiz([_issue("CRITICAL", control_id="wc-2")])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.code is StatusCode.OK
    assert critical.reason_texts == []


def test_custom_severity_map_overrides_default(monkeypatch):
    check = _check(severity_map={"medium": StatusCode.ERROR})
    fake = FakeWiz([_issue("MEDIUM")])
    result = _run(check, fake, monkeypatch)
    medium = next(c for c in result.children if c.name == "medium")
    assert medium.code is StatusCode.ERROR            # overridden from WARN


def test_unresolvable_secrets_are_recorded_at_construction(monkeypatch):
    """Unset credentials no longer fail per run: they are recorded at load and the
    engine pins the check to a visible ERROR (little-sister ADR-0023)."""
    monkeypatch.delenv("WIZ_CLIENT_ID", raising=False)
    monkeypatch.delenv("WIZ_CLIENT_SECRET", raising=False)
    check = _check()
    assert (check.client_id, check.client_secret) == ("", "")
    assert len(check.secret_errors) == 2
    assert "WIZ_CLIENT_ID" in check.secret_errors[0]


def test_each_check_names_its_own_credentials(monkeypatch):
    """Two wiz checks, one per tenant, each with its own client credentials."""
    monkeypatch.setenv("WIZ_EU_ID", "eu-id")
    monkeypatch.setenv("WIZ_EU_SECRET", "eu-sec")
    other = _check(path="/wiz/eu", client_id_ref="env://WIZ_EU_ID",
                   client_secret_ref="env://WIZ_EU_SECRET")
    assert (other.client_id, other.client_secret) == ("eu-id", "eu-sec")
    assert other.secret_errors == []


def test_pasted_secret_is_rejected_as_a_config_error():
    """A credential value where a name belongs fails the load, and the message
    never carries it onward."""
    pasted = "wiz-Zm9vYmFyYmF6cXV4L3NlY3JldA=="
    with pytest.raises(CheckError) as caught:
        _check(client_secret_ref=pasted)
    assert pasted not in str(caught.value)


def test_an_answer_wiz_gave_is_an_error(monkeypatch):
    """**Replaces** `test_query_error_is_error`, whose claim this slice overturns
    (ADR-0002): it used a 500 and asserted ERROR, and a 500 is the case that now warns.

    What still errors is an answer. A 403 means this tenant's credential is wrong or
    unauthorized — a true statement about this check's configuration, and one only a
    person can fix."""
    check = _check()
    fake = FakeWiz(error=WizError("boom", status=403, fault=Fault.ANSWERED))
    result = _run(check, fake, monkeypatch)
    assert result.code is StatusCode.ERROR
    assert "WIZ query failed" in result.reason_texts[0]


def test_a_read_failure_is_not_a_finding_about_the_tenant(monkeypatch):
    """The behavior change an operator will notice. *We could not ask WIZ* is a fact
    about WIZ, not about this tenant's cloud posture, so it warns rather than pages —
    and the sentence says which of the two happened."""
    check = _check()
    fake = FakeWiz(error=WizError("HTTP 503", status=503, fault=Fault.TRANSIENT))
    result = _run(check, fake, monkeypatch)
    assert result.code is StatusCode.WARN
    assert "could not ask WIZ this run" in result.reason_texts[0]


def test_an_unreadable_answer_still_errors(monkeypatch):
    """The third fault, and it does not get the transient reading. A schema change or
    a truncated payload is a defect in this check or in the API — waiting it out
    changes nothing, and somebody has to look."""
    check = _check()
    fake = FakeWiz(error=WizError("no nodes", status=200, fault=Fault.MALFORMED))
    result = _run(check, fake, monkeypatch)
    assert result.code is StatusCode.ERROR


def test_the_runs_budget_is_a_reading_and_not_a_traceback(monkeypatch):
    """`DeadlineExceeded` is deliberately not a `WizError`, so `run()` needs its own
    catch — without it the engine turns the whole check into an all-or-nothing check
    error (little-sister ADR-0040) instead of saying the run ran out of time."""
    check = _check()
    fake = FakeWiz(error=DeadlineExceeded(
        "the run's budget of 30s ran out after 30.0s"))
    result = _run(check, fake, monkeypatch)
    assert result.code is StatusCode.WARN
    assert "ran out" in result.reason_texts[0]
    assert result.children == ()


def test_the_run_builds_its_deadline_from_the_configured_timeout(monkeypatch):
    """`timeout:` is the run's budget and this is where it starts ticking. Before this
    it reached the socket layer as the *per-request* value — spent afresh on the auth
    request and on each query attempt, so nothing bounded the run at all."""
    seen = {}

    def _capture(cid, sec, deadline=None):
        seen["deadline"] = deadline
        return FakeWiz([])

    check = _check(timeout_seconds=42.0)
    monkeypatch.setattr(check, "_make_client", _capture)
    check.run()
    assert isinstance(seen["deadline"], Deadline)
    assert seen["deadline"].seconds == 42.0


def test_config_loads_via_loader(tmp_path):
    # tmp_path is a *configuration root*: the loader reads its `checks/` aspect
    # (little-sister ADR-0031), so the config goes one level down.
    from little_sister.checks import load_checks
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks" / "wiz.yaml").write_text(
        "type: wiz\n"
        "secrets:\n"
        "  client_id: env://WIZ_CLIENT_ID\n"
        "  client_secret: env://WIZ_CLIENT_SECRET\n"
        "path: /wiz\n"
        "api_url: https://api.example.app.wiz.io/graphql\n"
        "severity_map:\n"
        "  critical: ERROR\n"
        "  medium: WARN\n"
        "aggregation_level: entity\n"
        "ignore_control_ids: [wc-2]\n"
    )
    checks = load_checks(str(tmp_path))
    assert len(checks) == 1
    assert isinstance(checks[0], WizCheck)
    assert checks[0].ignore_control_ids == ("wc-2",)
    assert checks[0].severity_map["critical"] is StatusCode.ERROR
    assert checks[0].aggregation_level == "entity"


@pytest.mark.parametrize("value", ["control", "issue", "", 7, None])
def test_invalid_aggregation_level_is_a_config_error(value):
    with pytest.raises(CheckError, match=r"aggregation_level.*id.*entity"):
        _check(aggregation_level=value)


def test_id_aggregation_is_the_default_and_is_in_the_config_summary():
    check = _check()
    assert check.aggregation_level == "id"
    assert "**aggregation:** id level" in check.config_summary()


def test_bands_declare_the_built_in_text(monkeypatch):
    """The type ships every band's label, so a second tenant's config carries none.

    Read off the check rather than off the result: since little-sister took the
    `subnodes:` block (its ADR-0025) this package **declares**
    these and the library resolves them — `subnode_labels` is that resolution, and
    the engine writes it onto each band node. The `{entry_note}` token this package
    declares beside the text has expanded by the time it lands there.
    """
    check = _check()   # no subnodes configured
    _run(check, FakeWiz([_issue("CRITICAL")]), monkeypatch)
    assert check.subnode_labels["critical"] == {
        "title": band_glyph("critical"), "about": _about("critical")}
    assert check.subnode_labels["high"]["title"] == "🟠"


def test_a_declared_band_hands_over_no_label_of_its_own(monkeypatch):
    """The other half, where it can fail. A result carrying a band's glyph would
    be shadowed by the resolved label anyway — and would go on looking right in a
    test while a deployment's override was the thing actually painting."""
    result = _run(_check(), FakeWiz([_issue("CRITICAL")]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert (critical.title, critical.about) == ("", "")


def test_config_replaces_a_band_label():
    check = _check(subnode_labels={
        "critical": {"title": "Sev-1", "about": "Page the on-call."}})
    assert check.subnode_labels["critical"] == {
        "title": "Sev-1", "about": "Page the on-call."}
    assert check.subnode_labels["high"]["about"] == _about("high")   # untouched


def test_config_extends_a_band_label_with_the_default_token():
    check = _check(subnode_labels={
        "critical": {"about": "{default} Page the on-call."}})
    assert check.subnode_labels["critical"]["about"] == (
        _about("critical") + " Page the on-call.")


def _row(children):
    """The children in the order little-sister will draw them.

    The real sort is the library's, once, in the snapshot — `(order, name)`, ADR-0055
    decision 1. This mirrors that key rather than calling it, because the check hands
    back a `CheckResult` and the library sorts a tree node; what is asserted here is
    the row those ranks produce, not the sorting."""
    return [child.name for child in sorted(children, key=lambda c: (c.order, c.name))]


def test_every_declared_band_wears_its_own_colour(monkeypatch):
    """The row the operator sees. Worst-first by rank, and the colour says *how bad
    this is* — the same circle for the same severity, always."""
    check = _check()
    result = _run(check, FakeWiz([_issue(s) for s in
                                  ("CRITICAL", "HIGH", "MEDIUM", "LOW",
                                   "INFORMATIONAL")]), monkeypatch)
    row = sorted(result.children, key=lambda c: (c.order, c.name))
    assert [(c.name, check.subnode_labels[c.name]["title"]) for c in row] == [
        ("critical", "🔴"), ("high", "🟠"), ("medium", "🟡"),
        ("low", "🔵"), ("informational", "🟢")]


def test_a_bands_colour_does_not_move_when_its_rank_does(monkeypatch):
    """The decision, and the sister package is why. Ranking the ramp would make a
    colour mean *where this band sits in this row* rather than *how bad this is* —
    over there a deployment configures which severities are watched, so one `high` is
    rank 1 in one aspect and rank 2 in the next, and would wear a different circle in
    each on one dashboard.

    This check has no such knob, so the claim is made the only way it can be: move
    the declared order underneath and watch the ranks follow while the colours stay
    exactly where they were."""
    before = {s: band_glyph(s) for s in SEVERITY_ORDER}
    assert band_rank('critical') == 1 and band_rank('low') == 4

    monkeypatch.setattr(mod_wiz, 'SEVERITY_ORDER',
                        ('low', 'informational', 'critical', 'medium', 'high'))

    assert band_rank('low') == 1 and band_rank('critical') == 3   # ranks moved
    assert {s: band_glyph(s) for s in before} == before           # colours did not
    assert band_glyph('low') == '🔵'   # emphatically not the 🔴 its new rank would give


def test_informational_is_green_and_not_the_bottom_of_the_ramp():
    """The bottom of a severity scale and *nothing to do here* are not the same
    statement. This band renders while empty precisely so its silence is visible,
    and a white circle would read as the palest bad news rather than as good."""
    assert band_glyph("informational") == "🟢"
    assert "⚪" not in BAND_GLYPHS.values()


def test_a_severity_this_package_does_not_name_gets_a_question_mark(monkeypatch):
    """The band list is open — WIZ may add a severity tomorrow, and a `severity_map`
    may name one we have never heard of. A band with no colour must not borrow one."""
    result = _run(_check(), FakeWiz([_issue("BIZARRE")]), monkeypatch)
    band = next(c for c in result.children if c.name == "bizarre")
    assert band.title == "❓"
    assert band.title not in BAND_GLYPHS.values()


def test_a_band_named_only_by_the_severity_map_declares_its_circle():
    """A `severity_map` may name a severity this package writes no prose for. It
    still gets a declaration — the glyph — so the band is labelled rather than
    bare, and a deployment writing `{default}` into a title for it gets that
    circle back rather than nothing."""
    check = _check(severity_map={"catastrophic": StatusCode.ERROR})
    assert check.subnode_labels["catastrophic"] == {"title": "❓"}
    extended = _check(severity_map={"catastrophic": StatusCode.ERROR},
                      subnode_labels={"catastrophic": {"title": "{default}!"}})
    assert extended.subnode_labels["catastrophic"]["title"] == "❓!"


def test_a_deployment_still_overrules_a_band_title(monkeypatch):
    """Whatever this package picks is a default (little-sister ADR-0025). A tenant
    that wants the word back, or a different mark, writes one line."""
    check = _check(subnode_labels={"critical": {"title": "Sev-1"}})
    _run(check, FakeWiz([_issue("CRITICAL")]), monkeypatch)
    assert check.subnode_labels["critical"]["title"] == "Sev-1"


def test_the_glyph_does_not_fold_away_against_the_name(monkeypatch):
    """little-sister drops a title that only repeats its name, which is what used to
    happen to `Critical`. A circle repeats nothing, so it survives that rule — and
    where a surface draws a title *instead of* the name it now draws both
    (little-sister ADR-0061), so the word is never lost."""
    from little_sister.titles import label_parts, shown_title

    check = _check()
    result = _run(check, FakeWiz([_issue("CRITICAL")]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    title = check.subnode_labels[critical.name]["title"]
    assert shown_title(critical.name, title) == "🔴"
    assert label_parts(critical.name, title) == ("critical", "🔴")


def test_the_band_row_reads_worst_first_rather_than_alphabetically(monkeypatch):
    """The complaint this item existed for: the dashboard rendered
    `critical high informational low medium`, with `informational` — the band that
    means *nothing to do* — sitting third, between `high` and `low`."""
    result = _run(_check(), FakeWiz([_issue(s) for s in
                                     ("CRITICAL", "HIGH", "MEDIUM", "LOW",
                                      "INFORMATIONAL")]), monkeypatch)
    assert _row(result.children) == ["critical", "high", "medium", "low",
                                     "informational"]
    assert sorted(c.name for c in result.children) != _row(result.children)


def test_a_severity_nobody_declared_sorts_after_every_declared_band(monkeypatch):
    """And `0` is why this needs saying. `0` is the rank the *unranked* carry, so it
    sorts before every positive rank (little-sister ADR-0055 decision 4) — leaving an
    unknown severity at the default would put it at the **front** of the row."""
    result = _run(_check(), FakeWiz([_issue("CRITICAL"), _issue("BIZARRE")]),
                  monkeypatch)
    assert _row(result.children)[-1] == "bizarre"
    bizarre = next(c for c in result.children if c.name == "bizarre")
    assert bizarre.order > max(c.order for c in result.children
                               if c.name in SEVERITY_ORDER)
    assert bizarre.order != 0


def test_undeclared_severities_sort_by_name_among_themselves(monkeypatch):
    """They share one rank, so the name half of the key decides — rather than the
    order `groups` happened to encounter them in, which is the data's accident."""
    result = _run(_check(), FakeWiz([_issue("ZETA", issue_id="i1"),
                                     _issue("ALPHA", issue_id="i2"),
                                     _issue("CRITICAL", issue_id="i3")]), monkeypatch)
    # the four empty declared bands still render between them — a watched band's
    # silence is visible — so the claim is about the tail
    assert _row(result.children) == ["critical", "high", "medium", "low",
                                     "informational", "alpha", "zeta"]


def test_every_declared_band_carries_the_rank_its_constant_states():
    """One source. The glyph item will read these same numbers, and deriving a colour
    ramp separately from the sequence is how a row ends up reading amber above red."""
    assert [band_rank(s) for s in SEVERITY_ORDER] == [1, 2, 3, 4, 5]
    assert band_rank("something-wiz-invents") == len(SEVERITY_ORDER) + 1


def test_no_shipped_band_text_claims_a_code():
    """The regression, and the reason this item existed. Every band's `about` used
    to name its grade in prose — `graded ERROR`, `graded WARN`, `graded OK` — while
    `SUBNODES` is a module constant that cannot see `severity_map`. A deployment that
    graded `medium` as WARN therefore read **`graded ERROR`** on the medium band's own
    page: not a text that withheld the setting, a text that stated the wrong one.

    What a severity *means* stays in the prose; what it is *graded* is expanded from
    the map in force, into the band's `config` card."""
    assert SUBNODES                                     # not vacuously true
    for band, text in SUBNODES.items():
        rendered = text["about"]
        for code in ("ERROR", "WARN", "OK"):
            assert code not in rendered, f"{band}'s text names {code}"
        assert "graded" not in rendered.lower(), f"{band}'s text claims a grading"


def test_a_bands_config_states_the_grade_in_force_not_the_shipped_default(monkeypatch):
    """The whole point of moving it: an overridden band shows the operator's answer
    rather than this package's, on the band's own page."""
    check = _check(severity_map={"medium": StatusCode.WARN})
    result = _run(check, FakeWiz([_issue("MEDIUM"), _issue("HIGH")]), monkeypatch)
    bands = {child.name: child.config for child in result.children}
    assert "`WARN` when this band has findings" in bands["medium"]
    assert "`ERROR` when this band has findings" in bands["high"]


def test_every_band_says_what_an_empty_one_reads_as(monkeypatch):
    """An empty green band reads as *nothing found* when it means *nothing found, and
    that is the thing being watched* — which is why an empty band renders at all."""
    result = _run(_check(), FakeWiz([_issue("CRITICAL")]), monkeypatch)
    assert result.children                              # not vacuously true
    for child in result.children:
        assert "`OK`, so a watched band's silence is visible" in child.config


def test_a_band_taking_the_fallback_says_so(monkeypatch):
    """A severity WIZ invents tomorrow reaches a band with no `severity_map` entry and
    is graded WARN by the fallback. A band quietly taking the fallback is exactly the
    case a reader cannot see any other way."""
    result = _run(_check(), FakeWiz([_issue("BIZARRE")]), monkeypatch)
    band = next(c for c in result.children if c.name == "bizarre")
    assert "no `severity_map` entry, so the fallback applies" in band.config
    assert band.stored_code is StatusCode.WARN


def test_the_checks_own_card_carries_the_whole_map_in_force():
    """The one place every band's answer is visible together — and where a reader who
    overrode the map goes to confirm it took."""
    expected = ("**grading:** `critical` → **ERROR**, `high` → **ERROR**, "
                "`medium` → **ERROR**, `low` → **WARN**, `informational` → **OK**")
    assert expected in _check().config_summary()
    overridden = _check(severity_map={"low": StatusCode.OK}).config_summary()
    assert "`low` → **OK**" in overridden
    assert "`low` → **WARN**" not in overridden


def test_one_answer_for_every_band_is_said_once():
    """Five identical arrows are a wall a reader skips, and skipping is how the
    setting stays invisible — which is the complaint this line answers."""
    every = dict.fromkeys(SEVERITY_ORDER, StatusCode.ERROR)
    assert ("**grading:** **ERROR** for every band"
            in _check(severity_map=every).config_summary())


def test_a_severity_a_config_added_is_graded_after_the_declared_ones():
    """`SEVERITY_ORDER` is the decision; anything a config adds sorts by name after it,
    so the card does not reorder itself between two runs of the same deployment."""
    summary = _check(severity_map={"zeta": StatusCode.WARN,
                                   "alpha": StatusCode.ERROR}).config_summary()
    grading = summary.split("**grading:** ")[1].splitlines()[0]
    assert grading.startswith("`critical` → **ERROR**")
    assert grading.endswith("`alpha` → **ERROR**, `zeta` → **WARN**")


def test_entity_level_lines_are_members_keyed_by_the_wiz_issue_id(monkeypatch):
    """A WIZ issue id is minted with the issue and retired with it — exactly the
    identity ADR-0036 wants, so each band's lines are individually pinnable."""
    check = _check(aggregation_level="entity")
    fake = FakeWiz([_issue("CRITICAL", issue_id="abc-123", entity="db-1"),
                    _issue("CRITICAL", issue_id="def-456", entity="db-2")])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.members
    assert "Each line is one WIZ issue" in check.subnode_labels["critical"]["about"]
    assert [e.slug for e in critical.reason_entries] == ["wiz-abc-123",
                                                         "wiz-def-456"]


def test_default_id_level_groups_entities_by_control_id(monkeypatch):
    check = _check()
    fake = FakeWiz([
        _issue("CRITICAL", control_id="wc-1", issue_id="abc-123", entity="db-1"),
        _issue("CRITICAL", control_id="wc-1", issue_id="def-456", entity="db-2"),
        _issue("CRITICAL", control_id="wc-2", issue_id="ghi-789", entity="queue-1"),
    ])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")

    assert ("Each line is one WIZ **control**"
            in check.subnode_labels["critical"]["about"])
    assert [entry.slug for entry in critical.reason_entries] == [
        "wiz-control-wc-1", "wiz-control-wc-2"]
    first = critical.reason_texts[0]
    assert first.startswith("[**Public bucket**](https://app.wiz.io/issues")
    assert first.count("https://app.wiz.io/issues") == 1
    assert "**db-1** (bucket)" in first
    assert "**db-2** (bucket)" in first
    assert "[**db-1**" not in first
    assert "[**db-2**" not in first
    assert "~issue~'abc-123" in first
    assert "~issue~'def-456" not in first


def test_control_slug_survives_reworded_aggregate_content(monkeypatch):
    check = _check()
    first = _run(check, FakeWiz([
        _issue("HIGH", control_id="wc-1", issue_id="x1", name="Old control name",
               entity="old-entity")]), monkeypatch)
    second = _run(check, FakeWiz([
        _issue("HIGH", control_id="wc-1", issue_id="x2", name="New control name",
               entity="new-entity")]), monkeypatch)

    def slug_of(result):
        band = next(c for c in result.children if c.name == "high")
        return band.reason_entries[0].slug

    assert slug_of(first) == slug_of(second) == "wiz-control-wc-1"


def test_id_level_does_not_merge_issues_without_a_control_id(monkeypatch):
    check = _check()
    fake = FakeWiz([
        _issue("CRITICAL", control_id="", issue_id="abc-123", entity="db-1"),
        _issue("CRITICAL", control_id="", issue_id="def-456", entity="db-2"),
    ])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert [entry.slug for entry in critical.reason_entries] == [
        "wiz-abc-123", "wiz-def-456"]


def test_a_slug_survives_a_reworded_line(monkeypatch):
    """The pin must outlive an improvement to the text — which is why the slug is
    built from the id and not from the wording."""
    check = _check(aggregation_level="entity")
    first = _run(check, FakeWiz([_issue("HIGH", issue_id="x1", name="Old name")]),
                 monkeypatch)
    second = _run(check, FakeWiz([_issue("HIGH", issue_id="x1", name="New name")]),
                  monkeypatch)

    def slug_of(result):
        band = next(c for c in result.children if c.name == "high")
        return band.reason_entries[0].slug

    assert slug_of(first) == slug_of(second)


def test_an_issue_without_an_id_falls_back_to_a_content_hash(monkeypatch):
    """Nothing stable to key on — so the text becomes the identity, never the
    position in the list."""
    check = _check(aggregation_level="entity")
    result = _run(check, FakeWiz([_issue("CRITICAL", issue_id="")]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.reason_entries[0].derived


def test_the_line_leads_with_the_entity_and_names_its_kind(monkeypatch):
    check = _check(aggregation_level="entity")
    fake = FakeWiz([_issue("CRITICAL", name="Publicly exposed", entity="db-1")])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    text = critical.reason_texts[0]
    assert text.startswith("**db-1** (bucket) —")   # entity first, then its kind
    assert "[Publicly exposed](https://app.wiz.io/issues" in text


def test_an_in_progress_issue_says_so(monkeypatch):
    """Already-being-worked-on is in the payload we fetch; hiding it made two
    engineers pick up the same finding."""
    issue = _issue("CRITICAL")
    issue["status"] = "IN_PROGRESS"
    result = _run(_check(), FakeWiz([issue]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.reason_texts[0].endswith("*in progress*")


def test_an_issue_without_an_entity_still_reads(monkeypatch):
    issue = _issue("CRITICAL", name="Org policy drift")
    issue["entity"] = None
    result = _run(_check(aggregation_level="entity"), FakeWiz([issue]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.reason_texts[0].startswith("[Org policy drift](")


def test_low_warns_and_medium_errors_by_default(monkeypatch):
    """The type's default grading: a low finding is still work, and an OK band is
    dimmed on the dashboard — indistinguishable from 'nothing found'. A deployment
    that disagrees says so in its own `severity_map`."""
    result = _run(_check(), FakeWiz([_issue("LOW"), _issue("MEDIUM", issue_id="m")]),
                  monkeypatch)
    bands = {c.name: c.code for c in result.children}
    assert bands["low"] is StatusCode.WARN
    assert bands["medium"] is StatusCode.ERROR
    assert bands["informational"] is StatusCode.OK


# --- WizClient, through the real request path ---------------------------------
#
# Everything above this line stubs `_make_client` out, so until now **the client had
# no tests at all**: the OAuth2 exchange, the GraphQL envelope, the status handling
# and the retry loop were asserted by nobody. That loop shipped asking three times
# with no wait between them and treating a bare 500 as final, and the suite stayed
# green.
#
# So the stub sits one level **below** `fetch`, patching the opener the library
# builds. What runs in every test below is the shipped inversion (an HTTP status is
# an answer, not an exception), the shipped classification, and the shipped retry.

class _Answer:
    """One HTTP response, in the shape `fetch`'s opener hands back."""

    def __init__(self, status=200, body=b"{}", headers=None):
        self.status = status
        self.url = "https://api.example.app.wiz.io/graphql"
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value
        self._body = body

    def read1(self, size=-1):
        """What `fetch._read` calls, and it calls nothing else on a body stream.
        `read1` rather than `read` because a real `read(n)` blocks until it has all *n*
        bytes: reading a body with it cannot be bounded by a clock, which is the defect
        little-sister ADR-0058's 2026-08-16 amendment records. A double offering `read`
        alone would still be modelling the version that could not be bounded."""
        size = len(self._body) if size < 0 else size
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Opener:
    """Stands in for the module-level opener inside `little_sister.fetch`.

    `answer` is an `_Answer`, an exception to raise, or a callable of
    `(request, timeout)` — a callable, when a test needs a *fresh* answer per attempt,
    because an `HTTPError` carries a one-shot body.
    """

    def __init__(self, answer):
        self._answer = answer
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        answer = self._answer
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            answer = answer(request, timeout)
        if isinstance(answer, BaseException):
            raise answer
        return answer


@contextlib.contextmanager
def _through(answer):
    """A real `WizClient` whose requests reach ``answer`` through the real `fetch`.

    Yields `(build, opener)`. `WizClient` does not follow redirects, so it is the
    *reporting* opener that has to be replaced — patching the following one would leave
    every test below talking to the real internet.
    """
    opener = _Opener(answer)
    with mock.patch.object(ls_fetch, "_REPORTING", opener):
        def build(**over):
            kwargs = {"api_url": "https://api.example.app.wiz.io/graphql",
                      "token_url": "https://auth.example.wiz.io/oauth/token",
                      "sleep": lambda _s: None}
            kwargs.update(over)
            return WizClient("cid", "secret", **kwargs)
        yield build, opener


_TOKEN_OK = b'{"access_token": "tok"}'
_ONE_ISSUE = (b'{"data": {"issues": {"nodes": '
              b'[{"id": "i1", "severity": "CRITICAL"}]}}}')


def _sequence(*answers):
    """Hand back one canned answer per request, so a token exchange and a query — or
    a retry — can differ."""
    remaining = list(answers)

    def opener(_request, _timeout):
        return remaining.pop(0)
    return opener


def _graphql_error(code, body=b'{"message": "nope"}', headers=None):
    import io
    import urllib.error
    carried = Message()
    for name, value in (headers or {}).items():
        carried[name] = value
    return urllib.error.HTTPError(
        "https://api.example.app.wiz.io/graphql", code, "err", carried,
        io.BytesIO(body))


def test_the_client_authenticates_then_queries():
    """The happy path, which nothing exercised: two POSTs, the token from the first
    used as the bearer on the second."""
    with _through(_sequence(_Answer(body=_TOKEN_OK),
                            _Answer(body=_ONE_ISSUE))) as (build, opener):
        issues = build().issues(10)
    assert [issue["id"] for issue in issues] == ["i1"]
    auth, query = opener.requests
    assert auth.get_method() == "POST"
    assert b"client_credentials" in auth.data
    assert query.get_header("Authorization") == "Bearer tok"
    assert query.get_header("Content-type") == "application/json"


def test_a_plain_500_is_retried_now():
    """The defect the plan named. The old loop retried 502/503/504 and let a bare
    **500** — the commonest transient status there is — through as final, on the first
    ask."""
    attempts = []

    def flaky(_request, _timeout):
        attempts.append(1)
        if len(attempts) == 1:
            return _Answer(body=_TOKEN_OK)
        if len(attempts) == 2:
            return _graphql_error(500)
        return _Answer(body=_ONE_ISSUE)

    with _through(flaky) as (build, _opener):
        assert len(build().issues(10)) == 1
    assert len(attempts) == 3          # token, the 500, and the retry that worked


def test_the_backoff_is_actually_slept_between_attempts():
    """The other half of that defect, and the worse half: the old loop asked three
    times **in the same millisecond**, which is the one thing certain not to help."""
    slept = []
    answers = _sequence(_Answer(body=_TOKEN_OK), _graphql_error(503),
                        _graphql_error(503), _Answer(body=_ONE_ISSUE))
    with _through(answers) as (build, _opener):
        build(sleep=slept.append).issues(10)
    assert slept == [RETRY_BACKOFF_SECONDS, RETRY_BACKOFF_SECONDS]


def test_three_attempts_and_then_the_real_status_is_reported():
    """The attempt count is preserved from the loop this replaced. What is not is the
    sentence at the end of it: that loop raised `WIZ query failed after retries (5xx)`,
    which threw away the status and the body it had been given three times."""
    attempts = []

    def always(_request, _timeout):
        attempts.append(1)
        if len(attempts) == 1:
            return _Answer(body=_TOKEN_OK)
        return _graphql_error(502, b'{"message": "upstream gone"}')

    with _through(always) as (build, _opener):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert len(attempts) == 4                  # the token, then three query attempts
    assert caught.value.status == 502
    assert caught.value.fault is Fault.TRANSIENT
    assert "upstream gone" in str(caught.value)


def test_a_rejected_credential_is_an_answer_and_is_not_retried():
    """One credential for a whole tenant, so a 403 is not the ambiguous status it is in
    the sister package: nothing about asking again can make a wrong secret right."""
    attempts = []

    def denied(_request, _timeout):
        attempts.append(1)
        return _graphql_error(403, b'{"message": "forbidden"}')

    with _through(denied) as (build, _opener):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert len(attempts) == 1                  # asked once, believed it
    assert caught.value.fault is Fault.ANSWERED
    assert "WIZ auth failed" in str(caught.value)


def test_a_429_is_transient_here_and_the_wait_it_names_is_honored():
    """The one place this package departs from the library's reading. `fault_for` keeps
    429 *answered*, because a 429 in general may be crawler protection with no stated
    end; this is an authenticated API with a documented limit, so it is a *not now* —
    and `Retry-After` replaces our backoff when WIZ sends one."""
    slept = []
    answers = _sequence(_Answer(body=_TOKEN_OK),
                        _graphql_error(429, b"{}", {"Retry-After": "4"}),
                        _Answer(body=_ONE_ISSUE))
    with _through(answers) as (build, _opener):
        assert len(build(sleep=slept.append).issues(10)) == 1
    assert slept == [4.0]                      # WIZ's four seconds, not our one


def test_only_the_standard_retry_after_is_read():
    """No vendor dialect is invented here, deliberately: a header set nobody has
    verified is worse than not reading one. A 429 with WIZ-shaped headers we have not
    confirmed falls back to our own backoff."""
    slept = []
    answers = _sequence(_Answer(body=_TOKEN_OK),
                        _graphql_error(429, b"{}",
                                       {"X-RateLimit-Reset": "1700000060"}),
                        _Answer(body=_ONE_ISSUE))
    with _through(answers) as (build, _opener):
        build(sleep=slept.append).issues(10)
    assert slept == [RETRY_BACKOFF_SECONDS]


def test_a_transient_auth_failure_is_retried_too():
    """It was not before: the token exchange sat outside the retry loop, so one 503
    from the auth endpoint ended a run the next second would have completed."""
    attempts = []

    def flaky(_request, _timeout):
        attempts.append(1)
        if len(attempts) == 1:
            return _graphql_error(503)
        if len(attempts) == 2:
            return _Answer(body=_TOKEN_OK)
        return _Answer(body=_ONE_ISSUE)

    with _through(flaky) as (build, _opener):
        assert len(build().issues(10)) == 1


def test_an_auth_answer_without_a_token_is_malformed_not_a_traceback():
    """It used to be a bare `KeyError` — raised past `run()`'s `except WizError`, so
    the engine reported the whole check as an all-or-nothing check error instead of a
    reading (little-sister ADR-0040)."""
    with _through(_Answer(body=b'{"token_type": "Bearer"}')) as (build, _opener):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert caught.value.fault is Fault.MALFORMED
    assert "access_token" in str(caught.value)


def test_auth_that_answers_with_something_other_than_json_is_malformed():
    """A proxy login page where a token was expected. Also a `JSONDecodeError`
    escaping `run()` before this."""
    with _through(_Answer(body=b"<html>a proxy login page</html>")) as (build, _o):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert caught.value.fault is Fault.MALFORMED


def test_graphql_errors_inside_a_200_are_an_answer():
    """WIZ's own error channel. It answered, and the answer is no — a rejected query,
    a field this credential may not read — so it is not retried. Classified from the
    channel's presence and never from its message text: a backend timeout can arrive
    this way too, and telling those apart by prose is the rule this family keeps."""
    attempts = []

    def erroring(_request, _timeout):
        attempts.append(1)
        if len(attempts) == 1:
            return _Answer(body=_TOKEN_OK)
        return _Answer(body=b'{"errors": [{"message": "context deadline exceeded"}]}')

    with _through(erroring) as (build, _opener):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert caught.value.fault is Fault.ANSWERED
    assert len(attempts) == 2                  # the token, then one query
    assert "GraphQL errors" in str(caught.value)


def test_an_answer_with_no_payload_is_not_zero_issues():
    """**Green-when-blind, and it shipped.** The old read was
    `((data or {}).get("issues") or {}).get("nodes")` handed to `list(… or [])`, so an
    answer with no payload in it became *zero issues* — every band green, and a
    security tenant reported as clean by a check that had been told nothing."""
    for body in (b'{"data": {}}', b'{"data": null}', b'{}',
                 b'{"data": {"issues": {}}}',
                 b'{"data": {"issues": {"nodes": null}}}'):
        with _through(_sequence(_Answer(body=_TOKEN_OK),
                                _Answer(body=body))) as (build, _opener):
            with pytest.raises(WizError) as caught:
                build().issues(10)
        assert caught.value.fault is Fault.MALFORMED, body
        assert "data.issues.nodes" in str(caught.value)


def test_a_query_answer_that_is_not_a_json_object_is_malformed():
    """The two shapes above `data` itself: not JSON at all, and JSON that is not an
    object. A gateway's HTML error page reaches a 200 more often than it should, and
    `json.loads` on a bare `[]` or `null` would make the reads below raise
    `AttributeError` out of `run()` instead of reporting anything."""
    for body in (b"<html>gateway timeout</html>", b"[]", b"null", b'"nope"'):
        with _through(_sequence(_Answer(body=_TOKEN_OK),
                                _Answer(body=body))) as (build, _opener):
            with pytest.raises(WizError) as caught:
                build().issues(10)
        assert caught.value.fault is Fault.MALFORMED, body


def test_an_empty_nodes_list_really_is_zero_issues():
    """The other side of that line, and why it is a line rather than a rewrite: a
    tenant with nothing open is a real and common answer, and it must stay one."""
    with _through(_sequence(_Answer(body=_TOKEN_OK),
                            _Answer(body=b'{"data": {"issues": {"nodes": []}}}'))) \
            as (build, _opener):
        assert build().issues(10) == []


def test_one_request_may_never_outlive_what_is_left_of_the_run():
    """The clamp, asserted on the socket timeout the request was actually issued with.
    Without it an auth request and three query attempts could each be allowed the full
    `timeout:`, which is how a 30-second budget became two minutes."""
    clock = _Clock()
    deadline = Deadline(30.0, clock=clock)
    answers = _sequence(_Answer(body=_TOKEN_OK), _Answer(body=_ONE_ISSUE))
    with _through(answers) as (build, opener):
        client = build(timeout=120.0, deadline=deadline)
        clock.advance(25)
        client.issues(10)
    assert opener.timeouts[0] == 5.0           # clamped to what the run has left
    # and with no deadline at all it is simply the request's own budget
    with _through(_sequence(_Answer(body=_TOKEN_OK),
                            _Answer(body=_ONE_ISSUE))) as (build, plain_opener):
        build(timeout=120.0).issues(10)
    assert plain_opener.timeouts[0] == 120.0


def test_a_budget_already_spent_is_not_a_request_at_all():
    """`ask` checks the deadline on entry, so the request that finds the budget gone is
    never issued — rather than issued with a socket timeout of zero, which most socket
    APIs read as *non-blocking* and report as something else entirely."""
    clock = _Clock()
    spent = Deadline(5.0, clock=clock)
    clock.advance(6)
    with _through(_Answer(body=_TOKEN_OK)) as (build, opener):
        with pytest.raises(DeadlineExceeded):
            build(deadline=spent).issues(10)
    assert opener.requests == []


def test_a_wait_the_run_cannot_afford_is_refused_not_slept():
    """`ask`'s veto, from this side of it: **a wait outliving the check's budget is not
    the request layer's to take.** A ten-minute `Retry-After` inside a thirty-second
    run re-raises at once, and the check reports what it has."""
    slept = []
    clock = _Clock()
    answers = _sequence(_Answer(body=_TOKEN_OK),
                        _graphql_error(429, b"{}", {"Retry-After": "600"}))
    with _through(answers) as (build, opener):
        with pytest.raises(WizError) as caught:
            build(deadline=Deadline(30.0, clock=clock),
                  sleep=slept.append).issues(10)
    assert slept == []
    assert len(opener.requests) == 2           # the token, one query, no retry
    assert caught.value.retry_after == 600.0


def test_a_transport_failure_is_transient_and_the_sentence_is_ours():
    """No status at all — a dropped connection, a DNS blip, a socket timeout. urllib's
    own text arrives as the cause rather than in the sentence a reader gets, which
    otherwise carries proxy paths and certificate directories."""
    with _through(OSError("connection reset")) as (build, _opener):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert caught.value.status is None
    assert caught.value.fault is Fault.TRANSIENT
    assert "connection reset" in str(caught.value)
    assert "WIZ auth could not be sent" in str(caught.value)
    # ...and *only* ours. `fetch` words its own failure "request failed for POST <url>",
    # so passing the `RemoteError` through instead of its cause reads the URL and the
    # verb twice in one sentence. Asserting the cause's text alone does not catch that,
    # because the cause's text is inside the wrapper too.
    assert "request failed for" not in str(caught.value)
    assert str(caught.value).count("auth.example.wiz.io") == 1


def test_the_client_does_not_follow_a_redirect():
    """A 3xx from an API endpoint means the URL is wrong — which for a region-specific
    `api_url` (ADR-0001 §6) is the useful thing to report. Following it would be worse
    than useless: urllib turns a POST into a GET on redirect, so the request body would
    be silently dropped and the failure would arrive as something else."""
    with _through(_Answer(status=302, body=b"", headers={"Location": "/elsewhere"})) \
            as (build, opener):
        with pytest.raises(WizError) as caught:
            build().issues(10)
    assert len(opener.requests) == 1
    assert caught.value.status == 302
    assert caught.value.fault is Fault.ANSWERED


def test_the_token_is_fetched_once_per_client():
    """Two queries, one auth exchange. Cheap, and it keeps a credential out of the
    logs and off the wire more often than it needs to be."""
    answers = _sequence(_Answer(body=_TOKEN_OK), _Answer(body=_ONE_ISSUE),
                        _Answer(body=_ONE_ISSUE))
    with _through(answers) as (build, opener):
        client = build()
        client.issues(10)
        client.issues(10)
    assert len(opener.requests) == 3           # not 4
