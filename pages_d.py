"""Reports, Admin, Assistant & analytics."""
import io

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import db
import engine as E
import ui


def _pdf(title, tables):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    ss = getSampleStyleSheet()
    els = [Image("assets/logo_full.png", width=190, height=100), Paragraph(title, ss["Title"]),
           Paragraph(f"Generated {E.NOW:%Y-%m-%d %H:%M} · simulated data", ss["Normal"]), Spacer(1, 10)]
    for name, df in tables:
        els.append(Paragraph(name, ss["Heading2"]))
        data = [list(df.columns)] + df.astype(str).values.tolist()[:25]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9B1986")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), .25, colors.grey),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6EEF5")])]))
        els += [t, Spacer(1, 12)]
    doc.build(els)
    return buf.getvalue()


def _xlsx(sheets):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for n, df in sheets.items():
            df.to_excel(w, sheet_name=n[:31], index=False)
    return buf.getvalue()


def reports():
    inv, stt, inc = ui.current_data()
    st.subheader("Reports & analytics")
    ts = E.network_series()
    reg = E.region_trend(stt)
    mtbf = 24 * 30 / max(1, ts["incidents"].sum() / max(1, len(stt)) * 30 / 30)
    t1, t2, t3, t4 = st.tabs(["Uptime & SLA", "Top failing & cash-outs", "Report builder", "Scheduled & regulatory"])
    with t1:
        c = st.columns(4)
        ui.kpi(c[0], "30-day availability", f"{ts['availability'].mean():.2f}%")
        ui.kpi(c[1], "MTTR (h)", f"{ts['mttr_h'].mean():.1f}")
        ui.kpi(c[2], "MTBF (h)", f"{mtbf:.0f}")
        ui.kpi(c[3], "Incidents (30 d)", int(ts["incidents"].sum()))
        period = st.radio("Period", ["Daily", "Weekly", "Monthly"], horizontal=True)
        t = ts.set_index("date")
        t = t if period == "Daily" else t.resample("W" if period == "Weekly" else "ME").mean(numeric_only=True)
        fig = px.line(t.reset_index(), x="date", y="availability", markers=True, title=f"{period} availability (%)")
        fig.update_traces(line_color=ui.GOLD)
        st.plotly_chart(ui.style(fig, 300), width="stretch")
        a, b = st.columns(2)
        a.plotly_chart(ui.style(px.bar(ts, x="date", y="mttr_h", title="MTTR per day (h)").update_traces(marker_color=ui.PURPLE), 280), width="stretch")
        b.dataframe(reg, hide_index=True, width="stretch")
    with t2:
        top = stt.sort_values("health_score").head(15)[["atm_id", "region", "district", "vendor", "model", "state", "health_score"]]
        st.markdown("**Top failing ATMs**")
        st.dataframe(top, hide_index=True, width="stretch")
        co = stt.groupby("region").agg(cash_out=("cash_state", lambda s: (s == "Cash-out").sum()), low=("cash_state", lambda s: (s == "Low").sum())).reset_index()
        st.plotly_chart(ui.style(px.bar(co, x="region", y=["cash_out", "low"], title="Cash-out frequency by region"), 280), width="stretch")
    with t3:
        st.caption("Pick dimensions and measures, then export.")
        by = st.selectbox("Group by", ["region", "district", "vendor", "model", "link_type", "isp", "state"])
        meas = st.multiselect("Measures", ["health_score", "cash_pct", "tx_today", "decline_rate", "latency_ms", "packet_loss", "customers_affected"],
                              default=["health_score", "tx_today"])
        agg = st.selectbox("Aggregation", ["mean", "sum", "max", "min"])
        if meas:
            rep = stt.groupby(by)[meas].agg(agg).round(2).reset_index()
            rep.insert(1, "atms", stt.groupby(by).size().values)
            st.dataframe(rep, hide_index=True, width="stretch")
            st.plotly_chart(ui.style(px.bar(rep, x=by, y=meas[0], color=meas[0], color_continuous_scale="Purples"), 280), width="stretch")
    with t4:
        sheets = {"Region availability": reg, "Top failing ATMs": stt.sort_values("health_score").head(50)[["atm_id", "region", "district", "state", "health_score"]],
                  "Incidents": inc.drop(columns=["affected_atms"], errors="ignore"), "Cash low": stt[stt["cash_state"] != "OK"][["atm_id", "region", "cash_pct", "hours_to_cashout"]],
                  "30-day trend": ts}
        a, b, c = st.columns(3)
        a.download_button("⬇ Excel report", _xlsx(sheets), "CBE_ATM_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        b.download_button("⬇ PDF report", _pdf("CBE ATM & Network Availability Report", [("Region availability", reg), ("Top failing ATMs", sheets["Top failing ATMs"].head(15))]),
                          "CBE_ATM_report.pdf", "application/pdf", width="stretch")
        c.download_button("⬇ CSV (inventory + status)", stt.drop(columns=["state_label"]).to_csv(index=False), "CBE_atm_status.csv", "text/csv", width="stretch")
        st.markdown("**NBE regulatory pack (template)**")
        nbe = reg[["region", "atms", "availability"]].rename(columns={"atms": "ATMs in service base", "availability": "Availability %"})
        st.dataframe(nbe, hide_index=True, width="stretch")
        st.download_button("⬇ NBE return (Excel)", _xlsx({"NBE ATM availability": nbe}), "NBE_ATM_availability.xlsx", width="stretch")
        st.markdown("**Schedule report e-mail**")
        with st.form("sched"):
            x, y, z = st.columns(3)
            rcp = x.text_input("Recipients", "noc-head@cbe.example")
            frq = y.selectbox("Frequency", ["Daily 07:00", "Weekly Mon 08:00", "Monthly 1st"])
            fmt = z.selectbox("Format", ["PDF", "Excel"])
            if st.form_submit_button("Save schedule", disabled=not ui.can_act()):
                st.session_state["sched_reports"].append({"recipients": rcp, "frequency": frq, "format": fmt})
                ui.log_action(st.session_state["user"], "Report scheduled", f"{frq} → {rcp}")
        if st.session_state["sched_reports"]:
            st.dataframe(pd.DataFrame(st.session_state["sched_reports"]), hide_index=True, width="stretch")


ARCH = """digraph G { rankdir=TB; bgcolor="transparent"; node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fontcolor="#1B0A1A", fillcolor="#F5EDE0", color="#D4A537"]; edge [color="#D4A537"];
 subgraph cluster_src { label="Data sources"; fontcolor="#D4A537"; color="#9B1986"; ATM [label="ATMs / POS / CDM\\n(XFS agent, NDC/DDC logs)"]; NET [label="Routers & switches\\n(SNMP, ICMP, syslog)"]; SW [label="ATM switch / Core banking\\n(ISO 8583 read-only feed)"]; SRV [label="Servers & channels\\n(agents)"]; }
 COL [label="Regional collectors\\n(buffer if WAN down, secure tunnel)", fillcolor="#D4A537"];
 BUS [label="Message bus (Kafka / RabbitMQ)", fillcolor="#D4A537"];
 RULE [label="Event processor\\n+ correlation engine"]; TS [label="Time-series DB\\n(TimescaleDB)"]; ML [label="Analytics / ML\\n(forecast, anomaly)"];
 API [label="Core services API\\nAlerts · Incidents · Inventory · Cash · Reports · RBAC · Audit"]; PG [label="PostgreSQL + Redis"];
 UI [label="Web dashboard (this app)\\n+ mobile field app", fillcolor="#9B1986", fontcolor="white"]; NOTI [label="Notification gateway\\nSMS · Email · Telegram", fillcolor="#9B1986", fontcolor="white"];
 ATM -> COL; NET -> COL; SW -> COL; SRV -> COL; COL -> BUS; BUS -> RULE; BUS -> TS; BUS -> ML; RULE -> API; TS -> API; ML -> API; API -> PG; API -> UI; API -> NOTI; }"""


def admin():
    inv, stt, inc = ui.current_data()
    st.subheader("Administration")
    t1, t2, t3, t4, t5, t6 = st.tabs(["Asset inventory", "Roles & RBAC", "Thresholds", "Audit log", "Integrations & monitor health", "Architecture"])
    with t1:
        st.caption(f"{len(stt)} assets in scope · hierarchy: Head office → Region → District → Branch → ATM")
        cols = ["atm_id", "model", "vendor", "serial", "region", "district", "branch", "lat", "lon", "link_type", "isp", "install_year"]
        ex = pd.DataFrame(st.session_state["extra_atms"]) if st.session_state["extra_atms"] else pd.DataFrame(columns=cols)
        st.dataframe(pd.concat([inv[cols], ex], ignore_index=True), hide_index=True, width="stretch", height=300)
        with st.form("add_atm"):
            a, b, c, d = st.columns(4)
            nid = a.text_input("ATM ID", f"CBE-{9000 + len(st.session_state['extra_atms'])}")
            reg = b.selectbox("Region", [r[0] for r in E.REGIONS])
            ven = c.selectbox("Vendor", list(E.VENDORS))
            ser = d.text_input("Serial", "SN00000000")
            if st.form_submit_button("Add ATM to inventory", disabled=not ui.can_act()):
                st.session_state["extra_atms"].append({"atm_id": nid, "model": E.VENDORS[ven]["models"][0], "vendor": ven, "serial": ser, "region": reg,
                                                       "district": "—", "branch": "—", "lat": None, "lon": None, "link_type": "Fiber", "isp": "Ethio Telecom", "install_year": 2026})
                ui.log_action(st.session_state["user"], "ATM added to inventory", nid)
                st.rerun()
    with t2:
        rows = [{"Role": r, "Pages": "All" if v["pages"] == "all" else ", ".join(v["pages"]), "Can act (ack, resolve, remote)": "Yes" if v["act"] else "Read-only",
                 "Data scope": "Own region" if v["scope"] == "region" else "All regions"} for r, v in ui.ROLES.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Switch the role in the sidebar to see menus, data scope and buttons change. Production: AD/LDAP login, MFA for admins, config changes via approval workflow.")
    with t3:
        th = st.session_state["thresholds"]
        c = st.columns(4)
        th["cash_low"] = c[0].slider("Cash low (%)", 5, 50, th["cash_low"])
        th["latency_warn"] = c[1].slider("Latency warn (ms)", 50, 800, th["latency_warn"])
        th["loss_warn"] = c[2].slider("Packet loss warn (%)", 0.5, 10.0, th["loss_warn"])
        th["decline_warn"] = c[3].slider("Decline rate warn (%)", 5, 30, th["decline_warn"])
        st.caption("Thresholds apply immediately on the Network, Cash and Transactions pages.")
    with t4:
        ok, msg = db.status()
        (st.success if ok else st.info)(("🗄️ Database: " + msg))
        if st.session_state.get("db_error"):
            st.warning("Last database error: " + st.session_state["db_error"])
        log = pd.DataFrame(st.session_state["audit"])
        st.dataframe(log if len(log) else pd.DataFrame({"info": ["No actions yet – acknowledge an incident or run a remote action."]}), hide_index=True, width="stretch")
        st.caption("Append-only in production (immutable store).")
    with t5:
        a, b = st.columns(2)
        with a:
            st.markdown("**Integrations**")
            st.dataframe(pd.DataFrame([
                ("ATM switch / core banking (ISO 8583 log feed)", "🟢 Connected (read-only)"), ("Ticketing (ServiceNow / Jira)", "🟢 Webhook OK"),
                ("Active Directory / LDAP", "🟢 Connected"), ("SMS gateway (Ethio Telecom)", "🟢 OK"), ("Email (SMTP)", "🟢 OK"),
                ("Telegram / Teams bot", "🟡 Rate-limited"), ("CCTV system", "⚪ Not configured")], columns=["Integration", "Status"]), hide_index=True, width="stretch")
        with b:
            st.markdown("**Monitor self-health & watchdog**")
            col = pd.DataFrame({"collector": [f"collector-{r[0][:3].lower()}" for r in E.REGIONS[:6]], "last_data_sec": [3, 5, 4, 71, 6, 2],
                                "buffered_events": [0, 0, 0, 1240, 0, 0]})
            col["status"] = np.where(col["last_data_sec"] > 60, "🔴 No data > 60 s", "🟢 Healthy")
            st.dataframe(col, hide_index=True, width="stretch")
            st.caption("If a collector stops reporting, the watchdog raises an alert; collectors buffer locally and replay after WAN recovery. HQ runs active-active with DR site.")
    with t6:
        st.graphviz_chart(ARCH, width="stretch")
        st.markdown("**Core tables:** region · district · branch · atm · atm_component_status · cash_cassette · network_device · network_link · metric (time-series) · "
                    "event → alert → incident · maintenance_window · vendor · sla_policy · user · role · audit_log")


def assistant():
    inv, stt, inc = ui.current_data()
    st.subheader("Assistant & intelligence")
    t1, t2, t3, t4 = st.tabs(["Ask the monitor", "Predictive maintenance", "Site & capacity planning", "Cost & before/after"])
    with t1:
        q = st.text_input("Ask in plain English", "show all offline ATMs in Oromia")
        st.caption("Try: *low cash ATMs in Addis Ababa* · *worst health NCR* · *VSAT offline* · *ATMs on battery* · *baseline mismatch*")
        df, notes = E.nl_query(q, stt)
        st.write("Filters understood: " + (", ".join(f"`{n}`" for n in notes) if notes else "none – showing all"))
        st.dataframe(df[["atm_id", "state_label", "region", "district", "vendor", "cash_pct", "health_score"]], hide_index=True, width="stretch", height=330)
        st.caption(f"{len(df)} ATMs")
    with t2:
        fr = E.failure_risk(stt).head(15)
        st.markdown("**Highest failure risk (next 30 days)** – explainable score from age, component warnings, timeouts, declines and UPS age")
        st.dataframe(fr[["atm_id", "region", "model", "install_year", "risk_score", "likely_part"]], hide_index=True, width="stretch",
                     column_config={"risk_score": st.column_config.ProgressColumn("risk", min_value=0, max_value=100, format="%d")})
        st.caption("Production: train gradient-boosted models on journal error history; this demo uses a transparent scoring formula.")
    with t3:
        a, b = st.columns(2)
        use = stt[["atm_id", "region", "district", "avg_daily_tx", "install_year"]].copy()
        use["utilisation"] = np.where(use["avg_daily_tx"] < 150, "Under-used", np.where(use["avg_daily_tx"] > 550, "Over-used", "Normal"))
        a.plotly_chart(ui.style(px.histogram(use, x="avg_daily_tx", color="utilisation", title="Daily transactions per ATM"), 300), width="stretch")
        dist = use.groupby(["region", "utilisation"]).size().reset_index(name="atms")
        b.plotly_chart(ui.style(px.bar(dist, x="region", y="atms", color="utilisation", title="Utilisation by region"), 300), width="stretch")
        st.markdown("**Relocation candidates** (under-used) and **add-capacity candidates** (over-used)")
        c, d = st.columns(2)
        c.dataframe(use[use["utilisation"] == "Under-used"].head(8), hide_index=True, width="stretch")
        d.dataframe(use[use["utilisation"] == "Over-used"].head(8), hide_index=True, width="stretch")
        sv = E.servers()
        st.markdown("**Switch capacity planning** – projected transactions/min at 15% yearly growth")
        yrs = pd.DataFrame({"year": [2026, 2027, 2028, 2029], "tx_per_min": [1000 * 1.15 ** i for i in range(4)]})
        fig = px.line(yrs, x="year", y="tx_per_min", markers=True)
        fig.add_hline(y=1500, line_dash="dot", annotation_text="Switch licensed capacity")
        st.plotly_chart(ui.style(fig, 260), width="stretch")
    with t4:
        rng = np.random.default_rng(3)
        cost = stt.groupby("region").agg(atms=("atm_id", "count")).reset_index()
        cost["maintenance"] = cost["atms"] * rng.integers(900, 1500, len(cost))
        cost["cash_handling"] = cost["atms"] * rng.integers(1200, 2200, len(cost))
        cost["connectivity"] = cost["atms"] * rng.integers(600, 1100, len(cost))
        cost["downtime_loss"] = (stt.groupby("region")["customers_affected"].sum().values * 35)
        fig = px.bar(cost, x="region", y=["maintenance", "cash_handling", "connectivity", "downtime_loss"], title="Monthly cost by region (ETB, simulated)")
        st.plotly_chart(ui.style(fig, 330), width="stretch")
        st.markdown("**Before / after: link upgrade**")
        ba = pd.DataFrame({"metric": ["Availability %", "Avg latency (ms)", "Incidents / month"], "before": [97.4, 210, 31], "after": [99.1, 95, 12]})
        ba["change"] = (ba["after"] - ba["before"]).round(1)
        st.dataframe(ba, hide_index=True, width="stretch")
