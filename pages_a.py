"""Overview, NOC Live, ATM Detail."""
import pandas as pd
import plotly.express as px
import streamlit as st

import engine as E
import ui
from ui import STATE_COLORS, STATE_ICON, SEV_ICON


def overview():
    inv, stt, inc = ui.current_data()
    openinc = inc[inc["status"] != "Resolved"]
    n = len(stt)
    online = int(stt["online"].sum())
    st.subheader("Executive overview")
    c = st.columns(6)
    ui.kpi(c[0], "National availability", f"{online / n * 100:.1f}%", help="ATMs online / total ATMs")
    ui.kpi(c[1], "ATMs monitored", f"{n}")
    ui.kpi(c[2], "Offline", int((~stt["online"]).sum()), bad_if_up=True)
    ui.kpi(c[3], "Degraded / OOS", int(stt["state"].isin(["Degraded", "Out of Service"]).sum()))
    ui.kpi(c[4], "Cash low / out", int((stt["cash_state"] != "OK").sum()))
    ui.kpi(c[5], "Open incidents", len(openinc))

    c = st.columns(4)
    raw = int(openinc["raw_alerts"].sum()) if "raw_alerts" in openinc and len(openinc) else 0
    ui.kpi(c[0], "Customers affected (est./day)", f"{int(stt['customers_affected'].sum()):,}",
           help="Offline ATMs × half of their average daily transactions")
    ui.kpi(c[1], "Raw alerts → incidents", f"{raw} → {len(openinc)}", help="Correlation engine collapses child alerts into one parent incident")
    ui.kpi(c[2], "Avg health score", f"{stt['health_score'].mean():.0f}/100")
    ui.kpi(c[3], "Tx today (all ATMs)", f"{int(stt['tx_today'].sum()):,}")

    l, r = st.columns([1.05, 1])
    with l:
        reg = E.region_trend(stt).sort_values("availability")
        fig = px.bar(reg, x="availability", y="region", orientation="h", color="availability", text="availability",
                     color_continuous_scale=["#F85149", "#E3B341", "#3FB950"], range_color=[85, 100], title="Availability by region (%)")
        fig.update_layout(coloraxis_showscale=False)
        fig.update_xaxes(range=[70, 100])
        st.plotly_chart(ui.style(fig, 360), width="stretch")
    with r:
        ts = E.network_series()
        fig = px.area(ts, x="date", y="availability", title="30-day network availability (%)")
        fig.update_traces(line_color=ui.GOLD, fillcolor="rgba(212,165,55,.18)")
        fig.add_hline(y=99, line_dash="dot", line_color="#3FB950", annotation_text="Target 99%")
        fig.update_yaxes(range=[93, 100])
        st.plotly_chart(ui.style(fig, 360), width="stretch")

    l, r = st.columns([1, 1.05])
    with l:
        st.markdown("**Top 10 problem ATMs** (lowest health score)")
        top = stt.sort_values("health_score").head(10)[["atm_id", "state_label", "region", "district", "health_score", "cash_pct", "decline_rate"]]
        st.dataframe(top.rename(columns={"state_label": "state"}), hide_index=True, width="stretch",
                     column_config={"health_score": st.column_config.ProgressColumn("health", min_value=0, max_value=100, format="%d"),
                                    "cash_pct": st.column_config.ProgressColumn("cash %", min_value=0, max_value=100, format="%d")})
    with r:
        fig = px.histogram(stt, x="health_score", nbins=20, color="state", color_discrete_map=STATE_COLORS, title="ATM health score distribution")
        st.plotly_chart(ui.style(fig, 340), width="stretch")

    st.markdown("**Regional heat map**")
    st.plotly_chart(ui.status_map(stt, h=420), width="stretch")
    st.caption("Map blank? Switch on **Plain map** in the sidebar.")


@st.fragment(run_every="10s")
def _clock():
    st.caption(f"🔄 NOC wall refresh every 10 s · data time {E.NOW:%Y-%m-%d %H:%M} (simulated)")


def noc():
    inv, stt, inc = ui.current_data()
    st.subheader("NOC live view")
    _clock()
    cnt = stt["state"].value_counts()
    c = st.columns(5)
    for col, s in zip(c[:4], ["Online", "Degraded", "Out of Service", "Offline"]):
        ui.kpi(col, f"{STATE_ICON[s]} {s}", int(cnt.get(s, 0)))
    ui.kpi(c[4], "💵 Cash low/out", int((stt["cash_state"] != "OK").sum()))

    with st.expander("Simulate a live event (demo of the alert workflow)", expanded=False):
        a, b, d = st.columns([2, 2, 1])
        atm = a.selectbox("ATM", stt["atm_id"].tolist(), key="sim_atm")
        kind = b.selectbox("Event", ["Heartbeat missed", "Cash dispenser fault", "Card reader tamper sensor", "Cassette low"], key="sim_kind")
        if d.button("Inject event", disabled=not ui.can_act(), width="stretch"):
            row = stt[stt["atm_id"] == atm].iloc[0]
            maint = [m for m in st.session_state["maint"] if m["scope"].endswith(row["district"])]
            if maint:
                st.warning(f"Event suppressed – {row['district']} is in maintenance window ({maint[0]['reason']}).")
                ui.log_action(st.session_state["user"], "Event suppressed by maintenance window", atm)
            else:
                sev = {"Heartbeat missed": "Major", "Cash dispenser fault": "Major", "Card reader tamper sensor": "Critical", "Cassette low": "Minor"}[kind]
                root = {"Heartbeat missed": "DEVICE", "Cash dispenser fault": "COMPONENT", "Card reader tamper sensor": "SECURITY", "Cassette low": "CASH_OUT"}[kind]
                n = 2000 + len(st.session_state["extra_inc"])
                st.session_state["extra_inc"].append({
                    "incident_id": f"INC-{n}", "severity": sev, "sev_rank": E.SEV[sev], "title": f"{kind} – {atm}", "category": "Simulated",
                    "affected_atms": [atm], "region": row["region"], "district": row["district"], "vendor": row["vendor"], "opened": E.NOW,
                    "status": "Open", "assignee": "Unassigned", "root_cause": root, "customers_affected": int(row["avg_daily_tx"] // 2), "raw_alerts": 3})
                ui.notify("SMS", f"On-duty {row['region']} NOC", f"[{sev.upper()}] {kind} at {atm} ({row['district']})")
                ui.notify("Telegram", "#cbe-noc", f"INC-{n} opened: {kind} – {atm}")
                ui.log_action(st.session_state["user"], "Event processed → incident created", f"INC-{n}")
                st.success(f"Incident INC-{n} created, SMS + Telegram queued, escalation timer started.")
                st.rerun()

    l, r = st.columns([1.5, 1])
    with l:
        flt = st.multiselect("Show states", list(STATE_COLORS), default=list(STATE_COLORS), key="noc_flt")
        st.plotly_chart(ui.status_map(stt[stt["state"].isin(flt)], h=520), width="stretch")
        st.caption("Map blank? Your network may block map tiles – switch on **Plain map** in the sidebar.")
    with r:
        st.markdown("**Live incident list** (by severity)")
        o = inc[inc["status"] != "Resolved"].head(14).copy()
        o["sev"] = o["severity"].map(lambda s: f"{SEV_ICON[s]} {s}")
        o["age"] = ((E.NOW - o["opened"]).dt.total_seconds() / 60).astype(int).astype(str) + " m"
        o["atms"] = o["affected_atms"].apply(len)
        st.dataframe(o[["incident_id", "sev", "title", "atms", "age", "status"]], hide_index=True, width="stretch", height=470)
    with st.expander("Notification gateway log (SMS · Email · Telegram)"):
        if st.session_state["notif"]:
            st.dataframe(pd.DataFrame(st.session_state["notif"]), hide_index=True, width="stretch")
        else:
            st.caption("No notifications yet – inject an event above or acknowledge/resolve an incident.")


def atm_detail():
    inv, stt, inc = ui.current_data()
    st.subheader("ATM detail")
    default = stt.sort_values("health_score").iloc[0]["atm_id"]
    ids = stt["atm_id"].tolist()
    sel = st.selectbox("Select ATM (or search by ID)", ids, index=ids.index(st.session_state.get("focus_atm", default)) if st.session_state.get("focus_atm", default) in ids else 0)
    r = stt[stt["atm_id"] == sel].iloc[0]

    h1, h2, h3 = st.columns([2.2, 1.2, 1.4])
    with h1:
        st.markdown(f"### {STATE_ICON[r['state']]} {r['atm_id']} — {r['state']}")
        st.caption(f"{r['model']} ({r['vendor']}) · S/N {r['serial']} · {r['branch']} · {r['district']}, {r['region']} · "
                   f"GPS {r['lat']:.4f}, {r['lon']:.4f}")
        st.caption(f"Link: {r['link_type']} via {r['isp']} · router {r['router_id']} · installed {r['install_year']} · "
                   f"ATM QR: `cbe://atm/{r['atm_id']}`")
    h2.plotly_chart(ui.gauge(int(r["health_score"]), "Health score"), width="stretch")
    with h3:
        st.metric("Tx today", f"{int(r['tx_today']):,}")
        st.metric("Customers affected", f"{int(r['customers_affected']):,}")

    t1, t2, t3, t4 = st.tabs(["Components & cash", "Transactions & link", "Compliance & power", "Timeline, tickets & actions"])
    with t1:
        a, b = st.columns(2)
        with a:
            st.markdown("**Component health**")
            comp = pd.DataFrame({"component": E.COMPONENTS, "state": [r[c] for c in E.COMPONENTS]})
            comp["state"] = comp["state"].map({"OK": "🟢 OK", "Warning": "🟡 Warning", "Fault": "🔴 Fault"})
            st.dataframe(comp, hide_index=True, width="stretch")
        with b:
            st.markdown(f"**Cash cassettes** – {r['cash_pct']:.0f}% avg · ETB {int(r['cash_etb']):,}")
            for d in E.DENOMS:
                v = float(r[f"cass_{d}"])
                st.progress(int(v) / 100, text=f"ETB {d} cassette: {v:.0f}%" + ("  ⚠ low" if v < 20 else ""))
            hrs = r["hours_to_cashout"]
            st.info(f"Forecast: cash-out in ~{hrs:.0f} h at current burn ({r['daily_cash_burn_pct']}%/day)")
    with t2:
        a, b = st.columns([1.4, 1])
        with a:
            ts = E.tx_series(sel)
            fig = px.bar(ts, x="time", y=["success", "declined"], title="Transactions – last 24 h", barmode="stack",
                         color_discrete_map={"success": "#3FB950", "declined": "#F85149"})
            st.plotly_chart(ui.style(fig, 300), width="stretch")
        with b:
            st.markdown("**Link health**")
            st.metric("Active link", r["active_link"])
            st.metric("Latency", "—" if pd.isna(r["latency_ms"]) else f"{r['latency_ms']:.0f} ms")
            st.metric("Packet loss", f"{r['packet_loss']:.1f}%")
            st.metric("Bandwidth utilisation", f"{r['bandwidth_util']:.0f}%")
        st.caption(f"Decline rate {r['decline_rate']}% · timeouts {r['timeouts']} · reversals {r['reversals']}")
    with t3:
        a, b = st.columns(2)
        with a:
            st.markdown("**Power & environment**")
            st.metric("Power source", "UPS battery" if r["on_battery"] else "Grid")
            st.metric("UPS battery", f"{r['ups_battery_pct']}%", help=f"UPS age {r['ups_age_months']} months")
            st.metric("Cabinet temperature", f"{r['temp_c']} °C")
            if r["ups_age_months"] > 48:
                st.warning("UPS battery older than 48 months – replacement recommended.")
        with b:
            st.markdown("**Software & patch compliance**")
            st.write(f"OS: **{r['os_version']}**" + ("  ⚠ unsupported" if "Win7" in r["os_version"] else ""))
            st.write(f"ATM application: **{r['app_version']}**")
            st.write(f"Antivirus: **{'OK' if r['antivirus_ok'] else 'Out of date'}**")
            st.write(f"Config vs approved baseline: **{'Match' if r['baseline_ok'] else 'DIFFERS – investigate'}**")
            st.write(f"Certificate expiry: **{r['cert_expiry_days']} days**" + ("  ⚠" if r["cert_expiry_days"] < 30 else ""))
    with t4:
        a, b = st.columns([1.2, 1])
        with a:
            st.markdown("**Event timeline**")
            tl = E.timeline(r)
            tl["severity"] = tl["severity"].map(lambda s: f"{SEV_ICON[s]} {s}")
            st.dataframe(tl, hide_index=True, width="stretch", height=300)
            st.markdown("**Ticket history**")
            mine = inc[inc["affected_atms"].apply(lambda x: sel in x)]
            st.dataframe(mine[["incident_id", "severity", "title", "status", "opened"]] if len(mine) else pd.DataFrame({"info": ["No tickets"]}),
                         hide_index=True, width="stretch")
        with b:
            st.markdown("**Remote actions**")
            dis = not ui.can_act()
            if st.button("📡 Send ping", disabled=dis, width="stretch"):
                st.success("Ping reply: " + ("timeout – no response" if not r["online"] else f"{r['latency_ms']:.0f} ms"))
                ui.log_action(st.session_state["user"], "Remote ping", sel)
            if st.button("♻ Restart ATM service", disabled=dis, width="stretch"):
                st.success("Restart command queued (needs approval workflow in production).")
                ui.log_action(st.session_state["user"], "Remote service restart requested", sel)
            if st.button("🛑 Set Out of Service", disabled=dis, width="stretch"):
                st.warning("ATM flagged Out of Service; nearest-ATM feed updated.")
                ui.log_action(st.session_state["user"], "Set Out of Service", sel)
            st.markdown("**Nearest working ATMs**")
            ok = stt[(stt["online"]) & (stt["atm_id"] != sel) & (stt["cash_state"] == "OK")].copy()
            ok["km"] = (((ok["lat"] - r["lat"]) ** 2 + ((ok["lon"] - r["lon"]) * 0.98) ** 2) ** 0.5 * 111).round(1)
            st.dataframe(ok.nsmallest(4, "km")[["atm_id", "branch", "km"]], hide_index=True, width="stretch")
