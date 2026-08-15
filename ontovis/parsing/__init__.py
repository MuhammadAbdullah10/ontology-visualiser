"""RDF/OWL parsing layer: turns Turtle into a typed ontology model."""

from .models import (
    DatatypeProperty,
    Ontology,
    OntologyClass,
    OntologyParseError,
    OntologyStatistics,
    PropertySummary,
    Relation,
    RelationKind,
    RelationOrigin,
)
from .ontology_parser import OntologyParser, parse_ontology

__all__ = [
    "DatatypeProperty",
    "Ontology",
    "OntologyClass",
    "OntologyParseError",
    "OntologyStatistics",
    "PropertySummary",
    "Relation",
    "RelationKind",
    "RelationOrigin",
    "OntologyParser",
    "parse_ontology",
]
