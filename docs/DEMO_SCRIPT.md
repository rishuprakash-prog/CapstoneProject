# InsightAI — Demo Video Script (≈ 4½ minutes)

**Before recording:**
- Open the live app and wake it if it is asleep.
- Turn the Make.com scenario ON.
- Keep the CRT Excel file and Gmail ready in other tabs.
- Close notifications and use a clean browser window at 100% zoom.

**Recording tools (free):** Windows **Clipchamp** (screen + mic) or **OBS Studio**. Export at 1080p.

| Time | On screen | Voiceover |
|---|---|---|
| **0:00–0:25** | Title slide or the app's home page | "Every week, school health programmes in Bihar generate thousands of rows of monitoring data. Officers export Excel sheets and spend days preparing review notes, and by the time the meeting happens, the data is already stale. I built **InsightAI** to turn that data into decisions in minutes." |
| **0:25–0:50** | Upload page → upload the CRT Excel file → the "Detected Classroom Transaction report" banner and KPI cards | "I upload this week's Classroom Transaction export: almost nineteen thousand rows. InsightAI recognises the format automatically. One important detail: each row is an *activity*, so the same session repeats several times. Adding up the columns directly would over-count attendance by sixty-five per cent. InsightAI first collapses the file into eleven thousand real sessions." |
| **0:50–1:40** | Dashboard → KPI cards → District Report tab (two charts + table) → change the FY filter | "Here is the report the programme team actually needs. Thirty-one districts, one thousand seven hundred and sixty-two schools reported, and girls make up fifty-seven per cent of participants. The District tab shows schools reported per district and the average boys and girls per session, as charts and as a table, with a state total. I can filter by financial year, district or class." |
| **1:40–2:05** | Theme-wise tab → Weekly tab → District × Theme heatmap → Download Excel | "Theme-wise, I can see boys and girls participation for every module. The weekly view shows the trend and which themes were covered each week. The heatmap shows at a glance where districts are not covering a theme. And the whole report downloads as an Excel file with charts." |
| **2:05–2:40** | Click **✨ Generate AI summary** → scroll the answer | "Now the AI layer. Google Gemini receives only district-level aggregates, which pandas has already computed, so it never invents numbers. It explains what the data shows, *why* it may be happening, and which districts need attention." |
| **2:40–3:10** | Ask InsightAI → switch the language to हिंदी → ask "किन districts में girls की भागीदारी सबसे कम है?" | "Officers can just ask questions, even in Hindi. It answers with the exact districts, Araria, Banka and Gopalganj, a comparison table, and what that means for the programme." |
| **3:10–3:40** | Priority Actions → Generate → show one action card | "For the monthly review, it produces the top five priority issues, each with evidence, a possible reason, a recommended action, an owner and a timeline." |
| **3:40–4:10** | Review Brief → Generate → Download Word → open it briefly → **📧 Email via Make.com** → switch to Gmail and show the email with the attachment | "One click creates a meeting-ready review brief as a Word file. With the Make.com automation, it is emailed straight to the officer's inbox, with the report attached." |
| **4:10–4:30** | History page (Supabase) → quick view of the Make.com scenario | "Every question and report is saved in Supabase for traceability. The stack is Google AI Studio, Make.com, Supabase, Postman and Streamlit, and it runs entirely on free tiers." |
| **4:30–4:45** | Back to the dashboard / closing slide | "InsightAI: from raw programme data to decisions in minutes. Thank you. #IITPatnaCapstone" |

**Tips**
- Speak slowly. Pause for one second after each click so viewers can follow.
- If an AI answer takes 20–30 seconds, cut the wait in Clipchamp.
- Keep the final video between 3 and 5 minutes. Upload it to YouTube (Unlisted) or Google Drive and paste the link in the tracker.
