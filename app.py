"""Ontology Visualiser — Streamlit entry point.

Run with::

    streamlit run app.py

The Python layer parses the ontology and hands a fully rendered, self-contained
viewer to the browser.  The very same document is what the Download button
produces, which is why the export is not a degraded copy of the app.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from ontovis.ui.sidebar import render_sidebar
from ontovis.ui.state import get_state, viewer_html
from ontovis.ui.theme import apply_theme

st.set_page_config(
    page_title="Ontology Visualiser",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    apply_theme()
    state = get_state()
    render_sidebar(state)

    if state.error:
        st.error(state.error)
        return

    if not state.loaded:
        _render_empty_state()
        return

    if state.ontology.is_empty:
        st.warning(
            "The ontology was successfully parsed, but no visualisable classes or "
            "relationships were found. Check that it declares `owl:Class` or "
            "`rdfs:Class` resources."
        )

    _embed_viewer(viewer_html(state, embedded=True), state.viewer_height)


def _embed_viewer(html: str, height: int) -> None:
    """Embed the viewer, preferring the current API and degrading gracefully.

    Streamlit >= 1.60 ships ``st.iframe``; older releases only have
    ``components.html``. Both put the document in a sandboxed iframe, which is
    exactly what the viewer wants — it owns its whole page.
    """
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=False)


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="ov-empty">
          <h3>Start with a Turtle file</h3>
          <p>Upload a <code>.ttl</code> ontology in the sidebar, or load the bundled
          example, to draw its classes, object properties and attributes.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
