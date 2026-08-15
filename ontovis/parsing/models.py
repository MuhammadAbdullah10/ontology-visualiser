"""Typed, view-agnostic model of a parsed ontology.

Nothing in this module knows about RDF libraries or about the visualisation
layer.  The parser produces these objects; the graph/export layers consume
them.  Keeping the model in the middle means a different parser (JSON-LD,
SPARQL endpoint, ...) or a different renderer can be swapped in without
touching anything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class RelationKind(str, Enum):
    """How two classes are linked."""

    OBJECT_PROPERTY = "object"
    SUBCLASS_OF = "subclass"


class RelationOrigin(str, Enum):
    """Where the link was found in the source ontology.

    Knowing the origin lets the UI style *asserted* links differently from
    links that were read out of an OWL restriction, and lets the legend
    explain the difference honestly.
    """

    DOMAIN_RANGE = "domain_range"          # rdfs:domain / rdfs:range
    RESTRICTION = "restriction"            # owl:Restriction on a class
    ASSERTED = "asserted"                  # rdfs:subClassOf triple


@dataclass(frozen=True)
class DatatypeProperty:
    """A literal-valued attribute of a class (owl:DatatypeProperty)."""

    uri: str
    label: str
    curie: str
    range_label: Optional[str] = None      # e.g. "xsd:string"; None when absent
    range_uri: Optional[str] = None
    comment: Optional[str] = None
    inherited_from: Optional[str] = None   # URI of the superclass that declares it

    @property
    def is_inherited(self) -> bool:
        return self.inherited_from is not None

    def to_dict(self, owner_uri: str) -> dict[str, Any]:
        return {
            "id": f"{owner_uri}|dt|{self.uri}",
            "uri": self.uri,
            "label": self.label,
            "curie": self.curie,
            "range": self.range_label,
            "rangeUri": self.range_uri,
            "comment": self.comment,
            "inheritedFrom": self.inherited_from,
        }


@dataclass
class OntologyClass:
    """An owl:Class / rdfs:Class node."""

    uri: str
    label: str
    curie: str
    comment: Optional[str] = None
    datatype_properties: list[DatatypeProperty] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.uri,
            "uri": self.uri,
            "label": self.label,
            "curie": self.curie,
            "comment": self.comment,
            "datatypes": [d.to_dict(self.uri) for d in self.datatype_properties],
        }


@dataclass(frozen=True)
class Relation:
    """A directed class-to-class link."""

    source: str                        # class URI
    target: str                        # class URI
    kind: RelationKind
    label: str = ""                    # property label; empty for subclass links
    uri: Optional[str] = None          # property URI; None for subclass links
    curie: Optional[str] = None
    origin: RelationOrigin = RelationOrigin.DOMAIN_RANGE
    note: Optional[str] = None         # e.g. "some values from", "min 1"

    @property
    def id(self) -> str:
        key = self.uri or "subClassOf"
        return f"{self.source}|{key}|{self.target}|{self.origin.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "label": self.label,
            "uri": self.uri,
            "curie": self.curie,
            "origin": self.origin.value,
            "note": self.note,
        }


@dataclass(frozen=True)
class PropertySummary:
    """A property that could not be attached to any class in the graph.

    Kept so the user can still find it through search instead of silently
    losing it (a very common situation in partially specified ontologies).
    """

    uri: str
    label: str
    curie: str
    kind: str                          # "object" | "datatype"
    comment: Optional[str] = None
    reason: str = "No rdfs:domain declared"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "label": self.label,
            "curie": self.curie,
            "kind": self.kind,
            "comment": self.comment,
            "reason": self.reason,
        }


@dataclass
class OntologyStatistics:
    classes: int = 0
    object_properties: int = 0
    datatype_properties: int = 0
    subclass_relations: int = 0
    object_relations: int = 0

    @property
    def total_relationships(self) -> int:
        return self.subclass_relations + self.object_relations

    def to_dict(self) -> dict[str, int]:
        return {
            "classes": self.classes,
            "objectProperties": self.object_properties,
            "datatypeProperties": self.datatype_properties,
            "subclassRelations": self.subclass_relations,
            "objectRelations": self.object_relations,
            "totalRelationships": self.total_relationships,
        }


@dataclass
class Ontology:
    """The complete parsed ontology, ready to be turned into a graph."""

    classes: dict[str, OntologyClass] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    unattached_properties: list[PropertySummary] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)
    title: Optional[str] = None
    source_name: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Convenience accessors
    # ------------------------------------------------------------------ #
    @property
    def is_empty(self) -> bool:
        return not self.classes and not self.relations

    def class_labels(self) -> dict[str, str]:
        return {uri: cls.label for uri, cls in self.classes.items()}

    def sorted_classes(self) -> list[OntologyClass]:
        return sorted(self.classes.values(), key=lambda c: c.label.lower())

    def relations_of_kind(self, kind: RelationKind) -> list[Relation]:
        return [r for r in self.relations if r.kind is kind]

    def distinct_object_properties(self) -> list[Relation]:
        """One representative relation per object property URI."""
        seen: set[str] = set()
        out: list[Relation] = []
        for rel in self.relations:
            if rel.kind is not RelationKind.OBJECT_PROPERTY or not rel.uri:
                continue
            if rel.uri in seen:
                continue
            seen.add(rel.uri)
            out.append(rel)
        return out

    def datatype_property_uris(self) -> set[str]:
        uris: set[str] = set()
        for cls in self.classes.values():
            for prop in cls.datatype_properties:
                if not prop.is_inherited:
                    uris.add(prop.uri)
        uris.update(p.uri for p in self.unattached_properties if p.kind == "datatype")
        return uris

    @property
    def statistics(self) -> OntologyStatistics:
        object_uris = {r.uri for r in self.relations
                       if r.kind is RelationKind.OBJECT_PROPERTY and r.uri}
        object_uris.update(p.uri for p in self.unattached_properties
                           if p.kind == "object")
        return OntologyStatistics(
            classes=len(self.classes),
            object_properties=len(object_uris),
            datatype_properties=len(self.datatype_property_uris()),
            subclass_relations=len(self.relations_of_kind(RelationKind.SUBCLASS_OF)),
            object_relations=len(self.relations_of_kind(RelationKind.OBJECT_PROPERTY)),
        )


class OntologyParseError(Exception):
    """Raised when a document cannot be read as RDF at all."""


def dedupe(items: Iterable[Any]) -> list[Any]:
    """Order-preserving de-duplication helper."""
    seen: set[Any] = set()
    out: list[Any] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
