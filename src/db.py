"""Supabase (free tier) persistence: datasets, questions and generated insights.

Everything is optional — if Supabase is not configured or unreachable, the app keeps
working and simply does not save history.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class Store:
    def __init__(self, url: str | None, key: str | None):
        self.client = None
        self.error: str | None = None
        if not (url and key):
            self.error = "Supabase not configured"
            return
        try:
            from supabase import create_client
            self.client = create_client(url, key)
        except Exception as e:  # noqa: BLE001 - never let storage break the app
            self.error = f"Supabase connection failed: {e}"

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _safe(self, fn, default=None):
        if not self.enabled:
            return default
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            log.warning("Supabase call failed: %s", e)
            self.error = str(e)
            return default

    def save_dataset(self, session_id: str, file_name: str, n_rows: int, n_districts: int, periods: str) -> str | None:
        res = self._safe(lambda: self.client.table("datasets").insert({
            "session_id": session_id, "file_name": file_name, "n_rows": n_rows,
            "n_districts": n_districts, "periods": periods,
        }).execute())
        return res.data[0]["id"] if res and res.data else None

    def save_query(self, session_id: str, dataset_id: str | None, question: str, answer: str) -> None:
        self._safe(lambda: self.client.table("queries").insert({
            "session_id": session_id, "dataset_id": dataset_id, "question": question, "answer": answer,
        }).execute())

    def save_insight(self, session_id: str, dataset_id: str | None, kind: str, content: str) -> None:
        self._safe(lambda: self.client.table("insights").insert({
            "session_id": session_id, "dataset_id": dataset_id, "kind": kind, "content": content,
        }).execute())

    def history(self, session_id: str, limit: int = 50) -> dict[str, list[dict]]:
        def fetch(table: str):
            return self._safe(lambda: self.client.table(table).select("*").eq("session_id", session_id)
                              .order("created_at", desc=True).limit(limit).execute().data, [])
        return {"datasets": fetch("datasets"), "queries": fetch("queries"), "insights": fetch("insights")}

    def delete_session(self, session_id: str) -> None:
        """User-controlled retention: remove everything this session stored."""
        for table in ("queries", "insights", "datasets"):
            self._safe(lambda t=table: self.client.table(t).delete().eq("session_id", session_id).execute())
