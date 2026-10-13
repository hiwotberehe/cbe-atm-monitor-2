"""Shared UI helpers, session state, theming for the CBE monitoring app."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import db
import engine as E

GOLD, PURPLE, DEEP = "#D4A537", "#9B1986", "#1B0A1A"
STATE_COLORS = {"Online": "#3FB950", "Degraded": "#E3B341", "Out of Service": "#F0883E", "Offline": "#F85149"}
STATE_ICON = {"Online": "🟢", "Degraded": "🟡", "Out of Service": "🟠", "Offline": "🔴"}
SEV_ICON = {"Critical": "🔴", "Major": "🟠", "Minor": "🟡", "Info": "🔵"}

ROLES = {
    "NOC Operator": {"pages": "all", "act": True, "scope": "all"},
    "Regional Manager": {"pages": "all", "act": True, "scope": "region"},
    "Cash-in-Transit Team": {"pages": ["Overview", "Cash", "ATM Detail"], "act": True, "scope": "all"},
    "Vendor Engineer": {"pages": ["Overview", "ATM Detail", "Incidents", "Vendors & Field"], "act": True, "scope": "all"},
    "Auditor": {"pages": ["Overview", "Reports", "Admin", "Security"], "act": False, "scope": "all"},
    "Administrator": {"pages": "all", "act": True, "scope": "all"},
}

RUNBOOKS = {
    "LINK_DOWN": ["Confirm router/ISP status on the carrier portal", "Ping router and next-hop from the regional collector",
                  "If backup link exists, verify failover; otherwise call ISP with circuit ID",
                  "Dispatch network engineer if no ISP outage is declared within 30 min"],
    "POWER": ["Check EEU / grid outage notices for the district", "Verify UPS runtime on affected ATMs",
              "Notify branch to start generator where available", "Alert CIT to avoid cash handling at dark sites"],
    "DEVICE": ["Attempt remote ping and service restart", "Check last heartbeat and journal tail",
               "Dispatch vendor engineer under SLA if restart fails"],
    "COMPONENT": ["Pull component error code from the journal", "Remote reset module if supported",
                  "Dispatch vendor engineer with the right spare part", "Set ATM Out of Service until fixed"],
    "CASH_OUT": ["Confirm cassette counts from the last status poll", "Add to the nearest CIT replenishment route",
                 "Set 'cash low' notice in the nearest-ATM feed"],
    "SECURITY": ["Do NOT clear alert until verified", "Compare config hash with the approved baseline",
                 "Dispatch security + vendor engineer; isolate ATM from the network if tampering is suspected",
                 "Preserve journal and CCTV footage"],
}
ROOT_CODES = ["LINK_DOWN", "POWER", "DEVICE", "COMPONENT", "CASH_OUT", "SECURITY", "VANDALISM", "USER_ERROR", "NO_FAULT_FOUND"]
ENGINEERS = ["Abel T.", "Selam M.", "Dawit K.", "Meron A.", "Yonas B.", "Hanna G.", "Kidus W.", "Bethel S."]


@st.cache_data(show_spinner=False)
def load_data():
    inv = E.build_inventory()
    stt = E.build_status(inv)
    inc = E.build_incidents(stt)
    return inv, stt, inc


def init_state():
    ss = st.session_state
    ss.setdefault("inc_over", {})          # incident_id -> dict(status, assignee, ack_at, resolved_at, root)
    ss.setdefault("extra_inc", [])         # simulated new incidents
    ss.setdefault("audit", [])             # audit log
    ss.setdefault("notif", [])             # notification gateway log
    ss.setdefault("maint", [{"scope": "Oromia – Adama", "start": "2026-10-12 01:00", "end": "2026-10-12 04:00",
                             "reason": "Router firmware upgrade", "approved_by": "Regional Manager"}])
    ss.setdefault("cash_over", {})         # atm_id -> pct after replenishment
    ss.setdefault("ft_over", {})           # failed tx ref -> status
    ss.setdefault("thresholds", {"cash_low": 20, "latency_warn": 150, "loss_warn": 3.0, "decline_warn": 12})
    ss.setdefault("extra_atms", [])
    ss.setdefault("sched_reports", [])
    db.load_into_state()


def log_action(user, action, target=""):
    st.session_state["audit"].insert(0, {"time": E.NOW.strftime("%Y-%m-%d %H:%M") + f":{len(st.session_state['audit']) % 60:02d}",
                                         "user": user, "action": action, "target": target})
    db.save_audit(user, action, target)


def notify(channel, to, msg):
    st.session_state["notif"].insert(0, {"time": E.NOW.strftime("%H:%M"), "channel": channel, "to": to, "message": msg})


def can_act():
    return ROLES[st.session_state.get("role", "NOC Operator")]["act"]


def current_data():
    """Data after region scoping and cash overrides."""
    inv, stt, inc = load_data()
    stt = stt.copy()
    for aid, pct in st.session_state["cash_over"].items():
        stt.loc[stt["atm_id"] == aid, ["cash_pct"] + [f"cass_{d}" for d in E.DENOMS]] = [pct] + [pct] * 4
        stt.loc[stt["atm_id"] == aid, "cash_state"] = "OK"
        stt.loc[stt["atm_id"] == aid, "hours_to_cashout"] = 24 * pct / stt.loc[stt["atm_id"] == aid, "daily_cash_burn_pct"]
    stt["state_label"] = stt["state"].map(lambda s: f"{STATE_ICON[s]} {s}")
    inc = pd.concat([inc, pd.DataFrame(st.session_state["extra_inc"])], ignore_index=True) if st.session_state["extra_inc"] else inc.copy()
    for iid, o in st.session_state["inc_over"].items():
        for k, v in o.items():
            inc.loc[inc["incident_id"] == iid, k] = v
    inc["sev_rank"] = inc["severity"].map(E.SEV)
    inc = inc.sort_values(["sev_rank", "opened"]).reset_index(drop=True)
    scope = ROLES[st.session_state["role"]]["scope"]
    if scope == "region":
        r = st.session_state["region_scope"]
        stt = stt[stt["region"] == r]
        inc = inc[inc["region"] == r]
        inv = inv[inv["region"] == r]
    return inv, stt, inc


def style(fig, h=320):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=36, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#F5EDE0"), legend=dict(orientation="h", y=-0.2),
                      xaxis=dict(gridcolor="rgba(255,255,255,.08)"), yaxis=dict(gridcolor="rgba(255,255,255,.08)"))
    return fig


def status_map(df, color="state", h=470, size=9):
    """Basemap view (needs the browser to reach the CARTO tile server) or plain-coordinate view (works fully offline)."""
    hover = {"region": True, "district": True, "vendor": True, "health_score": True, "cash_pct": True, "lat": False, "lon": False}
    plain = st.session_state.get("plain_map", False)
    if plain:
        fig = px.scatter(df, x="lon", y="lat", color=color, color_discrete_map=STATE_COLORS, hover_name="atm_id", hover_data=hover, height=h)
        fig.update_traces(marker=dict(size=size - 1, line=dict(width=0.5, color="#1B0A1A")))
        fig.update_yaxes(scaleanchor="x", scaleratio=1, title="latitude", gridcolor="rgba(255,255,255,.08)")
        fig.update_xaxes(title="longitude", gridcolor="rgba(255,255,255,.08)")
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(45,16,41,.6)",
                          font=dict(color="#F5EDE0"), legend=dict(orientation="h", y=-0.12, title=None))
        return fig
    fig = px.scatter_map(df, lat="lat", lon="lon", color=color, color_discrete_map=STATE_COLORS, zoom=5, center=dict(lat=9.0, lon=39.5),
                         hover_name="atm_id", hover_data=hover, map_style="carto-darkmatter", height=h)
    fig.update_traces(marker=dict(size=size))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=0.01, x=0.01, bgcolor="rgba(27,10,26,.8)", title=None))
    return fig


def kpi(col, label, value, delta=None, help=None, bad_if_up=True):
    with col:
        st.metric(label, value, delta, delta_color=("inverse" if bad_if_up else "normal") if delta else "off", help=help)


def sla_text(row):
    hrs, remaining, penalty = E.sla_for(row)
    if remaining >= 0:
        return f"{remaining:.1f} h left of {hrs} h", penalty, False
    return f"BREACHED by {-remaining:.1f} h", penalty, True


def gauge(value, title):
    color = "#3FB950" if value >= 80 else "#E3B341" if value >= 60 else "#F85149"
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value, title={"text": title},
                                 gauge={"axis": {"range": [0, 100]}, "bar": {"color": color}, "bgcolor": "rgba(255,255,255,.06)"}))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=40, b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#F5EDE0"))
    return fig
