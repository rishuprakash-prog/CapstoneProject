"""InsightAI — AI-Powered Programme Data Insights & Action Assistant.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import ai as ai_mod
from src.analysis import (COMPLETENESS, COMPLETENESS_THRESHOLD, build_ai_context, below_average,
                          district_scores, district_table, district_trend, key_findings,
                          missing_streaks, prepare, sharpest_decline, state_trend, state_values)
from src.db import Store
from src.loader import Schema, detect_schema, list_sheets, read_file
from src.report import markdown_to_docx

APP_DIR = Path(__file__).parent
SAMPLE_FILE = APP_DIR / "data" / "shwp_sample.csv"
DEFAULT_PROGRAMME = "School Health & Wellness Programme (SHWP)"
EXAMPLE_QUESTIONS = [
    "Which districts are performing below the state average?",
    "What are the key trends in reporting over the last six months?",
    "Generate a summary of the top five priority issues for the monthly review meeting.",
    "Which districts have shown the sharpest decline since the last quarter?",
    "List schools with missing data for two consecutive reporting months.",
]
PAGES = ["🏠 Upload Data", "📊 Dashboard", "💬 Ask InsightAI", "🎯 Priority Actions", "📝 Review Brief", "🗂️ History"]

st.set_page_config(page_title="InsightAI — Programme Data Insights", page_icon="📊", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.hero h1 {margin-bottom: 0; font-size: 2.2rem;}
.hero p.tag {color: #5b6b7f; font-size: 1.1rem; margin-top: .2rem;}
.flow {display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; margin:.6rem 0 1rem;}
.flow span.step {background: rgba(31,78,121,.08); border:1px solid rgba(31,78,121,.25);
  border-radius: 999px; padding:.25rem .7rem; font-size:.85rem;}
.flow span.arrow {opacity:.5;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers

def secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - no secrets.toml present
        pass
    return os.environ.get(name, default)


ss = st.session_state
ss.setdefault("session_id", str(uuid.uuid4()))
ss.setdefault("chat", [])
ss.setdefault("outputs", {})
ss.setdefault("ai_cache", {})
ss.setdefault("page", PAGES[0])


@st.cache_resource
def get_store(url: str, key: str) -> Store:
    return Store(url, key)


store = get_store(secret("SUPABASE_URL"), secret("SUPABASE_KEY"))


def get_ai() -> ai_mod.GeminiClient | None:
    key = ss.get("user_gemini_key") or secret("GEMINI_API_KEY")
    if not key:
        return None
    models = [m.strip() for m in secret("GEMINI_MODEL").split(",") if m.strip()] or None
    if ss.get("_ai_key") != key:
        ss["_ai"] = ai_mod.GeminiClient(key, models)
        ss["_ai_key"] = key
    return ss["_ai"]


def fmt(value: float, metric: str) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:.1f}%" if "%" in metric else f"{value:.2f}"


def load_dataset(df: pd.DataFrame, name: str, schema: Schema | None = None) -> None:
    schema = schema or detect_schema(df)
    ss.df_raw, ss.schema, ss.file_name = df, schema, name
    problems = [p for p in schema.problems() if "district" in p or "indicator" in p]
    if problems:
        ss.pop("prep", None)
        return
    prep = prepare(df, schema)
    ss.prep = prep
    ss.table = district_table(prep)
    ss.state = state_values(prep)
    ss.findings = key_findings(prep)
    ss.context = build_ai_context(prep)
    ss.context_hash = hashlib.sha1(ss.context.encode()).hexdigest()[:12]
    ss.chat, ss.outputs = [], {}
    ss.dataset_id = store.save_dataset(ss.session_id, name, len(df), ss.table.shape[0], ", ".join(prep.periods))


def run_ai(kind: str, fn, *args, force: bool = False) -> str | None:
    """Call the AI with per-dataset caching (saves free-tier quota) and friendly errors."""
    ai = get_ai()
    if ai is None:
        st.warning("🔑 Gemini API key not set. Add it in the sidebar (free from aistudio.google.com).")
        return None
    lang = ss.get("language", "English")
    cache_key = (ss.context_hash, kind, lang) + tuple(str(a) for a in args)
    if not force and cache_key in ss.ai_cache:
        return ss.ai_cache[cache_key]
    try:
        with st.spinner("InsightAI is analysing the data…"):
            text = fn(ai, ss.context, *args, lang)
    except ai_mod.AIError as e:
        st.error(str(e))
        return None
    ss.ai_cache[cache_key] = text
    if kind != "qa":
        store.save_insight(ss.session_id, ss.get("dataset_id"), kind, text)
    return text


def need_data() -> bool:
    if "prep" not in ss:
        st.info("⬅️ First upload a dataset (or load the sample) on the **Upload Data** page.")
        if st.button("Load sample SHWP dataset", type="primary"):
            load_dataset(pd.read_csv(SAMPLE_FILE), SAMPLE_FILE.name)
            st.rerun()
        return True
    return False


def source_caption() -> None:
    model = getattr(ss.get("_ai"), "last_model", None)
    st.caption(f"Source: **{ss.file_name}** · figures computed with pandas · interpretation by "
               f"{model or 'Gemini'} — verify before official use.")


# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown("## 📊 InsightAI")
    st.caption("Turning Programme Data into Decisions.")
    page = st.radio("Navigate", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.radio("AI response language", ["English", "Hindi"], key="language", horizontal=True,
             format_func=lambda x: "हिंदी" if x == "Hindi" else x)

    st.markdown("**Status**")
    st.markdown(f"{'🟢' if 'prep' in ss else '⚪'} Dataset: {ss.get('file_name', 'not loaded')}")
    has_key = bool(ss.get("user_gemini_key") or secret("GEMINI_API_KEY"))
    st.markdown(f"{'🟢' if has_key else '🔴'} Gemini AI {'connected' if has_key else 'key missing'}")
    st.markdown(f"{'🟢' if store.enabled else '⚪'} Supabase {'saving history' if store.enabled else 'off (session only)'}")
    if not secret("GEMINI_API_KEY"):
        with st.expander("🔑 Use your own free Gemini key"):
            st.text_input("Gemini API key", type="password", key="user_gemini_key",
                          help="Get one free at https://aistudio.google.com/apikey — kept only in this session.")
    st.divider()
    st.caption("🔐 Aggregate data only — only district-level summaries are sent to the AI. "
               "No personal information is required.")


# ---------------------------------------------------------------- pages

def page_upload() -> None:
    st.markdown('<div class="hero"><h1>InsightAI</h1>'
                '<p class="tag">AI-Powered Programme Data Insights &amp; Action Assistant</p></div>',
                unsafe_allow_html=True)
    steps = ["📤 Upload", "🎛 Map indicators", "💬 Ask", "🧮 Analyse", "💡 Insights", "🎯 Actions", "📥 Brief"]
    st.markdown('<div class="flow">' + '<span class="arrow">➜</span>'.join(
        f'<span class="step">{s}</span>' for s in steps) + "</div>", unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        up = st.file_uploader("Upload district-wise programme data (CSV or Excel)", type=["csv", "xlsx", "xls"])
        if up is not None:
            data = up.getvalue()
            sheet = None
            if not up.name.lower().endswith(".csv"):
                sheets = list_sheets(data)
                sheet = st.selectbox("Sheet", sheets) if len(sheets) > 1 else sheets[0]
            token = f"{up.name}:{len(data)}:{sheet}"
            if ss.get("upload_token") != token:
                try:
                    load_dataset(read_file(up.name, data, sheet), up.name)
                    ss.upload_token = token
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not read the file: {e}")
    with right:
        with st.container(border=True):
            st.markdown("**No data handy?**")
            st.caption("Load a synthetic School Health & Wellness Programme dataset — "
                       "12 districts · 432 schools · 6 months (fictional, no personal data).")
            if st.button("Load sample SHWP dataset", type="primary", width="stretch"):
                load_dataset(pd.read_csv(SAMPLE_FILE), SAMPLE_FILE.name)
            st.download_button("Download sample file", SAMPLE_FILE.read_bytes(), SAMPLE_FILE.name,
                               "text/csv", width="stretch")

    if "df_raw" not in ss:
        return
    df, schema = ss.df_raw, ss.schema
    st.success(f"Loaded **{ss.file_name}** — {len(df):,} rows × {df.shape[1]} columns.")

    with st.expander("🎛 Column mapping (auto-detected — adjust if needed)", expanded="prep" not in ss):
        cols = [None] + list(df.columns)
        idx = lambda c: cols.index(c) if c in cols else 0  # noqa: E731
        c1, c2, c3, c4, c5 = st.columns(5)
        district = c1.selectbox("District *", cols, idx(schema.district))
        block = c2.selectbox("Block", cols, idx(schema.block))
        school = c3.selectbox("School / facility ID", cols, idx(schema.school))
        period = c4.selectbox("Month / period *", cols, idx(schema.period))
        submitted = c5.selectbox("Report submitted flag", cols, idx(schema.submitted))
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        indicators = st.multiselect("Indicator columns", numeric, [c for c in schema.indicators if c in numeric])
        if st.button("Apply mapping"):
            load_dataset(df, ss.file_name, Schema(district, block, school, period, submitted, indicators))
            st.rerun()

    for p in ss.schema.problems():
        st.warning(p)
    if "prep" in ss:
        prep = ss.prep
        st.markdown("#### Detected programme indicators")
        st.write(" · ".join(f"`{m}`" for m in prep.metric_names))
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Districts", ss.table.shape[0])
        k2.metric("Schools / units", prep.grid["school"].nunique() if prep.has_school else "—")
        k3.metric("Reporting periods", len(prep.periods))
        k4.metric("Overall reporting completeness", fmt(ss.state[COMPLETENESS], COMPLETENESS))
        st.dataframe(df.head(50), width="stretch", height=260)
        st.button("Continue to Dashboard ➜", type="primary", on_click=lambda: ss.update(page=PAGES[1]))


def page_dashboard() -> None:
    if need_data():
        return
    prep, table = ss.prep, ss.table
    st.title("📊 Programme Dashboard")
    source_caption()

    # KPI cards: latest period vs previous period
    latest = prep.periods[-1]
    prev = prep.periods[-2] if len(prep.periods) > 1 else None
    cur_v = state_values(prep, [latest])
    prev_v = state_values(prep, [prev]) if prev else None
    shown = prep.metric_names[:4] + ([COMPLETENESS] if COMPLETENESS not in prep.metric_names[:4] else [])
    st.markdown(f"##### State snapshot — {latest}" + (f" (vs {prev})" if prev else ""))
    for col, name in zip(st.columns(len(shown)), shown):
        delta = None if prev_v is None else cur_v[name] - prev_v[name]
        with col.container(border=True):
            st.metric(name, fmt(cur_v[name], name),
                      None if delta is None or pd.isna(delta) else f"{delta:+.1f}",
                      delta_color="normal" if prep.higher_is_better(name) else "inverse")

    st.markdown("### 🔍 Key findings")
    with st.container(border=True):
        for f in ss.findings:
            st.markdown(f"- {f}")
    if st.button("✨ Generate AI insights", type="primary"):
        ss.outputs["insights"] = run_ai("auto_insights", ai_mod.auto_insights)
    if ss.outputs.get("insights"):
        with st.container(border=True):
            st.markdown(ss.outputs["insights"])

    st.divider()
    f1, f2 = st.columns(2)
    metric = f1.selectbox("Indicator", prep.metric_names)
    period_choice = f2.selectbox("Period", ["All periods"] + prep.periods[::-1])
    periods = None if period_choice == "All periods" else [period_choice]
    t = district_table(prep, periods) if periods else table
    avg = state_values(prep, periods)[metric]
    hib = prep.higher_is_better(metric)

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown(f"#### District comparison — {metric}")
        d = t[[metric]].reset_index().rename(columns={"index": "District"}).sort_values(metric, ascending=hib)
        d["Status"] = ["Better than state" if ((v >= avg) if hib else (v <= avg)) else "Worse than state"
                       for v in d[metric]]
        fig = px.bar(d, x=metric, y="District", orientation="h", color="Status",
                     color_discrete_map={"Better than state": "#2E8B57", "Worse than state": "#D9534F"},
                     text=d[metric].round(1))
        fig.add_vline(x=avg, line_dash="dash", line_color="#1F4E79",
                      annotation_text=f"State avg {avg:.1f}", annotation_position="top")
        fig.update_layout(height=420, margin=dict(l=0, r=10, t=30, b=0), legend_title=None,
                          legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, width="stretch")
    with right:
        st.markdown("#### 🏅 Overall district ranking")
        scores = district_scores(t, prep).rename("Score (0-100)").to_frame()
        scores.insert(0, "Rank", range(1, len(scores) + 1))
        st.dataframe(scores, width="stretch", height=420,
                     column_config={"Score (0-100)": st.column_config.ProgressColumn(
                         min_value=0, max_value=100, format="%.0f")})

    if len(prep.periods) > 1:
        st.markdown(f"#### 📈 Trend over time — {metric}")
        dt = district_trend(prep, metric)
        worst = sharpest_decline(prep, metric)
        default = list(worst.index[:2]) + (list(worst.index[-1:]) if len(worst) > 2 else [])
        picks = st.multiselect("Compare districts", list(dt.index), default=default or list(dt.index[:3]))
        fig = go.Figure()
        st_tr = state_trend(prep)[metric]
        fig.add_scatter(x=st_tr.index, y=st_tr.values, name="State", mode="lines+markers",
                        line=dict(width=4, color="#1F4E79"))
        for dname in picks:
            fig.add_scatter(x=dt.columns, y=dt.loc[dname].values, name=dname, mode="lines+markers")
        fig.update_layout(height=380, margin=dict(l=0, r=10, t=10, b=0), yaxis_title=metric,
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")

        st.markdown("#### 🗓 Reporting completeness heatmap (%)")
        heat = district_trend(prep, COMPLETENESS)
        fig = px.imshow(heat.round(0), text_auto=True, aspect="auto", color_continuous_scale="RdYlGn",
                        zmin=50, zmax=100, labels=dict(color="%"))
        fig.update_layout(height=max(300, 28 * len(heat)), margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Threshold for adequate reporting: {COMPLETENESS_THRESHOLD:.0f}%.")

    gaps = missing_streaks(prep)
    st.markdown(f"#### 🏫 Schools with 2+ consecutive missing reports ({len(gaps)})")
    if len(gaps):
        st.dataframe(gaps, width="stretch", height=260, hide_index=True,
                     column_config={"still_missing": st.column_config.CheckboxColumn("Still missing")})
        st.download_button("Download list (CSV)", gaps.to_csv(index=False).encode(), "schools_missing_reports.csv")
    else:
        st.caption("None found 🎉")

    with st.expander("Full district indicator table"):
        st.dataframe(t.round(1), width="stretch")
        below = below_average(prep, metric, periods)
        st.caption(f"{len(below)} districts worse than state average on {metric}.")


def page_chat() -> None:
    if need_data():
        return
    st.title("💬 Ask InsightAI")
    st.caption("Ask questions about your data in plain language — English or Hindi.")
    source_caption()

    question = st.chat_input("e.g. Which districts are performing below the state average?")
    if not ss.chat:
        st.markdown("**Try one of these:**")
        for i, q in enumerate(EXAMPLE_QUESTIONS):
            if st.button(q, key=f"ex{i}"):
                question = q

    for turn in ss.chat:
        with st.chat_message(turn["role"], avatar="🧑‍💼" if turn["role"] == "user" else "📊"):
            st.markdown(turn["content"])

    if question:
        with st.chat_message("user", avatar="🧑‍💼"):
            st.markdown(question)
        with st.chat_message("assistant", avatar="📊"):
            answer = run_ai("qa", lambda ai, ctx, q, lang: ai_mod.answer_question(ai, ctx, q, ss.chat, lang),
                            question)
            if answer:
                st.markdown(answer)
        if answer:
            ss.chat += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
            store.save_query(ss.session_id, ss.get("dataset_id"), question, answer)

    if ss.chat and st.button("🧹 Clear conversation"):
        ss.chat = []
        st.rerun()


def page_actions() -> None:
    if need_data():
        return
    st.title("🎯 Priority Actions")
    st.caption("Top 5 issues to table at the next programme review, with evidence, owner and timeline.")
    source_caption()
    c1, c2 = st.columns([1, 1])
    if c1.button("Generate priority actions", type="primary"):
        ss.outputs["actions"] = run_ai("priority_actions", ai_mod.priority_actions)
    if ss.outputs.get("actions") and c2.button("↻ Regenerate"):
        ss.outputs["actions"] = run_ai("priority_actions", ai_mod.priority_actions, force=True)
    if ss.outputs.get("actions"):
        with st.container(border=True):
            st.markdown(ss.outputs["actions"])
        st.download_button("📥 Download (Markdown)", ss.outputs["actions"].encode("utf-8"), "priority_actions.md")


def page_brief() -> None:
    if need_data():
        return
    st.title("📝 Review Brief Generator")
    st.caption("A concise, meeting-ready brief for the monthly programme review — download as Word.")
    source_caption()
    c1, c2 = st.columns([2, 1])
    programme = c1.text_input("Programme name", DEFAULT_PROGRAMME)
    meeting = c2.date_input("Review meeting date", date.today())
    if st.button("Generate review brief", type="primary"):
        ss.outputs["brief"] = run_ai("review_brief", ai_mod.review_brief, programme, meeting.strftime("%d %B %Y"))
    brief = ss.outputs.get("brief")
    if brief:
        docx = markdown_to_docx(brief, ss.table, ss.file_name)
        d1, d2, _ = st.columns([1, 1, 2])
        d1.download_button("📥 Download Word (.docx)", docx, "InsightAI_Review_Brief.docx",
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           type="primary", width="stretch")
        d2.download_button("📥 Download Markdown", brief.encode("utf-8"), "InsightAI_Review_Brief.md",
                           width="stretch")
        with st.container(border=True):
            st.markdown(brief)


def page_history() -> None:
    st.title("🗂️ History")
    if not store.enabled:
        st.info("Supabase is not configured, so history is kept only for this browser session.")
        for turn in ss.chat:
            st.markdown(f"**{'You' if turn['role'] == 'user' else 'InsightAI'}:** {turn['content']}")
        for kind, text in ss.outputs.items():
            if text:
                with st.expander(kind):
                    st.markdown(text)
        return

    h = store.history(ss.session_id)
    st.caption("Everything below is stored in Supabase for this session and linked to its source dataset (traceability).")
    t1, t2, t3 = st.tabs([f"Questions ({len(h['queries'])})", f"Generated insights ({len(h['insights'])})",
                          f"Datasets ({len(h['datasets'])})"])
    with t1:
        for q in h["queries"]:
            with st.expander(f"{q['created_at'][:16].replace('T', ' ')} — {q['question']}"):
                st.markdown(q["answer"] or "")
    with t2:
        for i in h["insights"]:
            with st.expander(f"{i['created_at'][:16].replace('T', ' ')} — {i['kind']}"):
                st.markdown(i["content"])
    with t3:
        if h["datasets"]:
            st.dataframe(pd.DataFrame(h["datasets"])[["created_at", "file_name", "n_rows", "n_districts", "periods"]],
                         width="stretch", hide_index=True)
    st.divider()
    if st.button("🗑 Delete all my stored data", type="secondary"):
        store.delete_session(ss.session_id)
        st.success("Deleted all datasets, questions and insights stored for this session.")


{
    PAGES[0]: page_upload, PAGES[1]: page_dashboard, PAGES[2]: page_chat,
    PAGES[3]: page_actions, PAGES[4]: page_brief, PAGES[5]: page_history,
}[page]()
