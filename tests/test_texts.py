"""What the `wiz` type says of its nodes, as little-sister ADR-0133 divides it.

Each band's `about` says what to do when the band holds issues, by the sign the band
shows then under the map in force, and leads into the section of the **handbook** that
says it at length — one Markdown file this package ships beside its module and every
band names, which says what the bands read, how to read a band and its lines, the
grading in force among it, what to do and how to configure it. Each band's
`description` says what it reads in one sentence, the same for every band, and its
**details** link WIZ's own list of its open issues, as the check's own node's link the
tenant's — a link in a description would be counted in the sentence's length.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from little_sister.nodes import ABOUT_NOTED_PAST, DESCRIPTION_NOTED_PAST
from little_sister.render import anchors_of, short_links
from little_sister.status import StatusCode
from little_sister.transport import Fault
from test_wiz import FakeWiz, _check, _issue, _run

from little_sister_wiz import wiz
from little_sister_wiz.wiz import SEVERITY_ORDER, WizError

#: Where this package's handbook is: beside the module that names it.
PACKAGE = Path(wiz.__file__).parent

#: Every link a Markdown text writes, by its target.
_LINK = re.compile(r"\]\(([^)\s]+)\)")

#: A status a text names by its sign, as little-sister draws it.
_SIGN = re.compile(r"\{(ok|warn|error|maintenance|undefined)\}", re.IGNORECASE)

#: What a band says when its issues ask for work and the map grades it WARN, as it
#: grades a severity it does not name.
ACTING_WARN = ("{warn}: open each issue from its line and fix what WIZ found on the "
               "entity, setting the issue in progress in WIZ meanwhile — or ignore it "
               "there with its reason; "
               "[what to do](handbook#when-a-band-holds-issues).")

#: WIZ's list of the open and in-progress issues, as the app reads it from its address:
#: the tenant's whole list, and the list of the critical ones.
ALL_OPEN = ("https://app.wiz.io/issues#~(filters~(status~(equals~(~'OPEN"
            "~'IN_PROGRESS))))")
CRITICAL_OPEN = ("https://app.wiz.io/issues#~(filters~(status~(equals~(~'OPEN"
                 "~'IN_PROGRESS))~severity~(equals~(~'CRITICAL))))")


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The references resolve at construction (little-sister ADR-0023)."""
    monkeypatch.setenv("WIZ_CLIENT_ID", "id")
    monkeypatch.setenv("WIZ_CLIENT_SECRET", "sec")


def test_every_band_names_the_one_handbook_this_package_ships() -> None:
    # a band differs from another by its severity and its grading alone, so every
    # band — one the map names and this package does not among them — names one file
    check = _check(severity_map={"catastrophic": StatusCode.ERROR})
    assert (PACKAGE / wiz.HANDBOOK).is_file()
    # a file nothing names is a handbook no page shows
    assert set((PACKAGE / "handbook").glob("*.md")) == {PACKAGE / wiz.HANDBOOK}
    assert set(check.subnode_labels) == {*SEVERITY_ORDER, "catastrophic"}
    shared = check.subnode_labels["critical"]["handbook"]
    for band, labels in check.subnode_labels.items():
        assert set(labels) == {"title", "about", "handbook"}, band
        assert labels["handbook"] == shared, band


@pytest.mark.parametrize("severity_map", [
    {},                                             # as shipped
    {"medium": StatusCode.WARN, "low": StatusCode.OK,
     "informational": StatusCode.ERROR},
    {"critical": StatusCode.MAINTENANCE, "high": StatusCode.UNDEFINED},
])
def test_an_about_says_what_to_do_by_the_sign_its_band_shows(
        severity_map: dict[str, StatusCode]) -> None:
    # the sign is the one a band holding issues shows under the map in force, and an
    # about leads into the handbook's section for what that sign asks
    check = _check(severity_map=severity_map)
    in_force = {**wiz.DEFAULT_SEVERITY_MAP, **severity_map}
    for band, labels in check.subnode_labels.items():
        about = labels["about"]
        assert len(about) <= ABOUT_NOTED_PAST, (band, len(about))
        assert {sign.lower() for sign in _SIGN.findall(about)} == {
            in_force[band].name.lower()}, band
        acting = in_force[band] in (StatusCode.WARN, StatusCode.ERROR)
        sections = {section.lstrip("#") for section in short_links(about)}
        assert sections == ({"when-a-band-holds-issues"} if acting
                            else {"how-to-read-it"}), band
        assert sections <= anchors_of(labels["handbook"]), band


def test_informational_says_that_nothing_waits_on_it() -> None:
    about = _check().subnode_labels["informational"]["about"]
    assert about == ("Nothing to do: with issues this band reads {ok}, and lists them "
                     "for information; [how to read it](handbook#how-to-read-it).")


def test_the_handbook_links_its_own_sections_and_says_the_grading_in_force() -> None:
    shipped = _check().subnode_labels["critical"]["handbook"]
    overridden = _check(severity_map={"medium": StatusCode.WARN}).subnode_labels[
        "medium"]["handbook"]
    assert shipped.startswith("# WIZ issues by severity\n")
    for text in (shipped, overridden):
        # every token expands — a status's sign is the renderer's, and no token
        assert "{" not in _SIGN.sub("", text)
        # a handbook is read at /handbook/<path>, where a relative link leads nowhere
        for target in _LINK.findall(text):
            assert target.startswith(("#", "https://")), target
            if target.startswith("#"):
                assert target[1:] in anchors_of(text), target
    assert ("A band holding issues is graded by `severity_map` — `critical` → "
            "**ERROR**, `high` → **ERROR**, `medium` → **ERROR**, `low` → **WARN**, "
            "`informational` → **OK** — and a band of a severity the map does not name "
            "**WARN**. A band holding none reads `OK`") in shipped
    assert "`medium` → **WARN**" in overridden
    assert "`medium` → **ERROR**" not in overridden


@pytest.mark.parametrize(("level", "other"), [("id", "entity"), ("entity", "id")])
def test_the_handbook_says_how_a_line_reads_and_ends_with_its_pin(
        level: str, other: str) -> None:
    # a line is a control or an issue by the configured aggregation level, which is
    # what can be pinned on its own — the last thing the handbook says
    text = _check(aggregation_level=level).subnode_labels["critical"]["handbook"]
    how = text.split("\n## How to read it\n", 1)[1].split("\n## ", 1)[0]
    assert wiz.LINE_NOTES[level] in how
    assert wiz.LINE_NOTES[other] not in text
    assert text.rstrip("\n").endswith(
        "\n## While you work on it\n\n" + wiz.PIN_NOTES[level])


def test_a_deployments_entry_note_still_says_what_it_said() -> None:
    # `{entry_note}`, the paragraph every band's about ended with until the handbook
    # took it, is a token a deployment's own text may name
    check = _check(subnode_labels={"critical": {"about": "{entry_note}"}})
    assert check.subnode_labels["critical"]["about"] == (
        "Each line is one WIZ **control**, followed by every entity it flagged and "
        "that entity's kind, each linked to its own issue in WIZ. A finding marked "
        "*in progress* is already being worked on in WIZ. Because the line carries "
        "the control ID, each control is separately addressable: put **that one "
        "line** into maintenance while you work on it and the rest of the band keeps "
        "reporting.")


def test_a_description_is_one_sentence_within_its_length() -> None:
    sentence = wiz.BAND_DESCRIPTION
    assert len(sentence) <= DESCRIPTION_NOTED_PAST, sentence
    assert sentence[:1].isupper() and sentence.endswith("."), sentence
    assert "](" not in sentence, sentence


def test_every_node_of_a_run_names_its_object(monkeypatch: pytest.MonkeyPatch) -> None:
    # The details of each object (little-sister ADR-0133 decision 6): the tenant's
    # whole list of open issues on the check's own node, and each band's own list.
    result = _run(_check(), FakeWiz([_issue("CRITICAL", issue_id="c1"),
                                     _issue("BIZARRE", issue_id="b1")]), monkeypatch)
    assert result.details == {"issues": f"[All open issues]({ALL_OPEN})"}
    bands = {band.name: band for band in result.children}
    assert set(bands) == {*SEVERITY_ORDER, "bizarre"}
    assert bands["critical"].details == {
        "issues": f"[All open critical issues]({CRITICAL_OPEN})"}
    for name, band in bands.items():
        assert band.description == wiz.BAND_DESCRIPTION, name
        assert band.details == {"issues": f"[All open {name} issues]("
                                          + CRITICAL_OPEN.replace(
                                              "CRITICAL", name.upper()) + ")"}, name
        # nothing a run writes links a handbook: a band's labels are declared
        for text in (band.description, *band.details.values()):
            assert not short_links(text, inline=True), (name, text)
    # a severity WIZ invents is named by the data, so nothing declared its labels:
    # its run hands them over — its circle, the about its fallback grading gives, and
    # the handbook every band names
    assert (bands["bizarre"].title, bands["bizarre"].about,
            bands["bizarre"].handbook) == ("❓", ACTING_WARN, wiz.HANDBOOK)


@pytest.mark.parametrize(("stated", "handed"), [
    ({"title": "Bizarre"}, ("", ACTING_WARN, wiz.HANDBOOK)),
    ({"about": "Ask the security team."}, ("❓", "", wiz.HANDBOOK)),
])
def test_a_band_hands_over_each_label_nothing_declared_for_it(
        monkeypatch: pytest.MonkeyPatch, stated: dict[str, str],
        handed: tuple[str, str, str]) -> None:
    # field by field, as the library reads them: a deployment that writes one label
    # for a severity WIZ invents keeps the type's others for its band
    check = _check(subnode_labels={"bizarre": stated})
    result = _run(check, FakeWiz([_issue("BIZARRE")]), monkeypatch)
    bizarre = next(band for band in result.children if band.name == "bizarre")
    assert (bizarre.title, bizarre.about, bizarre.handbook) == handed


def test_a_severity_wiz_invents_shows_what_every_band_shows(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # through the engine, which reads the handbook a run names from this package and
    # expands the type's tokens in it as in what is declared (little-sister ADR-0133
    # decision 2): the grading in force, how a line reads, what a pin holds
    from little_sister.engine import Engine
    from little_sister.tree import StatusTree

    check = _check()
    monkeypatch.setattr(check, "_make_client",
                        lambda cid, sec, deadline=None: FakeWiz([_issue("BIZARRE")]))
    tree = StatusTree()
    Engine([check], tree).run_once()
    texts = tree.texts("/wiz/bizarre")
    assert (texts["title"], texts["about"]) == ("❓", ACTING_WARN)
    assert tree.handbook("/wiz/bizarre") == check.subnode_labels["critical"]["handbook"]
    assert "{grading}" not in tree.handbook("/wiz/bizarre")


@pytest.mark.parametrize("fault", [Fault.TRANSIENT, Fault.ANSWERED, Fault.MALFORMED])
def test_a_failed_read_still_names_the_tenants_issues(
        monkeypatch: pytest.MonkeyPatch, fault: Fault) -> None:
    # the check's own node says what failed, and where to look in the meantime
    result = _run(_check(), FakeWiz(error=WizError("boom", status=503, fault=fault)),
                  monkeypatch)
    assert result.children == ()
    assert result.details == {"issues": f"[All open issues]({ALL_OPEN})"}


def test_the_lists_are_on_the_app_url(monkeypatch: pytest.MonkeyPatch) -> None:
    app = "https://app.example.org"
    result = _run(_check(app_url=f"{app}/"), FakeWiz([_issue("CRITICAL")]),
                  monkeypatch)
    assert result.details == {
        "issues": f"[All open issues]({ALL_OPEN.replace('https://app.wiz.io', app)})"}
    critical = next(band for band in result.children if band.name == "critical")
    assert critical.details == {
        "issues": "[All open critical issues]("
                  f"{CRITICAL_OPEN.replace('https://app.wiz.io', app)})"}
