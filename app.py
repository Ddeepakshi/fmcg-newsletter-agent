"""Streamlit dashboard for the FMCG Deal Intelligence Agent (spec section 4/10)."""
import logging

import pandas as pd
import streamlit as st

import config
from src.pipeline import load_last_known_good, run_pipeline_safe

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="FMCG Deal Intelligence Agent", layout="wide")


def _init_state():
    if "summary" not in st.session_state:
        cached = load_last_known_good()
        st.session_state.summary = cached
        st.session_state.used_cache = cached is not None
        st.session_state.last_error = None


_init_state()

st.title("FMCG Deal Intelligence Agent")
st.caption(
    "Discovers recent FMCG M&A, investment, and funding news; de-duplicates, "
    "filters for relevance and credibility, and drafts a business newsletter."
)

with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Refresh Now", type="primary", use_container_width=True):
        with st.spinner("Running pipeline: ingest → clean → dedup → filter → score → extract → draft..."):
            try:
                summary, used_cache = run_pipeline_safe()
                st.session_state.summary = summary
                st.session_state.used_cache = used_cache
                st.session_state.last_error = None
            except Exception as exc:
                st.session_state.last_error = str(exc)
        st.rerun()

    st.divider()
    st.subheader("Filters (display only)")
    region_filter = st.multiselect("Region", ["India", "Global", "Other"], default=["India", "Global", "Other"])
    min_credibility = st.slider("Minimum credibility score", 0.0, 1.0, 0.0, 0.05)

    st.divider()
    st.caption(f"Recency window: last {config.RECENCY_DAYS} days (config.py)")
    st.caption(f"Dedup similarity threshold: {config.DEDUP_SIMILARITY_THRESHOLD}")
    st.caption(f"Credibility exclusion threshold: {config.CREDIBILITY_THRESHOLD}")
    if not config.GROQ_API_KEY:
        st.warning("GROQ_API_KEY not set — LLM stages (ambiguous relevance review, "
                   "extraction, newsletter drafting) will use their documented fallbacks.")

if st.session_state.last_error:
    st.error(f"Last live run failed: {st.session_state.last_error}")

summary = st.session_state.summary

if summary is None:
    st.info("No cached data yet. Click **Refresh Now** in the sidebar to run the pipeline for the first time.")
    st.stop()

if st.session_state.used_cache:
    st.warning("Showing last known good cached dataset (live run unavailable or not yet triggered).")

records = summary.get("records", [])
df = pd.DataFrame(records)
if not df.empty:
    df = df[df["region"].isin(region_filter)]
    df = df[df["credibility_score"].fillna(0) >= min_credibility]

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Raw fetched", summary.get("raw_count", 0))
col2.metric("After cleaning", summary.get("cleaned_count", 0))
col3.metric("After dedup", summary.get("after_dedup_count", 0))
col4.metric("Relevant", summary.get("relevant_count", 0))
col5.metric("Recent", summary.get("recent_count", 0))
col6.metric("Final (credible)", summary.get("final_count", 0))

st.caption(
    f"Run started: {summary.get('run_started_at', 'n/a')} · "
    f"completed: {summary.get('run_completed_at', 'n/a')}"
)

tab_newsletter, tab_dataset, tab_downloads = st.tabs(["📰 Newsletter", "📊 Dataset", "⬇️ Downloads"])

with tab_newsletter:
    if summary.get("newsletter_used_fallback"):
        st.info("Newsletter drafted via extractive fallback template (LLM unavailable/rate-limited).")
    st.markdown(summary.get("newsletter_markdown", "_No newsletter available._"))

with tab_dataset:
    st.dataframe(df, use_container_width=True, height=500)

with tab_downloads:
    output_paths = summary.get("output_paths", {})
    labels = {
        "csv": ("📄 Deals (CSV)", "text/csv"),
        "json": ("🧾 Deals (JSON)", "application/json"),
        "docx": ("📝 Newsletter (Word)", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "xlsx": ("📈 Deals (Excel)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "pptx": ("🖥️ Newsletter (PowerPoint)", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    }
    dl_cols = st.columns(len(labels))
    for i, (key, (label, mime)) in enumerate(labels.items()):
        path = output_paths.get(key)
        if not path:
            continue
        try:
            with open(path, "rb") as f:
                dl_cols[i].download_button(label, f.read(), file_name=path.split("/")[-1], mime=mime)
        except FileNotFoundError:
            dl_cols[i].caption(f"{label}: not generated yet")
