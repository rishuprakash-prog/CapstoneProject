# InsightAI — Turning Programme Data into Decisions

**IIT Patna Generative AI Capstone Sprint 2026** · #IITPatnaCapstone

| | |
|---|---|
| **Live app** | https://capstoneproject-n9k7dyiappt5htaaj2nppxl.streamlit.app/ |
| **Code** | https://github.com/rishuprakash-prog/CapstoneProject/tree/feature/insightai-mvp |
| **Domain** | AI for Governance & Public Health |
| **MVP use case** | School Health & Wellness Programme (SHWP), Bihar |

---

## 1. Problem

Public health programmes collect a large amount of monitoring data, but they use little of it.
District teams export Excel sheets every week and compare districts by hand. Review notes are
prepared days before each monthly review, from data that is already stale. The data contains
early-warning signals, but nobody surfaces them in time.

The Classroom Transaction (CRT) export shows the problem clearly. It has **18,853 rows**, with one
row per *activity*. The same session repeats once for every activity done in it, so adding up the
boys and girls columns over-counts attendance by about 65% (7,15,700 instead of 4,33,328 for
FY 2026-27). Most people who open the file do not notice this.

## 2. Solution

InsightAI is a web app. A programme manager uploads the monitoring file and gets the following,
in minutes:

- A **decision-ready report**: schools reporting per district, average boys and girls per session, theme-wise and weekly participation, and a financial-year view, shown as charts and tables together
- **AI interpretation**: what the numbers show, why it may be happening, and what to do next
- **Plain-language Q&A** in English or Hindi
- **Top-5 priority actions**, each with evidence, owner and timeline
- A **meeting-ready review brief** as a Word file, which can be **emailed automatically** through Make.com

## 3. System flow

```
 Upload CSV / Excel
        │
        ▼
 Detect format ──► CRT export? ──► de-duplicate activity rows into sessions
        │                         (UDISE × class × section × date × theme)
        ▼
 pandas analysis engine — every number is computed here, deterministically
        │
        ├──► Dashboard / CRT report (Plotly charts + tables, Excel export)
        │
        ├──► Aggregate context (district-level only) ──► Gemini
        │                                                ├─ AI summary
        │                                                ├─ Q&A (English / हिंदी)
        │                                                ├─ Top-5 priority actions
        │                                                └─ Review brief
        │
        ├──► Word report (python-docx)
        │        └──► Make.com webhook ──► Gmail (Word attached)
        │
        └──► Supabase: datasets, questions, insights (history + traceability)
```

## 4. Tools used (approved categories)

| Category | Tool | What it does in InsightAI |
|---|---|---|
| LLMs & AI APIs | **Google AI Studio — Gemini** | Insight generation, Q&A, priority actions, review brief |
| Automation | **Make.com** | Webhook → Gmail delivery of reports with the Word file attached |
| Database & Backend | **Supabase** | Stores session history: dataset metadata, questions, AI outputs; RLS enabled |
| Testing & Integration | **Postman** | Collection that tests the Gemini endpoints and the Make webhook |
| UI & Hosting | Streamlit + Streamlit Community Cloud | Dashboard, report and chat UI; free public hosting |
| Data processing | Python, pandas, Plotly | De-duplication, aggregation, charts |

The whole stack runs on **free tiers (₹0)**.

## 5. Key design decisions

1. **pandas calculates and the AI interprets.** The LLM never does arithmetic. It receives a compact, aggregated summary of about 2,000 tokens. As a result, numbers are always correct, token use stays inside the free tier, and only district-level aggregates leave the app.
2. **Session-level de-duplication for CRT data.** Totals are computed on unique sessions, not raw activity rows. Muzaffarpur shows 607 schools reported, and this matches a manual count from the raw file.
3. **Model resilience.** Google retired the Gemini models the app first used. The app now tries a list of current models. If all of them fail, it asks the API which Flash models the key can use and picks the newest.
4. **Automation without code changes.** The app only posts to a webhook. Make.com decides what happens next (Gmail today, Drive or WhatsApp later), so new channels need no app release.
5. **Privacy by design.** No personal data is needed. API keys stay server-side in Streamlit secrets. The raw file is never stored, and users can delete their history.

## 6. Data quality handling (CRT report)

| Check | FY 2026-27 example |
|---|---|
| Raw activity rows | 18,853 |
| Exact duplicate rows removed | 210 |
| Unique sessions | 11,741 |
| Sessions with 0 participants | 34 |
| Sessions with > 200 participants (likely entry error) | 56 (can be excluded with one toggle) |

## 7. Testing

- Automated UI tests with Streamlit `AppTest` cover every page, the filters, downloads, the AI flows (with a mocked model) and the Make.com panel (against a local server).
- The analysis was cross-checked against hand calculations on the raw file.
- End-to-end checks against the real services: Gemini, a Make.com webhook delivering to Gmail with a Word attachment that opens correctly, and a Supabase save → read → delete cycle, including an RLS block check.
- The Postman collection is in `postman/InsightAI.postman_collection.json`.

## 8. Learnings

1. **Understand the data before you analyse it.** The CRT file looked like one row per session, but it was one row per activity. Without de-duplication every total would have been about 65% too high, with no visible error.
2. **Let code compute and let the LLM explain.** Giving the model pre-computed tables instead of raw rows made answers accurate and cheap, and the AI never had to "guess" a number.
3. **Plan for AI models being retired.** A model that worked one week returned `404 NOT_FOUND` the next. Fallback lists and live model discovery are now part of my default design.
4. **Integration details matter more than integration count.** In Make.com, a *mailhook* is not a *webhook*. Passing a file as base64 text produced an unreadable Word attachment. Sending a real multipart file fixed it.
5. **Free tiers are enough for an MVP if you design for them.** Small prompts, cached AI answers, a free database and free hosting gave a working, public product at zero cost.
6. **Treat secrets as a deliverable.** Before making the repository public, I scanned the whole git history to confirm that no key had ever been committed.
7. **Build the narrow workflow first.** Getting upload → analysis → AI → report working end to end for one programme (SHWP) made every later feature easier to add.

## 9. Future scope

- Login for each district team, with role-based views
- Scheduled weekly reports (Make.com scheduler → email or WhatsApp)
- More programme templates: nutrition, education, gender
- Trend alerts when a district drops below a threshold

---
*Screenshots to add in Notion: Upload page · CRT report (District, Theme, Weekly tabs) · AI summary · Hindi Q&A · Priority actions · Review brief Word file · Make.com scenario · Gmail email with attachment · Supabase tables · Postman test results.*
