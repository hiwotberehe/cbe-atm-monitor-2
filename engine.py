"""
Simulation engine for the CBE Bank Network & ATM Status Monitoring System.

All data here is SIMULATED (seeded, deterministic) so the demo works without
access to real ATM switches. In production, each function below is replaced by a
read from the collectors / message bus / PostgreSQL / TimescaleDB described in
the architecture (see README).
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

SEED = 2026
NOW = pd.Timestamp("2026-10-11 20:00:00")

# region: (name, amharic, lat, lon, atm_count, districts)
REGIONS = [
    ("Addis Ababa", "አዲስ አበባ", 9.03, 38.74, 70, ["Bole", "Piassa", "Merkato", "Kality", "CMC", "Megenagna"]),
    ("Oromia", "ኦሮሚያ", 8.55, 39.27, 40, ["Adama", "Jimma", "Bishoftu", "Shashemene"]),
    ("Amhara", "አማራ", 11.60, 37.39, 28, ["Bahir Dar", "Gondar", "Dessie"]),
    ("Tigray", "ትግራይ", 13.50, 39.47, 12, ["Mekelle", "Adigrat"]),
    ("SNNPR", "ደቡብ", 6.85, 37.75, 20, ["Hawassa", "Arba Minch", "Wolaita Sodo"]),
    ("Sidama", "ሲዳማ", 6.74, 38.48, 8, ["Hawassa City", "Yirgalem"]),
    ("Somali", "ሶማሌ", 9.35, 42.80, 8, ["Jigjiga", "Gode"]),
    ("Afar", "አፋር", 11.75, 41.00, 6, ["Semera", "Asayita"]),
    ("Dire Dawa", "ድሬዳዋ", 9.60, 41.86, 8, ["Dire Dawa City"]),
    ("Harari", "ሐረሪ", 9.31, 42.12, 4, ["Harar"]),
]

VENDORS = {
    "NCR": {"models": ["SelfServ 84", "SelfServ 66"], "sla_hours": 8, "penalty_per_hr": 150},
    "Diebold Nixdorf": {"models": ["DN 200", "CS 5550"], "sla_hours": 8, "penalty_per_hr": 140},
    "Hyosung": {"models": ["MX 8600", "MX 5600"], "sla_hours": 12, "penalty_per_hr": 100},
    "GRG Banking": {"models": ["H68N", "P2800"], "sla_hours": 12, "penalty_per_hr": 90},
}

COMPONENTS = ["Card Reader", "Cash Dispenser", "Receipt Printer", "Journal Printer",
              "PIN Pad / Encryptor", "Door / Safe Sensor"]
DENOMS = [200, 100, 50, 10]
LINK_TYPES = ["Fiber", "Fiber", "Fiber", "VSAT", "4G/LTE", "Microwave"]
ISPS = ["Ethio Telecom", "Ethio Telecom", "Safaricom ET", "Hughes VSAT"]

AMHARIC = {
    "Overview": "አጠቃላይ እይታ", "NOC Live": "የቀጥታ ክትትል", "ATM Detail": "የኤቲኤም ዝርዝር",
    "Network": "ኔትወርክ", "Cash": "ጥሬ ገንዘብ", "Transactions": "ግብይቶች",
    "Security": "ደህንነት", "Incidents": "ክስተቶች", "Vendors & Field": "አቅራቢዎች",
    "Reports": "ሪፖርቶች", "Admin": "አስተዳደር", "Assistant": "ረዳት",
    "Online": "ግንኙነት ላይ", "Offline": "ከመስመር ውጭ", "Degraded": "የተበላሸ",
    "Low Cash": "ጥሬ ገንዘብ ዝቅተኛ", "Availability": "ተገኝነት",
}


def _rng(offset=0):
    return np.random.default_rng(SEED + offset)


# --------------------------------------------------------------------------
# Inventory + live status
# --------------------------------------------------------------------------
def build_inventory() -> pd.DataFrame:
    rng = _rng(1)
    rows, n = [], 0
    for reg, am, lat, lon, cnt, districts in REGIONS:
        for _ in range(cnt):
            n += 1
            vendor = rng.choice(list(VENDORS), p=[0.4, 0.3, 0.2, 0.1])
            dist = rng.choice(districts)
            spread = 0.35 if reg not in ("Addis Ababa", "Harari", "Dire Dawa") else 0.07
            rows.append({
                "atm_id": f"CBE-{n:04d}",
                "region": reg, "region_am": am, "district": dist,
                "branch": f"{dist} Branch {rng.integers(1, 9)}",
                "lat": lat + rng.normal(0, spread), "lon": lon + rng.normal(0, spread),
                "vendor": vendor, "model": rng.choice(VENDORS[vendor]["models"]),
                "serial": f"SN{rng.integers(10**7, 10**8)}",
                "link_type": rng.choice(LINK_TYPES), "isp": rng.choice(ISPS),
                "sim_balance_etb": int(rng.integers(0, 600)),
                "install_year": int(rng.integers(2014, 2025)),
                "avg_daily_tx": int(rng.integers(80, 700)),
                "router_id": f"RTR-{dist[:3].upper()}-{rng.integers(1, 6)}",
                "has_backup_link": bool(rng.random() < 0.55),
                "os_version": rng.choice(["Win10 IoT 22H2", "Win10 IoT 21H2", "Win7 Embedded"], p=[.6, .3, .1]),
                "app_version": rng.choice(["APTRA 6.4.2", "APTRA 6.3.9", "ProClassic 3.1", "ProClassic 3.0"]),
                "cert_expiry_days": int(rng.integers(5, 400)),
                "baseline_ok": bool(rng.random() > 0.05),
                "antivirus_ok": bool(rng.random() > 0.07),
            })
    return pd.DataFrame(rows)


def build_status(inv: pd.DataFrame) -> pd.DataFrame:
    """Current live state per ATM. Router failures create correlated outages."""
    rng = _rng(2)
    df = inv.copy()
    routers = df["router_id"].unique()
    failed_routers = set(rng.choice(routers, size=max(2, len(routers) // 25), replace=False))
    power_districts = set(rng.choice(df["district"].unique(), size=2, replace=False))

    df["link_up"] = ~df["router_id"].isin(failed_routers)
    df["power_ok"] = ~df["district"].isin(power_districts)
    # a power cut hits ~70% of ATMs in that district (those without UPS life)
    df["power_ok"] &= ~((df["district"].isin(power_districts)) & (rng.random(len(df)) < 0.0))
    df["on_battery"] = df["district"].isin(power_districts) & (rng.random(len(df)) < 0.7)
    df["ups_battery_pct"] = np.where(df["on_battery"], rng.integers(8, 60, len(df)), rng.integers(70, 100, len(df)))
    df["ups_age_months"] = rng.integers(2, 60, len(df))
    df["temp_c"] = np.round(rng.normal(31, 5, len(df)), 1)

    own_fault = rng.random(len(df)) < 0.035
    df["own_fault"] = own_fault
    df["online"] = df["link_up"] & ~(df["on_battery"] & (df["ups_battery_pct"] < 15)) & ~own_fault

    # component health
    for c in COMPONENTS:
        p_bad = {"Card Reader": .05, "Cash Dispenser": .06, "Receipt Printer": .10,
                 "Journal Printer": .04, "PIN Pad / Encryptor": .02, "Door / Safe Sensor": .02}[c]
        r = rng.random(len(df))
        df[c] = np.where(r < p_bad * 0.4, "Fault", np.where(r < p_bad, "Warning", "OK"))
    df.loc[df["atm_id"].isin(df.sample(6, random_state=7)["atm_id"]), "Cash Dispenser"] = "Fault"
    crit = df[COMPONENTS].eq("Fault").any(axis=1)
    warn = df[COMPONENTS].eq("Warning").any(axis=1)

    df["state"] = np.select(
        [~df["online"], crit, warn | (df["on_battery"]) | (df["cert_expiry_days"] < 15)],
        ["Offline", "Out of Service", "Degraded"], default="Online")

    # cassettes
    for d in DENOMS:
        df[f"cass_{d}"] = np.clip(rng.beta(2.2, 1.6, len(df)) * 100, 0, 100).round(0)
    df.loc[df.sample(14, random_state=11).index, [f"cass_{d}" for d in DENOMS]] = 0
    df["cash_pct"] = df[[f"cass_{d}" for d in DENOMS]].mean(axis=1).round(0)
    df["cash_etb"] = (df["cass_200"] * 2000 + df["cass_100"] * 1500 + df["cass_50"] * 1000 + df["cass_10"] * 400).astype(int)
    df["daily_cash_burn_pct"] = np.round(df["avg_daily_tx"] / 40 + rng.normal(0, 1.2, len(df)), 1).clip(2, 25)
    df["hours_to_cashout"] = (df["cash_pct"] / df["daily_cash_burn_pct"] * 24).round(0)
    df["cash_state"] = np.select([df["cash_pct"] <= 5, df["cash_pct"] < 20], ["Cash-out", "Low"], default="OK")

    # network
    base_lat = df["link_type"].map({"Fiber": 18, "Microwave": 35, "4G/LTE": 60, "VSAT": 620})
    df["latency_ms"] = np.where(df["link_up"], (base_lat * rng.uniform(.8, 1.8, len(df))).round(0), np.nan)
    df["packet_loss"] = np.where(df["link_up"], np.round(rng.exponential(0.6, len(df)), 2).clip(0, 12), 100.0)
    df["bandwidth_util"] = np.round(rng.uniform(5, 85, len(df)), 0)
    df["active_link"] = np.where(df["has_backup_link"] & (rng.random(len(df)) < 0.1), "Backup", "Primary")
    df.loc[~df["link_up"] & df["has_backup_link"], ["link_up", "active_link"]] = [True, "Backup"]
    df.loc[df["active_link"].eq("Backup") & df["link_up"], "latency_ms"] = 140
    df["online"] = df["link_up"] & ~(df["on_battery"] & (df["ups_battery_pct"] < 15)) & ~own_fault
    df["state"] = np.where(~df["online"], "Offline", df["state"].where(df["state"] != "Offline", "Degraded"))

    # transactions today
    df["tx_today"] = (df["avg_daily_tx"] * rng.uniform(.6, 1.2, len(df)) * (df["online"])).astype(int)
    df["decline_rate"] = np.round(rng.beta(2, 30, len(df)) * 100, 1)
    df.loc[df.sample(8, random_state=5).index, "decline_rate"] = rng.uniform(18, 40, 8).round(1)
    df["timeouts"] = rng.poisson(2, len(df))
    df["reversals"] = rng.poisson(1.2, len(df))

    # health score
    score = (100
             - (~df["online"]) * 45
             - df[COMPONENTS].eq("Fault").sum(axis=1) * 15
             - df[COMPONENTS].eq("Warning").sum(axis=1) * 5
             - (df["decline_rate"] > 12) * 10
             - (df["packet_loss"].clip(0, 10)) * 1.5
             - (df["cash_state"] == "Cash-out") * 8
             - (2026 - df["install_year"]) * 0.8
             - (df["ups_age_months"] > 48) * 4)
    df["health_score"] = score.clip(0, 100).round(0).astype(int)
    df["customers_affected"] = np.where(df["online"], 0, df["avg_daily_tx"] // 2)
    return df


# --------------------------------------------------------------------------
# Incidents with correlation, SLA
# --------------------------------------------------------------------------
def build_incidents(st_df: pd.DataFrame) -> pd.DataFrame:
    """Correlate offline ATMs into parent incidents (one per root cause)."""
    rng = _rng(3)
    inc, n = [], 1000
    off = st_df[~st_df["online"]]

    # link failures -> one incident per router
    for rid, g in off[~off["link_up"] | off["router_id"].isin(st_df.loc[~st_df["link_up"], "router_id"])].groupby("router_id"):
        n += 1
        inc.append(_inc(n, "Critical" if len(g) >= 3 else "Major", f"Router {rid} unreachable",
                        "Network link", g, rng, root="LINK_DOWN"))
    # power
    pw = off[off["on_battery"] & (off["ups_battery_pct"] < 15)]
    for dist, g in pw.groupby("district"):
        n += 1
        inc.append(_inc(n, "Critical" if len(g) >= 3 else "Major", f"Grid power outage – {dist}", "Power", g, rng, root="POWER"))
    # device faults
    for _, r in off[off["own_fault"]].iterrows():
        n += 1
        inc.append(_inc(n, "Major", f"{r.atm_id} not responding", "ATM device", r.to_frame().T, rng, root="DEVICE"))
    # component faults on online ATMs
    for _, r in st_df[st_df["online"] & (st_df["state"] == "Out of Service")].iterrows():
        comp = [c for c in COMPONENTS if r[c] == "Fault"][0]
        n += 1
        inc.append(_inc(n, "Major", f"{comp} fault – {r.atm_id}", "ATM component", r.to_frame().T, rng, root="COMPONENT"))
    # cash-outs
    for _, r in st_df[(st_df["cash_state"] == "Cash-out") & st_df["online"]].iterrows():
        n += 1
        inc.append(_inc(n, "Minor", f"Cash-out – {r.atm_id}", "Cash", r.to_frame().T, rng, root="CASH_OUT"))
    # tamper / security
    for _, r in st_df[(~st_df["baseline_ok"])].head(3).iterrows():
        n += 1
        inc.append(_inc(n, "Critical", f"Config differs from baseline – {r.atm_id}", "Security", r.to_frame().T, rng, root="SECURITY"))

    df = pd.DataFrame(inc)
    if df.empty:
        return df
    df["raw_alerts"] = df["affected_atms"].apply(lambda x: len(x) * 3 + 1)
    return df.sort_values(["sev_rank", "opened"]).reset_index(drop=True)


SEV = {"Critical": 0, "Major": 1, "Minor": 2, "Info": 3}


def _inc(n, sev, title, cat, g, rng, root):
    opened = NOW - pd.Timedelta(minutes=int(rng.integers(8, 520)))
    return {
        "incident_id": f"INC-{n}", "severity": sev, "sev_rank": SEV[sev], "title": title, "category": cat,
        "affected_atms": list(g["atm_id"]), "region": g["region"].iloc[0], "district": g["district"].iloc[0],
        "vendor": g["vendor"].iloc[0] if len(g) == 1 else "—",
        "opened": opened, "status": "Open", "assignee": "Unassigned", "root_cause": root,
        "customers_affected": int(g["customers_affected"].sum()),
    }


def sla_for(incident_row, vendors=VENDORS):
    """SLA hours + penalty for a single-ATM incident."""
    v = incident_row["vendor"]
    hours = vendors[v]["sla_hours"] if v in vendors else 6
    elapsed = (NOW - incident_row["opened"]).total_seconds() / 3600
    remaining = hours - elapsed
    breach_h = max(0, -remaining)
    penalty = breach_h * vendors[v]["penalty_per_hr"] if v in vendors else 0
    return hours, remaining, round(penalty)


# --------------------------------------------------------------------------
# Time series
# --------------------------------------------------------------------------
def tx_series(atm_id: str, hours=24) -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(atm_id.encode()))
    idx = pd.date_range(end=NOW, periods=hours, freq="h")
    base = 20 + 15 * np.clip(np.sin((np.asarray(idx.hour) - 9) / 24 * 2 * np.pi), -0.3, 1)
    ok = (base * rng.uniform(.7, 1.2, hours)).round()
    return pd.DataFrame({"time": idx, "success": ok, "declined": (ok * rng.uniform(.02, .12, hours)).round(),
                         "errors": rng.poisson(0.8, hours)})


def network_series(days=30) -> pd.DataFrame:
    rng = _rng(9)
    idx = pd.date_range(end=NOW.normalize(), periods=days, freq="D")
    avail = np.clip(98.2 + rng.normal(0, 0.9, days), 94, 99.9)
    return pd.DataFrame({"date": idx, "availability": avail.round(2),
                         "mttr_h": np.clip(rng.normal(4.8, 1.3, days), 1.5, 10).round(1),
                         "incidents": rng.poisson(14, days)})


def region_trend(st_df):
    g = st_df.groupby("region").agg(atms=("atm_id", "count"), online=("online", "sum"),
                                    avg_health=("health_score", "mean"),
                                    cash_low=("cash_state", lambda s: (s != "OK").sum()),
                                    customers_affected=("customers_affected", "sum")).reset_index()
    g["availability"] = (g["online"] / g["atms"] * 100).round(1)
    g["avg_health"] = g["avg_health"].round(0)
    return g


# --------------------------------------------------------------------------
# Failed-transaction tracker (debited, not dispensed)
# --------------------------------------------------------------------------
def failed_transactions(st_df: pd.DataFrame, n=40) -> pd.DataFrame:
    rng = _rng(4)
    atms = st_df.sample(n, random_state=21, replace=True)["atm_id"].values
    amounts = rng.choice([500, 1000, 2000, 3000, 5000, 8000], n)
    types = rng.choice(["Debited – cash not dispensed", "Timeout after debit", "Partial dispense", "Double debit"], n,
                       p=[.45, .3, .15, .1])
    age = rng.integers(1, 72, n)
    df = pd.DataFrame({
        "ref": [f"FT-{100000 + i}" for i in range(n)], "atm_id": atms,
        "card_masked": [f"4***-****-****-{rng.integers(1000, 9999)}" for _ in range(n)],
        "type": types, "amount_etb": amounts, "age_hours": age,
        "status": rng.choice(["Reversal pending", "Reversed", "Under review"], n, p=[.5, .35, .15]),
        "complaint_id": [f"CC-{rng.integers(10000, 99999)}" if rng.random() < .4 else "" for _ in range(n)],
    })
    return df


# --------------------------------------------------------------------------
# Security events + unusual activity
# --------------------------------------------------------------------------
def security_events(st_df: pd.DataFrame, n=30) -> pd.DataFrame:
    rng = _rng(5)
    kinds = ["Card reader tamper sensor", "Unexpected device attached", "Door open (unscheduled)",
             "Safe opened outside CIT window", "Vibration / tilt detected", "Alarm triggered",
             "Multiple failed PIN attempts", "Repeated withdrawals just under limit", "Transaction spike",
             "Firmware differs from baseline"]
    sev = {"Card reader tamper sensor": "Critical", "Unexpected device attached": "Critical",
           "Door open (unscheduled)": "Major", "Safe opened outside CIT window": "Critical",
           "Vibration / tilt detected": "Major", "Alarm triggered": "Critical",
           "Multiple failed PIN attempts": "Major", "Repeated withdrawals just under limit": "Major",
           "Transaction spike": "Minor", "Firmware differs from baseline": "Critical"}
    k = rng.choice(kinds, n)
    ts = [NOW - pd.Timedelta(minutes=int(m)) for m in rng.integers(3, 1400, n)]
    df = pd.DataFrame({"time": ts, "atm_id": rng.choice(st_df["atm_id"], n), "event": k,
                       "severity": [sev[x] for x in k],
                       "status": rng.choice(["New", "Investigating", "Closed"], n, p=[.5, .3, .2])})
    return df.sort_values("time", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Vendor / spares / contracts / engineers
# --------------------------------------------------------------------------
def spare_parts() -> pd.DataFrame:
    rng = _rng(6)
    parts = ["Card reader", "Dispenser module", "Receipt printer", "Journal printer", "PIN pad", "UPS battery", "Router", "Fan unit"]
    rows = []
    for reg, *_ in REGIONS[:6]:
        for p in parts:
            rows.append({"region": reg, "part": p, "stock": int(rng.integers(0, 14)), "reorder_at": 3,
                         "used_30d": int(rng.integers(0, 9))})
    df = pd.DataFrame(rows)
    df["status"] = np.where(df["stock"] <= df["reorder_at"], "Reorder", "OK")
    return df


def contracts() -> pd.DataFrame:
    rng = _rng(7)
    rows = []
    for v, d in VENDORS.items():
        for kind in ["Maintenance contract", "Software license"]:
            rows.append({"vendor": v, "item": kind, "expires_in_days": int(rng.integers(12, 540)),
                         "sla_hours": d["sla_hours"], "penalty_etb_per_hr": d["penalty_per_hr"]})
    return pd.DataFrame(rows)


def engineers() -> pd.DataFrame:
    rng = _rng(8)
    names = ["Abel T.", "Selam M.", "Dawit K.", "Meron A.", "Yonas B.", "Hanna G.", "Kidus W.", "Bethel S."]
    return pd.DataFrame({
        "engineer": names, "region": rng.choice([r[0] for r in REGIONS[:6]], len(names)),
        "avg_response_min": rng.integers(25, 140, len(names)),
        "first_time_fix_pct": rng.integers(62, 96, len(names)),
        "repeat_visit_pct": rng.integers(3, 22, len(names)),
        "open_tasks": rng.integers(0, 6, len(names)),
    })


# --------------------------------------------------------------------------
# Cash logistics
# --------------------------------------------------------------------------
HOLIDAYS = {"2026-10-31": "Month-end salary", "2026-11-13": "Ethiopian holiday (demo)", "2026-09-27": "Meskel"}


def replenishment_plan(st_df: pd.DataFrame, threshold=20, horizon_h=36) -> pd.DataFrame:
    need = st_df[(st_df["cash_pct"] < threshold) | (st_df["hours_to_cashout"] < horizon_h)].copy()
    need = need[need["online"]]
    need["priority"] = np.select([need["cash_pct"] <= 5, need["hours_to_cashout"] < 12], ["Urgent", "High"], default="Normal")
    need["load_etb"] = ((100 - need["cash_pct"]) / 100 * 3_500_000).round(-4).astype(int)
    need["route"] = need["region"] + " – " + need["district"]
    need["_p"] = need["priority"].map({"Urgent": 0, "High": 1, "Normal": 2})
    return need.sort_values(["_p", "hours_to_cashout"]).drop(columns="_p")


def cash_analytics(st_df):
    d = st_df.copy()
    d["idle_cash_etb"] = np.where(d["cash_pct"] > 70, d["cash_etb"], 0)
    return d.groupby("region").agg(cash_total_etb=("cash_etb", "sum"), idle_cash_etb=("idle_cash_etb", "sum"),
                                   cashouts=("cash_state", lambda s: (s == "Cash-out").sum())).reset_index()


def reconciliation(st_df, n=12):
    rng = _rng(10)
    s = st_df.sample(n, random_state=3)
    loaded = rng.integers(2_000_000, 4_000_000, n) // 10000 * 10000
    dispensed = (loaded * rng.uniform(.4, .85, n)) // 10000 * 10000
    mismatch = np.where(rng.random(n) < .2, rng.choice([-20000, -10000, 10000, 30000], n), 0)
    remaining = loaded - dispensed + mismatch
    return pd.DataFrame({"atm_id": s["atm_id"].values, "loaded_etb": loaded.astype(int), "dispensed_etb": dispensed.astype(int),
                         "counted_remaining_etb": remaining.astype(int), "variance_etb": mismatch.astype(int),
                         "result": np.where(mismatch == 0, "Balanced", "MISMATCH")})


# --------------------------------------------------------------------------
# Natural-language assistant (rule based)
# --------------------------------------------------------------------------
def nl_query(q: str, st_df: pd.DataFrame):
    ql = q.lower()
    df = st_df.copy()
    notes = []
    for reg in [r[0] for r in REGIONS]:
        if reg.lower() in ql:
            df = df[df["region"] == reg]; notes.append(f"region = {reg}")
    for v in VENDORS:
        if v.lower() in ql:
            df = df[df["vendor"] == v]; notes.append(f"vendor = {v}")
    if "offline" in ql:
        df = df[~df["online"]]; notes.append("offline")
    elif "degraded" in ql:
        df = df[df["state"] == "Degraded"]; notes.append("degraded")
    elif "out of service" in ql:
        df = df[df["state"] == "Out of Service"]; notes.append("out of service")
    elif "online" in ql:
        df = df[df["online"]]; notes.append("online")
    if "low cash" in ql or "cash-out" in ql or "cash out" in ql or "no cash" in ql:
        df = df[df["cash_state"] != "OK"]; notes.append("low / no cash")
    if "vsat" in ql: df = df[df["link_type"] == "VSAT"]; notes.append("VSAT link")
    if "battery" in ql or "power" in ql: df = df[df["on_battery"]]; notes.append("on battery / power issue")
    if "tamper" in ql or "baseline" in ql: df = df[~df["baseline_ok"]]; notes.append("baseline mismatch")
    if "worst" in ql or "health" in ql: df = df.sort_values("health_score").head(15); notes.append("lowest health score")
    return df, notes


# --------------------------------------------------------------------------
# Servers, channels, POS, response codes, timeline, predictive risk
# --------------------------------------------------------------------------
def servers() -> pd.DataFrame:
    rng = _rng(12)
    rows = [("ATM Switch (primary)", "Switch"), ("ATM Switch (DR)", "Switch"), ("Core Banking Interface", "Integration"),
            ("HSM Cluster", "Security"), ("Card Management DB", "Database"), ("Monitoring DB (PostgreSQL)", "Database"),
            ("Time-series DB", "Database"), ("Message Bus (Kafka)", "Middleware"), ("App Server 01", "Application"),
            ("App Server 02", "Application")]
    out = []
    for name, kind in rows:
        cpu, mem = int(rng.integers(18, 78)), int(rng.integers(30, 82))
        st = "Healthy"
        if name == "App Server 02": cpu, st = 91, "Warning"
        out.append({"service": name, "type": kind, "cpu_pct": cpu, "mem_pct": mem,
                    "response_ms": int(rng.integers(8, 160)), "status": st})
    return pd.DataFrame(out)


def channels() -> pd.DataFrame:
    rng = _rng(13)
    rows = [("ATM", 98.1), ("POS", 97.4), ("Mobile Banking", 99.3), ("Internet Banking", 99.6), ("USSD", 98.8),
            ("Agent Banking", 96.9), ("CBE Birr", 99.1)]
    return pd.DataFrame({"channel": [r[0] for r in rows], "success_rate": [r[1] for r in rows],
                         "avg_response_ms": rng.integers(180, 1400, len(rows)),
                         "error_rate": [round(100 - r[1], 1) for r in rows],
                         "tx_per_min": rng.integers(40, 900, len(rows))})


def pos_terminals(n=60) -> pd.DataFrame:
    rng = _rng(14)
    types = rng.choice(["POS", "Cash Deposit Machine", "Passbook Printer", "Self-service Kiosk"], n, p=[.6, .15, .15, .1])
    online = rng.random(n) > 0.09
    return pd.DataFrame({"terminal_id": [f"T-{3000 + i}" for i in range(n)], "type": types,
                         "merchant_or_branch": [f"Merchant {i % 17 + 1}" if t == "POS" else f"Branch {i % 12 + 1}" for i, t in enumerate(types)],
                         "region": rng.choice([r[0] for r in REGIONS], n), "online": online,
                         "success_rate": np.where(online, rng.uniform(90, 99.8, n), 0).round(1),
                         "last_seen_min": np.where(online, rng.integers(0, 4, n), rng.integers(30, 600, n))})


def response_codes(hours=24) -> pd.DataFrame:
    rng = _rng(15)
    idx = pd.date_range(end=NOW, periods=hours, freq="h")
    codes = {"00 Approved": 900, "51 Insufficient funds": 45, "55 Wrong PIN": 22, "91 Issuer unavailable": 6,
             "96 System malfunction": 4, "05 Do not honor": 12}
    rows = []
    for i, t in enumerate(idx):
        for c, b in codes.items():
            v = rng.poisson(b / 6)
            if c.startswith("91") and i in (hours - 5, hours - 4, hours - 3): v += 38  # spike
            rows.append({"time": t, "code": c, "count": int(v)})
    return pd.DataFrame(rows)


def timeline(atm_row) -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(atm_row["atm_id"].encode()) + 1)
    evs = [("Heartbeat OK", "Info"), ("Cassette level updated", "Info"), ("Link latency spike", "Minor"),
           ("Receipt printer low paper", "Minor"), ("Card reader retry", "Minor"), ("Replenishment confirmed", "Info"),
           ("Door opened (CIT window)", "Info"), ("Service restarted (auto-remediation)", "Info")]
    rows = [(NOW - pd.Timedelta(minutes=int(m)), *evs[rng.integers(0, len(evs))]) for m in sorted(rng.integers(5, 2800, 10))]
    if not atm_row["online"]:
        rows.append((NOW - pd.Timedelta(minutes=int(rng.integers(8, 120))), "Heartbeat missed – ATM marked OFFLINE", "Critical"))
    return pd.DataFrame(rows, columns=["time", "event", "severity"]).sort_values("time", ascending=False)


def failure_risk(st_df: pd.DataFrame) -> pd.DataFrame:
    """Simple explainable predictive-maintenance score (0-100)."""
    d = st_df.copy()
    age = (2026 - d["install_year"]).clip(0, 12) / 12
    d["risk_score"] = (35 * age + 20 * d[COMPONENTS].eq("Warning").sum(axis=1).clip(0, 3) / 3
                       + 20 * (d["timeouts"].clip(0, 8) / 8) + 15 * (d["decline_rate"].clip(0, 30) / 30)
                       + 10 * (d["ups_age_months"] > 48)).round(0)
    d["likely_part"] = d[COMPONENTS[:4]].apply(lambda r: next((c for c in COMPONENTS[:4] if r[c] == "Warning"), "Card Reader" if age.mean() else "—"), axis=1)
    return d.sort_values("risk_score", ascending=False)


def tx_anomalies(st_df: pd.DataFrame) -> pd.DataFrame:
    d = st_df[st_df["online"]].copy()
    mu, sd = d["tx_today"].mean(), d["tx_today"].std()
    d["z_vs_peers"] = ((d["tx_today"] - mu) / sd).round(2)
    d["unusual"] = (d["z_vs_peers"].abs() > 2) | (d["decline_rate"] > 15)
    return d[d["unusual"]].sort_values("z_vs_peers", ascending=False)


def recurring_faults(st_df: pd.DataFrame, n=10) -> pd.DataFrame:
    rng = _rng(16)
    s = st_df.sample(n, random_state=17)
    return pd.DataFrame({"atm_id": s["atm_id"].values, "model": s["model"].values, "install_year": s["install_year"].values,
                         "same_fault_30d": rng.integers(3, 9, n),
                         "fault": rng.choice(["Cash dispenser jam", "Card reader error", "Link flapping", "Receipt printer"], n),
                         "recommendation": np.where(s["install_year"].values < 2018, "Replace unit", "Vendor deep-service / relocate")})
