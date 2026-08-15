"""Design tokens.

One dictionary drives the whole product: the Streamlit shell reads it for its
chrome, and it is serialised into the exported HTML so the standalone file and
the in-app view are pixel-identical.  Changing a colour here changes it
everywhere.

Palette rationale
-----------------
Two carrier hues only — a cool blue for *things you can name* (classes) and a
warm ochre for *values* (datatype properties).  Blue/ochre stays separable
under deuteranopia and protanopia, and every distinction is additionally
carried by shape (rounded box vs diamond) or line style (solid vs dashed vs
dotted), so no meaning depends on colour alone.  Teal marks the current
selection and crimson marks a discovered path; both are used sparingly, on at
most a handful of elements at a time.
"""

from __future__ import annotations

from typing import Any

THEME: dict[str, Any] = {
    "ink": "#0F1D2A",
    "ink2": "#33475B",
    "muted": "#6B7C8C",
    "hairline": "#DEE5EB",
    "surface": "#FFFFFF",
    "surfaceAlt": "#F7F9FB",
    "canvas": "#F4F6F8",
    "canvasDot": "#DCE3E9",
    "accent": "#0E7C86",          # selection
    "path": "#C0405E",            # discovered path
    "warn": "#B4741E",
    "class": {
        "fill": "#DCE9F5",
        "border": "#2A6294",
        "font": "#12354F",
        "hoverFill": "#CFE1F2",
    },
    "datatype": {
        "fill": "#FAECD4",
        "border": "#B4741E",
        "font": "#6B4310",
        "hoverFill": "#F6E1BC",
    },
    "edge": {
        "object": "#8697A6",
        "objectLabel": "#4A5C6B",
        "subclass": "#8E86B8",
        "attribute": "#C9A26B",
        "dim": "#D5DDE3",
    },
}

NETWORK_OPTIONS: dict[str, Any] = {
    "class_node": {
        "shape": "box",
        "borderWidth": 1.6,
        "margin": {"top": 10, "bottom": 10, "left": 14, "right": 14},
        "font_size": 15,
        "shadow_size": 10,
    },
    "datatype_node": {
        "shape": "diamond",
        "size": 12,
        "borderWidth": 1.4,
        "font_size": 12,
    },
    "physics": {
        "solver": "forceAtlas2Based",
        "gravitationalConstant": -78,
        "centralGravity": 0.012,
        "springLength": 230,
        "springConstant": 0.07,
        "damping": 0.55,
        "avoidOverlap": 0.72,
        "stabilization_iterations": 320,
    },
    "layout": {
        # Attributes fan out on an arc away from the class's neighbours. The
        # radius grows with the number of attributes so labels never stack.
        "attribute_radius": 150,
        "attribute_radius_per_item": 11,
        "attribute_spread_degrees": 210,
        "attribute_min_spacing": 74,      # chord distance between neighbours
        "attribute_stagger": 38,          # every other one pushed out a row
        "attribute_max_radius": 520,
    },
}


def viewer_style() -> dict[str, Any]:
    """Everything the browser side needs, in one JSON-serialisable blob."""
    return {"theme": THEME, "network": NETWORK_OPTIONS}
