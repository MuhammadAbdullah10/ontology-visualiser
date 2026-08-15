"""Renders the standalone interactive HTML.

There is exactly one viewer (``templates/viewer.html``).  The Streamlit app
embeds the *same* rendered string it offers for download, so "what you see" and
"what you export" cannot drift apart — the export is not a second, weaker
rendering path.

Rendering is a deliberate no-templating-engine affair: the file is a valid,
openable HTML document on its own, and three markers are substituted:

``__PAGE_TITLE__``     document title
``/*__CSS_TOKENS__*/`` CSS custom properties generated from styling.py
``/*__PAYLOAD__*/``    the assignment of the ontology payload as JSON
``/*__VIS_INLINE__*/`` an optional inlined copy of vis-network (offline exports)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..graphmodel.graph_builder import build_payload
from ..graphmodel.styling import THEME
from ..parsing.models import Ontology

TEMPLATE_PATH = Path(__file__).parent / "templates" / "viewer.html"

_TOKEN_MAP: dict[str, tuple[str, ...]] = {
    "--ink": ("ink",),
    "--ink-2": ("ink2",),
    "--muted": ("muted",),
    "--hairline": ("hairline",),
    "--surface": ("surface",),
    "--surface-alt": ("surfaceAlt",),
    "--canvas": ("canvas",),
    "--canvas-dot": ("canvasDot",),
    "--accent": ("accent",),
    "--path": ("path",),
    "--warn": ("warn",),
    "--class-fill": ("class", "fill"),
    "--class-border": ("class", "border"),
    "--class-font": ("class", "font"),
    "--dt-fill": ("datatype", "fill"),
    "--dt-border": ("datatype", "border"),
    "--dt-font": ("datatype", "font"),
    "--edge": ("edge", "object"),
    "--edge-subclass": ("edge", "subclass"),
    "--edge-attr": ("edge", "attribute"),
}


def _css_tokens() -> str:
    declarations = []
    for name, keys in _TOKEN_MAP.items():
        value: Any = THEME
        for key in keys:
            value = value[key]
        declarations.append(f"  {name}:{value};")
    return ":root{\n" + "\n".join(declarations) + "\n}"


def _json_payload(payload: dict[str, Any]) -> str:
    """JSON safe to drop inside a <script> element."""
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # `</script>` inside a string literal would close the tag early.
    return encoded.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render_html(
    ontology: Ontology,
    *,
    title: Optional[str] = None,
    embedded: bool = False,
    vis_library: Optional[Path] = None,
) -> str:
    """Return the complete, self-contained HTML document as a string.

    ``vis_library`` optionally points at a local ``vis-network.min.js``
    (standalone UMD build).  When given, the library is inlined and the export
    needs no network at all; otherwise the page fetches it from a CDN, with a
    same-folder ``vis-network.min.js`` as the last fallback.
    """
    payload = build_payload(ontology, title=title, embedded=embedded)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    page_title = f"{payload['meta']['title']} — Ontology Visualiser"
    library = ""
    if vis_library is not None:
        library = Path(vis_library).read_text(encoding="utf-8")
    return (
        template.replace("__PAGE_TITLE__", _escape_html(page_title))
        .replace("/*__VIS_INLINE__*/", library)
        .replace("/*__CSS_TOKENS__*/", _css_tokens())
        .replace(
            "/*__PAYLOAD__*/",
            "window.__ONTOLOGY_PAYLOAD__ = " + _json_payload(payload) + ";",
        )
    )


def write_html(
    ontology: Ontology,
    destination: Path,
    *,
    title: Optional[str] = None,
    vis_library: Optional[Path] = None,
) -> Path:
    """Write the standalone export to ``destination`` and return the path."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_html(ontology, title=title, vis_library=vis_library), encoding="utf-8"
    )
    return destination


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
