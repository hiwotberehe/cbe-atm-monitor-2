"""Optional Supabase persistence. If no credentials are configured, the app runs
exactly as before (in-memory demo mode). Never raises into the UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import engine as E


def _creds():
    try:
        s = st.secrets["supabase"]
        return s["url"], s["key"]
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _client():
    c = _creds()
    if not c:
        return None
    try:
        from supabase import create_client
        return create_client(*c)
    except Exception:
        return None


def enabled() -> bool:
    return _client() is not None


def status() -> tuple[bool, str]:
    """Live connection test for the Admin page."""
    cl = _client()
    if cl is None:
        return False, "Not configured – running in demo mode (data resets on refresh)."
    try:
        cl.table("audit_log").select("id").limit(1).execute()
        return True, "Connected to Supabase."
    except Exception as e:  # missing tables, wrong key, etc.
        return False, f"Configured but failing: {str(e)[:160]}"


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        st.session_state["db_error"] = str(e)[:200]
        return None


def save_audit(user, action, target=""):
    cl = _client()
    if cl:
        _safe(lambda: cl.table("audit_log").insert({"username": user, "action": action, "target": target}).execute())


def save_override(incident_id, o: dict):
    cl = _client()
    if not cl:
        return
    row = {"incident_id": incident_id, "updated_at": pd.Timestamp.utcnow().isoformat()}
    for k in ("status", "assignee", "root_cause"):
        if k in o:
            row[k] = o[k]
    if "resolved_at" in o:
        row["resolved_at"] = pd.Timestamp(o["resolved_at"]).isoformat() + ("" if pd.Timestamp(o["resolved_at"]).tzinfo else "Z")
    _safe(lambda: cl.table("incident_overrides").upsert(row).execute())


def save_maintenance(w: dict):
    cl = _client()
    if cl:
        _safe(lambda: cl.table("maintenance_windows").insert(
            {"scope": w["scope"], "start_time": w["start"], "end_time": w["end"],
             "reason": w["reason"], "approved_by": w["approved_by"]}).execute())


def load_into_state():
    """Called once per browser session: pull saved data back into session_state."""
    cl = _client()
    ss = st.session_state
    if not cl or ss.get("db_loaded"):
        return
    ss["db_loaded"] = True
    r = _safe(lambda: cl.table("audit_log").select("*").order("id", desc=True).limit(500).execute())
    if r is not None:
        def _t(v):
            t = pd.Timestamp(v)
            t = t.tz_convert("Africa/Addis_Ababa") if t.tzinfo else t
            return t.strftime("%Y-%m-%d %H:%M:%S")
        ss["audit"] = [{"time": _t(x["created_at"]), "user": x["username"],
                        "action": x["action"], "target": x["target"]} for x in r.data]
    r = _safe(lambda: cl.table("incident_overrides").select("*").execute())
    if r is not None:
        for x in r.data:
            o = {k: x[k] for k in ("status", "assignee", "root_cause") if x.get(k)}
            if x.get("resolved_at"):
                o["resolved_at"] = pd.Timestamp(x["resolved_at"], tz="UTC").tz_convert(None) if pd.Timestamp(x["resolved_at"]).tzinfo is None else pd.Timestamp(x["resolved_at"]).tz_convert(None)
            ss["inc_over"][x["incident_id"]] = o
    r = _safe(lambda: cl.table("maintenance_windows").select("*").order("id").execute())
    if r is not None and r.data:
        ss["maint"] = [{"scope": x["scope"], "start": x["start_time"], "end": x["end_time"],
                        "reason": x["reason"], "approved_by": x["approved_by"]} for x in r.data]
