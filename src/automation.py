"""Make.com automation: push generated reports to a Make Custom Webhook.

The Make scenario (Webhook -> Gmail -> Google Drive) decides what happens next, so new
delivery channels can be added in Make without changing this app.
"""
from __future__ import annotations

import base64
import html
import re
from datetime import datetime

import httpx

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match(addr.strip()))


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)


def markdown_to_html(md: str) -> str:
    """Small Markdown -> HTML converter for email bodies (headings, lists, tables, bold)."""
    out, in_list, table = [], None, []

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    def flush_table():
        if not table:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table
                if not re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", r)]
        cells = "".join(
            "<tr>" + "".join(f"<{'th' if i == 0 else 'td'} style='border:1px solid #ccc;padding:4px 8px'>"
                             f"{_inline(c)}</{'th' if i == 0 else 'td'}>" for c in r) + "</tr>"
            for i, r in enumerate(rows))
        out.append(f"<table style='border-collapse:collapse;font-size:13px'>{cells}</table>")
        table.clear()

    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|"):
            close_list()
            table.append(s)
            continue
        flush_table()
        if m := re.match(r"^(#{1,4})\s+(.*)", s):
            close_list()
            level = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{level} style='color:#1F4E79'>{_inline(m.group(2))}</h{level}>")
        elif m := re.match(r"^[-*•]\s+(.*)", s):
            if in_list != "ul":
                close_list()
                out.append("<ul>")
                in_list = "ul"
            out.append(f"<li>{_inline(m.group(1))}</li>")
        elif m := re.match(r"^\d+[.)]\s+(.*)", s):
            if in_list != "ol":
                close_list()
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{_inline(m.group(1))}</li>")
        elif s and s not in ("---", "***"):
            close_list()
            out.append(f"<p>{_inline(s)}</p>")
    close_list()
    flush_table()
    return "<div style='font-family:Arial,sans-serif;font-size:14px;color:#1B2733'>" + "\n".join(out) + "</div>"


def build_payload(kind: str, recipient: str, subject: str, body_markdown: str, source_file: str,
                  model: str | None = None, docx: bytes | None = None, docx_filename: str | None = None,
                  extra: dict | None = None) -> dict:
    payload = {
        "kind": kind,
        "recipient_email": recipient.strip(),
        "subject": subject,
        "body_markdown": body_markdown,
        "body_html": markdown_to_html(body_markdown),
        "source_file": source_file,
        "model": model or "",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "app": "InsightAI",
        "has_attachment": docx is not None,
        "docx_filename": docx_filename or "",
        "docx_base64": base64.b64encode(docx).decode() if docx else "",
    }
    payload.update(extra or {})
    return payload


def send_to_make(webhook_url: str, payload: dict, timeout: float = 30.0) -> tuple[bool, str]:
    """POST the payload to a Make Custom Webhook. Returns (ok, user-facing message)."""
    if not webhook_url:
        return False, "Make.com webhook URL not configured (MAKE_WEBHOOK_URL)."
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=timeout)
    except httpx.TimeoutException:
        return False, "Make.com did not respond in time. Check that the scenario is ON and try again."
    except httpx.HTTPError as e:
        return False, f"Could not reach Make.com: {e}"
    if resp.status_code in (200, 202):
        return True, f"Sent to Make.com ✅ — the scenario will email {payload.get('recipient_email')}."
    if resp.status_code == 410:
        return False, "Make.com webhook not found or scenario turned off (410). Turn the scenario ON in Make."
    if resp.status_code == 400 and "queue is full" in resp.text.lower():
        return False, "Make.com webhook queue is full — run/enable the scenario in Make."
    return False, f"Make.com returned {resp.status_code}: {resp.text[:200]}"
