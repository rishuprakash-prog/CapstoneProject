# InsightAI — Turning Programme Data into Decisions

AI-powered web app that turns district-wise programme monitoring data (CSV/Excel) into
insights, district comparisons, prioritised actions and a downloadable review brief.
MVP use case: **School Health & Wellness Programme (SHWP)** monitoring data.

IIT Patna Generative AI Capstone Sprint 2026 · #IITPatnaCapstone

## 100% free stack

| Category | Tool | Cost |
|---|---|---|
| LLM / AI | Google AI Studio — Gemini API (free tier) | ₹0 |
| App / UI | Streamlit (Python) | ₹0 |
| Hosting | Streamlit Community Cloud | ₹0 |
| Database | Supabase free tier | ₹0 |
| Data processing | pandas, Plotly | ₹0 (open source) |
| API testing | Postman free (optional) | ₹0 |

## Features

1. **Data upload** — CSV / Excel, automatic column detection (district, block, school, month, indicators) with manual override
2. **AI data analysis** — automated insights and a watch list
3. **Natural language Q&A** — ask in English or Hindi
4. **District performance analysis** — comparison against the state average and an overall ranking
5. **Automated key findings** — rule-based, and they still work if the AI is unavailable
6. **Top-5 priority actions** — each with evidence, possible reasons, owner and timeline
7. **Review brief generator** — download as Word (.docx) or Markdown
8. **Interactive dashboard** — KPI cards, district bars, trends and a reporting-completeness heatmap
9. **History and traceability** — questions and insights saved in Supabase and linked to their dataset; a user can delete everything they stored

## System flow

```
Upload CSV/XLSX ──► Schema detection (loader.py)
                      │
                      ▼
            pandas analysis engine (analysis.py)
            averages · rankings · trends · completeness · missing-report streaks
                      │                          │
                      ▼                          ▼
          Dashboard + key findings      Aggregate context (district-level only)
                (app.py, Plotly)                 │
                                                 ▼
                                   Gemini reasoning layer (ai.py)
                                   Q&A · insights · top-5 actions · review brief
                                                 │
                         ┌───────────────────────┴───────────────┐
                         ▼                                       ▼
               Word/Markdown brief (report.py)        Supabase history (db.py)
```

**Design choice:** pandas calculates every number, and Gemini only interprets them. This keeps
the figures accurate (the AI does not invent numbers), keeps token usage inside the free
tier, and sends only district-level aggregates to the AI, never school-level raw data.

## Project structure

```
insightai/
├── app.py                  # Streamlit UI (6 pages)
├── src/
│   ├── loader.py           # CSV/Excel reading + column auto-mapping
│   ├── analysis.py         # deterministic analytics + AI context builder
│   ├── ai.py               # Gemini client, prompts, model fallback, rate-limit handling
│   ├── report.py           # Markdown -> Word review brief
│   └── db.py               # Supabase persistence (optional)
├── data/
│   ├── generate_sample.py  # synthetic SHWP dataset generator
│   └── shwp_sample.csv/.xlsx
├── supabase/schema.sql     # tables + RLS
└── .streamlit/             # theme + secrets template
```

## Run locally (Windows)

```powershell
cd insightai
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml   # then paste your keys
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### Get the free keys
1. **Gemini:** open https://aistudio.google.com/apikey, sign in with Google, click **Create API key**, and paste it as `GEMINI_API_KEY`. No card is needed.
2. **Supabase (optional):**
   1. Create a free project at https://supabase.com.
   2. Open **SQL Editor**, paste `supabase/schema.sql`, and click **Run**.
   3. Go to **Project Settings → API** and copy the Project URL into `SUPABASE_URL`.
   4. Copy the `service_role` or secret key into `SUPABASE_KEY`.

   The service key stays on the server. It is never sent to the browser. A free project pauses after 7 days without use, so open the dashboard once before your demo.

## Deploy free (Streamlit Community Cloud)
1. Create a free GitHub account and a new public repo. Upload the contents of the `insightai` folder. Do **not** upload `.venv` or `secrets.toml`.
2. Open https://share.streamlit.io, sign in with GitHub, click **Create app**, choose the repo, and set the main file to `app.py`.
3. Under **Advanced settings → Secrets**, paste the contents of your `secrets.toml`. Choose Python 3.12, then click **Deploy**.
4. You get a live URL like `https://insightai-xyz.streamlit.app`. Share it in your submission.

## Regenerate sample data
```powershell
.\.venv\Scripts\python.exe data\generate_sample.py
```
The data is synthetic: 12 Bihar districts × 3 blocks × 12 schools × 6 months (Apr–Sep 2026).
Some patterns are planted on purpose: low and declining reporting in Sitamarhi and Purnia,
a steady improvement in Nalanda, and some schools with 2+ consecutive missing reports.

## Privacy by design
- The app works on aggregate indicators. It needs no personal data.
- Only district-level summaries go to the AI. API keys stay server-side.
- The database stores only metadata, questions and AI outputs, not the raw file.
- Users can delete their stored history at any time from the History page.
- Every output shows its source dataset and the AI model used. AI interpretations are labelled for human verification.

## Demo script (3–5 min)
1. Problem: 30 seconds on data overload in monthly programme reviews.
2. Load the sample SHWP data and show the auto-detected columns.
3. Dashboard: KPI cards, district comparison, trend, completeness heatmap, missing schools.
4. Click **Generate AI insights**.
5. Ask InsightAI two questions, one in English and one in Hindi.
6. Open **Priority Actions** to show the top 5 with owners and timelines.
7. Open **Review Brief**, download the Word file, and open it.
8. Close with the impact: from days of preparation to minutes, and how it scales to nutrition, education and other programmes.
