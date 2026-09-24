"""Gemini (Google AI Studio free tier) reasoning layer.

Only the aggregate context built by analysis.build_ai_context() is sent to the model.
"""
from __future__ import annotations

import time

from google import genai
from google.genai import errors, types

# Tried in order; falls through on quota (429) or unknown-model (404) errors.
DEFAULT_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

SYSTEM = """You are InsightAI, an experienced programme analyst supporting government
public-health programme managers in India (district and state level).

Rules:
- Use ONLY the figures in the DATA CONTEXT. Never invent numbers, districts or schools.
  If the context cannot answer the question, say so plainly and suggest what data is needed.
- Always quote the specific numbers that support a statement (e.g. "Sitamarhi 71.2% vs state 88.4%").
- Separate what the data shows from why it might be happening: label causes as
  "possible reasons" (hypotheses to verify), not facts.
- Recommendations must be concrete and actionable for a programme review: what, who
  (e.g. District Programme Manager, Block Education Officer, RBSK team), and by when.
- Be concise. Use Markdown: short headings, bullet points, **bold** district names.
"""

LANG_NOTE = {
    "English": "Respond in English.",
    "Hindi": "Respond in simple Hindi (Devanagari script). Keep district names, indicator names and numbers as they are.",
}


class AIError(RuntimeError):
    pass


class GeminiClient:
    def __init__(self, api_key: str, models: list[str] | None = None):
        if not api_key:
            raise AIError("Gemini API key missing. Add GEMINI_API_KEY to .streamlit/secrets.toml.")
        self.client = genai.Client(api_key=api_key)
        self.models = models or DEFAULT_MODELS
        self.last_model: str | None = None

    def generate(self, prompt: str, language: str = "English", temperature: float = 0.3) -> str:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM + "\n" + LANG_NOTE.get(language, LANG_NOTE["English"]),
            temperature=temperature,
        )
        last_err: Exception | None = None
        for model in self.models:
            for attempt in range(2):
                try:
                    resp = self.client.models.generate_content(model=model, contents=prompt, config=config)
                    self.last_model = model
                    if not resp.text:
                        raise AIError("The model returned an empty response. Please try again.")
                    return resp.text
                except errors.APIError as e:
                    last_err = e
                    if e.code == 429 and attempt == 0:
                        time.sleep(3)  # brief back-off, then retry once before switching model
                        continue
                    if e.code in (404, 429, 500, 503):
                        break  # try the next model
                    raise AIError(_friendly(e)) from e
        raise AIError(_friendly(last_err))


def _friendly(e: Exception | None) -> str:
    code = getattr(e, "code", None)
    if code == 429:
        return "Free-tier rate limit reached on all Gemini models. Wait a minute and try again."
    if code in (400, 401, 403):
        return f"Gemini rejected the request ({code}). Check that GEMINI_API_KEY is valid."
    return f"AI service error: {e}"


def _with_context(context: str, task: str) -> str:
    return f"DATA CONTEXT (aggregated, computed with pandas):\n{context}\n\nTASK:\n{task}"


def auto_insights(ai: GeminiClient, context: str, language: str) -> str:
    return ai.generate(_with_context(context, """
Write automated insights for a programme manager:
1. **Executive summary** — 2-3 sentences on overall programme health.
2. **Key findings** — 5-7 bullets covering: districts below state average, reporting
   completeness / data gaps, trends over time (improving vs declining), top performers,
   and any anomaly worth attention. Each bullet must cite numbers.
3. **Watch list** — the 3 districts needing the most attention, one line each on why.
"""), language)


def answer_question(ai: GeminiClient, context: str, question: str,
                    history: list[dict], language: str) -> str:
    convo = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in history[-6:])
    task = (f"Previous conversation:\n{convo}\n\n" if convo else "") + f"""
Answer the user's question using the data context. Start with a direct answer, then
supporting numbers (a small Markdown table if comparing several districts), then a one-line
"So what" implication for the programme.

QUESTION: {question}
"""
    return ai.generate(_with_context(context, task), language)


def priority_actions(ai: GeminiClient, context: str, language: str) -> str:
    return ai.generate(_with_context(context, """
Identify the TOP 5 priority issues to table at the next monthly programme review meeting,
ranked by severity x scale. For each, use exactly this structure:

### <n>. <short issue title>
- **Evidence:** numbers from the data
- **Possible reasons:** 1-2 hypotheses to verify
- **Recommended action:** specific corrective step
- **Owner:** role responsible
- **Timeline:** e.g. within 2 weeks / before next review
"""), language, temperature=0.2)


def review_brief(ai: GeminiClient, context: str, programme: str, meeting_date: str, language: str) -> str:
    return ai.generate(_with_context(context, f"""
Draft a meeting-ready REVIEW BRIEF (about 1-2 pages) for the monthly review of the
"{programme}" scheduled on {meeting_date}. Use these Markdown sections:

# {programme} — Monthly Review Brief
## 1. Executive Summary
## 2. Performance Snapshot (a Markdown table: indicator | state value | best district | weakest district)
## 3. Districts Requiring Attention
## 4. Reporting Completeness & Data Quality
## 5. Trends Since Last Quarter
## 6. Top 5 Priority Actions (numbered; action, owner, timeline)
## 7. Recognition — Top-Performing Districts
## 8. Decisions Sought from the Review Meeting

Keep it factual and crisp; every claim must be backed by a number from the data.
"""), language, temperature=0.2)
