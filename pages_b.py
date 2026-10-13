"""Network & Services, Cash, Transactions & Customer impact."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import engine as E
import ui


def network():
    inv, stt, inc = ui.current_data()
    th = st.session_state["thresholds"]
    st.subheader("Network, services & channels")
    t1, t2, t3, t4 = st.tabs(["Links & routers", "Correlation (parent → child)", "ISP & SIM", "Servers · channels · POS/CDM/kiosk"])
    with t1:
        up = stt[stt["link_up"]]
        c = st.columns(4)
        ui.kpi(c[0], "Links up", f"{len(up)}/{len(stt)}")
        ui.kpi(c[1], "On backup link", int((stt["active_link"] == "Backup").sum()))
        ui.kpi(c[2], f"Latency > {th['latency_warn']} ms", int((up["latency_ms"] > th["latency_warn"]).sum()))
        ui.kpi(c[3], f"Packet loss > {th['loss_warn']}%", int((stt["packet_loss"].between(th["loss_warn"], 99)).sum()))
        a, b = st.columns(2)
        fig = px.box(up, x="link_type", y="latency_ms", color="link_type", title="Latency by link type (ms)", points="outliers")
        a.plotly_chart(ui.style(fig, 330), width="stretch")
        fig = px.scatter(up, x="bandwidth_util", y="packet_loss", color="link_type", hover_name="atm_id", title="Bandwidth utilisation vs packet loss")
        b.plotly_chart(ui.style(fig, 330), width="stretch")
        rt = stt.groupby(["router_id", "region", "district"]).agg(atms=("atm_id", "count"), link_up=("link_up", "all"),
                                                                 avg_latency=("latency_ms", "mean"), loss=("packet_loss", "mean")).reset_index()
        rt["avg_latency"] = rt["avg_latency"].round(0)
        rt["loss"] = rt["loss"].round(1)
        rt["status"] = np.where(rt["link_up"], "🟢 Up", "🔴 Down")
        st.markdown("**Routers / branch links**")
        st.dataframe(rt.sort_values("link_up")[["router_id", "region", "district", "atms", "status", "avg_latency", "loss"]], hide_index=True,
                     width="stretch", height=300)
    with t2:
        st.caption("One failed router becomes one parent incident instead of many ATM-offline alerts.")
        parents = inc[(inc["category"] == "Network link") & (inc["status"] != "Resolved")]
        if parents.empty:
            st.success("No router-level incidents open.")
        for _, p in parents.iterrows():
            with st.expander(f"{ui.SEV_ICON[p['severity']]} {p['incident_id']} · {p['title']} · {len(p['affected_atms'])} ATMs suppressed as children"):
                st.write(f"Raw alerts collapsed: **{p['raw_alerts']} → 1**")
                st.write(", ".join(p["affected_atms"]))
    with t3:
        d = stt[["atm_id", "region", "isp", "link_type", "sim_balance_etb", "has_backup_link"]].copy()
        d["sim_state"] = np.where(d["link_type"].eq("4G/LTE"), np.where(d["sim_balance_etb"] < 100, "⚠ Top-up needed", "OK"), "n/a")
        c = st.columns(3)
        ui.kpi(c[0], "SIMs needing top-up", int((d["sim_state"] == "⚠ Top-up needed").sum()))
        ui.kpi(c[1], "Sites with backup link", int(d["has_backup_link"].sum()))
        ui.kpi(c[2], "Sites without backup", int((~d["has_backup_link"]).sum()))
        isp = stt.groupby("isp").agg(atms=("atm_id", "count"), uptime=("link_up", "mean"), latency=("latency_ms", "mean"), loss=("packet_loss", "mean")).reset_index()
        isp["uptime"] = (isp["uptime"] * 100).round(1)
        isp["latency"] = isp["latency"].round(0)
        isp["loss"] = isp["loss"].round(2)
        isp["SLA 99%"] = np.where(isp["uptime"] >= 99, "✅ met", "❌ missed")
        st.markdown("**ISP SLA tracking**")
        st.dataframe(isp, hide_index=True, width="stretch")
        st.markdown("**SIM list**")
        st.dataframe(d[d["link_type"] == "4G/LTE"].sort_values("sim_balance_etb"), hide_index=True, width="stretch", height=240)
    with t4:
        sv = E.servers()
        sv["status"] = sv["status"].map({"Healthy": "🟢 Healthy", "Warning": "🟡 Warning"})
        st.markdown("**Servers & core services**")
        st.dataframe(sv, hide_index=True, width="stretch",
                     column_config={"cpu_pct": st.column_config.ProgressColumn("CPU %", min_value=0, max_value=100, format="%d"),
                                    "mem_pct": st.column_config.ProgressColumn("Mem %", min_value=0, max_value=100, format="%d")})
        ch = E.channels()
        a, b = st.columns(2)
        fig = px.bar(ch, x="channel", y="success_rate", color="success_rate", range_color=[96, 100], color_continuous_scale=["#F85149", "#E3B341", "#3FB950"],
                     title="Channel success rate (%)")
        fig.update_layout(coloraxis_showscale=False)
        fig.update_yaxes(range=[94, 100])
        a.plotly_chart(ui.style(fig, 300), width="stretch")
        b.dataframe(ch, hide_index=True, width="stretch")
        pos = E.pos_terminals()
        pos["state"] = np.where(pos["online"], "🟢 Online", "🔴 Offline")
        c = st.columns(4)
        for col, t in zip(c, ["POS", "Cash Deposit Machine", "Passbook Printer", "Self-service Kiosk"]):
            s = pos[pos["type"] == t]
            ui.kpi(col, t, f"{int(s['online'].sum())}/{len(s)} online")
        st.dataframe(pos.sort_values("online")[["terminal_id", "type", "merchant_or_branch", "region", "state", "success_rate", "last_seen_min"]],
                     hide_index=True, width="stretch", height=260)


def cash():
    inv, stt, inc = ui.current_data()
    th = st.session_state["thresholds"]
    st.subheader("Cash management & logistics")
    c = st.columns(5)
    ui.kpi(c[0], "Cash-out", int((stt["cash_state"] == "Cash-out").sum()))
    ui.kpi(c[1], f"Below {th['cash_low']}%", int((stt["cash_pct"] < th["cash_low"]).sum()))
    ui.kpi(c[2], "Cash in network (ETB M)", f"{stt['cash_etb'].sum() / 1e6:,.0f}")
    idle = stt.loc[stt["cash_pct"] > 70, "cash_etb"].sum()
    ui.kpi(c[3], "Idle cash >70% (ETB M)", f"{idle / 1e6:,.0f}")
    ui.kpi(c[4], "Forecast cash-out <24 h", int((stt["hours_to_cashout"] < 24).sum()))

    t1, t2, t3, t4 = st.tabs(["Replenishment tasks & CIT routes", "Forecast", "Cost analytics", "Reconciliation"])
    with t1:
        mult = st.slider("Demand multiplier (holiday / month-end)", 1.0, 2.5, 1.0, 0.1,
                         help="Month-end salary days, market days and holidays burn cash faster")
        s2 = stt.copy()
        s2["daily_cash_burn_pct"] *= mult
        s2["hours_to_cashout"] = (s2["cash_pct"] / s2["daily_cash_burn_pct"] * 24).round(0)
        plan = E.replenishment_plan(s2, th["cash_low"])
        st.caption("Upcoming demand events: " + " · ".join(f"{k} – {v}" for k, v in E.HOLIDAYS.items()))
        cap = st.number_input("Vehicle capacity (ETB million)", 5, 100, 25)
        st.markdown(f"**{len(plan)} replenishment tasks**, grouped by route")
        for route, g in plan.groupby("route"):
            tot = g["load_etb"].sum() / 1e6
            vehicles = int(np.ceil(tot / cap))
            with st.expander(f"🚚 {route} · {len(g)} ATMs · ETB {tot:.1f} M · {vehicles} vehicle(s)"):
                g = g.copy()
                g["stop"] = range(1, len(g) + 1)
                # nearest-neighbour stop order
                remaining = g.to_dict("records"); order = [remaining.pop(0)]
                while remaining:
                    last = order[-1]
                    j = int(np.argmin([(x["lat"] - last["lat"]) ** 2 + (x["lon"] - last["lon"]) ** 2 for x in remaining]))
                    order.append(remaining.pop(j))
                od = pd.DataFrame(order)
                od["stop"] = range(1, len(od) + 1)
                st.dataframe(od[["stop", "atm_id", "branch", "priority", "cash_pct", "hours_to_cashout", "load_etb"]], hide_index=True, width="stretch")
                if st.button("✅ Mark route replenished", key=f"rep_{route}", disabled=not ui.can_act()):
                    for a in od["atm_id"]:
                        st.session_state["cash_over"][a] = 95
                    ui.log_action(st.session_state["user"], "Route replenished", route)
                    ui.notify("Email", "cash-ops@cbe", f"Route {route} replenished ({len(od)} ATMs) – balances confirmed from ATMs")
                    st.rerun()
    with t2:
        d = stt.nsmallest(25, "hours_to_cashout")
        fig = px.bar(d, x="atm_id", y="hours_to_cashout", color="cash_pct", color_continuous_scale="YlOrRd_r", title="Hours until cash-out (25 most at risk)")
        st.plotly_chart(ui.style(fig, 340), width="stretch")
        fig = px.histogram(stt, x="cash_pct", nbins=20, title="Cassette level distribution (avg %)")
        fig.update_traces(marker_color=ui.GOLD)
        st.plotly_chart(ui.style(fig, 280), width="stretch")
    with t3:
        ca = E.cash_analytics(stt)
        ca["cash_total_etb"] = (ca["cash_total_etb"] / 1e6).round(1)
        ca["idle_cash_etb"] = (ca["idle_cash_etb"] / 1e6).round(1)
        fig = px.bar(ca, x="region", y=["cash_total_etb", "idle_cash_etb"], barmode="group", title="Cash vs idle cash by region (ETB million)",
                     color_discrete_sequence=[ui.GOLD, ui.PURPLE])
        st.plotly_chart(ui.style(fig, 340), width="stretch")
        st.dataframe(ca, hide_index=True, width="stretch")
        st.caption("Idle cash = cash sitting in ATMs above 70% fill. Overfilled ATMs tie up capital; frequent cash-outs signal under-filling.")
    with t4:
        rc = E.reconciliation(stt)
        st.dataframe(rc, hide_index=True, width="stretch")
        if (rc["result"] == "MISMATCH").any():
            st.warning(f"{(rc['result'] == 'MISMATCH').sum()} ATM(s) show a variance between cash loaded, dispensed and counted.")


def transactions():
    inv, stt, inc = ui.current_data()
    th = st.session_state["thresholds"]
    st.subheader("Transactions & customer impact")
    t1, t2, t3, t4 = st.tabs(["Success / decline & response codes", "Failed-transaction tracker", "Complaints & customer impact", "Nearest ATM & customer notices"])
    with t1:
        tot = stt["tx_today"].sum()
        c = st.columns(4)
        ui.kpi(c[0], "Tx today", f"{int(tot):,}")
        ui.kpi(c[1], "Avg decline rate", f"{stt['decline_rate'].mean():.1f}%")
        ui.kpi(c[2], "Timeouts", int(stt["timeouts"].sum()))
        ui.kpi(c[3], "Reversals", int(stt["reversals"].sum()))
        rc = E.response_codes()
        fig = px.area(rc[~rc["code"].str.startswith("00")], x="time", y="count", color="code", title="Decline / error response codes – last 24 h")
        st.plotly_chart(ui.style(fig, 320), width="stretch")
        spike = rc[rc["code"].str.startswith("91")].sort_values("count").iloc[-1]
        st.error(f"Spike detected: response code 91 (issuer unavailable) reached {spike['count']} at {spike['time']:%H:%M} – check core-banking interface.")
        hot = stt[stt["decline_rate"] > th["decline_warn"]].sort_values("decline_rate", ascending=False)
        st.markdown(f"**ATMs with decline rate > {th['decline_warn']}%** ({len(hot)})")
        st.dataframe(hot[["atm_id", "region", "district", "decline_rate", "timeouts", "reversals", "tx_today"]], hide_index=True, width="stretch")
    with t2:
        ft = E.failed_transactions(stt)
        ft["status"] = [st.session_state["ft_over"].get(r, s) for r, s in zip(ft["ref"], ft["status"])]
        pend = ft[ft["status"] != "Reversed"]
        c = st.columns(3)
        ui.kpi(c[0], "Open cases", len(pend))
        ui.kpi(c[1], "Amount to reverse (ETB)", f"{pend['amount_etb'].sum():,}")
        ui.kpi(c[2], "Older than 48 h (breach risk)", int((pend["age_hours"] > 48).sum()))
        st.caption("Detected from switch + journal logs: account debited but cash not dispensed / timeout after debit. Card numbers are masked at the collector.")
        st.dataframe(pend.sort_values("age_hours", ascending=False), hide_index=True, width="stretch", height=300)
        a, b = st.columns([3, 1])
        ref = a.selectbox("Case", pend["ref"].tolist(), key="ft_ref")
        if b.button("Create reversal task", disabled=not ui.can_act(), width="stretch"):
            st.session_state["ft_over"][ref] = "Reversed"
            ui.log_action(st.session_state["user"], "Reversal executed", ref)
            ui.notify("Email", "customer-care@cbe", f"{ref}: reversal posted, customer to be informed")
            st.rerun()
    with t3:
        st.markdown("**Complaint ↔ ATM linkage**")
        a, b, c = st.columns(3)
        cid = a.text_input("Complaint / call-centre ID", "CC-48213")
        atm = b.selectbox("ATM named by customer", stt["atm_id"].tolist(), key="cmp_atm")
        when = c.time_input("Time of transaction", value=pd.Timestamp("2026-10-11 14:30").time())
        if st.button("Check ATM status at that time"):
            row = stt[stt["atm_id"] == atm].iloc[0]
            mine = inc[inc["affected_atms"].apply(lambda x: atm in x)]
            if len(mine):
                m = mine.iloc[0]
                st.warning(f"{cid}: {atm} had **{m['incident_id']} – {m['title']}** (opened {m['opened']:%H:%M}). Likely valid claim → route to reversal.")
            else:
                st.success(f"{cid}: no incident recorded for {atm}. ATM state now: {row['state']}.")
            ui.log_action(st.session_state["user"], "Complaint linked", f"{cid} → {atm}")
        st.markdown("**Customer impact of current outages**")
        imp = stt[~stt["online"]].sort_values("customers_affected", ascending=False)
        st.dataframe(imp[["atm_id", "region", "district", "customers_affected", "avg_daily_tx"]], hide_index=True, width="stretch", height=250)
    with t4:
        a, b = st.columns(2)
        with a:
            st.markdown("**Nearest working ATM**")
            reg = st.selectbox("Region", sorted(stt["region"].unique()), key="nn_reg")
            dist = st.selectbox("District", sorted(stt[stt["region"] == reg]["district"].unique()), key="nn_dist")
            here = stt[stt["district"] == dist]
            ok = stt[stt["online"] & (stt["cash_state"] == "OK") & (stt["district"] == dist)]
            st.dataframe(ok[["atm_id", "branch", "cash_pct", "health_score"]].head(6) if len(ok) else pd.DataFrame({"info": ["No working ATM in district"]}),
                         hide_index=True, width="stretch")
            if len(here):
                st.plotly_chart(ui.status_map(here, h=260, size=12), width="stretch")
        with b:
            st.markdown("**Proactive customer notice**")
            bad = stt[(~stt["online"]) | (stt["cash_state"] != "OK")]
            areas = bad.groupby("district").size().sort_values(ascending=False)
            area = st.selectbox("Affected area", areas.index.tolist() if len(areas) else ["—"])
            lang = st.radio("Language", ["English", "አማርኛ"], horizontal=True)
            msg = (f"CBE: Some ATMs in {area} are temporarily unavailable. Please use another ATM, mobile banking or a branch. Sorry for the inconvenience."
                   if lang == "English" else f"የኢትዮጵያ ንግድ ባንክ: በ{area} የሚገኙ አንዳንድ ኤቲኤሞች ለጊዜው አገልግሎት አይሰጡም። እባክዎ ሌላ ኤቲኤም፣ ሞባይል ባንኪንግ ወይም ቅርንጫፍ ይጠቀሙ።")
            st.text_area("Message preview", msg, height=120)
            if st.button("Send via in-app + SMS", disabled=not ui.can_act()):
                ui.notify("SMS (customers)", f"area:{area}", msg[:60] + "…")
                ui.log_action(st.session_state["user"], "Customer notice sent", area)
                st.success("Notice queued for the app feed and SMS gateway.")
