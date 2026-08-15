"""Turns an :class:`Ontology` into the payload consumed by the viewer.

The payload is intentionally *semantic*, not visual: it lists classes,
relations and attributes, and lets the browser decide which vis-network nodes
to instantiate.  That is what makes lazy expansion cheap — attribute nodes only
come into existence when a class is opened, so a 400-class ontology with 900
datatype properties starts life as 400 nodes, not 1300.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..parsing.models import Ontology, RelationKind
from .styling import viewer_style


def build_payload(
    ontology: Ontology,
    *,
    title: Optional[str] = None,
    embedded: bool = False,
) -> dict[str, Any]:
    """Assemble the complete viewer payload."""
    classes = [cls.to_dict() for cls in ontology.sorted_classes()]
    relations = [rel.to_dict() for rel in ontology.relations]

    return {
        "meta": {
            "title": title or ontology.title or "Ontology",
            "source": ontology.source_name or "ontology.ttl",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "namespaces": ontology.namespaces,
            "embedded": embedded,
            "warnings": ontology.warnings,
        },
        "stats": ontology.statistics.to_dict(),
        "classes": classes,
        "relations": relations,
        "searchIndex": build_search_index(ontology),
        "unattachedProperties": [p.to_dict() for p in ontology.unattached_properties],
        "style": viewer_style(),
    }


def build_search_index(ontology: Ontology) -> list[dict[str, Any]]:
    """Flat, pre-computed index so search stays instant in the browser.

    Each entry carries the *action target* the viewer needs: a class URI, a
    relation id, or an attribute node id plus its owning class.
    """
    entries: list[dict[str, Any]] = []

    for cls in ontology.sorted_classes():
        entries.append(
            {
                "kind": "class",
                "label": cls.label,
                "curie": cls.curie,
                "detail": cls.comment or cls.curie,
                "target": cls.uri,
            }
        )

    for rel in sorted(ontology.distinct_object_properties(), key=lambda r: r.label.lower()):
        endpoints = [
            r for r in ontology.relations
            if r.kind is RelationKind.OBJECT_PROPERTY and r.uri == rel.uri
        ]
        detail = " · ".join(
            f"{_label(ontology, r.source)} → {_label(ontology, r.target)}"
            for r in endpoints[:3]
        )
        entries.append(
            {
                "kind": "objectProperty",
                "label": rel.label,
                "curie": rel.curie or "",
                "detail": detail,
                "target": rel.uri,
                "edgeIds": [r.id for r in endpoints],
            }
        )

    seen_attributes: set[tuple[str, str]] = set()
    for cls in ontology.sorted_classes():
        for prop in cls.datatype_properties:
            if prop.is_inherited:
                continue
            key = (cls.uri, prop.uri)
            if key in seen_attributes:
                continue
            seen_attributes.add(key)
            entries.append(
                {
                    "kind": "datatypeProperty",
                    "label": prop.label,
                    "curie": prop.curie,
                    "detail": f"{cls.label}"
                    + (f" · {prop.range_label}" if prop.range_label else ""),
                    "target": f"{cls.uri}|dt|{prop.uri}",
                    "owner": cls.uri,
                }
            )

    for prop in ontology.unattached_properties:
        entries.append(
            {
                "kind": "objectProperty" if prop.kind == "object" else "datatypeProperty",
                "label": prop.label,
                "curie": prop.curie,
                "detail": prop.reason,
                "target": None,
                "unattached": True,
            }
        )
    return entries


def _label(ontology: Ontology, uri: str) -> str:
    cls = ontology.classes.get(uri)
    return cls.label if cls else uri


def class_choices(ontology: Ontology) -> list[tuple[str, str]]:
    """(uri, label) pairs for path-finding dropdowns, sorted by label."""
    return [(cls.uri, cls.label) for cls in ontology.sorted_classes()]
