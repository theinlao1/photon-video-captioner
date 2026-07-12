"""
Photon Video Captioner — demo web app (Streamlit).

IMPORTANT: this file only IMPORTS the existing pipeline (app/frames.py,
app/captioner.py, app/llm_client.py). It does not modify the agent in any way.
Deploy target: Streamlit Community Cloud. Main file path: streamlit_app.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# 0) Config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Photon Video Captioner", page_icon="🎬", layout="wide")

STYLES = ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]
STYLE_META = {
    "formal":            ("Formal",            "4D9BFF", "professional, factual"),
    "sarcastic":         ("Sarcastic",         "F5A623", "dry, ironic"),
    "humorous_tech":     ("Humorous · tech",   "27D6E6", "tech / code jokes"),
    "humorous_non_tech": ("Humorous · everyday","F96167", "everyday humor"),
}
ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# 1) Push secrets into env BEFORE calling the pipeline.
#    llm_client.py reads PRIMARY_*/FALLBACK_* from os.environ at call time.
# ---------------------------------------------------------------------------
_SECRET_KEYS = [
    "PRIMARY_BASE_URL", "PRIMARY_API_KEY", "PRIMARY_VISION_MODEL", "PRIMARY_TEXT_MODEL",
    "FALLBACK_BASE_URL", "FALLBACK_API_KEY", "FALLBACK_VISION_MODEL", "FALLBACK_TEXT_MODEL",
    "DISABLE_REASONING",
]
def _pull(mapping) -> None:
    for _k in _SECRET_KEYS:
        try:
            if _k in mapping and str(mapping[_k]).strip():
                os.environ[_k] = str(mapping[_k])
        except Exception:
            pass


try:
    _secrets = st.secrets
    _pull(_secrets)                       # top-level keys
    for _sk in list(_secrets.keys()):     # also look one level into any [section]
        _sv = _secrets[_sk]
        if hasattr(_sv, "keys"):
            _pull(_sv)
except Exception:
    # No secrets configured at all. Examples tab still works; live tab shows a hint.
    pass

LIVE_ENABLED = bool(os.environ.get("PRIMARY_API_KEY"))

# import the existing pipeline as a library (no changes to it)
sys.path.insert(0, str(ROOT / "app"))
_PIPELINE_OK = True
try:
    from frames import extract_frames          # type: ignore
    from captioner import caption_video        # type: ignore
except Exception as _e:                          # pragma: no cover
    _PIPELINE_OK = False
    _IMPORT_ERR = _e

# ---------------------------------------------------------------------------
# 2) Theme — Photon logo colors (electric blue / cyan / violet on near-black)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
      .stApp { background: #060912; }
      #MainMenu, footer { visibility: hidden; }
      .photon-title { font-size: 3.1rem; font-weight: 800; letter-spacing: .22em;
        color: #38B6FF; margin: 0; }
      .photon-sub { letter-spacing: .35em; color: #27D6E6; font-size: 1rem; margin: .1rem 0 0; }
      .photon-tag { color: #8FA3C8; font-size: 1.02rem; margin-top: .6rem; }
      .cap-card { background:#0E1728; border-radius:14px; padding:16px 18px; margin-bottom:14px; }
      .cap-head { display:flex; align-items:center; gap:8px; font-weight:700; font-size:.95rem; }
      .cap-dot { width:12px; height:12px; border-radius:50%; display:inline-block; }
      .cap-body { color:#E8EEF9; font-size:.98rem; margin-top:8px; line-height:1.45; }
      .chip { display:inline-block; border:1px solid; border-radius:10px; padding:4px 12px;
        margin:4px 8px 4px 0; color:#fff; font-size:.82rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 3) Header (logo + tagline)
# ---------------------------------------------------------------------------
logo = ROOT / "assets" / "photon_logo.png"
c1, c2 = st.columns([1, 3])
with c1:
    if logo.exists():
        st.image(str(logo), use_column_width=True)
with c2:
    if not logo.exists():
        st.markdown('<p class="photon-title">PHOTON</p>', unsafe_allow_html=True)
        st.markdown('<p class="photon-sub">VIDEO CAPTIONER</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="photon-tag">A multimodal agent that watches any short clip and '
        'captions it — in four different voices.</p>',
        unsafe_allow_html=True,
    )
    chips = "".join(
        f'<span class="chip" style="border-color:#{c}">● {STYLE_META[s][0]}</span>'
        for s, (lbl, c, _d) in ((s, STYLE_META[s]) for s in STYLES)
    )
    st.markdown(chips, unsafe_allow_html=True)

st.markdown("---")


def render_captions(captions: dict[str, str]) -> None:
    cols = st.columns(2)
    for i, s in enumerate(STYLES):
        lbl, color, _ = STYLE_META[s]
        text = captions.get(s, "—")
        with cols[i % 2]:
            st.markdown(
                f'<div class="cap-card">'
                f'<div class="cap-head" style="color:#{color}">'
                f'<span class="cap-dot" style="background:#{color}"></span>{lbl}</div>'
                f'<div class="cap-body">{text}</div></div>',
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# 4) Tabs — Examples (instant) + Try your own (live)
# ---------------------------------------------------------------------------
tab_ex, tab_live = st.tabs(["✨ Examples", "🎬 Try your own"])

with tab_ex:
    ex_path = ROOT / "examples_results.json"
    examples = json.loads(ex_path.read_text()) if ex_path.exists() else []
    if not examples:
        st.info("examples_results.json not found — add it next to streamlit_app.py.")
    for ex in examples:
        st.subheader(ex.get("title", ex["task_id"]))
        vc1, vc2 = st.columns([1, 1])
        with vc1:
            if ex.get("video_url"):
                st.video(ex["video_url"])
        with vc2:
            render_captions(ex["captions"])
        st.markdown("---")

with tab_live:
    if not _PIPELINE_OK:
        st.error(f"Pipeline import failed: {_IMPORT_ERR}")
    elif not LIVE_ENABLED:
        st.warning("Live mode is off (no API key in secrets). Add PRIMARY_* to enable.")
    else:
        st.caption("Paste a direct video URL (mp4). Generation takes ~30–60s.")
        url = st.text_input("Video URL", placeholder="https://.../clip.mp4")
        if st.button("Generate captions", type="primary") and url.strip():
            with st.spinner("Sampling frames → describing → restyling…"):
                try:
                    frames = extract_frames(url.strip())
                    try:
                        captions = caption_video(frames.paths, STYLES)
                    finally:
                        frames.cleanup()
                    render_captions(captions)
                except Exception as e:
                    st.error(f"Could not process this video: {e}")
