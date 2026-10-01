# InsightAI — 4 Build-in-Public Posts (LinkedIn)

**How to use these drafts:**
- Post one per week, or space them a few days apart.
- Attach the suggested screenshot to each post.
- Tag @IIT Patna and your course page if allowed.
- Change the wording so each post sounds like you.

---

## Post 1: The idea (Week 1)

🚀 **Kicking off my IIT Patna Generative AI Capstone: InsightAI**

Public health programmes collect huge amounts of monitoring data every week, but turning it into decisions still means manual Excel work and review notes that take days to prepare.

The gap is not data. The gap is interpretation.

So I'm building **InsightAI**, an AI assistant for programme managers:
📤 Upload district-wise monitoring data (CSV / Excel)
💬 Ask questions in plain English or Hindi
🎯 Get gaps, trends and **prioritised actions**
📝 Download a meeting-ready review brief

The first use case is Bihar's **School Health & Wellness Programme** data, a workflow I know first-hand.

Stack: Google AI Studio (Gemini) · Supabase · Make.com · Streamlit, all on free tiers.

Follow along as I build it in public over the next 4 weeks 👇

#IITPatnaCapstone #GenerativeAI #PublicHealth #AIforGood #BuildInPublic

📎 *Screenshot: the 1-Pager or a simple architecture sketch*

---

## Post 2: Core build (Week 2)

🛠️ **InsightAI, week 2: the data was lying to me (and how I caught it)**

Our Classroom Transaction export has ~19,000 rows. It looks like one row per session, but it's actually **one row per activity**. The same session repeats for every activity, with the same boys/girls counts each time.

Summing the columns directly would have over-counted attendance by **65%**, and nothing would look "wrong".

What I built this week:
✅ Automatic format detection
✅ De-duplication into 11,741 real sessions
✅ District report: schools reported, average boys and girls per session, theme-wise and weekly participation, by financial year
✅ Every number cross-checked against a manual count

Lesson: **understand the data before you let AI talk about it.** In my design, pandas computes every figure and the LLM only interprets them.

#IITPatnaCapstone #DataQuality #Python #GenerativeAI #BuildInPublic

📎 *Screenshot: the District Report tab (charts + table)*

---

## Post 3: AI + integration (Week 3)

🤖 **InsightAI, week 3: from dashboard to AI analyst**

This week the app learned to *explain*:
🧠 **Google Gemini** turns pre-computed district tables into a summary: what happened, why it may be happening, what to do next
🇮🇳 Officers can ask in **Hindi**, e.g. "किन districts में girls की भागीदारी सबसे कम है?"
🎯 Top-5 priority actions, each with evidence, owner and timeline
🗄️ **Supabase** stores every question and report for traceability
⚙️ **Make.com** emails the Word review brief straight to the officer's inbox

Two things that broke (and what I learned):
1️⃣ The Gemini model I started with was retired mid-sprint and returned 404. The app now falls back to newer models automatically.
2️⃣ In Make.com, sending the Word file as base64 text gave an unreadable attachment. Sending it as a real file fixed it.

Integration details matter more than the number of integrations.

#IITPatnaCapstone #GoogleGemini #Supabase #MakeDotCom #Automation #BuildInPublic

📎 *Screenshot: the Hindi Q&A answer, or the Gmail email with the Word attachment*

---

## Post 4: Demo (Week 4)

🎬 **InsightAI is live! Turning Programme Data into Decisions**

Four weeks ago this was a one-page idea. Today it's a working AI web app:

📤 Upload the weekly monitoring export
📊 Instant report: 31 districts, 1,762 schools, theme-wise and weekly participation, as charts and tables together
🧠 AI summary + Q&A in English and Hindi
🎯 Top-5 priority actions for the monthly review
📧 One-click review brief, emailed automatically with Make.com

From several days of review preparation to **a few minutes**, on a ₹0 stack: Google AI Studio · Supabase · Make.com · Postman · Streamlit.

🔗 Live app: https://capstoneproject-n9k7dyiappt5htaaj2nppxl.streamlit.app/
🎥 Demo: <paste video link>

Thank you, IIT Patna, for a sprint that pushed me from idea to deployed product. Feedback from people working in public health and M&E is very welcome 🙏

#IITPatnaCapstone #GenerativeAI #PublicHealth #AIforGovernance #BuildInPublic

📎 *Attach: the demo video, or a carousel of 4–5 app screenshots*
