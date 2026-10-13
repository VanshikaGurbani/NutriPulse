"""Global CSS. Generic selectors and our own class names only: no data-testid hooks, because Streamlit
does not promise to keep them. Colours that Streamlit already themes (text, background, primary) come from
.streamlit/config.toml instead of CSS."""
import streamlit as st

CSS = """
<style>
/* readable measure on desktop; full width on phones */
.stMainBlockContainer, .block-container { max-width: 1180px; padding-top: 1.2rem; padding-bottom: 2rem; }
@media (max-width: 640px) { .stMainBlockContainer, .block-container { padding-left: 0.9rem; padding-right: 0.9rem; } }

/* visible keyboard focus everywhere */
:focus-visible { outline: 3px solid #1a56db !important; outline-offset: 2px; }

.np-header { display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; margin: 0 0 .5rem; }
.np-header h1 { font-size: 1.5rem; margin: 0; padding: 0; line-height: 1.2; }
.np-muted { color: #3b4a3f; font-size: .9rem; margin: 0 0 .4rem; line-height: 1.4; }

.np-strip { background: #fff; border: 1px solid #b9cdbd; border-radius: 12px; padding: .7rem .9rem; margin: .4rem 0 .8rem; }
.np-strip-top { display: flex; justify-content: space-between; align-items: baseline; gap: .6rem; flex-wrap: wrap; }
.np-strip-main { font-size: 1.15rem; font-weight: 700; }
.np-strip-note { font-size: .9rem; color: #2f3d33; }
.np-strip-macros { font-size: .9rem; color: #2f3d33; margin-top: .35rem; display: flex; gap: .3rem 1rem; flex-wrap: wrap; }

.np-bar { background: #dfe8e0; border-radius: 99px; height: 12px; overflow: hidden; margin: .35rem 0; }
.np-bar > span { display: block; height: 100%; border-radius: 99px; }
.np-prog { margin: .45rem 0; }
.np-prog-row { display: flex; justify-content: space-between; gap: .5rem; font-size: .92rem; }

.np-macrobar { display: flex; height: 30px; border-radius: 8px; overflow: hidden; margin: .3rem 0 .5rem; }
.np-seg { display: flex; align-items: center; justify-content: center; font-size: .85rem; font-weight: 700; color: #111; min-width: 3px; }
.np-legend { list-style: none; padding: 0; margin: 0 0 .4rem; font-size: .92rem; }
.np-legend li { margin: .15rem 0; }
.np-swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: .45rem; vertical-align: -1px; }

.np-table { width: 100%; border-collapse: collapse; font-size: .92rem; margin: .4rem 0; }
.np-table caption { text-align: left; font-weight: 700; padding: .2rem 0; }
.np-table th { text-align: left; font-weight: 600; color: #2f3d33; border-bottom: 2px solid #b9cdbd; padding: .3rem .4rem; }
.np-table td { padding: .4rem; border-bottom: 1px solid #dfe8e0; vertical-align: top; }
.np-table td.num, .np-table th.num { text-align: right; white-space: nowrap; }
.np-scroll { overflow-x: auto; }

.np-badge { display: inline-block; padding: .05rem .5rem; border-radius: 99px; font-size: .82rem; font-weight: 600; border: 1px solid; white-space: nowrap; }
.np-good { background: #e3f4ea; color: #0b4a2a; border-color: #7fbf9a; }
.np-warn { background: #fff4d6; color: #5c4200; border-color: #d9b44a; }
.np-bad { background: #fde7e7; color: #7a1010; border-color: #d98a8a; }
.np-neutral { background: #eef1ee; color: #2f3d33; border-color: #b9c4bb; }

.np-meal { display: flex; justify-content: space-between; font-weight: 700; background: #e4eee6; border-radius: 8px; padding: .35rem .6rem; margin: .7rem 0 .2rem; }
.np-entry { display: flex; justify-content: space-between; gap: .6rem; padding: .3rem .6rem; border-bottom: 1px solid #dfe8e0; font-size: .95rem; }
.np-entry small { color: #3b4a3f; }

.np-tip { background: #fff; border: 1px solid #b9cdbd; border-radius: 10px; padding: .5rem .7rem; margin: .4rem 0; }
.np-empty { text-align: center; padding: 1rem .5rem; color: #2f3d33; }
.np-grade { display: inline-flex; width: 72px; height: 72px; border-radius: 50%; align-items: center; justify-content: center;
            font-size: 2.2rem; font-weight: 800; color: #fff; }
.np-step { font-size: .9rem; color: #2f3d33; margin-bottom: .2rem; }
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
