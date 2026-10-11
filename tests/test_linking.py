"""Entity linking (PLAN 2.1): alias table from the CSVs and `link_entities`."""
from __future__ import annotations

from collections import Counter

import pytest

from waypoint.graph.db import run_read
from waypoint.graph.load import read_csv
from waypoint.retrieval.aliases import (
    REJECTED_SKILL_MERGES,
    SKILL_MERGES,
    alias_table,
    canonical_skill,
    skill_merge_candidates,
    skill_variants,
)
from waypoint.retrieval.linking import EntityMatch, link_entities


def ids(text: str) -> list[tuple[str, str]]:
    return [(m.label, m.id) for m in link_entities(text)]


def skill_id(name: str) -> str:
    return next(r["skill_id"] for r in read_csv("skills") if r["skill"] == name)


EMPLOYEES = read_csv("employees")


# ---------------------------------------------------------------- employees

@pytest.mark.parametrize("row", EMPLOYEES, ids=lambda r: r["employee_id"])
def test_every_employee_by_full_name_and_id(row: dict[str, str]) -> None:
    eid = row["employee_id"]
    assert ids(f"Who manages {row['full_name']}?") == [("Employee", eid)]
    assert ids(f"Who manages {row['full_name'].lower()}?") == [("Employee", eid)]
    assert ids(f"Profile of {eid}.") == [("Employee", eid)]
    assert ids(f"Profile of {eid.lower()}.") == [("Employee", eid)]


def test_unique_first_names_resolve_and_ambiguous_ones_do_not() -> None:
    firsts = Counter(r["full_name"].split()[0] for r in EMPLOYEES)
    for r in EMPLOYEES:
        first = r["full_name"].split()[0]
        got = ids(f"Where does {first} sit?")
        if firsts[first] == 1:
            assert got == [("Employee", r["employee_id"])], first
        else:
            assert got == [], first
    assert ids("Where does pooja sit?") == []  # first names are case-sensitive


def test_ambiguous_first_names_are_reported() -> None:
    table = alias_table()
    firsts = Counter(r["full_name"].split()[0] for r in EMPLOYEES)
    assert set(table.excluded_first_names) == {f for f, n in firsts.items() if n > 1}


def test_shared_first_names_and_titles_are_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real CSV has no shared first names or titles, so add a namesake."""
    import waypoint.retrieval.aliases as aliases_mod
    import waypoint.retrieval.linking as linking_mod

    real = aliases_mod.read_csv
    pooja = next(r for r in EMPLOYEES if r["full_name"] == "Pooja Agarwal")
    twin = {**pooja, "employee_id": "ZV-9999", "full_name": "Pooja Raman"}

    def fake(name: str) -> list[dict[str, str]]:
        rows = real(name)
        return rows + [twin] if name == "employees" else rows

    monkeypatch.setattr(aliases_mod, "read_csv", fake)
    aliases_mod.alias_table.cache_clear()
    linking_mod._compiled.cache_clear()
    try:
        table = aliases_mod.alias_table()
        assert table.excluded_first_names == {"Pooja": ["ZV-1031", "ZV-9999"]}
        assert table.excluded_titles == {pooja["title"]: ["ZV-1031", "ZV-9999"]}
        assert ids("Where does Pooja sit?") == []
        assert ids("Ask the Data Engineer.") == []
        assert ids("Ask Pooja Raman.") == [("Employee", "ZV-9999")]
    finally:
        monkeypatch.undo()
        aliases_mod.alias_table.cache_clear()
        linking_mod._compiled.cache_clear()


def test_possessive_first_name() -> None:
    assert ids("What is Arjun's notice period?") == [("Employee", "ZV-1042")]


def test_unique_titles_and_chief_acronyms() -> None:
    assert ids("Who is the CTO?") == [("Employee", "ZV-1002")]
    assert ids("Who is the CEO?") == [("Employee", "ZV-1001")]
    assert ids("Ask the CISO.") == [("Employee", "ZV-1012")]
    assert ids("Who is the Head of People & Culture?") == [("Employee", "ZV-1006")]
    titles = Counter(r["title"] for r in EMPLOYEES)
    for r in EMPLOYEES:
        if titles[r["title"]] > 1:
            assert r["title"] in alias_table().excluded_titles


# ---------------------------------------------------------------- departments, projects, products, policies

def test_department_names_codes_and_short_names() -> None:
    assert ids("Who heads Data & AI?") == [("Department", "D05")]
    assert ids("Who heads the Backend Engineering department?") == [("Department", "D03")]
    assert ids("Is Customer Support (Zenvora Care) in Pune?") == [("Department", "D10")]
    assert ids("Escalate to CSC.") == [("Department", "D10")]
    assert ids("Talk to HR about it.") == [("Department", "D01")]
    assert ids("Ask the Data team.") == [("Department", "D05")]
    assert ids("Ask the data team.") == [("Department", "D05")]
    assert ids("Who leads Support at Zenvora?") == [("Department", "D10")]


def test_zenvora_care_product_unless_followed_by_team_word() -> None:
    assert ids("Zenvora Care launched in 2021.") == [("Product", "PR03")]
    assert ids("Who uses Zenvora Care?") == [("Product", "PR03")]
    assert ids("Ask the Zenvora Care team.") == [("Department", "D10")]
    assert ids("Zenvora Care department head?") == [("Department", "D10")]
    assert ids("Zenvora Care dept") == [("Department", "D10")]


def test_projects_and_products_full_and_short() -> None:
    assert ids("Who led Project Atlas?") == [("Project", "PJ01")]
    assert ids("who led project atlas?") == [("Project", "PJ01")]
    assert ids("Who worked on Atlas and Nova?") == [("Project", "PJ01"), ("Project", "PJ09")]
    assert ids("Atlas was a migration.") == [("Project", "PJ01")]
    assert ids("Who owns Pulse?") == [("Product", "PR01")]
    assert ids("Who owns Zenvora Ledger?") == [("Product", "PR02")]
    assert ids("Members of the Horizon project") == [("Project", "PJ06")]


def test_policy_codes_and_titles() -> None:
    assert ids("Which policies cite ZEN-POL-004?") == [("Policy", "ZEN-POL-004")]
    assert ids("Which policies cite zen-pol-004?") == [("Policy", "ZEN-POL-004")]
    assert ids("Read the Hybrid Work Policy.") == [("Policy", "ZEN-POL-002")]
    assert ids("Progressive Discipline Policy (ZEN-POL-004)") == [("Policy", "ZEN-POL-004")] * 2
    assert ids("ZEN-POL-0040 is not a code") == []


# ---------------------------------------------------------------- organisations and locations (2.2)

@pytest.mark.parametrize("row", read_csv("organizations"), ids=lambda r: r["org_id"])
def test_every_organization_by_full_name_and_id(row: dict[str, str]) -> None:
    assert ids(f"Who worked at {row['name']}?") == [("Organization", row["org_id"])]
    assert ids(f"Who worked at {row['name'].lower()}?") == [("Organization", row["org_id"])]
    assert ids(f"Who worked at {row['org_id']}?") == [("Organization", row["org_id"])]


def test_organization_short_names_are_restricted() -> None:
    assert ids("Who worked at Tessera?") == [("Organization", "ORG016")]
    assert ids("Who worked at Brightpath before?") == [("Organization", "ORG002")]
    assert ids("a maple tree and the Maple of Canada") == []
    assert ids("He saw the sunrise.") == []


@pytest.mark.parametrize("row", read_csv("locations"), ids=lambda r: r["location_id"])
def test_every_location_by_full_name_id_and_city(row: dict[str, str]) -> None:
    lid = row["location_id"]
    assert ids(f"Who sits in {row['name']}?") == [("Location", lid)]
    assert ids(f"Who sits in {row['name'].lower()}?") == [("Location", lid)]
    assert ids(f"Who works from {row['city']}?") == [("Location", lid)]
    assert ids(f"Who works from {row['city'].lower()}?") == []


def test_city_inside_another_proper_name_does_not_link() -> None:
    assert ids("Which employees studied at JNTU Hyderabad?") == []
    assert ids("Who on Project Beacon works from Bengaluru?") == [("Project", "PJ03"), ("Location", "L02")]
    # the full organisation name wins over the city it contains
    org = next(o for o in read_csv("organizations") if "Austin" in o["name"])
    assert ids(f"People from {org['name']} joined.") == [("Organization", org["org_id"])]


# ---------------------------------------------------------------- skills

def test_parenthetical_skill_variants_normalise() -> None:
    py = skill_id("Python")
    for variant in ("Python (FastAPI)", "Python (pandas)", "Python scripting"):
        assert canonical_skill(skill_id(variant)) == py, variant
    assert skill_variants(py) == {py, skill_id("Python (FastAPI)"), skill_id("Python (pandas)"),
                                  skill_id("Python scripting")}
    [m] = link_entities("Who knows Python (FastAPI)?")
    assert (m.label, m.id, m.canonical_id, m.surface) == (
        "Skill", skill_id("Python (FastAPI)"), py, "Python (FastAPI)")
    [m] = link_entities("Who knows Python scripting?")
    assert m.canonical_id == py


def test_skill_merges_are_explicit_and_valid() -> None:
    names = {r["skill"] for r in read_csv("skills")}
    for variant, base in SKILL_MERGES.items():
        assert variant in names and base in names and variant.startswith(base + " ")


def test_every_word_suffix_candidate_is_decided() -> None:
    decided = set(SKILL_MERGES.items()) | set(REJECTED_SKILL_MERGES.items())
    assert set(skill_merge_candidates()) == decided
    assert not set(SKILL_MERGES) & set(REJECTED_SKILL_MERGES)


def test_skill_names_link() -> None:
    assert ids("Which employees list Kafka as a skill?") == [("Skill", skill_id("Kafka"))]
    assert ids("Which employees list Employee relations as a skill?") == [
        ("Skill", skill_id("Employee relations"))]
    assert ids("Who knows Pulse inbox administration?") == [
        ("Skill", skill_id("Pulse inbox administration"))]


# ---------------------------------------------------------------- precision

def test_common_words_do_not_link() -> None:
    assert ids("the Atlas of the world") == []
    assert ids("a Compass and a map") == []
    assert ids("Can I paste customer data into an AI chatbot?") == []
    assert ids("Data retention rules apply.") == []
    assert ids("Design reviews happen weekly.") == []
    assert ids("Testing happens before release.") == []
    assert ids("we sell support and care") == []
    assert ids("Go to the office.") == []
    # part of a longer proper name: the organisation links (2.2), the skill Analytics does not
    assert ids("Which Zenvora employees previously worked at Finwise Analytics?") == [
        ("Organization", "ORG003")]
    assert ids("He worked at Atlas Systems before.") == []
    assert ids("Which Atlas engineers report to Divya?") == [("Project", "PJ01"), ("Employee", "ZV-1004")]


def test_spans_never_overlap_and_are_ordered() -> None:
    text = ("Lakshmi Prasanna Varma, Head of People & Culture, asked the Zenvora Care team "
            "about Project Atlas, ZEN-POL-004 and Python (FastAPI) with Arjun.")
    matches = link_entities(text)
    for a, b in zip(matches, matches[1:]):
        assert a.end <= b.start
    for m in matches:
        assert text[m.start:m.end] == m.surface
    assert [m.id for m in matches] == ["ZV-1006", "ZV-1006", "D10", "PJ01", "ZEN-POL-004",
                                       skill_id("Python (FastAPI)"), "ZV-1042"]


def test_match_type() -> None:
    [m] = link_entities("Ask ZV-1042.")
    assert m == EntityMatch(id="ZV-1042", label="Employee", surface="ZV-1042", start=4, end=11,
                            canonical_id="ZV-1042")


def test_no_alias_points_to_two_entities() -> None:
    table = alias_table()
    seen: dict[tuple[str, bool], tuple[str, str]] = {}
    for a in table.aliases:
        key = (a.text.lower() if a.ignore_case else a.text, a.ignore_case)
        assert seen.setdefault(key, (a.label, a.id)) == (a.label, a.id) or a.alt is not None, a.text


# ---------------------------------------------------------------- graph

@pytest.mark.neo4j
def test_every_alias_target_is_a_graph_node(driver) -> None:
    keys = {"Employee": "employee_id", "Department": "department_id", "Project": "project_id",
            "Product": "product_id", "Policy": "policy_id", "Skill": "skill_id",
            "Organization": "org_id", "Location": "location_id"}
    wanted: dict[str, set[str]] = {}
    for a in alias_table().aliases:
        wanted.setdefault(a.label, set()).add(a.id)
        if a.alt:
            wanted.setdefault(a.alt[0], set()).add(a.alt[1])
    for label, want in wanted.items():
        rows = run_read(driver, f"MATCH (n:{label}) WHERE n.{keys[label]} IN $ids "
                                f"RETURN n.{keys[label]} AS id", {"ids": sorted(want)})
        assert {r["id"] for r in rows} == want, label


def test_eval_entities_does_not_depend_on_linking() -> None:
    """The scorer's entity reference stays independent of the linker it is used to check."""
    import inspect

    import waypoint.eval.entities as entities

    src = inspect.getsource(entities)
    assert "retrieval.linking" not in src and "retrieval.aliases" not in src


# ---------------------------------------------------------------- unresolved code-like mentions (2.4)

from waypoint.retrieval.linking import LinkResult, UnresolvedMention, link_mentions  # noqa: E402


@pytest.mark.parametrize("text,surface,label", [
    ("Who owns ZEN-POL-099?", "ZEN-POL-099", "Policy"),
    ("What does zen-pol-099 say?", "zen-pol-099", "Policy"),
    ("Summarise ZEN-DPL-XYZ-07.", "ZEN-DPL-XYZ-07", "Policy"),
    ("Is ZEN-POL-0040 in force?", "ZEN-POL-0040", "Policy"),
    ("Who is ZV-9999?", "ZV-9999", "Employee"),
    ("How many people are in D99?", "D99", "Department"),
    ("Who leads PJ99?", "PJ99", "Project"),
    ("Who owns PR07?", "PR07", "Product"),
])
def test_unresolved_code_like_tokens(text: str, surface: str, label: str) -> None:
    r = link_mentions(text)
    assert isinstance(r, LinkResult)
    assert [(u.surface, u.label) for u in r.unresolved] == [(surface, label)]
    assert r.matches == tuple(link_entities(text))


def test_known_ids_are_not_unresolved() -> None:
    r = link_mentions("ZEN-POL-004, ZEN-DPL-HR-01, ZV-1042, D03, PJ01, PR01 and L01")
    assert r.unresolved == ()
    assert [m.id for m in r.matches] == ["ZEN-POL-004", "ZEN-DPL-HR-01", "ZV-1042", "D03", "PJ01", "PR01", "L01"]


def test_mixed_known_and_unknown() -> None:
    r = link_mentions("Does ZEN-POL-004 reference ZEN-POL-099, and who in D03 reports to ZV-9999?")
    assert [m.id for m in r.matches] == ["ZEN-POL-004", "D03"]
    assert r.unresolved == (UnresolvedMention("ZEN-POL-099", "Policy", 27, 38),
                            UnresolvedMention("ZV-9999", "Employee", 66, 73))


def test_plain_words_are_not_code_like() -> None:
    for text in ("Who leads D&AI?", "Is the d99 printer broken?", "Room L1 or level 2", "COVID-19 rules", "H1 FY2026-27"):
        assert link_mentions(text).unresolved == (), text
