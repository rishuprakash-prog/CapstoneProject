"""Read CSV/Excel uploads and detect which columns hold geography, period and indicators."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

# Keyword hints used for automatic column mapping (matched against normalised names).
ROLE_HINTS = {
    "district": ["district", "dist", "zila", "jila"],
    "block": ["block", "taluk", "tehsil", "mandal"],
    "school": ["school_id", "udise", "school_code", "schoolid", "school", "facility", "institution"],
    "period": ["month", "period", "reporting_month", "date", "year_month"],
    "submitted": ["report_submitted", "submitted", "reported", "report_status"],
}


@dataclass
class Schema:
    district: str | None = None
    block: str | None = None
    school: str | None = None
    period: str | None = None
    submitted: str | None = None
    indicators: list[str] = field(default_factory=list)

    def problems(self) -> list[str]:
        issues = []
        if not self.district:
            issues.append("No district column selected.")
        if not self.period:
            issues.append("No month/period column selected — trends will be unavailable.")
        if not self.indicators:
            issues.append("No numeric indicator columns found.")
        return issues


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def list_sheets(data: bytes) -> list[str]:
    return pd.ExcelFile(io.BytesIO(data)).sheet_names


def read_file(name: str, data: bytes, sheet: str | None = None) -> pd.DataFrame:
    if name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _pick(columns: list[str], hints: list[str], used: set[str]) -> str | None:
    normed = {c: _norm(c) for c in columns if c not in used}
    for hint in hints:  # exact match first, then substring
        for col, n in normed.items():
            if n == hint:
                return col
    for hint in hints:
        for col, n in normed.items():
            if hint in n:
                return col
    return None


def detect_schema(df: pd.DataFrame) -> Schema:
    cols = list(df.columns)
    used: set[str] = set()
    schema = Schema()
    for role in ["submitted", "district", "block", "school", "period"]:
        col = _pick(cols, ROLE_HINTS[role], used)
        setattr(schema, role, col)
        if col:
            used.add(col)
    id_like = {c for c in cols if re.search(r"(^|_)(id|code|udise|pin)(_|$)", _norm(c))}
    schema.indicators = [
        c for c in cols
        if c not in used and c not in id_like and pd.api.types.is_numeric_dtype(df[c])
    ]
    return schema
