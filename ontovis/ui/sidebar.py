"""The Streamlit sidebar: load a file, see what came out, take it away."""

from __future__ import annotations

import streamlit as st

from .state import AppState, load_example, load_ontology, viewer_html


def render_sidebar(state: AppState) -> None:
    with st.sidebar:
        st.markdown("### Ontology Visualiser")
        st.markdown(
            '<p class="ov-note">Load a Turtle file to explore its classes, '
            "relationships and attributes.</p>",
            unsafe_allow_html=True,
        )

        upload = st.file_uploader(
            "Upload a TTL file",
            type=["ttl", "owl", "rdf", "n3", "nt", "jsonld"],
            help="Turtle is the primary format; RDF/XML, N-Triples, N3 and JSON-LD also load.",
        )
        if upload is not None:
            data = upload.getvalue()
            if data != state.raw_bytes or upload.name != state.source_name:
                load_ontology(state, data, upload.name)

        if st.button("Load the example ontology", use_container_width=True):
            load_example(state)

        st.divider()
        _render_options(state)

        if state.loaded:
            st.divider()
            _render_statistics(state)
            st.divider()
            _render_export(state)

        st.divider()
        with st.expander("How to use it"):
            st.markdown(
                """
- **Click a class** to open its datatype properties; click again to close them.
- **Search** matches classes, object properties and datatype properties.
  Selecting a result zooms to it and highlights it.
- **Find path** traces how two classes connect through object properties and
  `rdfs:subClassOf`. Datatype properties are never used as routes.
- **Save HTML** gives you the same interactive graph as a single file that
  works offline in any browser.
                """
            )


def _render_options(state: AppState) -> None:
    st.markdown('<p class="ov-eyebrow">Options</p>', unsafe_allow_html=True)
    inherited = st.checkbox(
        "Include inherited attributes",
        value=state.include_inherited,
        help="Show datatype properties a class inherits from its superclasses, "
        "tagged with where they came from.",
    )
    if inherited != state.include_inherited:
        state.include_inherited = inherited
        if state.raw_bytes is not None and state.source_name is not None:
            load_ontology(state, state.raw_bytes, state.source_name)

    state.viewer_height = st.slider(
        "Viewer height (px)", min_value=560, max_value=1400, value=state.viewer_height, step=20
    )


def _render_statistics(state: AppState) -> None:
    stats = state.ontology.statistics
    st.markdown('<p class="ov-eyebrow">Ontology statistics</p>', unsafe_allow_html=True)
    rows = [
        ("Classes", stats.classes),
        ("Object properties", stats.object_properties),
        ("Datatype properties", stats.datatype_properties),
        ("Subclass relations", stats.subclass_relations),
        ("Total relationships", stats.total_relationships),
    ]
    st.markdown(
        "".join(f'<div class="ov-stat"><span>{name}</span><b>{value}</b></div>'
                for name, value in rows),
        unsafe_allow_html=True,
    )
    for warning in state.ontology.warnings:
        st.caption(warning)


def _render_export(state: AppState) -> None:
    st.markdown('<p class="ov-eyebrow">Export</p>', unsafe_allow_html=True)
    html = viewer_html(state, embedded=False)
    filename = (state.source_name or "ontology").rsplit(".", 1)[0] + "-visualisation.html"
    st.download_button(
        "Download interactive HTML",
        data=html.encode("utf-8"),
        file_name=filename,
        mime="text/html",
        use_container_width=True,
    )
    st.caption("One self-contained file: zoom, pan, expand, search and path finding all still work.")
