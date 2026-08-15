"""Command line interface.

Examples
--------
Export a standalone visualisation::

    python -m ontovis.cli examples/valuation.ttl -o valuation.html

Print the statistics and a path without opening a browser::

    python -m ontovis.cli examples/valuation.ttl --stats
    python -m ontovis.cli examples/valuation.ttl --path Company ValuationMethod
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .export.html_exporter import write_html
from .graphmodel.path_finder import PathFinder
from .parsing.models import Ontology, OntologyParseError
from .parsing.ontology_parser import OntologyParser


def _normalise(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _resolve_class(ontology: Ontology, needle: str) -> Optional[str]:
    """Match a class by label, CURIE, local name or URI, ignoring punctuation."""
    target = _normalise(needle)
    for uri, cls in ontology.classes.items():
        candidates = {_normalise(cls.label), _normalise(cls.curie),
                      _normalise(uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1])}
        if target in candidates:
            return uri
    for uri, cls in ontology.classes.items():
        if target and target in _normalise(cls.label):
            return uri
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ontovis",
        description="Parse a TTL ontology and export an interactive HTML visualisation.",
    )
    parser.add_argument("ontology", type=Path, help="Path to a .ttl (or other RDF) file")
    parser.add_argument("-o", "--output", type=Path, help="Where to write the HTML export")
    parser.add_argument("--stats", action="store_true", help="Print ontology statistics")
    parser.add_argument(
        "--embed-vis", type=Path, metavar="VIS_JS",
        help="Inline a local vis-network.min.js so the export works with no network",
    )
    parser.add_argument(
        "--path", nargs=2, metavar=("FROM", "TO"),
        help="Print the shortest class-to-class path between two classes",
    )
    parser.add_argument(
        "--all-paths", action="store_true",
        help="With --path, list every simple route instead of the shortest one",
    )
    parser.add_argument(
        "--undirected", action="store_true",
        help="With --path, ignore relationship direction",
    )
    parser.add_argument(
        "--no-inherited", action="store_true",
        help="Do not copy superclass attributes down to subclasses",
    )
    args = parser.parse_args(argv)

    try:
        ontology = OntologyParser(
            include_inherited_attributes=not args.no_inherited
        ).parse_file(args.ontology)
    except OntologyParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.stats or not (args.output or args.path):
        stats = ontology.statistics
        print(f"Ontology:             {ontology.title or args.ontology.name}")
        print(f"Classes:              {stats.classes}")
        print(f"Object properties:    {stats.object_properties}")
        print(f"Datatype properties:  {stats.datatype_properties}")
        print(f"Subclass relations:   {stats.subclass_relations}")
        print(f"Total relationships:  {stats.total_relationships}")
        for warning in ontology.warnings:
            print(f"note: {warning}")

    if args.path:
        source = _resolve_class(ontology, args.path[0])
        target = _resolve_class(ontology, args.path[1])
        if not source or not target:
            missing = args.path[0] if not source else args.path[1]
            print(f"error: no class matching '{missing}'", file=sys.stderr)
            return 2
        finder = PathFinder(ontology, respect_direction=not args.undirected)
        labels = ontology.class_labels()
        if args.all_paths:
            routes = finder.all_paths(source, target)
            if not routes:
                print("No route found.")
            for index, route in enumerate(routes, start=1):
                print(f"\nRoute {index} ({route.length} hops)")
                print(route.as_text(labels))
        else:
            route = finder.shortest_path(source, target)
            print("\n" + (route.as_text(labels) if route else "No route found."))

    if args.output:
        destination = write_html(ontology, args.output, vis_library=args.embed_vis)
        print(f"\nWrote {destination} ({destination.stat().st_size / 1024:.0f} kB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
