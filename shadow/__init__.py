"""
SHADOW — how seemingly harmless information becomes revealing when connected.

The package is deliberately small so that every step can be explained:

    catalogue.py  the kinds of information a person might share (the *nodes*)
    rules.py      relationships between them (the *edges*) and risky combinations
    graph.py      a plain graph data structure with the algorithms we need
    engine.py     puts it together: build the graph, apply the rules, score it
    storage.py    saves scenarios to a small SQLite database
    cli.py        run an analysis from the terminal
"""

from .catalogue import CATALOGUE, CATALOGUE_BY_KEY, InfoType
from .engine import Analysis, analyse, max_raw_score
from .graph import Graph
from .rules import COMBINATIONS, RELATIONS, Combination, Relation

__all__ = [
    "CATALOGUE",
    "CATALOGUE_BY_KEY",
    "COMBINATIONS",
    "RELATIONS",
    "Analysis",
    "Combination",
    "Graph",
    "InfoType",
    "Relation",
    "analyse",
    "max_raw_score",
]
