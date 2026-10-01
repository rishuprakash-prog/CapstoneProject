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
from src import automation, crt
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
.kpi-grid {display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:.75rem; margin:.4rem 0 1rem;}
.kpi {border:1px solid rgba(31,78,121,.18); border-radius:12px; padding:.75rem .9rem; background:#fff;
  border-left:5px solid var(--accent, #1F4E79); box-shadow:0 1px 3px rgba(0,0,0,.04);}
.kpi .kpi-head {display:flex; align-items:center; gap:.45rem; color:#5b6b7f; font-size:.82rem; line-height:1.2;}
.kpi .kpi-icon {font-size:1.35rem;}
.kpi .kpi-value {font-size:1.65rem; font-weight:700; color:#1B2733; margin-top:.25rem; white-space:nowrap;
  font-variant-numeric: tabular-nums;}
.kpi .kpi-sub {font-size:.75rem; color:#7a8899; margin-top:.1rem;}
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


def set_context(context: str) -> None:
    ss.context = context
    ss.context_hash = hashlib.sha1(context.encode()).hexdigest()[:12]


def load_dataset(df: pd.DataFrame, name: str, schema: Schema | None = None) -> None:
    ss.chat, ss.outputs = [], {}
    if schema is None and crt.is_crt(df):
        # Classroom Transaction export: dedicated session-level report instead of generic analysis
        data = crt.prepare_sessions(df)
        ss.mode, ss.crt, ss.df_raw, ss.file_name = "crt", data, df, name
        for k in ("prep", "schema", "crt_fy", "crt_district", "crt_class"):
            ss.pop(k, None)
        s = crt.filter_sessions(data, data.fin_years[-1:])
        ss.table = crt.district_report(s)
        set_context(crt.build_context(data, s, f"FY {', '.join(data.fin_years[-1:])}"))
        ss.dataset_id = store.save_dataset(ss.session_id, name, len(df), s["district"].nunique(),
                                           ", ".join(data.fin_years))
        return
    ss.mode = "generic"
    ss.pop("crt", None)
    schema = schema or detect_schema(df)
    ss.df_raw, ss.schema, ss.file_name = df, schema, name
    problems = [p for p in schema.problems() if "district" in p or "indicator" in p]
    if problems:
        ss.pop("prep", None)
        ss.pop("context", None)
        return
    prep = prepare(df, schema)
    ss.prep = prep
    ss.table = district_table(prep)
    ss.state = state_values(prep)
    ss.findings = key_findings(prep)
    set_context(build_ai_context(prep))
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
    if "prep" not in ss and "crt" not in ss:
        st.info("⬅️ First upload a dataset (or load the sample) on the **Upload Data** page.")
        if st.button("Load sample SHWP dataset", type="primary"):
            load_dataset(pd.read_csv(SAMPLE_FILE), SAMPLE_FILE.name)
            st.rerun()
        return True
    return False


def make_panel(kind: str, subject: str, body_md: str, docx: bytes | None = None,
               docx_filename: str | None = None) -> None:
    """'Email via Make.com' panel: sends the output to the Make webhook (Gmail/Drive in Make)."""
    url = secret("MAKE_WEBHOOK_URL")
    with st.expander("📧 Email via Make.com automation", expanded=False):
        if not url:
            st.caption("Make.com is not configured. Add MAKE_WEBHOOK_URL to secrets to enable email delivery.")
            return
        to = st.text_input("Recipient email", secret("MAKE_DEFAULT_RECIPIENT"), key=f"mk_to_{kind}")
        st.caption("Make.com scenario: Webhook → Gmail (with Word attachment) → Google Drive.")
        if st.button("📧 Send now", key=f"mk_send_{kind}", type="primary"):
            if not automation.valid_email(to):
                st.error("Please enter a valid email address.")
                return
            payload = automation.build_payload(
                kind, to, subject, body_md, ss.file_name, getattr(ss.get("_ai"), "last_model", None),
                docx, docx_filename, {"language": ss.get("language", "English")})
            with st.spinner("Sending to Make.com…"):
                ok, msg = automation.send_to_make(url, payload)
            (st.success if ok else st.error)(msg)
            if ok:
                store.save_insight(ss.session_id, ss.get("dataset_id"), "sent_via_make",
                                   f"{kind} → {to}: {subject}")


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
    st.markdown(f"{'🟢' if 'context' in ss else '⚪'} Dataset: {ss.get('file_name', 'not loaded')}")
    has_key = bool(ss.get("user_gemini_key") or secret("GEMINI_API_KEY"))
    st.markdown(f"{'🟢' if has_key else '🔴'} Gemini AI {'connected' if has_key else 'key missing'}")
    st.markdown(f"{'🟢' if store.enabled else '⚪'} Supabase {'saving history' if store.enabled else 'off (session only)'}")
    has_make = bool(secret("MAKE_WEBHOOK_URL"))
    st.markdown(f"{'🟢' if has_make else '⚪'} Make.com {'automation on' if has_make else 'not configured'}")
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
    df = ss.df_raw
    st.success(f"Loaded **{ss.file_name}** — {len(df):,} rows × {df.shape[1]} columns.")

    if ss.get("mode") == "crt":
        data = ss.crt
        st.info("📋 Detected a **Classroom Transaction (CRT) report**. Rows are de-duplicated into sessions "
                "(class-section × date × theme) so boys/girls are not double-counted across activities.")
        kpi_cards([
            ("📍", "Districts", indian(data.sessions["district"].nunique()), "in file", "#1F4E79"),
            ("🏫", "Schools", indian(data.sessions["school"].nunique()), "unique UDISE", "#2E8B57"),
            ("📚", "Sessions", indian(len(data.sessions)), f"from {indian(data.raw_rows)} activity rows", "#7B5EA7"),
            ("🎯", "Themes", indian(data.sessions["theme"].nunique()), "modules", "#E08E0B"),
            ("📅", "Financial years", " · ".join(data.fin_years), "", "#3A7CA5"),
        ])
        st.dataframe(df.head(50), width="stretch", height=260)
        st.button("Open CRT Report ➜", type="primary", on_click=lambda: ss.update(page=PAGES[1]))
        return

    schema = ss.schema

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


GENDER_COLORS = {"Boys": "#2F6DB5", "Girls": "#D6457A"}


def indian(n: float) -> str:
    """Format a number with Indian digit grouping: 245063 -> 2,45,063."""
    s = str(int(round(n)))
    neg, s = s.startswith("-"), s.lstrip("-")
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + groups) + "," + tail
    return ("-" if neg else "") + s


def kpi_cards(cards: list[tuple[str, str, str, str, str]]) -> None:
    """cards: (icon, label, value, sub-text, accent colour) rendered as a responsive grid."""
    html = "".join(
        f'<div class="kpi" style="--accent:{accent}"><div class="kpi-head"><span class="kpi-icon">{icon}</span>'
        f'<span>{label}</span></div><div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>'
        for icon, label, value, sub, accent in cards)
    st.markdown(f'<div class="kpi-grid">{html}</div>', unsafe_allow_html=True)


def _bar_height(n: int) -> int:
    return max(320, 26 * n + 80)


def page_crt_report() -> None:
    data: crt.CRTData = ss.crt
    st.title("📋 Classroom Transaction Report")
    st.caption(f"Source: **{ss.file_name}** · weekly school health & wellness sessions · "
               "unit = session (class-section × date × theme)")

    sessions = data.sessions
    f1, f2, f3, f4 = st.columns([1.8, 2, 1.5, 1.3])
    fys = f1.multiselect("Financial year", data.fin_years, default=data.fin_years[-1:], key="crt_fy")
    districts = f2.multiselect("District", sorted(sessions["district"].unique()), key="crt_district",
                               placeholder="All districts")
    classes = f3.multiselect("Class", sorted(sessions["class"].unique(), key=lambda c: (len(str(c)), str(c))),
                             key="crt_class", placeholder="All classes")
    f4.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
    drop_out = f4.toggle("Exclude outliers", key="crt_outliers",
                         help=f"Hide sessions with 0 participants or more than {crt.OUTLIER_LIMIT} "
                              "(likely data-entry errors).")
    s = crt.filter_sessions(data, fys, districts, classes, drop_out)
    if s.empty:
        st.warning("No sessions match these filters.")
        return

    filters = (f"FY {', '.join(fys) or 'all'}; districts: {', '.join(districts) or 'all'}; "
               f"classes: {', '.join(classes) or 'all'}; outliers {'excluded' if drop_out else 'included'}")
    dist = crt.district_report(s)
    themes = crt.theme_report(s)
    weekly = crt.weekly_report(s)
    fy_tab = crt.fy_summary(s)
    ss.table = dist
    set_context(crt.build_context(data, s, filters))  # AI pages answer on exactly this filtered view

    # KPI strip
    boys, girls = int(s["boys"].sum()), int(s["girls"].sum())
    n_schools, n_sessions = s["school"].nunique(), len(s)
    girls_pct = 100 * girls / max(boys + girls, 1)
    kpi_cards([
        ("📍", "Districts", indian(s["district"].nunique()), "reporting", "#1F4E79"),
        ("🗺️", "Blocks", indian(s["block"].nunique()), "reporting", "#3A7CA5"),
        ("🏫", "Schools reported", indian(n_schools), f"{n_sessions / max(n_schools, 1):.1f} sessions / school", "#2E8B57"),
        ("📚", "Sessions held", indian(n_sessions), f"{s['week'].nunique()} weeks", "#7B5EA7"),
        ("👦", "Boys participated", indian(boys), f"avg {s['boys'].mean():.1f} / session", GENDER_COLORS["Boys"]),
        ("👧", "Girls participated", indian(girls), f"avg {s['girls'].mean():.1f} / session", GENDER_COLORS["Girls"]),
        ("⚖️", "Girls share", f"{girls_pct:.1f}%", f"boys {100 - girls_pct:.1f}%", "#E08E0B"),
    ])

    sheets = {"FY Summary": fy_tab, "District Report": dist, "Theme Report": themes, "Weekly Report": weekly,
              "District x Theme": crt.district_theme_matrix(s),
              "Week x Theme": crt.weekly_theme(s).pivot_table(index="Week", columns="Theme",
                                                              values=["Boys", "Girls"], aggfunc="sum", fill_value=0),
              "Data Quality": crt.data_quality(data, s).set_index("Check")}
    st.download_button("📥 Download full report (Excel with charts)",
                       crt.excel_report(sheets, "Classroom Transaction Report"),
                       f"CRT_Report_{'_'.join(fys) or 'all'}.xlsx", type="primary")

    t1, t2, t3, t4, t5, t6 = st.tabs(["🏫 District Report", "🎯 Theme-wise", "📅 Weekly Sessions",
                                      "🗺 District × Theme", "📆 Financial Year", "✅ Data Quality"])
    plot_dist = dist.drop(index="STATE TOTAL", errors="ignore").reset_index()

    with t1:
        st.markdown("#### Schools reported and boys/girls participation per district")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            d = plot_dist.sort_values("Schools Reported")
            fig = px.bar(d, x="Schools Reported", y="District", orientation="h", text="Schools Reported",
                         color_discrete_sequence=["#1F4E79"], title="Number of schools reported")
            fig.update_layout(height=_bar_height(len(d)), margin=dict(l=0, r=10, t=40, b=0))
            st.plotly_chart(fig, width="stretch")
        with c2:
            d = plot_dist.sort_values("Schools Reported").melt(
                id_vars="District", value_vars=["Avg Boys / Session", "Avg Girls / Session"],
                var_name="Gender", value_name="Average per session")
            d["Gender"] = d["Gender"].str.split().str[1]
            fig = px.bar(d, x="Average per session", y="District", color="Gender", orientation="h",
                         barmode="group", color_discrete_map=GENDER_COLORS, text="Average per session",
                         title="Average boys & girls per session")
            fig.update_layout(height=_bar_height(len(plot_dist)), margin=dict(l=0, r=10, t=40, b=0),
                              legend=dict(orientation="h", y=1.02, x=0.6))
            st.plotly_chart(fig, width="stretch")
        st.dataframe(dist, width="stretch", height=min(40 + 35 * len(dist), 700),
                     column_config={"Girls %": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("Avg / Session = mean boys (or girls) present per session. Boys/Girls totals count "
                   "session attendances, not unique students.")

    with t2:
        st.markdown("#### Theme-wise boys and girls participation in weekly sessions")
        c1, c2 = st.columns([2, 1], gap="large")
        with c1:
            d = themes.reset_index().melt(id_vars="Theme (Module)", value_vars=["Boys", "Girls"],
                                          var_name="Gender", value_name="Participants")
            fig = px.bar(d, x="Participants", y="Theme (Module)", color="Gender", orientation="h",
                         barmode="group", color_discrete_map=GENDER_COLORS, text="Participants",
                         title="Participants by theme")
            fig.update_layout(height=_bar_height(2 * len(themes)), margin=dict(l=0, r=10, t=40, b=0),
                              yaxis=dict(categoryorder="total ascending"), legend=dict(orientation="h", y=1.02, x=0.6))
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig = px.pie(names=["Boys", "Girls"], values=[boys, girls], hole=0.55, title="Overall gender split",
                         color=["Boys", "Girls"], color_discrete_map=GENDER_COLORS)
            fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, width="stretch")
            fig = px.bar(themes.reset_index().sort_values("Sessions"), x="Sessions", y="Theme (Module)",
                         orientation="h", title="Sessions per theme", color_discrete_sequence=["#1F4E79"])
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), yaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        st.dataframe(themes, width="stretch",
                     column_config={"Girls %": st.column_config.NumberColumn(format="%.1f%%")})

    with t3:
        st.markdown("#### Weekly session participation")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            d = weekly.melt(id_vars=["Financial Year", "Week"], value_vars=["Boys", "Girls"],
                            var_name="Gender", value_name="Participants")
            d["Week label"] = d["Financial Year"].str[2:4] + "-" + d["Financial Year"].str[-2:] + " W" + d["Week"].astype(str)
            fig = px.line(d, x="Week label", y="Participants", color="Gender", markers=True,
                          color_discrete_map=GENDER_COLORS, title="Boys & girls participated per week")
            fig.update_layout(height=380, margin=dict(l=0, r=10, t=40, b=0), xaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        with c2:
            gender = st.radio("Show", ["Girls", "Boys"], horizontal=True, key="wk_gender")
            wt = crt.weekly_theme(s)
            fig = px.bar(wt, x="Week", y=gender, color="Theme", title=f"Theme-wise {gender.lower()} per week")
            fig.update_layout(height=380, margin=dict(l=0, r=10, t=40, b=0), legend=dict(font=dict(size=9)),
                              barmode="stack")
            st.plotly_chart(fig, width="stretch")
        st.dataframe(weekly, width="stretch", hide_index=True,
                     column_config={"Girls %": st.column_config.NumberColumn(format="%.1f%%")})
        with st.expander("Week × theme table (boys / girls)"):
            st.dataframe(sheets["Week x Theme"], width="stretch")

    with t4:
        metric = st.radio("Value", ["Sessions", "Participants (boys + girls)"], horizontal=True, key="dt_val")
        m = crt.district_theme_matrix(s, "sessions" if metric == "Sessions" else "participants")
        fig = px.imshow(m, text_auto=True, aspect="auto", color_continuous_scale="Blues",
                        title=f"{metric} by district and theme")
        fig.update_layout(height=max(380, 26 * len(m) + 160), margin=dict(l=0, r=0, t=40, b=0),
                          xaxis=dict(tickangle=-35))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(m, width="stretch")

    with t5:
        c1, c2 = st.columns([1, 1], gap="large")
        with c1:
            d = fy_tab.reset_index().melt(id_vars="Financial Year", value_vars=["Boys", "Girls"],
                                          var_name="Gender", value_name="Participants")
            fig = px.bar(d, x="Financial Year", y="Participants", color="Gender", barmode="group",
                         color_discrete_map=GENDER_COLORS, text="Participants", title="Participation by financial year")
            fig.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, width="stretch")
        with c2:
            st.dataframe(fy_tab.T, width="stretch")
        st.caption("Tip: select several financial years in the filter above to compare them.")

    with t6:
        st.dataframe(crt.data_quality(data, s), width="stretch", hide_index=True)
        st.caption("Each CRT row is an activity; a session repeats once per activity with identical counts. "
                   "InsightAI keeps one row per session (highest reported count) before computing totals.")

    st.divider()
    if st.button("✨ Generate AI summary of this report", type="primary"):
        ss.outputs["insights"] = run_ai("auto_insights", ai_mod.auto_insights)
    if ss.outputs.get("insights"):
        with st.container(border=True):
            st.markdown(ss.outputs["insights"])
        make_panel("ai_summary", f"InsightAI — CRT Report AI Summary ({filters})", ss.outputs["insights"])


def page_dashboard() -> None:
    if need_data():
        return
    if ss.get("mode") == "crt":
        page_crt_report()
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
        make_panel("priority_actions", f"InsightAI — Top 5 Priority Actions ({ss.file_name})", ss.outputs["actions"])


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
        make_panel("review_brief", f"{programme} — Review Brief ({meeting.strftime('%d %b %Y')})", brief,
                   docx, "InsightAI_Review_Brief.docx")
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
