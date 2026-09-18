"""
Tests for the SHADOW engine.

    python -m pytest tests -q

The most important test is `test_more_information_never_lowers_exposure`:
it tries every one of the 4096 possible sets of shared information and checks
that adding one more item never reduces the score. That is the property the
whole app relies on for the "experiment" feature to make sense.
"""

from __future__ import annotations

from itertools import combinations

import pytest

from shadow import CATALOGUE, COMBINATIONS, RELATIONS, Graph, analyse
from shadow.catalogue import ALL_KEYS, CATEGORIES
from shadow.engine import level_for, max_raw_score, quick_score
from shadow.rules import matching_combinations
from shadow.storage import ScenarioStore


# --------------------------------------------------------------------------
# The rules themselves
# --------------------------------------------------------------------------
def test_every_rule_refers_to_a_real_catalogue_key():
    for r in RELATIONS:
        assert r.a in ALL_KEYS and r.b in ALL_KEYS and r.a != r.b
    for c in COMBINATIONS:
        assert c.items <= ALL_KEYS and len(c.items) >= 2


def test_catalogue_categories_are_valid():
    for info in CATALOGUE:
        assert info.category in CATEGORIES
        assert 0 <= info.sensitivity <= 3


def test_no_duplicate_relations():
    pairs = [frozenset((r.a, r.b)) for r in RELATIONS]
    assert len(pairs) == len(set(pairs))


def test_superset_combinations_are_at_least_as_severe():
    """If A ⊂ B then severity(B) >= severity(A); otherwise the score could drop."""
    for small in COMBINATIONS:
        for big in COMBINATIONS:
            if small.items < big.items:
                assert big.severity >= small.severity, (small.title, big.title)


def test_only_maximal_combinations_are_reported():
    found = matching_combinations(frozenset({"username", "school", "schedule"}))
    titles = {c.title for c in found}
    assert "Strong chain: handle → school → routine" in titles
    assert "Identity correlation" not in titles      # absorbed by the strong chain
    assert "Predictable routine" not in titles


# --------------------------------------------------------------------------
# Graph algorithms
# --------------------------------------------------------------------------
def test_shortest_path_is_bfs():
    g = Graph()
    for a, b in [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d"), ("x", "y")]:
        g.add_edge(a, b)
    assert g.shortest_path("a", "d") == ["a", "d"]          # direct beats a-b-c-d
    assert g.shortest_path("b", "d") in (["b", "a", "d"], ["b", "c", "d"])
    assert g.shortest_path("a", "x") is None                # different component
    assert g.shortest_path("a", "a") == ["a"]
    assert len(g.connected_components()) == 2
    assert g.density() == pytest.approx(5 / 15)


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------
def test_empty_is_zero():
    a = analyse([])
    assert a.score == 0 and a.level == "Nothing shared"
    assert a.findings == [] and a.trace is None


def test_everything_is_100():
    assert analyse(ALL_KEYS).score == 100
    assert max_raw_score() > 0


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError):
        analyse(["school", "home_address"])


def test_the_demo_story_escalates():
    """School + City -> + Schedule -> + Username should climb through the levels."""
    s1 = analyse(["school", "city"])
    s2 = analyse(["school", "city", "schedule"])
    s3 = analyse(["school", "city", "schedule", "username"])
    assert s1.level == "Low"
    assert s2.level == "Moderate"
    assert s3.level == "High"
    assert s1.score < s2.score < s3.score


def test_combinations_dominate_individual_points():
    """The thesis: three items together score more than the sum of their parts."""
    parts = sum(analyse([k]).raw for k in ("city", "school", "schedule"))
    together = analyse(["city", "school", "schedule"]).raw
    assert together > 2 * parts


def test_trace_finds_path_from_username_to_a_place():
    a = analyse(["username", "public_profile", "school", "schedule"])
    assert a.trace is not None
    assert a.trace.path[0] == "username" and a.trace.path[-1] == "school"
    assert len(a.trace.steps) == len(a.trace.path) - 1
    # Without the profile the username is not connected to anything.
    assert analyse(["username", "school", "schedule"]).trace is None


def test_what_if_is_consistent_with_recomputing():
    a = analyse(["username", "public_profile", "school", "schedule", "city"])
    for w in a.what_if_remove:
        assert w.score == analyse(a.selected - {w.key}).score
        assert w.delta == w.score - a.score
    for w in a.what_if_add:
        assert w.score == analyse(a.selected | {w.key}).score
    # Sorted: biggest reduction first, biggest increase first.
    deltas = [w.delta for w in a.what_if_remove]
    assert deltas == sorted(deltas)
    deltas = [w.delta for w in a.what_if_add]
    assert deltas == sorted(deltas, reverse=True)


def test_more_information_never_lowers_exposure():
    """Exhaustive: for every subset S and every x not in S, score(S ∪ {x}) >= score(S)."""
    keys = sorted(ALL_KEYS)
    for n in range(len(keys)):
        for subset in combinations(keys, n):
            base = frozenset(subset)
            before = quick_score(base)
            for extra in ALL_KEYS - base:
                assert quick_score(base | {extra}) >= before, (sorted(base), extra)


def test_levels_are_monotonic():
    assert level_for(0) == "Nothing shared"
    assert level_for(5) == "Low"
    assert level_for(15) == "Moderate"
    assert level_for(30) == "High"
    assert level_for(80) == "Severe"


def test_to_dict_is_json_shaped():
    d = analyse(["school", "city", "schedule"]).to_dict()
    assert {i["key"] for i in d["items"]} == {"school", "city", "schedule"}
    assert all({"source", "target", "strength", "reason"} <= e.keys() for e in d["edges"])
    assert d["findings"][0]["severity_label"] == "high"
    assert d["what_if"]["remove"][0]["delta"] <= 0


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def test_scenario_store_round_trip(tmp_path):
    store = ScenarioStore(tmp_path / "test.db")
    sid = store.save("before", ["city", "school"], 3, "Low")
    assert store.get(sid)["items"] == ["city", "school"]
    assert [s["name"] for s in store.list()] == ["before"]
    assert store.delete(sid) is True
    assert store.delete(sid) is False
    assert store.list() == []
