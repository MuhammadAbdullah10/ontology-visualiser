"""Streamlit chrome.

The shell is intentionally quiet: the graph is the product, so the Python page
around it keeps to upload, status and download, styled with the same tokens the
viewer uses.
"""

from __future__ import annotations

import streamlit as st

from ..graphmodel.styling import THEME

_CSS = """
<style>
  .block-container {{ padding: 0.9rem 1.1rem 0.6rem; max-width: 100%; }}
  header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
  #MainMenu, footer {{ visibility: hidden; }}
  section[data-testid="stSidebar"] {{ background: {surface_alt}; border-right: 1px solid {hairline}; }}
  section[data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}
  h1, h2, h3, h4 {{ color: {ink}; letter-spacing: -0.01em; }}
  .ov-eyebrow {{
    font-size: 10.5px; font-weight: 650; letter-spacing: .1em; text-transform: uppercase;
    color: {muted}; margin: 0 0 6px;
  }}
  .ov-note {{ font-size: 12.5px; color: {ink2}; line-height: 1.5; }}
  .ov-stat {{
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 4px 0; border-bottom: 1px dotted {hairline}; font-size: 13px; color: {ink2};
  }}
  .ov-stat b {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: {ink}; }}
  .ov-empty {{
    border: 1px dashed {hairline}; border-radius: 10px; padding: 34px 28px; text-align: center;
    background: {canvas};
  }}
  .ov-empty h3 {{ margin: 0 0 6px; font-size: 17px; }}
  .ov-empty p {{ margin: 0 auto; max-width: 52ch; color: {ink2}; font-size: 13.5px; }}
  .stDownloadButton button, .stButton button {{ border-radius: 8px; font-size: 13px; }}
</style>
"""


def apply_theme() -> None:
    st.markdown(
        _CSS.format(
            ink=THEME["ink"],
            ink2=THEME["ink2"],
            muted=THEME["muted"],
            hairline=THEME["hairline"],
            surface_alt=THEME["surfaceAlt"],
            canvas=THEME["canvas"],
        ),
        unsafe_allow_html=True,
    )
