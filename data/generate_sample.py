"""Generate a realistic *synthetic* School Health & Wellness Programme (SHWP) dataset.

The data is fictional and contains no personal information. Patterns are planted on
purpose so the demo has something to find:
  - Sitamarhi and Purnia: low reporting and declining performance
  - Nalanda: steadily improving
  - A handful of schools with 2+ consecutive months of missing reports

Run:  python data/generate_sample.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(2026)
OUT_DIR = Path(__file__).parent

MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]

# district: (base quality 0-1, monthly trend, reporting probability)
DISTRICTS = {
    "Patna": (0.88, 0.005, 0.97),
    "Gaya": (0.78, 0.000, 0.92),
    "Muzaffarpur": (0.80, 0.004, 0.94),
    "Bhagalpur": (0.74, -0.004, 0.90),
    "Darbhanga": (0.70, 0.002, 0.88),
    "Purnia": (0.72, -0.030, 0.78),
    "Nalanda": (0.66, 0.040, 0.95),
    "Saran": (0.83, 0.000, 0.96),
    "Vaishali": (0.79, 0.003, 0.93),
    "Begusarai": (0.76, -0.002, 0.91),
    "Rohtas": (0.85, 0.002, 0.95),
    "Sitamarhi": (0.62, -0.035, 0.70),
}
BLOCKS_PER_DISTRICT = 3
SCHOOLS_PER_BLOCK = 12


def clip(x, lo=0.0, hi=1.0):
    return float(min(hi, max(lo, x)))


def build() -> pd.DataFrame:
    rows = []
    for d_idx, (district, (quality, trend, report_p)) in enumerate(DISTRICTS.items()):
        for b in range(1, BLOCKS_PER_DISTRICT + 1):
            block = f"{district} Block-{b}"
            for s in range(1, SCHOOLS_PER_BLOCK + 1):
                school_id = f"BR{d_idx + 1:02d}{b}{s:03d}"
                school_name = f"Govt. School {district[:3].upper()}-{b}{s:02d}"
                enrolled = int(RNG.integers(180, 900))
                school_q = quality + RNG.normal(0, 0.05)
                # ~4% of schools stop reporting for a stretch of consecutive months
                gap_start = RNG.integers(1, len(MONTHS) - 1) if RNG.random() < 0.04 else None
                gap_len = int(RNG.integers(2, 4)) if gap_start is not None else 0

                for m_idx, month in enumerate(MONTHS):
                    in_gap = gap_start is not None and gap_start <= m_idx < gap_start + gap_len
                    decay = 0.02 * m_idx if trend < -0.02 else 0.0  # reporting worsens in declining districts
                    submitted = (not in_gap) and RNG.random() < clip(report_p - decay)
                    row = {
                        "State": "Bihar",
                        "District": district,
                        "Block": block,
                        "School_ID": school_id,
                        "School_Name": school_name,
                        "Month": month,
                        "Students_Enrolled": enrolled,
                        "Report_Submitted": "Yes" if submitted else "No",
                    }
                    if submitted:
                        q = clip(school_q + trend * m_idx + RNG.normal(0, 0.03), 0.2, 0.99)
                        screened = int(enrolled * clip(q + RNG.normal(0, 0.02), 0.1, 1.0))
                        anaemia = int(screened * clip(0.34 - 0.18 * q + RNG.normal(0, 0.02), 0.03, 0.6))
                        referrals = int(anaemia * clip(0.55 + RNG.normal(0, 0.05)) + screened * 0.02)
                        completed = int(referrals * clip(q - 0.1 + RNG.normal(0, 0.05)))
                        sessions = int(max(0, round(4 * q + RNG.normal(0, 0.7))))
                        ambassadors = int(max(0, round(2 * q + RNG.normal(0, 0.5))))
                        row.update(
                            Students_Screened=screened,
                            Anaemia_Cases=anaemia,
                            Referrals_Made=referrals,
                            Referrals_Completed=completed,
                            Health_Sessions_Held=sessions,
                            Wellness_Ambassadors_Trained=ambassadors,
                        )
                    rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT_DIR / "shwp_sample.csv", index=False)
    df.to_excel(OUT_DIR / "shwp_sample.xlsx", index=False, sheet_name="SHWP_Monitoring")
    print(f"Wrote {len(df):,} rows, {df['School_ID'].nunique()} schools, "
          f"{df['District'].nunique()} districts -> {OUT_DIR}")
