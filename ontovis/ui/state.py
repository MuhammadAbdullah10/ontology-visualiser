"""Session state for the Streamlit shell.

Parsing and rendering are cached on the *content* of the uploaded file, so
re-runs triggered by a slider or a checkbox never re-parse the ontology.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import streamlit as st

from ..export.html_exporter import render_html
from ..parsing.models import Ontology, OntologyParseError
from ..parsing.ontology_parser import OntologyParser

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "valuation.ttl"


@dataclass
class AppState:
    """Everything the shell needs to know between re-runs."""

    source_name: Optional[str] = None
    raw_bytes: Optional[bytes] = None
    ontology: Optional[Ontology] = None
    error: Optional[str] = None
    viewer_height: int = 860
    include_inherited: bool = True
    _html_cache: dict[str, str] = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return self.ontology is not None

    @property
    def digest(self) -> str:
        payload = (self.raw_bytes or b"") + str(self.include_inherited).encode()
        return hashlib.sha1(payload).hexdigest()


def get_state() -> AppState:
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState()
    return st.session_state.app_state


@st.cache_data(show_spinner=False)
def _parse_cached(data: bytes, source_name: str, include_inherited: bool) -> Ontology:
    parser = OntologyParser(include_inherited_attributes=include_inherited)
    return parser.parse_bytes(data, source_name=source_name)


def load_ontology(state: AppState, data: bytes, source_name: str) -> None:
    """Parse ``data`` into the state, converting failures into a friendly message."""
    state.raw_bytes = data
    state.source_name = source_name
    try:
        state.ontology = _parse_cached(data, source_name, state.include_inherited)
        state.error = None
    except OntologyParseError as exc:
        state.ontology = None
        state.error = str(exc)
    except Exception as exc:  # noqa: BLE001 - never leak a traceback to the user
        state.ontology = None
        state.error = (
            "Unable to parse ontology.\n\n"
            "Please check that the uploaded file is valid Turtle/RDF.\n\n"
            f"Details: {type(exc).__name__}: {exc}"
        )


def load_example(state: AppState) -> None:
    load_ontology(state, EXAMPLE_PATH.read_bytes(), EXAMPLE_PATH.name)


def viewer_html(state: AppState, *, embedded: bool) -> str:
    """Render (and memoise) the viewer for the current ontology."""
    if state.ontology is None:
        return ""
    key = f"{state.digest}:{embedded}"
    if key not in state._html_cache:
        state._html_cache.clear()
        state._html_cache[key] = render_html(state.ontology, embedded=embedded)
    return state._html_cache[key]
