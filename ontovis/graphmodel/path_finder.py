"""Path finding across the *semantic* graph of classes.

Only class-to-class links take part: object properties (asserted through
domain/range or through OWL restrictions) and ``rdfs:subClassOf``.  Datatype
properties are deliberately excluded — ``Company --name--> xsd:string`` is an
attribute, not a route between two classes.

Two strategies are offered:

``shortest``
    Breadth-first search.  O(V + E), returns one minimal-hop path.

``all``
    Depth-first enumeration of *simple* paths (no repeated class), bounded by
    ``max_depth`` and ``max_paths`` so a densely connected ontology cannot
    blow up the UI.

The same algorithms are re-implemented in JavaScript inside the viewer so the
exported HTML keeps working without Python; this module is the reference
implementation and is what the tests exercise.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Optional

from ..parsing.models import Ontology, Relation, RelationKind


@dataclass(frozen=True)
class PathStep:
    """One hop: ``source --relation--> target`` (possibly traversed backwards)."""

    source: str
    target: str
    relation: Relation
    reversed: bool = False

    def describe(self, labels: dict[str, str]) -> str:
        arrow = "<--" if self.reversed else "-->"
        label = self.relation.label or "subClassOf"
        return f"{labels.get(self.source, self.source)} {arrow[:2]}{label}{arrow[-1]} " \
               f"{labels.get(self.target, self.target)}"


@dataclass(frozen=True)
class OntologyPath:
    steps: tuple[PathStep, ...]

    @property
    def nodes(self) -> tuple[str, ...]:
        if not self.steps:
            return ()
        return (self.steps[0].source,) + tuple(step.target for step in self.steps)

    @property
    def length(self) -> int:
        return len(self.steps)

    def as_text(self, labels: dict[str, str]) -> str:
        """Readable rendering, e.g.::

            Company
              --hasValuation-->
            Valuation
        """
        if not self.steps:
            return ""
        lines = [labels.get(self.steps[0].source, self.steps[0].source)]
        for step in self.steps:
            label = step.relation.label or "subClassOf"
            connector = f"  <--{label}--" if step.reversed else f"  --{label}-->"
            lines.append(connector)
            lines.append(labels.get(step.target, step.target))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "nodes": list(self.nodes),
            "edges": [
                {
                    "id": step.relation.id,
                    "source": step.source,
                    "target": step.target,
                    "label": step.relation.label,
                    "kind": step.relation.kind.value,
                    "reversed": step.reversed,
                }
                for step in self.steps
            ],
        }


class PathFinder:
    """Builds an adjacency index once, then answers many path queries."""

    def __init__(
        self,
        ontology: Ontology,
        *,
        include_subclass: bool = True,
        respect_direction: bool = True,
    ) -> None:
        self.ontology = ontology
        self.include_subclass = include_subclass
        self.respect_direction = respect_direction
        self._forward: dict[str, list[tuple[str, Relation, bool]]] = defaultdict(list)
        self._build_index()

    def _build_index(self) -> None:
        for relation in self.ontology.relations:
            if relation.kind is RelationKind.SUBCLASS_OF and not self.include_subclass:
                continue
            self._forward[relation.source].append((relation.target, relation, False))
            if not self.respect_direction:
                self._forward[relation.target].append((relation.source, relation, True))

    # ------------------------------------------------------------------ #
    def neighbours(self, node: str) -> Iterable[tuple[str, Relation, bool]]:
        return self._forward.get(node, [])

    def shortest_path(self, source: str, target: str) -> Optional[OntologyPath]:
        if source == target:
            return OntologyPath(())
        if source not in self.ontology.classes or target not in self.ontology.classes:
            return None

        previous: dict[str, tuple[str, Relation, bool]] = {}
        visited = {source}
        queue: deque[str] = deque([source])

        while queue:
            current = queue.popleft()
            for neighbour, relation, is_reversed in self.neighbours(current):
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                previous[neighbour] = (current, relation, is_reversed)
                if neighbour == target:
                    return self._reconstruct(previous, source, target)
                queue.append(neighbour)
        return None

    def all_paths(
        self,
        source: str,
        target: str,
        *,
        max_depth: int = 6,
        max_paths: int = 25,
    ) -> list[OntologyPath]:
        if source not in self.ontology.classes or target not in self.ontology.classes:
            return []
        results: list[OntologyPath] = []
        stack_path: list[PathStep] = []
        on_path = {source}

        def walk(node: str) -> None:
            if len(results) >= max_paths or len(stack_path) >= max_depth:
                return
            for neighbour, relation, is_reversed in self.neighbours(node):
                if neighbour in on_path:
                    continue
                step = PathStep(node, neighbour, relation, is_reversed)
                stack_path.append(step)
                if neighbour == target:
                    results.append(OntologyPath(tuple(stack_path)))
                    if len(results) >= max_paths:
                        stack_path.pop()
                        return
                else:
                    on_path.add(neighbour)
                    walk(neighbour)
                    on_path.discard(neighbour)
                stack_path.pop()

        walk(source)
        results.sort(key=lambda p: p.length)
        return results

    # ------------------------------------------------------------------ #
    def _reconstruct(
        self,
        previous: dict[str, tuple[str, Relation, bool]],
        source: str,
        target: str,
    ) -> OntologyPath:
        steps: list[PathStep] = []
        cursor = target
        while cursor != source:
            parent, relation, is_reversed = previous[cursor]
            steps.append(PathStep(parent, cursor, relation, is_reversed))
            cursor = parent
        steps.reverse()
        return OntologyPath(tuple(steps))
