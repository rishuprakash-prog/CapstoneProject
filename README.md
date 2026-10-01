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

## Classroom Transaction (CRT) report

When the uploaded file is a **Classroom Transaction export**, InsightAI switches to a dedicated
report. It detects this from columns such as `District`, `UDISE`, `BoysP`, `GirlsP`, `Module`,
`FinYear` and `Weak`.

**De-duplication:** each CRT row is one *activity*. A session repeats once per activity, with the
same boys/girls counts each time. The report therefore first collapses the data to one row per
session (UDISE × class × section × date × theme) and computes totals from that, so participants
are not double-counted.

**Filters:** financial year, district, class, and an option to exclude sessions with zero or
implausibly high counts.

| Tab | Graphs | Table |
|---|---|---|
| District Report | Schools reported per district; average boys vs girls per session | Blocks, schools reported, sessions, boys, girls, averages, girls %, state total |
| Theme-wise | Boys vs girls by theme; gender split; sessions per theme | Theme-wise schools, sessions, boys, girls, girls % |
| Weekly Sessions | Weekly boys/girls trend; theme-wise participation per week | Week-wise schools, sessions, boys, girls |
| District × Theme | Heatmap (sessions or participants) | District × theme matrix |
| Financial Year | Boys/girls by FY | FY summary |
| Data Quality | — | Raw rows, duplicates removed, zero and outlier sessions |

The full report downloads as **Excel with native charts**. The AI summary, Q&A and review brief
always use the currently filtered view.

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

## Automation with Make.com (free)

The AI summary, Priority Actions and Review Brief pages each have an **📧 Email via Make.com** panel.
It sends the output to a Make **Custom Webhook**, and Make emails it through Gmail with a Word file
attached. Every send includes a Word file. The request is `multipart/form-data`: the text fields are
form fields, and the Word document is a real file field called `attachment`. Because Make receives a
real file, it can pass it straight to Gmail, with no `toBinary()` conversion.

**Set up the scenario (tested end to end):**
1. Sign up at https://www.make.com (free plan) and click **Create a new scenario**.
2. Add **Webhooks → Custom webhook**. Choose *Custom webhook*, not *Custom mailhook*. Click **Add**, name it `InsightAI`, and leave API keys empty.
3. Copy the `https://hook.<region>.make.com/...` URL into `.streamlit/secrets.toml` as `MAKE_WEBHOOK_URL`, then restart the app.
4. On the webhook module, click **Detect new values** (shown as *Redetermine data structure* in older UI). While it is listening, send one email from the app, so Make learns the fields, including `attachment`.
5. Add **Gmail → Send an email** and connect your Google account. Map the fields:
   - **To:** `recipient_email`
   - **Subject:** `subject`
   - **Body type:** Raw HTML. **Content:** `body_html`
   - **Attachments → Add attachment:** File name `docx_filename`, Data `attachment → data`
6. Optional: add **Google Drive → Upload a file**, using the same file name and data, to keep an archive.
7. Save the scenario and turn **Immediately as data arrives** ON.

**Fields sent:** `kind` (review_brief, priority_actions, ai_summary), `recipient_email`, `subject`,
`body_markdown`, `body_html`, `has_attachment`, `docx_filename`, `source_file`, `model`,
`generated_at`, `language`, plus the file field `attachment`.

## API testing with Postman (free)

Import `postman/InsightAI.postman_collection.json` into Postman. Set the collection variables
`gemini_api_key`, `make_webhook_url` and `test_email`, then run the collection. It has three requests:
1. **Gemini: List models.** Checks that the configured model is available for your key.
2. **Gemini: Generate insight.** Sends sample district data and checks that the answer names the right district.
3. **Make.com: Send test report.** Checks that the webhook accepts the payload with status 200 or 202.

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
