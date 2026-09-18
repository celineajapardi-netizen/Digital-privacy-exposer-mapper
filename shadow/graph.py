"""
A small undirected graph, written from scratch so every algorithm is visible.

Nodes are strings (the catalogue keys). Edges carry a `strength` weight.
Only what the engine needs is implemented:

    neighbours(n)          adjacency lookup
    density()              how connected the graph is, 0..1
    connected_components() groups of nodes that can reach each other
    shortest_path(a, b)    breadth-first search, fewest hops
"""

from __future__ import annotations

from collections import deque


class Graph:
    def __init__(self) -> None:
        # adjacency list: node -> {neighbour: strength}
        self._adj: dict[str, dict[str, int]] = {}

    # -- building ----------------------------------------------------------
    def add_node(self, node: str) -> None:
        self._adj.setdefault(node, {})

    def add_edge(self, a: str, b: str, strength: int = 1) -> None:
        self.add_node(a)
        self.add_node(b)
        self._adj[a][b] = strength
        self._adj[b][a] = strength

    # -- reading -----------------------------------------------------------
    @property
    def nodes(self) -> list[str]:
        return list(self._adj)

    def edges(self) -> list[tuple[str, str, int]]:
        """Each undirected edge once, as (a, b, strength) with a < b."""
        seen = []
        for a, nbrs in self._adj.items():
            for b, strength in nbrs.items():
                if a < b:
                    seen.append((a, b, strength))
        return seen

    def neighbours(self, node: str) -> dict[str, int]:
        return self._adj.get(node, {})

    def has_node(self, node: str) -> bool:
        return node in self._adj

    # -- algorithms --------------------------------------------------------
    def density(self) -> float:
        """Edges present divided by edges possible. 0 for fewer than 2 nodes."""
        n = len(self._adj)
        if n < 2:
            return 0.0
        possible = n * (n - 1) / 2
        return len(self.edges()) / possible

    def connected_components(self) -> list[set[str]]:
        """Flood-fill: start at an unvisited node, collect everything reachable."""
        visited: set[str] = set()
        components: list[set[str]] = []
        for start in self._adj:
            if start in visited:
                continue
            component: set[str] = set()
            stack = [start]
            while stack:
                node = stack.pop()
                if node in component:
                    continue
                component.add(node)
                stack.extend(self._adj[node])
            visited |= component
            components.append(component)
        return components

    def shortest_path(self, start: str, goal: str) -> list[str] | None:
        """
        Breadth-first search. Because every hop counts as 1, the first time we
        reach `goal` we have found a path with the fewest hops. Returns the
        list of nodes from start to goal, or None if they are not connected.
        """
        if start not in self._adj or goal not in self._adj:
            return None
        if start == goal:
            return [start]
        parent: dict[str, str | None] = {start: None}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nbr in self._adj[node]:
                if nbr in parent:
                    continue
                parent[nbr] = node
                if nbr == goal:
                    # Walk back through the parents to rebuild the path.
                    path = [goal]
                    while parent[path[-1]] is not None:
                        path.append(parent[path[-1]])  # type: ignore[arg-type]
                    return path[::-1]
                queue.append(nbr)
        return None
