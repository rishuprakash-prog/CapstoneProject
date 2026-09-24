"""Deterministic analysis engine.

All numbers shown to the user or sent to the AI come from here (pandas), so the AI only
interprets figures and never has to calculate them.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .loader import Schema

COMPLETENESS = "Reporting Completeness (%)"
COMPLETENESS_THRESHOLD = 85.0
YES_VALUES = {"yes", "y", "true", "1", "submitted", "reported", "done"}


@dataclass
class Metric:
    name: str
    num: str
    den: str | None = None  # ratio metric: 100 * sum(num) / sum(den); otherwise mean(num)
    higher_is_better: bool = True


@dataclass
class Prepared:
    rows: pd.DataFrame  # one row per submitted/received record, standard column names
    grid: pd.DataFrame  # one row per *expected* report: district, block, school, period, submitted
    metrics: list[Metric]
    periods: list[str]
    has_school: bool

    @property
    def metric_names(self) -> list[str]:
        return [m.name for m in self.metrics] + [COMPLETENESS]

    def higher_is_better(self, name: str) -> bool:
        for m in self.metrics:
            if m.name == name:
                return m.higher_is_better
        return True


# ---------------------------------------------------------------- preparation

def _find(cols: list[str], *must: str, exclude: str | None = None) -> str | None:
    for c in cols:
        low = c.lower()
        if all(k in low for k in must) and not (exclude and exclude in low):
            return c
    return None


def build_metrics(indicators: list[str]) -> list[Metric]:
    """Derive meaningful programme KPIs when known SHWP columns exist; fall back to means."""
    enrolled = _find(indicators, "enrol")
    screened = _find(indicators, "screen")
    anaemia = _find(indicators, "anaemia") or _find(indicators, "anemia")
    referred = _find(indicators, "referr", exclude="complet")
    completed = _find(indicators, "referr", "complet")
    sessions = _find(indicators, "session")

    metrics: list[Metric] = []
    if enrolled and screened:
        metrics.append(Metric("Screening Coverage (%)", screened, enrolled))
    if referred and completed:
        metrics.append(Metric("Referral Completion (%)", completed, referred))
    if anaemia and screened:
        metrics.append(Metric("Anaemia Prevalence (%)", anaemia, screened, higher_is_better=False))
    if sessions:
        metrics.append(Metric("Health Sessions per School", sessions))

    used = {enrolled, screened, anaemia, referred, completed, sessions}
    for col in indicators:
        if col not in used:
            metrics.append(Metric(f"Avg {col.replace('_', ' ')}", col))
    return metrics


def _to_period(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.notna().mean() > 0.9:
        return parsed.dt.to_period("M").astype(str)
    return series.astype(str)


def prepare(df: pd.DataFrame, schema: Schema) -> Prepared:
    out = pd.DataFrame(index=df.index)
    out["district"] = df[schema.district].astype(str).str.strip()
    out["block"] = df[schema.block].astype(str).str.strip() if schema.block else ""
    out["school"] = df[schema.school].astype(str).str.strip() if schema.school else out.index.astype(str)
    out["period"] = _to_period(df[schema.period]) if schema.period else "All"
    for col in schema.indicators:
        out[col] = pd.to_numeric(df[col], errors="coerce")

    if schema.submitted:
        out["submitted"] = df[schema.submitted].astype(str).str.strip().str.lower().isin(YES_VALUES)
    else:
        out["submitted"] = out[schema.indicators].notna().any(axis=1)

    periods = sorted(out["period"].unique().tolist())

    if schema.school:
        # Build the full school x period grid so that *absent* rows also count as missing.
        schools = out.drop_duplicates("school")[["district", "block", "school"]]
        full = schools.merge(pd.DataFrame({"period": periods}), how="cross")
        got = out.groupby(["school", "period"], as_index=False)["submitted"].max()
        grid = full.merge(got, on=["school", "period"], how="left")
        grid["submitted"] = grid["submitted"].fillna(False).astype(bool)
    else:
        grid = out[["district", "block", "school", "period", "submitted"]].copy()

    return Prepared(out, grid, build_metrics(schema.indicators), periods, bool(schema.school))


# ---------------------------------------------------------------- core metrics

def _metric_value(frame: pd.DataFrame, m: Metric) -> float:
    sub = frame[frame["submitted"]]
    if m.den:
        den = sub[m.den].sum()
        return float(100 * sub[m.num].sum() / den) if den else np.nan
    return float(sub[m.num].mean()) if len(sub) else np.nan


def _completeness(grid: pd.DataFrame) -> float:
    return float(100 * grid["submitted"].mean()) if len(grid) else np.nan


def _values(prep: Prepared, rows: pd.DataFrame, grid: pd.DataFrame) -> dict[str, float]:
    vals = {m.name: _metric_value(rows, m) for m in prep.metrics}
    vals[COMPLETENESS] = _completeness(grid)
    return vals


def _filter(prep: Prepared, periods: list[str] | None):
    if not periods:
        return prep.rows, prep.grid
    return prep.rows[prep.rows["period"].isin(periods)], prep.grid[prep.grid["period"].isin(periods)]


def state_values(prep: Prepared, periods: list[str] | None = None) -> pd.Series:
    rows, grid = _filter(prep, periods)
    return pd.Series(_values(prep, rows, grid))


def district_table(prep: Prepared, periods: list[str] | None = None) -> pd.DataFrame:
    rows, grid = _filter(prep, periods)
    data = {
        d: _values(prep, rows[rows["district"] == d], grid[grid["district"] == d])
        for d in sorted(grid["district"].unique())
    }
    return pd.DataFrame.from_dict(data, orient="index")


def state_trend(prep: Prepared) -> pd.DataFrame:
    return pd.DataFrame({p: _values(prep, *_filter(prep, [p])) for p in prep.periods}).T


def district_trend(prep: Prepared, metric: str) -> pd.DataFrame:
    """District x period table for one metric."""
    return pd.DataFrame({p: district_table(prep, [p])[metric] for p in prep.periods})


def district_scores(table: pd.DataFrame, prep: Prepared) -> pd.Series:
    """Composite 0-100 score: average direction-adjusted percentile rank across all metrics."""
    ranks = []
    for col in table.columns:
        r = table[col].rank(pct=True, ascending=prep.higher_is_better(col))
        ranks.append(r)
    return (pd.concat(ranks, axis=1).mean(axis=1) * 100).round(1).sort_values(ascending=False)


def below_average(prep: Prepared, metric: str, periods: list[str] | None = None) -> pd.DataFrame:
    table = district_table(prep, periods)
    avg = state_values(prep, periods)[metric]
    worse = table[metric] < avg if prep.higher_is_better(metric) else table[metric] > avg
    res = table.loc[worse, [metric]].copy()
    res["State Average"] = avg
    res["Gap"] = res[metric] - avg
    return res.sort_values("Gap", ascending=prep.higher_is_better(metric))


def split_periods(prep: Prepared) -> tuple[list[str], list[str]]:
    """Recent window (last up to 3 periods) vs the window just before it."""
    n = min(3, len(prep.periods) // 2)
    if n == 0:
        return [], []
    return prep.periods[-n:], prep.periods[-2 * n:-n]


def period_change(prep: Prepared) -> pd.DataFrame:
    """Recent-window minus previous-window value, per district and metric."""
    recent, previous = split_periods(prep)
    if not recent:
        return pd.DataFrame()
    return district_table(prep, recent) - district_table(prep, previous)


def sharpest_decline(prep: Prepared, metric: str) -> pd.Series:
    change = period_change(prep)
    if change.empty:
        return pd.Series(dtype=float)
    # "decline" means getting worse, which is a rise for lower-is-better metrics
    signed = change[metric] if prep.higher_is_better(metric) else -change[metric]
    return signed.sort_values()


def missing_streaks(prep: Prepared, min_months: int = 2) -> pd.DataFrame:
    """Schools whose reports were missing for >= min_months consecutive periods."""
    if not prep.has_school or len(prep.periods) < min_months:
        return pd.DataFrame(columns=["district", "block", "school", "longest_gap", "missing_months", "still_missing"])
    order = {p: i for i, p in enumerate(prep.periods)}
    records = []
    for (district, block, school), g in prep.grid.groupby(["district", "block", "school"]):
        g = g.sort_values("period", key=lambda s: s.map(order))
        best, run, months = 0, 0, []
        for p, ok in zip(g["period"], g["submitted"]):
            run = 0 if ok else run + 1
            best = max(best, run)
            if not ok:
                months.append(p)
        if best >= min_months:
            records.append({
                "district": district, "block": block, "school": school, "longest_gap": best,
                "missing_months": ", ".join(months), "still_missing": not bool(g["submitted"].iloc[-1]),
            })
    res = pd.DataFrame(records, columns=["district", "block", "school", "longest_gap", "missing_months", "still_missing"])
    return res.sort_values(["longest_gap", "district"], ascending=[False, True]).reset_index(drop=True)


# ---------------------------------------------------------------- rule-based findings

def key_findings(prep: Prepared) -> list[str]:
    """Plain-language findings computed without AI (always available, even offline)."""
    out: list[str] = []
    table = district_table(prep)
    state = state_values(prep)

    low_rep = table[table[COMPLETENESS] < COMPLETENESS_THRESHOLD][COMPLETENESS].sort_values()
    if len(low_rep):
        names = ", ".join(f"{d} ({v:.0f}%)" for d, v in low_rep.items())
        out.append(f"**{len(low_rep)} district(s) below the {COMPLETENESS_THRESHOLD:.0f}% reporting threshold:** {names}.")

    if prep.metrics:
        m = prep.metrics[0].name
        below = below_average(prep, m)
        if len(below):
            out.append(f"**{len(below)} of {len(table)} districts are worse than the state average** on {m} "
                       f"(state: {state[m]:.1f}); weakest is {below.index[0]} ({below[m].iloc[0]:.1f}).")

    recent, previous = split_periods(prep)
    if recent:
        window = f"{recent[0]}–{recent[-1]} vs {previous[0]}–{previous[-1]}"
        for m in [x.name for x in prep.metrics[:2]] + [COMPLETENESS]:
            dec = sharpest_decline(prep, m)
            if len(dec) and dec.iloc[0] < 0:
                out.append(f"**Sharpest decline in {m}:** {dec.index[0]} ({dec.iloc[0]:+.1f} pts, {window}).")
        if prep.metrics:
            m = prep.metrics[0].name
            dec = sharpest_decline(prep, m)
            if len(dec) and dec.iloc[-1] > 0:
                out.append(f"**Most improved on {m}:** {dec.index[-1]} ({dec.iloc[-1]:+.1f} pts, {window}).")

    gaps = missing_streaks(prep)
    if len(gaps):
        still = int(gaps["still_missing"].sum())
        worst = gaps["district"].value_counts().head(3)
        spread = ", ".join(f"{d} ({n})" for d, n in worst.items())
        out.append(f"**{len(gaps)} schools missed 2+ consecutive monthly reports** ({still} still not reporting); "
                   f"most affected: {spread}.")

    scores = district_scores(table, prep)
    if len(scores) >= 2:
        out.append(f"**Top performer overall:** {scores.index[0]} (score {scores.iloc[0]:.0f}/100). "
                   f"**Lowest overall:** {scores.index[-1]} ({scores.iloc[-1]:.0f}/100).")
    return out


# ---------------------------------------------------------------- AI context

def _csv(df: pd.DataFrame) -> str:
    return df.round(1).to_csv()


def build_ai_context(prep: Prepared, max_trend_metrics: int = 4, max_periods: int = 6) -> str:
    """Compact, aggregate-only summary of the dataset for the LLM (no school-level indicator values)."""
    table = district_table(prep)
    state = state_values(prep)
    periods = prep.periods[-max_periods:]
    parts = [
        "## Dataset overview",
        f"Districts: {table.shape[0]}; expected reports (school x month): {len(prep.grid)}; "
        f"periods: {', '.join(prep.periods)}.",
        "Metric direction: " + "; ".join(
            f"{n} ({'higher' if prep.higher_is_better(n) else 'lower'} is better)" for n in prep.metric_names),
        f"Reporting completeness threshold: {COMPLETENESS_THRESHOLD:.0f}%.",
        "## State values (all periods)",
        state.round(1).to_csv(header=False),
        "## District values (all periods)",
        _csv(table),
        "## District composite score (0-100, higher = better overall)",
        district_scores(table, prep).to_csv(header=False),
        "## State trend by period",
        _csv(state_trend(prep).loc[periods]),
    ]
    names = [m.name for m in prep.metrics[:max_trend_metrics]] + [COMPLETENESS]
    for name in names:
        parts +=[f"## District trend: {name}", _csv(district_trend(prep, name)[periods])]

    recent, previous = split_periods(prep)
    if recent:
        parts += [f"## Change: recent ({', '.join(recent)}) minus previous ({', '.join(previous)})",
                  _csv(period_change(prep))]

    gaps = missing_streaks(prep)
    parts.append(f"## Schools with 2+ consecutive missing reports: {len(gaps)}")
    if len(gaps):
        parts += ["By district:", gaps["district"].value_counts().to_csv(header=False),
                  "Longest gaps (first 25):", gaps.head(25).to_csv(index=False)]
    return "\n".join(parts)
