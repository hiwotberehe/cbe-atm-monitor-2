"""Security, Incidents & tickets, Vendors & field."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import db
import engine as E
import ui
from ui import SEV_ICON


def security():
    inv, stt, inc = ui.current_data()
    st.subheader("Security, fraud & compliance")
    ev = E.security_events(stt)
    ev = ev[ev["atm_id"].isin(stt["atm_id"])]
    t1, t2, t3, t4 = st.tabs(["Security & physical events", "Unusual activity", "Unauthorized change detection", "Software & patch compliance"])
    with t1:
        c = st.columns(4)
        for col, s in zip(c[:3], ["Critical", "Major", "Minor"]):
            ui.kpi(col, f"{SEV_ICON[s]} {s}", int((ev["severity"] == s).sum()))
        ui.kpi(c[3], "Unreviewed", int((ev["status"] == "New").sum()))
        e2 = ev.copy()
        e2["severity"] = e2["severity"].map(lambda s: f"{SEV_ICON[s]} {s}")
        st.dataframe(e2, hide_index=True, width="stretch", height=330)
        fig = px.histogram(ev, y="event", color="severity", title="Events by type",
                           color_discrete_map={"Critical": "#F85149", "Major": "#F0883E", "Minor": "#E3B341"})
        st.plotly_chart(ui.style(fig, 300), width="stretch")
        st.caption("Sources: tamper/door/vibration/tilt sensors, device-attach detection, alarm panel; optional CCTV link per ATM.")
    with t2:
        an = E.tx_anomalies(stt)
        st.markdown(f"**{len(an)} ATMs deviate from peer behaviour** (|z| > 2 on volume or decline rate > 15%)")
        st.dataframe(an[["atm_id", "region", "district", "tx_today", "z_vs_peers", "decline_rate", "timeouts"]], hide_index=True, width="stretch")
        fig = px.scatter(stt[stt["online"]], x="tx_today", y="decline_rate", color="state", color_discrete_map=ui.STATE_COLORS, hover_name="atm_id",
                         title="Volume vs decline rate (outliers = potential fraud or malfunction)")
        st.plotly_chart(ui.style(fig, 320), width="stretch")
    with t3:
        bad = stt[~stt["baseline_ok"]]
        ui.kpi(st.columns(4)[0], "ATMs differing from baseline", len(bad))
        st.dataframe(bad[["atm_id", "region", "district", "app_version", "os_version", "model"]], hide_index=True, width="stretch")
        st.caption("Baseline = approved hash of ATM application, firmware and configuration files; any difference raises a Critical security incident.")
    with t4:
        c = st.columns(4)
        ui.kpi(c[0], "Unsupported OS (Win7)", int(stt["os_version"].str.contains("Win7").sum()))
        ui.kpi(c[1], "Antivirus out of date", int((~stt["antivirus_ok"]).sum()))
        ui.kpi(c[2], "Cert expiring < 30 d", int((stt["cert_expiry_days"] < 30).sum()))
        ui.kpi(c[3], "Old app version", int(stt["app_version"].isin(["APTRA 6.3.9", "ProClassic 3.0"]).sum()))
        a, b = st.columns(2)
        a.plotly_chart(ui.style(px.pie(stt, names="os_version", hole=.5, title="OS versions"), 300), width="stretch")
        b.plotly_chart(ui.style(px.pie(stt, names="app_version", hole=.5, title="ATM application versions"), 300), width="stretch")
        st.dataframe(stt[stt["cert_expiry_days"] < 30][["atm_id", "region", "cert_expiry_days"]].sort_values("cert_expiry_days"), hide_index=True, width="stretch")


def incidents():
    inv, stt, inc = ui.current_data()
    st.subheader("Incidents, tickets & SLA")
    t1, t2, t3 = st.tabs(["Incident queue", "Maintenance windows & change calendar", "Post-incident review"])
    with t1:
        c = st.columns(5)
        op = inc[inc["status"] != "Resolved"]
        ui.kpi(c[0], "Open", len(op))
        ui.kpi(c[1], "Critical", int((op["severity"] == "Critical").sum()))
        ui.kpi(c[2], "Unassigned", int((op["assignee"] == "Unassigned").sum()))
        ui.kpi(c[3], "Acknowledged", int((inc["status"] == "Acknowledged").sum()))
        ui.kpi(c[4], "Resolved", int((inc["status"] == "Resolved").sum()))
        f1, f2, f3 = st.columns(3)
        sev = f1.multiselect("Severity", list(E.SEV), default=["Critical", "Major", "Minor"])
        sts = f2.multiselect("Status", ["Open", "Acknowledged", "Resolved"], default=["Open", "Acknowledged"])
        cat = f3.multiselect("Category", sorted(inc["category"].unique()), default=sorted(inc["category"].unique()))
        q = inc[inc["severity"].isin(sev) & inc["status"].isin(sts) & inc["category"].isin(cat)].copy()
        q["sev"] = q["severity"].map(lambda s: f"{SEV_ICON[s]} {s}")
        q["atms"] = q["affected_atms"].apply(len)
        st.dataframe(q[["incident_id", "sev", "title", "category", "region", "district", "atms", "status", "assignee", "opened"]],
                     hide_index=True, width="stretch", height=300)
        if q.empty:
            st.info("No incidents match the filters.")
            return
        st.markdown("---")
        sel = st.selectbox("Open incident", q["incident_id"].tolist())
        r = inc[inc["incident_id"] == sel].iloc[0]
        a, b = st.columns([1.3, 1])
        with a:
            st.markdown(f"### {SEV_ICON[r['severity']]} {r['incident_id']} · {r['title']}")
            st.write(f"**Root-cause hypothesis:** `{r['root_cause']}` · **Customers affected:** {int(r['customers_affected']):,} · "
                     f"**Alerts correlated:** {r.get('raw_alerts', 1)} → 1")
            st.write("**Affected ATMs:** " + ", ".join(r["affected_atms"][:20]) + (" …" if len(r["affected_atms"]) > 20 else ""))
            mins = (E.NOW - r["opened"]).total_seconds() / 60
            st.write(f"**Opened:** {r['opened']:%Y-%m-%d %H:%M} ({mins:.0f} min ago)")
            lvl = "L3 – Head of NOC" if mins > 240 else "L2 – Regional manager" if mins > 90 else "L1 – On-duty NOC"
            st.write(f"**Escalation level:** {lvl}")
            if r["vendor"] != "—":
                txt, pen, breached = ui.sla_text(r)
                (st.error if breached else st.info)(f"Vendor SLA ({r['vendor']}): {txt}" + (f" · penalty ETB {pen:,}" if breached else ""))
            with st.expander("📘 Runbook", expanded=True):
                for i, step in enumerate(ui.RUNBOOKS.get(r["root_cause"], ["Investigate and document findings"]), 1):
                    st.write(f"{i}. {step}")
        with b:
            st.markdown("**Workflow actions**")
            dis = not ui.can_act()
            eng = st.selectbox("Assign to", ui.ENGINEERS, key=f"as_{sel}")
            if st.button("🙋 Acknowledge & assign", disabled=dis or r["status"] == "Resolved", width="stretch"):
                st.session_state["inc_over"].setdefault(sel, {}).update({"status": "Acknowledged", "assignee": eng})
                db.save_override(sel, st.session_state["inc_over"][sel])
                ui.log_action(st.session_state["user"], f"Acknowledged, assigned to {eng}", sel)
                ui.notify("SMS", eng, f"{sel} assigned: {r['title']}")
                st.rerun()
            rc = st.selectbox("Root-cause code", ui.ROOT_CODES, index=ui.ROOT_CODES.index(r["root_cause"]) if r["root_cause"] in ui.ROOT_CODES else 0, key=f"rc_{sel}")
            if st.button("✅ Resolve & close", disabled=dis or r["status"] == "Resolved", width="stretch"):
                st.session_state["inc_over"].setdefault(sel, {}).update({"status": "Resolved", "root_cause": rc, "resolved_at": E.NOW})
                db.save_override(sel, st.session_state["inc_over"][sel])
                ui.log_action(st.session_state["user"], f"Resolved ({rc}); SLA recorded", sel)
                st.rerun()
            if st.button("⬆ Escalate", disabled=dis, width="stretch"):
                ui.notify("Email", "regional-manager@cbe", f"ESCALATION {sel}: {r['title']}")
                ui.notify("SMS", "Head of NOC", f"ESCALATION {sel}")
                ui.log_action(st.session_state["user"], "Escalated", sel)
                st.warning("Escalation sent by SMS + email.")
            if dis:
                st.caption("🔒 Your role is read-only.")
    with t2:
        st.caption("Planned work suppresses alerts for the scoped district. Changes need approval.")
        st.dataframe(pd.DataFrame(st.session_state["maint"]), hide_index=True, width="stretch")
        with st.form("maint_form"):
            a, b, c, d = st.columns(4)
            scope = a.selectbox("Scope", sorted({f"{r} – {d}" for r, d in zip(stt["region"], stt["district"])}))
            s = b.text_input("Start", "2026-10-14 01:00")
            e = c.text_input("End", "2026-10-14 03:00")
            why = d.text_input("Reason", "Patch window")
            if st.form_submit_button("Request window", disabled=not ui.can_act()):
                st.session_state["maint"].append({"scope": scope, "start": s, "end": e, "reason": why, "approved_by": "Pending approval"})
                db.save_maintenance(st.session_state["maint"][-1])
                ui.log_action(st.session_state["user"], "Maintenance window requested", scope)
                st.rerun()
    with t3:
        st.caption("Template for major outages (Critical, > 3 ATMs).")
        major = inc[(inc["severity"] == "Critical") & (inc["affected_atms"].apply(len) >= 3)]
        if major.empty:
            st.info("No major outage in scope.")
        else:
            m = major.iloc[0]
            st.text_area("Post-incident review", f"""PIR – {m['incident_id']}: {m['title']}
Impact: {len(m['affected_atms'])} ATMs, ~{int(m['customers_affected']):,} customers/day
Detection: heartbeat loss at {m['opened']:%H:%M}; correlated into 1 parent incident
Timeline: detected → acknowledged → ISP/vendor engaged → restored
Root cause: {m['root_cause']}
What went well: correlation prevented {m.get('raw_alerts', 0)} duplicate alerts
Prevention actions: 1) add backup link  2) review UPS capacity  3) update runbook
Owner / due date: ____________""", height=240)


def vendors():
    inv, stt, inc = ui.current_data()
    st.subheader("Vendors, spares & field operations")
    t1, t2, t3, t4, t5 = st.tabs(["Vendor SLA & penalty", "Spare parts", "Contracts & warranty", "Engineers", "Field app & recurring faults"])
    with t1:
        rows = []
        single = inc[(inc["affected_atms"].apply(len) == 1) & (inc["vendor"] != "—")]
        for v in E.VENDORS:
            s = single[single["vendor"] == v]
            br, pen = 0, 0
            for _, r in s.iterrows():
                _, rem, p = E.sla_for(r)
                if rem < 0: br += 1; pen += p
            rows.append({"vendor": v, "SLA hours": E.VENDORS[v]["sla_hours"], "tickets": len(s), "breached": br,
                         "compliance %": round(100 * (1 - br / max(len(s), 1)), 0), "penalty (ETB)": pen})
        vd = pd.DataFrame(rows)
        a, b = st.columns([1.2, 1])
        a.dataframe(vd, hide_index=True, width="stretch")
        fig = px.bar(vd, x="vendor", y="compliance %", color="compliance %", range_color=[0, 100], color_continuous_scale=["#F85149", "#E3B341", "#3FB950"], title="SLA compliance")
        fig.update_layout(coloraxis_showscale=False)
        b.plotly_chart(ui.style(fig, 260), width="stretch")
        st.metric("Total penalty claimable (ETB)", f"{vd['penalty (ETB)'].sum():,}")
        st.markdown("**Penalty calculator**")
        c1, c2, c3 = st.columns(3)
        v = c1.selectbox("Vendor", list(E.VENDORS))
        hrs = c2.number_input("Actual downtime (h)", 0.0, 200.0, 20.0)
        pen = max(0, hrs - E.VENDORS[v]["sla_hours"]) * E.VENDORS[v]["penalty_per_hr"]
        c3.metric("Penalty (ETB)", f"{pen:,.0f}", help=f"SLA {E.VENDORS[v]['sla_hours']} h · ETB {E.VENDORS[v]['penalty_per_hr']}/h beyond SLA")
    with t2:
        sp = E.spare_parts()
        st.metric("Parts at/under reorder level", int((sp["status"] == "Reorder").sum()))
        piv = sp.pivot(index="region", columns="part", values="stock")
        fig = px.imshow(piv, text_auto=True, aspect="auto", color_continuous_scale="YlOrRd_r", title="Stock by region and part")
        st.plotly_chart(ui.style(fig, 340), width="stretch")
        st.dataframe(sp[sp["status"] == "Reorder"], hide_index=True, width="stretch")
    with t3:
        ct = E.contracts()
        ct["state"] = np.where(ct["expires_in_days"] < 60, "🔴 Renew now", np.where(ct["expires_in_days"] < 180, "🟡 Plan renewal", "🟢 OK"))
        st.dataframe(ct.sort_values("expires_in_days"), hide_index=True, width="stretch")
    with t4:
        en = E.engineers()
        st.dataframe(en, hide_index=True, width="stretch",
                     column_config={"first_time_fix_pct": st.column_config.ProgressColumn("first-time fix %", min_value=0, max_value=100, format="%d")})
        fig = px.scatter(en, x="avg_response_min", y="first_time_fix_pct", size="open_tasks", text="engineer", title="Response time vs first-time fix")
        st.plotly_chart(ui.style(fig, 300), width="stretch")
    with t5:
        a, b = st.columns(2)
        with a:
            st.markdown("**Field engineer app (mobile mock-up)**")
            with st.form("field"):
                atm = st.selectbox("Scan ATM QR / pick ATM", stt["atm_id"].tolist())
                st.caption("📍 GPS check-in: " + "within 50 m of ATM ✅")
                part = st.selectbox("Spare part used", ["—"] + E.spare_parts()["part"].unique().tolist())
                note = st.text_area("Work note")
                st.file_uploader("Photo (before/after)", type=["png", "jpg"])
                if st.form_submit_button("Check in & submit", disabled=not ui.can_act()):
                    ui.log_action(st.session_state["user"], f"Field visit logged (part: {part})", atm)
                    st.success("Visit saved (works offline in the real app and syncs later).")
        with b:
            st.markdown("**Recurring-fault detection**")
            st.dataframe(E.recurring_faults(stt), hide_index=True, width="stretch", height=380)
