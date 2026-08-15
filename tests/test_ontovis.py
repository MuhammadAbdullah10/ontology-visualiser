"""Test suite for the Ontology Visualiser.

    pytest -q

The JavaScript side has its own headless suite; see tests/js/README.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontovis.export.html_exporter import render_html
from ontovis.graphmodel.graph_builder import build_payload, build_search_index
from ontovis.graphmodel.path_finder import PathFinder
from ontovis.parsing.models import OntologyParseError, RelationKind, RelationOrigin
from ontovis.parsing.ontology_parser import OntologyParser, parse_ontology

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
EX = "http://example.org/valuation#"


@pytest.fixture(scope="module")
def ontology():
    return parse_ontology(EXAMPLES / "valuation.ttl")


# --------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------- #
def test_classes_are_found(ontology):
    labels = {cls.label for cls in ontology.classes.values()}
    assert {"Company", "Valuation", "Valuation Method", "Backsolve"} <= labels
    assert len(ontology.classes) == 12


def test_owl_thing_and_datatypes_are_not_classes(ontology):
    assert not any("XMLSchema" in uri for uri in ontology.classes)
    assert not any(uri.endswith("#Thing") for uri in ontology.classes)


def test_domain_range_becomes_a_directed_relation(ontology):
    relation = next(r for r in ontology.relations if r.label == "hasValuation")
    assert relation.source == EX + "Company"
    assert relation.target == EX + "Valuation"
    assert relation.kind is RelationKind.OBJECT_PROPERTY
    assert relation.origin is RelationOrigin.DOMAIN_RANGE


def test_union_domain_expands_to_one_relation_per_member(ontology):
    sources = {r.source for r in ontology.relations if r.label == "documentedIn"}
    assert sources == {EX + "Valuation", EX + "FundingRound"}


def test_subclass_relations_are_separate_from_object_properties(ontology):
    subclasses = {
        (r.source, r.target) for r in ontology.relations_of_kind(RelationKind.SUBCLASS_OF)
    }
    assert (EX + "DCF", EX + "ValuationMethod") in subclasses
    assert (EX + "Company", EX + "Organisation") in subclasses
    assert len(subclasses) == 5


def test_restriction_becomes_an_object_relation_not_a_subclass(ontology):
    restriction = next(r for r in ontology.relations if r.origin is RelationOrigin.RESTRICTION)
    assert (restriction.source, restriction.label, restriction.target) == (
        EX + "Backsolve",
        "calibratedTo",
        EX + "FundingRound",
    )
    assert restriction.note == "some values from"
    # The restriction filler must never be read as a superclass.
    assert not any(
        r.kind is RelationKind.SUBCLASS_OF and r.target == EX + "FundingRound"
        for r in ontology.relations
    )


def test_datatype_properties_attach_to_their_domain(ontology):
    company = ontology.classes[EX + "Company"]
    own = {p.label: p.range_label for p in company.datatype_properties if not p.is_inherited}
    assert own == {
        "id": "xsd:string",
        "sector": "xsd:string",
        "currency": "xsd:string",
        "revenue": "xsd:decimal",
        "foundedDate": "xsd:date",
    }


def test_missing_range_is_not_invented(ontology):
    valuation = ontology.classes[EX + "Valuation"]
    note = next(p for p in valuation.datatype_properties if p.label == "internalNote")
    assert note.range_label is None


def test_attributes_are_inherited_and_tagged(ontology):
    company = ontology.classes[EX + "Company"]
    inherited = {p.label: p.inherited_from for p in company.datatype_properties if p.is_inherited}
    assert inherited == {"name": EX + "Organisation", "jurisdiction": EX + "Organisation"}


def test_inheritance_can_be_switched_off():
    parser = OntologyParser(include_inherited_attributes=False)
    ontology = parser.parse_file(EXAMPLES / "valuation.ttl")
    company = ontology.classes[EX + "Company"]
    assert all(not p.is_inherited for p in company.datatype_properties)


def test_property_without_domain_is_kept_for_search(ontology):
    unattached = {p.label for p in ontology.unattached_properties}
    assert "legacyCode" in unattached
    assert ontology.warnings


def test_labels_prefer_rdfs_label(ontology):
    assert ontology.classes[EX + "GPC"].label == "Guideline Public Company"


def test_statistics(ontology):
    stats = ontology.statistics
    assert stats.classes == 12
    assert stats.object_properties == 10          # 9 with domain/range + calibratedTo
    assert stats.datatype_properties == 23
    assert stats.subclass_relations == 5
    assert stats.total_relationships == stats.subclass_relations + stats.object_relations


# --------------------------------------------------------------------- #
# Modelling-style tolerance and error handling
# --------------------------------------------------------------------- #
def test_rdfs_style_ontology_without_owl():
    turtle = """
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
    @prefix ex:   <http://example.org/lib#> .

    ex:Book     a rdfs:Class .
    ex:Author   a rdfs:Class .
    ex:writtenBy a rdf:Property ; rdfs:domain ex:Book ; rdfs:range ex:Author .
    ex:title     a rdf:Property ; rdfs:domain ex:Book ; rdfs:range xsd:string .
    """
    ontology = parse_ontology(turtle, source_name="lib.ttl")
    assert len(ontology.classes) == 2
    relation = ontology.relations[0]
    assert relation.kind is RelationKind.OBJECT_PROPERTY and relation.label == "writtenBy"
    book = ontology.classes["http://example.org/lib#Book"]
    assert [p.label for p in book.datatype_properties] == ["title"]


def test_invalid_turtle_raises_a_friendly_error():
    with pytest.raises(OntologyParseError) as excinfo:
        parse_ontology("this is definitely not turtle {{{", source_name="broken.ttl")
    assert "valid Turtle/RDF" in str(excinfo.value)


def test_ontology_with_no_classes_is_empty_not_broken():
    ontology = parse_ontology(
        '@prefix ex: <http://example.org/> . ex:a ex:b "c" .', source_name="thin.ttl"
    )
    assert ontology.is_empty
    assert ontology.statistics.classes == 0


def test_missing_domain_and_range_do_not_crash():
    turtle = """
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix ex:  <http://example.org/x#> .
    ex:A a owl:Class .
    ex:p a owl:ObjectProperty .
    """
    ontology = parse_ontology(turtle)
    assert ontology.relations == []
    assert [p.label for p in ontology.unattached_properties] == ["p"]


# --------------------------------------------------------------------- #
# Path finding
# --------------------------------------------------------------------- #
def test_shortest_path_follows_object_properties(ontology):
    finder = PathFinder(ontology)
    path = finder.shortest_path(EX + "Company", EX + "ValuationMethod")
    assert [step.relation.label for step in path.steps] == ["hasValuation", "usesMethod"]
    assert path.nodes == (EX + "Company", EX + "Valuation", EX + "ValuationMethod")


def test_path_text_is_readable(ontology):
    finder = PathFinder(ontology)
    path = finder.shortest_path(EX + "Company", EX + "ValuationMethod")
    text = path.as_text(ontology.class_labels())
    assert text.splitlines()[:3] == ["Company", "  --hasValuation-->", "Valuation"]


def test_datatype_properties_are_never_a_route(ontology):
    finder = PathFinder(ontology)
    for step in finder.all_paths(EX + "Company", EX + "Report", max_paths=10)[0].steps:
        assert step.relation.uri is None or step.relation.uri not in ontology.datatype_property_uris()


def test_direction_is_respected_unless_disabled(ontology):
    directed = PathFinder(ontology)
    assert directed.shortest_path(EX + "ValuationMethod", EX + "Company") is None
    undirected = PathFinder(ontology, respect_direction=False)
    assert undirected.shortest_path(EX + "ValuationMethod", EX + "Company") is not None


def test_subclass_links_can_be_excluded(ontology):
    with_subclass = PathFinder(ontology, respect_direction=False)
    without = PathFinder(ontology, include_subclass=False, respect_direction=False)
    assert with_subclass.shortest_path(EX + "DCF", EX + "Company") is not None
    assert without.shortest_path(EX + "DCF", EX + "Company") is None


def test_all_paths_are_simple_and_bounded(ontology):
    finder = PathFinder(ontology, respect_direction=False)
    paths = finder.all_paths(EX + "Company", EX + "Report", max_depth=6, max_paths=5)
    assert 1 <= len(paths) <= 5
    for path in paths:
        assert len(set(path.nodes)) == len(path.nodes)      # no class visited twice
        assert path.length <= 6
    assert paths == sorted(paths, key=lambda p: p.length)


def test_unknown_class_returns_nothing(ontology):
    finder = PathFinder(ontology)
    assert finder.shortest_path("http://nope", EX + "Company") is None
    assert finder.all_paths(EX + "Company", "http://nope") == []


# --------------------------------------------------------------------- #
# Payload and export
# --------------------------------------------------------------------- #
def test_search_index_covers_all_three_element_types(ontology):
    index = build_search_index(ontology)
    kinds = {entry["kind"] for entry in index}
    assert kinds == {"class", "objectProperty", "datatypeProperty"}
    labels = {entry["label"] for entry in index}
    assert {"Valuation", "hasValuation", "valuationDate"} <= labels


def test_payload_keeps_attributes_off_the_initial_graph(ontology):
    payload = build_payload(ontology)
    assert len(payload["classes"]) == 12
    assert all("datatypes" in cls for cls in payload["classes"])
    # attributes travel inside their class, never as top-level nodes
    assert "nodes" not in payload


def test_export_is_self_contained_and_parsable(ontology, tmp_path):
    html = render_html(ontology)
    assert html.startswith("<!doctype html>")
    for marker in ("__PAGE_TITLE__", "/*__CSS_TOKENS__*/", "/*__PAYLOAD__*/"):
        assert marker not in html
    assert "window.__ONTOLOGY_PAYLOAD__ = {" in html
    blob = html.split("window.__ONTOLOGY_PAYLOAD__ = ", 2)[2].split(";\n</script>")[0]
    payload = json.loads(blob.replace("<\\/", "</"))
    assert payload["stats"]["classes"] == 12
    assert payload["style"]["theme"]["accent"]


def test_export_escapes_script_terminators():
    turtle = """
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix ex: <http://example.org/x#> .
    ex:A a owl:Class ; rdfs:comment "watch out </script><script>alert(1)</script>" .
    """
    html = render_html(parse_ontology(turtle))
    assert "</script><script>alert(1)" not in html


def test_embedded_flag_hides_the_save_button(ontology):
    assert '"embedded":true' in render_html(ontology, embedded=True)
    assert '"embedded":false' in render_html(ontology, embedded=False)
