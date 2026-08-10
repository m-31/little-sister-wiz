"""Fixture-based tests for the ``wiz`` check type — no live WIZ calls."""
from __future__ import annotations

import pytest
from little_sister.checks import CheckError
from little_sister.status import StatusCode

from little_sister_wiz.wiz import (
    ENTRY_NOTE,
    SUBNODES,
    WizCheck,
    WizError,
)


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
    monkeypatch.setattr(check, "_make_client", lambda cid, sec: fake)
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


def test_query_error_is_error(monkeypatch):
    check = _check()
    fake = FakeWiz(error=WizError("boom", status=500))
    result = _run(check, fake, monkeypatch)
    assert result.code is StatusCode.ERROR
    assert "WIZ query failed" in result.reason_texts[0]


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


def test_bands_carry_the_built_in_text(monkeypatch):
    """The type ships every band's label, so a second tenant's config carries none."""
    check = _check()   # no subnodes configured
    result = _run(check, FakeWiz([_issue("CRITICAL")]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.title == SUBNODES["critical"]["title"]
    assert critical.about == _about("critical")
    high = next(c for c in result.children if c.name == "high")
    assert high.title == "High"


def test_config_replaces_a_band_label(monkeypatch):
    check = _check(subnodes={
        "critical": {"title": "Sev-1", "about": "Page the on-call."}})
    result = _run(check, FakeWiz([_issue("CRITICAL")]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.title == "Sev-1"
    assert critical.about == "Page the on-call."
    high = next(c for c in result.children if c.name == "high")   # untouched
    assert high.about == _about("high")


def test_config_extends_a_band_label_with_the_default_token(monkeypatch):
    check = _check(subnodes={
        "critical": {"about": "{default} Page the on-call."}})
    result = _run(check, FakeWiz([_issue("CRITICAL")]), monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.about == _about("critical") + " Page the on-call."


def test_entity_level_lines_are_members_keyed_by_the_wiz_issue_id(monkeypatch):
    """A WIZ issue id is minted with the issue and retired with it — exactly the
    identity ADR-0036 wants, so each band's lines are individually pinnable."""
    check = _check(aggregation_level="entity")
    fake = FakeWiz([_issue("CRITICAL", issue_id="abc-123", entity="db-1"),
                    _issue("CRITICAL", issue_id="def-456", entity="db-2")])
    result = _run(check, fake, monkeypatch)
    critical = next(c for c in result.children if c.name == "critical")
    assert critical.members
    assert "Each line is one WIZ issue" in critical.about
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

    assert "Each line is one WIZ **control**" in critical.about
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
