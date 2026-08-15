"""Turtle/RDF -> :class:`Ontology` parsing.

Design notes
------------
The parser is deliberately tolerant.  Real ontologies are modelled in very
different styles, so instead of assuming one shape we collect evidence:

* **Classes** come from ``owl:Class`` / ``rdfs:Class`` declarations, but also
  from anything that is used as the subject or object of ``rdfs:subClassOf``
  and from the domains/ranges of object properties.
* **Properties** come from ``owl:ObjectProperty`` / ``owl:DatatypeProperty``
  declarations, and bare ``rdf:Property`` declarations are classified by
  looking at their range (literal-ish range -> datatype property).
* **Relations** are read from ``rdfs:domain``/``rdfs:range`` *and* from
  ``owl:Restriction`` blocks, because many ontologies express "Company has a
  Valuation" only as a restriction.
* Class expressions (``owl:unionOf`` / ``owl:intersectionOf``) are unfolded so
  a property with a union domain produces one relation per member.

Anything that cannot be interpreted is skipped and recorded in
``Ontology.warnings`` rather than raising.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional, Union

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from .models import (
    DatatypeProperty,
    Ontology,
    OntologyClass,
    OntologyParseError,
    PropertySummary,
    Relation,
    RelationKind,
    RelationOrigin,
)

# Terms that are technically classes but only add noise to a diagram.
_IGNORED_CLASSES: frozenset[URIRef] = frozenset(
    {
        OWL.Thing,
        OWL.Nothing,
        RDFS.Resource,
        RDFS.Literal,
        RDFS.Class,
        OWL.Class,
        OWL.Restriction,
        OWL.Ontology,
        OWL.NamedIndividual,
    }
)

# Restriction fillers, mapped to the human-readable note shown on the edge.
_RESTRICTION_FILLERS: tuple[tuple[URIRef, str], ...] = (
    (OWL.someValuesFrom, "some values from"),
    (OWL.allValuesFrom, "all values from"),
    (OWL.onClass, "qualified cardinality"),
    (OWL.hasValue, "has value"),
    (OWL.onDataRange, "qualified cardinality"),
)

_LABEL_PREDICATES: tuple[URIRef, ...] = (
    RDFS.label,
    SKOS.prefLabel,
    DCTERMS.title,
    URIRef("http://purl.org/dc/elements/1.1/title"),
)

_COMMENT_PREDICATES: tuple[URIRef, ...] = (
    RDFS.comment,
    SKOS.definition,
    DCTERMS.description,
    URIRef("http://purl.org/dc/elements/1.1/description"),
)

_TURTLE_FORMATS: tuple[str, ...] = ("turtle", "n3", "xml", "json-ld", "nt", "trig")


class OntologyParser:
    """Parses an RDF document into an :class:`Ontology`."""

    def __init__(
        self,
        *,
        include_inherited_attributes: bool = True,
        preferred_language: str = "en",
    ) -> None:
        self.include_inherited_attributes = include_inherited_attributes
        self.preferred_language = preferred_language
        self._graph: Graph = Graph()
        self._namespaces: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Entry points
    # ------------------------------------------------------------------ #
    def parse_file(self, path: Union[str, Path]) -> Ontology:
        path = Path(path)
        try:
            data = path.read_text(encoding="utf-8")
        except OSError as exc:  # unreadable file
            raise OntologyParseError(f"Could not read {path.name}: {exc}") from exc
        return self.parse_text(data, source_name=path.name)

    def parse_text(self, data: str, *, source_name: Optional[str] = None) -> Ontology:
        graph = self._load_graph(data)
        return self.parse_graph(graph, source_name=source_name)

    def parse_bytes(self, data: bytes, *, source_name: Optional[str] = None) -> Ontology:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")
        return self.parse_text(text, source_name=source_name)

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def _load_graph(self, data: str) -> Graph:
        """Try Turtle first, then a few other syntaxes before giving up."""
        errors: list[str] = []
        for fmt in _TURTLE_FORMATS:
            graph = Graph()
            try:
                graph.parse(data=data, format=fmt)
            except Exception as exc:  # noqa: BLE001 - rdflib raises many types
                errors.append(f"{fmt}: {exc}")
                continue
            if len(graph) > 0 or fmt == "turtle":
                return graph
        raise OntologyParseError(
            "Unable to parse ontology. Please check that the uploaded file is "
            "valid Turtle/RDF.\n\nParser said: " + (errors[0] if errors else "unknown error")
        )

    # ------------------------------------------------------------------ #
    # Main parse
    # ------------------------------------------------------------------ #
    def parse_graph(self, graph: Graph, *, source_name: Optional[str] = None) -> Ontology:
        self._graph = graph
        self._namespaces = {
            prefix: str(uri) for prefix, uri in graph.namespaces() if prefix
        }

        class_uris = self._collect_classes(graph)
        object_props, datatype_props = self._classify_properties(graph)

        ontology = Ontology(
            namespaces=self._namespaces,
            title=self._ontology_title(graph),
            source_name=source_name,
        )

        # 1. Class nodes -------------------------------------------------
        for uri in sorted(class_uris, key=str):
            ontology.classes[str(uri)] = OntologyClass(
                uri=str(uri),
                label=self._label_for(uri),
                curie=self._curie(uri),
                comment=self._comment_for(uri),
            )

        # 2. Subclass edges ---------------------------------------------
        relations: list[Relation] = []
        relations.extend(self._subclass_relations(graph, class_uris))

        # 3. Object property edges from domain/range ---------------------
        attached_object_props: set[URIRef] = set()
        for prop in sorted(object_props, key=str):
            edges = self._domain_range_relations(graph, prop, class_uris)
            if edges:
                attached_object_props.add(prop)
                relations.extend(edges)

        # 4. Object property edges from OWL restrictions -----------------
        restriction_edges, restriction_datatypes = self._restriction_relations(
            graph, class_uris, object_props, datatype_props
        )
        for edge in restriction_edges:
            if edge.uri:
                attached_object_props.add(URIRef(edge.uri))
        relations.extend(restriction_edges)

        ontology.relations = self._dedupe_relations(relations)

        # 5. Datatype properties attached to their domain classes --------
        attached_datatype_props = self._attach_datatype_properties(
            graph, ontology, datatype_props, class_uris, restriction_datatypes
        )

        # 6. Properties we could not place ------------------------------
        for prop in sorted(object_props - attached_object_props, key=str):
            ontology.unattached_properties.append(
                PropertySummary(
                    uri=str(prop),
                    label=self._label_for(prop),
                    curie=self._curie(prop),
                    kind="object",
                    comment=self._comment_for(prop),
                    reason="No rdfs:domain/rdfs:range pointing at known classes",
                )
            )
        for prop in sorted(datatype_props - attached_datatype_props, key=str):
            ontology.unattached_properties.append(
                PropertySummary(
                    uri=str(prop),
                    label=self._label_for(prop),
                    curie=self._curie(prop),
                    kind="datatype",
                    comment=self._comment_for(prop),
                    reason="No rdfs:domain declared",
                )
            )

        # 7. Inherited attributes ---------------------------------------
        if self.include_inherited_attributes:
            self._propagate_inherited_attributes(ontology)

        if ontology.unattached_properties:
            ontology.warnings.append(
                f"{len(ontology.unattached_properties)} propert"
                f"{'y' if len(ontology.unattached_properties) == 1 else 'ies'} "
                "could not be attached to a class (missing domain/range). "
                "They are still searchable."
            )
        return ontology

    # ------------------------------------------------------------------ #
    # Class collection
    # ------------------------------------------------------------------ #
    def _collect_classes(self, graph: Graph) -> set[URIRef]:
        candidates: set[URIRef] = set()

        for class_type in (OWL.Class, RDFS.Class):
            for subject in graph.subjects(RDF.type, class_type):
                if isinstance(subject, URIRef):
                    candidates.add(subject)

        # Anything taking part in a subclass axiom is a class.
        for subject, obj in graph.subject_objects(RDFS.subClassOf):
            for term in (subject, obj):
                if isinstance(term, URIRef):
                    candidates.add(term)

        # Domains and ranges of object properties are classes.
        for prop in graph.subjects(RDF.type, OWL.ObjectProperty):
            for predicate in (RDFS.domain, RDFS.range):
                for term in graph.objects(prop, predicate):
                    candidates.update(self._expand_class_expression(term))

        # Domains of datatype properties are classes too.
        for prop in graph.subjects(RDF.type, OWL.DatatypeProperty):
            for term in graph.objects(prop, RDFS.domain):
                candidates.update(self._expand_class_expression(term))

        # Restrictions point at classes via their fillers.
        for restriction in graph.subjects(RDF.type, OWL.Restriction):
            for filler_predicate, _ in _RESTRICTION_FILLERS:
                for term in graph.objects(restriction, filler_predicate):
                    if isinstance(term, URIRef) and not self._is_datatype(term):
                        candidates.add(term)

        return {c for c in candidates if c not in _IGNORED_CLASSES and not self._is_datatype(c)}

    # ------------------------------------------------------------------ #
    # Property classification
    # ------------------------------------------------------------------ #
    def _classify_properties(self, graph: Graph) -> tuple[set[URIRef], set[URIRef]]:
        object_props: set[URIRef] = {
            p for p in graph.subjects(RDF.type, OWL.ObjectProperty) if isinstance(p, URIRef)
        }
        datatype_props: set[URIRef] = {
            p for p in graph.subjects(RDF.type, OWL.DatatypeProperty) if isinstance(p, URIRef)
        }

        # Bare rdf:Property declarations: classify by range.
        for prop in graph.subjects(RDF.type, RDF.Property):
            if not isinstance(prop, URIRef) or prop in object_props or prop in datatype_props:
                continue
            ranges = list(graph.objects(prop, RDFS.range))
            if any(self._is_datatype(r) for r in ranges):
                datatype_props.add(prop)
            elif ranges:
                object_props.add(prop)
            else:
                # No range at all: assume it links to a literal, which is the
                # safer default (it will not invent class-to-class edges).
                datatype_props.add(prop)

        # A property declared as both is treated as an object property.
        datatype_props -= object_props
        # Annotation properties are metadata, not ontology structure.
        annotations = {
            p for p in graph.subjects(RDF.type, OWL.AnnotationProperty) if isinstance(p, URIRef)
        }
        return object_props - annotations, datatype_props - annotations

    # ------------------------------------------------------------------ #
    # Relations
    # ------------------------------------------------------------------ #
    def _subclass_relations(self, graph: Graph, class_uris: set[URIRef]) -> list[Relation]:
        relations: list[Relation] = []
        for child, parent in graph.subject_objects(RDFS.subClassOf):
            if not isinstance(child, URIRef) or child not in class_uris:
                continue
            for resolved in self._expand_class_expression(parent, follow_restrictions=False):
                if resolved in class_uris and resolved != child:
                    relations.append(
                        Relation(
                            source=str(child),
                            target=str(resolved),
                            kind=RelationKind.SUBCLASS_OF,
                            label="subClassOf",
                            origin=RelationOrigin.ASSERTED,
                        )
                    )
        return relations

    def _domain_range_relations(
        self, graph: Graph, prop: URIRef, class_uris: set[URIRef]
    ) -> list[Relation]:
        domains = [
            d
            for term in graph.objects(prop, RDFS.domain)
            for d in self._expand_class_expression(term)
            if d in class_uris
        ]
        ranges = [
            r
            for term in graph.objects(prop, RDFS.range)
            for r in self._expand_class_expression(term)
            if r in class_uris
        ]
        if not domains or not ranges:
            return []

        label = self._label_for(prop)
        curie = self._curie(prop)
        return [
            Relation(
                source=str(domain),
                target=str(range_),
                kind=RelationKind.OBJECT_PROPERTY,
                label=label,
                uri=str(prop),
                curie=curie,
                origin=RelationOrigin.DOMAIN_RANGE,
            )
            for domain in domains
            for range_ in ranges
        ]

    def _restriction_relations(
        self,
        graph: Graph,
        class_uris: set[URIRef],
        object_props: set[URIRef],
        datatype_props: set[URIRef],
    ) -> tuple[list[Relation], dict[URIRef, set[URIRef]]]:
        """Read ``A rdfs:subClassOf [ owl:onProperty p ; owl:someValuesFrom B ]``.

        Returns the class-to-class relations plus a map of extra datatype
        properties discovered on classes through restrictions.
        """
        relations: list[Relation] = []
        extra_datatypes: dict[URIRef, set[URIRef]] = defaultdict(set)

        linking_predicates = (RDFS.subClassOf, OWL.equivalentClass)
        for predicate in linking_predicates:
            for owner, expression in graph.subject_objects(predicate):
                if not isinstance(owner, URIRef) or owner not in class_uris:
                    continue
                for restriction in self._restrictions_in(expression):
                    prop = next(iter(graph.objects(restriction, OWL.onProperty)), None)
                    if not isinstance(prop, URIRef):
                        continue
                    filler, note = self._restriction_filler(graph, restriction)
                    if prop in datatype_props:
                        extra_datatypes[owner].add(prop)
                        continue
                    if prop not in object_props:
                        continue
                    for target in self._expand_class_expression(filler):
                        if target in class_uris and target != owner:
                            relations.append(
                                Relation(
                                    source=str(owner),
                                    target=str(target),
                                    kind=RelationKind.OBJECT_PROPERTY,
                                    label=self._label_for(prop),
                                    uri=str(prop),
                                    curie=self._curie(prop),
                                    origin=RelationOrigin.RESTRICTION,
                                    note=note,
                                )
                            )
        return relations, extra_datatypes

    def _restrictions_in(self, expression: Node) -> Iterable[BNode]:
        """Yield restriction nodes inside a (possibly nested) class expression."""
        graph = self._graph
        if isinstance(expression, BNode):
            if (expression, RDF.type, OWL.Restriction) in graph:
                yield expression
                return
            for collection_predicate in (OWL.intersectionOf, OWL.unionOf):
                for collection in graph.objects(expression, collection_predicate):
                    for member in self._collection_members(collection):
                        yield from self._restrictions_in(member)

    def _restriction_filler(
        self, graph: Graph, restriction: BNode
    ) -> tuple[Optional[Node], Optional[str]]:
        for predicate, note in _RESTRICTION_FILLERS:
            filler = next(iter(graph.objects(restriction, predicate)), None)
            if filler is not None:
                cardinality = self._cardinality_note(graph, restriction)
                return filler, cardinality or note
        return None, None

    def _cardinality_note(self, graph: Graph, restriction: BNode) -> Optional[str]:
        for predicate, template in (
            (OWL.minQualifiedCardinality, "min {}"),
            (OWL.maxQualifiedCardinality, "max {}"),
            (OWL.qualifiedCardinality, "exactly {}"),
            (OWL.minCardinality, "min {}"),
            (OWL.maxCardinality, "max {}"),
            (OWL.cardinality, "exactly {}"),
        ):
            value = next(iter(graph.objects(restriction, predicate)), None)
            if isinstance(value, Literal):
                return template.format(value)
        return None

    @staticmethod
    def _dedupe_relations(relations: Iterable[Relation]) -> list[Relation]:
        seen: set[tuple[str, str, str, Optional[str]]] = set()
        out: list[Relation] = []
        for rel in relations:
            key = (rel.source, rel.target, rel.kind.value, rel.uri)
            if key in seen:
                continue
            seen.add(key)
            out.append(rel)
        return out

    # ------------------------------------------------------------------ #
    # Datatype properties
    # ------------------------------------------------------------------ #
    def _attach_datatype_properties(
        self,
        graph: Graph,
        ontology: Ontology,
        datatype_props: set[URIRef],
        class_uris: set[URIRef],
        restriction_datatypes: dict[URIRef, set[URIRef]],
    ) -> set[URIRef]:
        attached: set[URIRef] = set()

        def add(owner: URIRef, prop: URIRef) -> None:
            cls = ontology.classes.get(str(owner))
            if cls is None:
                return
            if any(existing.uri == str(prop) for existing in cls.datatype_properties):
                return
            range_uri, range_label = self._datatype_range(graph, prop)
            cls.datatype_properties.append(
                DatatypeProperty(
                    uri=str(prop),
                    label=self._label_for(prop),
                    curie=self._curie(prop),
                    range_label=range_label,
                    range_uri=range_uri,
                    comment=self._comment_for(prop),
                )
            )
            attached.add(prop)

        for prop in sorted(datatype_props, key=str):
            for term in graph.objects(prop, RDFS.domain):
                for domain in self._expand_class_expression(term):
                    if domain in class_uris:
                        add(domain, prop)

        for owner, props in restriction_datatypes.items():
            for prop in sorted(props, key=str):
                add(owner, prop)

        for cls in ontology.classes.values():
            cls.datatype_properties.sort(key=lambda p: p.label.lower())
        return attached

    def _datatype_range(
        self, graph: Graph, prop: URIRef
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (range uri, display label) or (None, None) if not declared.

        The parser never invents a datatype: a property with no declared range
        is shown by name only.
        """
        for term in graph.objects(prop, RDFS.range):
            if isinstance(term, URIRef):
                return str(term), self._curie(term)
            if isinstance(term, BNode):
                # e.g. owl:oneOf enumerations or datatype restrictions
                for member in graph.objects(term, OWL.onDatatype):
                    if isinstance(member, URIRef):
                        return str(member), self._curie(member)
        return None, None

    def _propagate_inherited_attributes(self, ontology: Ontology) -> None:
        """Copy superclass attributes down, tagged with their origin."""
        parents: dict[str, list[str]] = defaultdict(list)
        for rel in ontology.relations:
            if rel.kind is RelationKind.SUBCLASS_OF:
                parents[rel.source].append(rel.target)

        resolved: dict[str, list[DatatypeProperty]] = {}

        def inherited_for(uri: str, seen: frozenset[str]) -> list[DatatypeProperty]:
            if uri in resolved:
                return resolved[uri]
            if uri in seen:                       # cyclic subclass axioms
                return []
            collected: list[DatatypeProperty] = []
            for parent_uri in parents.get(uri, []):
                parent = ontology.classes.get(parent_uri)
                if parent is None:
                    continue
                for prop in parent.datatype_properties:
                    origin = prop.inherited_from or parent_uri
                    collected.append(
                        DatatypeProperty(
                            uri=prop.uri,
                            label=prop.label,
                            curie=prop.curie,
                            range_label=prop.range_label,
                            range_uri=prop.range_uri,
                            comment=prop.comment,
                            inherited_from=origin,
                        )
                    )
                collected.extend(inherited_for(parent_uri, seen | {uri}))
            resolved[uri] = collected
            return collected

        for uri, cls in ontology.classes.items():
            own = {p.uri for p in cls.datatype_properties}
            added: set[str] = set()
            for prop in inherited_for(uri, frozenset()):
                if prop.uri in own or prop.uri in added:
                    continue
                added.add(prop.uri)
                cls.datatype_properties.append(prop)
            cls.datatype_properties.sort(key=lambda p: (p.is_inherited, p.label.lower()))

    # ------------------------------------------------------------------ #
    # Class expressions
    # ------------------------------------------------------------------ #
    def _expand_class_expression(
        self, term: Optional[Node], *, follow_restrictions: bool = True
    ) -> list[URIRef]:
        """Unfold unions/intersections into the named classes they mention.

        ``follow_restrictions`` is off for ``rdfs:subClassOf``: the filler of an
        anonymous restriction is *not* a superclass, it is the other end of a
        property, and treating it as one invents a false hierarchy.
        """
        if term is None:
            return []
        if isinstance(term, URIRef):
            return [] if term in _IGNORED_CLASSES or self._is_datatype(term) else [term]
        if not isinstance(term, BNode):
            return []

        graph = self._graph
        out: list[URIRef] = []
        for predicate in (OWL.unionOf, OWL.intersectionOf):
            for collection in graph.objects(term, predicate):
                for member in self._collection_members(collection):
                    out.extend(
                        self._expand_class_expression(
                            member, follow_restrictions=follow_restrictions
                        )
                    )
        # A restriction used directly as a domain/range: use its filler.
        if follow_restrictions and (term, RDF.type, OWL.Restriction) in graph:
            filler, _ = self._restriction_filler(graph, term)
            if filler is not None and filler != term:
                out.extend(self._expand_class_expression(filler))
        return list(dict.fromkeys(out))

    def _collection_members(self, collection: Node) -> list[Node]:
        """Walk an RDF list without recursing on very long collections."""
        members: list[Node] = []
        graph = self._graph
        current = collection
        guard = 0
        while current and current != RDF.nil and guard < 5000:
            first = next(iter(graph.objects(current, RDF.first)), None)
            if first is not None:
                members.append(first)
            current = next(iter(graph.objects(current, RDF.rest)), None)
            guard += 1
        return members

    # ------------------------------------------------------------------ #
    # Labels, CURIEs, misc
    # ------------------------------------------------------------------ #
    def _is_datatype(self, term: Node) -> bool:
        if not isinstance(term, URIRef):
            return False
        text = str(term)
        return (
            text.startswith(str(XSD))
            or term in (RDFS.Literal, RDF.langString, RDF.PlainLiteral)
            or (self._graph is not None and (term, RDF.type, RDFS.Datatype) in self._graph)
        )

    def _literal_for(self, subject: Node, predicates: Iterable[URIRef]) -> Optional[str]:
        fallback: Optional[str] = None
        for predicate in predicates:
            for value in self._graph.objects(subject, predicate):
                if not isinstance(value, Literal):
                    continue
                language = value.language
                if language == self.preferred_language or language is None:
                    return str(value).strip()
                fallback = fallback or str(value).strip()
        return fallback

    def _label_for(self, term: Node) -> str:
        label = self._literal_for(term, _LABEL_PREDICATES)
        if label:
            return label
        return self._local_name(term)

    def _comment_for(self, term: Node) -> Optional[str]:
        return self._literal_for(term, _COMMENT_PREDICATES)

    @staticmethod
    def _local_name(term: Node) -> str:
        text = str(term)
        for separator in ("#", "/", ":"):
            if separator in text:
                candidate = text.rsplit(separator, 1)[-1]
                if candidate:
                    return candidate
        return text

    def _curie(self, term: Node) -> str:
        try:
            curie = self._graph.namespace_manager.normalizeUri(term)
        except Exception:  # noqa: BLE001 - normalizeUri is best-effort
            return str(term)
        return curie.strip("<>")

    def _ontology_title(self, graph: Graph) -> Optional[str]:
        for subject in graph.subjects(RDF.type, OWL.Ontology):
            title = self._literal_for(subject, _LABEL_PREDICATES)
            if title:
                return title
            return self._local_name(subject)
        return None


def parse_ontology(
    source: Union[str, bytes, Path],
    *,
    source_name: Optional[str] = None,
    include_inherited_attributes: bool = True,
) -> Ontology:
    """Convenience wrapper used by the app, the CLI and the tests."""
    parser = OntologyParser(include_inherited_attributes=include_inherited_attributes)
    if isinstance(source, Path):
        return parser.parse_file(source)
    if isinstance(source, bytes):
        return parser.parse_bytes(source, source_name=source_name)
    if isinstance(source, str) and "\n" not in source and Path(source).exists():
        return parser.parse_file(Path(source))
    return parser.parse_text(source, source_name=source_name)
