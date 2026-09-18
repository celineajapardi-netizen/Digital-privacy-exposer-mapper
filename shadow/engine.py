"""
The engine: turn a set of shared information into a graph, apply the rules,
and produce an exposure score with an explanation.

    analyse({"school", "city", "schedule"})  ->  Analysis

The score is built from four parts, all of which can only grow when more
information is added:

    points          sum of each item's own sensitivity           (small numbers)
    relationships   sum of the strength of every active edge     (medium)
    combinations    weight of every maximal risky pattern found  (large - the point)
    trace           bonus if a stranger could walk from an
                    identity item to a location item

The raw total is scaled so that sharing *everything* scores 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

from .catalogue import ALL_KEYS, CATALOGUE, CATALOGUE_BY_KEY
from .graph import Graph
from .rules import (
    RELATIONS,
    SEVERITY_LABEL,
    Combination,
    Relation,
    active_relations,
    matching_combinations,
)

# How much each risky pattern adds. Deliberately larger than the item
# sensitivities (0-3) so that combinations dominate the score.
COMBINATION_WEIGHT = {1: 3, 2: 6, 3: 10}
TRACE_BONUS = 3

# Score bands. The scale is relative to "everything public" = 100.
LEVELS = (
    (0, "Nothing shared"),
    (1, "Low"),
    (10, "Moderate"),
    (20, "High"),
    (45, "Severe"),
)

# Where the "trace" starts (what a stranger might know first) and where it
# tries to get to (a physical place), in order of preference.
TRACE_SOURCES = ("username", "public_profile", "real_name", "contact", "photos", "friends", "birthday")
TRACE_TARGETS = ("neighbourhood", "school", "city")


def level_for(score: int) -> str:
    label = LEVELS[0][1]
    for threshold, name in LEVELS:
        if score >= threshold:
            label = name
    return label


# --------------------------------------------------------------------------
# Result objects
# --------------------------------------------------------------------------
@dataclass
class TraceStep:
    source: str
    target: str
    reason: str


@dataclass
class Trace:
    path: list[str]
    steps: list[TraceStep]
    summary: str


@dataclass
class WhatIf:
    key: str
    label: str
    score: int
    level: str
    delta: int      # new score minus current score


@dataclass
class Analysis:
    selected: frozenset[str]
    graph: Graph
    relations: list[Relation]
    findings: list[Combination]
    trace: Trace | None
    raw: int
    score: int
    level: str
    breakdown: dict[str, int | float]
    what_if_remove: list[WhatIf] = field(default_factory=list)
    what_if_add: list[WhatIf] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Plain JSON-able version for the web app and the CLI."""
        return {
            "items": [
                {
                    "key": info.key,
                    "label": info.label,
                    "category": info.category,
                    "sensitivity": info.sensitivity,
                    "description": info.description,
                }
                for info in CATALOGUE if info.key in self.selected
            ],
            "edges": [
                {"source": r.a, "target": r.b, "strength": r.strength, "reason": r.reason}
                for r in self.relations
            ],
            "findings": [
                {
                    "items": sorted(c.items),
                    "severity": c.severity,
                    "severity_label": SEVERITY_LABEL[c.severity],
                    "title": c.title,
                    "explanation": c.explanation,
                }
                for c in self.findings
            ],
            "trace": None if self.trace is None else {
                "path": self.trace.path,
                "steps": [{"source": s.source, "target": s.target, "reason": s.reason} for s in self.trace.steps],
                "summary": self.trace.summary,
            },
            "raw": self.raw,
            "score": self.score,
            "level": self.level,
            "breakdown": self.breakdown,
            "what_if": {
                "remove": [w.__dict__ for w in self.what_if_remove],
                "add": [w.__dict__ for w in self.what_if_add],
            },
        }


# --------------------------------------------------------------------------
# Core computation
# --------------------------------------------------------------------------
def build_graph(selected: frozenset[str]) -> tuple[Graph, list[Relation]]:
    """Nodes for every selected item, edges for every relation between them."""
    graph = Graph()
    for key in selected:
        graph.add_node(key)
    relations = active_relations(selected)
    for r in relations:
        graph.add_edge(r.a, r.b, r.strength)
    return graph, relations


def find_trace(graph: Graph, selected: frozenset[str]) -> Trace | None:
    """
    Could a stranger get from something they know online to a real place?

    Try each starting point in order of preference, and for the first one
    that is connected to any location item, return the shortest path to the
    most specific location it can reach.
    """
    reasons = {frozenset((r.a, r.b)): r.reason for r in RELATIONS}
    for source in TRACE_SOURCES:
        if source not in selected:
            continue
        for target in TRACE_TARGETS:
            if target not in selected or target == source:
                continue
            path = graph.shortest_path(source, target)
            if path is None or len(path) < 2:
                continue
            steps = [
                TraceStep(a, b, reasons[frozenset((a, b))])
                for a, b in zip(path, path[1:])
            ]
            hops = len(path) - 1
            summary = (
                f"Starting from only your {CATALOGUE_BY_KEY[source].label.lower()}, "
                f"someone could follow {hops} link{'s' if hops != 1 else ''} "
                f"to reach your {CATALOGUE_BY_KEY[target].label.lower()}."
            )
            return Trace(path, steps, summary)
    return None


def raw_score(selected: frozenset[str]) -> tuple[int, dict[str, int | float], Graph, list[Relation], list[Combination], Trace | None]:
    graph, relations = build_graph(selected)
    findings = matching_combinations(selected)
    trace = find_trace(graph, selected)

    points = sum(CATALOGUE_BY_KEY[k].sensitivity for k in selected)
    relationship_score = sum(r.strength for r in relations)
    combination_score = sum(COMBINATION_WEIGHT[c.severity] for c in findings)
    trace_score = TRACE_BONUS if trace else 0
    raw = points + relationship_score + combination_score + trace_score

    breakdown = {
        "items": len(selected),
        "points": points,
        "relationships": len(relations),
        "strong_relationships": sum(1 for r in relations if r.strength == 3),
        "relationship_score": relationship_score,
        "findings": len(findings),
        "high_findings": sum(1 for c in findings if c.severity == 3),
        "combination_score": combination_score,
        "trace_score": trace_score,
        "density": round(graph.density(), 2),
        "components": len(graph.connected_components()),
    }
    return raw, breakdown, graph, relations, findings, trace


@lru_cache(maxsize=1)
def max_raw_score() -> int:
    """The raw score when every kind of information is public. Used to scale to 100."""
    return raw_score(ALL_KEYS)[0]


def scaled(raw: int) -> int:
    return round(100 * raw / max_raw_score())


def quick_score(selected: frozenset[str]) -> int:
    """Score only - used for the what-if experiments so we do not recurse."""
    return scaled(raw_score(selected)[0])


def analyse(items: Iterable[str], with_what_if: bool = True) -> Analysis:
    selected = frozenset(items)
    unknown = selected - ALL_KEYS
    if unknown:
        raise ValueError(f"Unknown information keys: {sorted(unknown)}")

    raw, breakdown, graph, relations, findings, trace = raw_score(selected)
    score = scaled(raw)
    analysis = Analysis(
        selected=selected,
        graph=graph,
        relations=relations,
        findings=findings,
        trace=trace,
        raw=raw,
        score=score,
        level=level_for(score),
        breakdown=breakdown,
    )

    if with_what_if:
        # "What if I removed X?" for everything shared ...
        for key in selected:
            new = quick_score(selected - {key})
            analysis.what_if_remove.append(
                WhatIf(key, CATALOGUE_BY_KEY[key].label, new, level_for(new), new - score)
            )
        # ... and "what if I also shared Y?" for everything not shared.
        for key in ALL_KEYS - selected:
            new = quick_score(selected | {key})
            analysis.what_if_add.append(
                WhatIf(key, CATALOGUE_BY_KEY[key].label, new, level_for(new), new - score)
            )
        # Biggest reduction first / biggest increase first.
        analysis.what_if_remove.sort(key=lambda w: (w.delta, w.label))
        analysis.what_if_add.sort(key=lambda w: (-w.delta, w.label))

    return analysis
