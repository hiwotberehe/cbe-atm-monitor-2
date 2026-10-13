# CBE Bank Network & ATM Status Monitoring System

Streamlit demo for the Commercial Bank of Ethiopia internship project. It runs on **simulated data** (seeded, deterministic), so it works anywhere without access to real ATM switches. `engine.py` is the only place data is produced; in production each function is replaced by a read from the collectors / message bus / PostgreSQL / TimescaleDB.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud (free)
1. Create a GitHub repo and upload everything in this folder (keep `assets/` and `.streamlit/`).
2. Go to https://share.streamlit.io → **Create app** → pick the repo, branch `main`, main file `app.py`.
3. Deploy. The build installs `requirements.txt` automatically. You get a public `*.streamlit.app` link.

## Pages
Overview · NOC Live (map, incidents, event simulator) · ATM Detail · Network (links, correlation, ISP/SIM, servers, channels, POS/CDM/kiosk) · Cash (replenishment, CIT routes, forecast, reconciliation) · Transactions (response codes, failed-transaction tracker, complaints, customer notices) · Security · Incidents (SLA, runbooks, maintenance windows, PIR) · Vendors & Field · Reports (Excel/PDF/CSV, NBE pack, scheduled) · Admin (inventory, RBAC, thresholds, audit log, integrations, architecture) · Assistant (natural-language search, predictive maintenance, capacity, cost).

## Files
- `app.py` shell, theme, navigation, roles · `engine.py` simulation · `ui.py` shared helpers · `pages_a..d.py` pages
- `assets/` CBE logo files · `.streamlit/config.toml` theme

Note: plotly is pinned `<7` because Streamlit's front-end does not yet draw plotly 7 scatter traces.
