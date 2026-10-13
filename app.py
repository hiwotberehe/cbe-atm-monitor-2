"""CBE Bank Network & ATM Status Monitoring System – Streamlit app."""
import base64

import streamlit as st

import engine as E
import pages_a, pages_b, pages_c, pages_d
import ui

st.set_page_config(page_title="CBE Network & ATM Monitor", page_icon="assets/emblem.png", layout="wide", initial_sidebar_state="expanded")
ui.init_state()

st.markdown("""
<style>
.block-container {padding-top: 3.2rem; max-width: 1500px;}
[data-testid="stMetric"] {background: rgba(155,25,134,.16); border: 1px solid rgba(212,165,55,.35); border-radius: 10px; padding: 10px 14px;}
[data-testid="stMetricValue"] {color:#D4A537;}
.cbe-head {background: linear-gradient(90deg,#9B1986 0%,#9B1986 22%,#5E0F55 100%); border-radius: 12px; padding: 6px 18px 6px 6px; display:flex; align-items:center; gap:18px; border:1px solid rgba(212,165,55,.5); margin-bottom: 14px;}
.cbe-head img {height: 92px; border-radius: 8px;}
.cbe-head h1 {margin:0; font-size:1.45rem; color:#F5EDE0; line-height:1.15;}
.cbe-head p {margin:0; color:#D4A537; font-size:.85rem;}
.stTabs [aria-selected="true"] {color:#D4A537 !important;}
</style>""", unsafe_allow_html=True)

PAGES = {"Overview": pages_a.overview, "NOC Live": pages_a.noc, "ATM Detail": pages_a.atm_detail, "Network": pages_b.network,
         "Cash": pages_b.cash, "Transactions": pages_b.transactions, "Security": pages_c.security, "Incidents": pages_c.incidents,
         "Vendors & Field": pages_c.vendors, "Reports": pages_d.reports, "Admin": pages_d.admin, "Assistant": pages_d.assistant}
ICONS = {"Overview": "📊", "NOC Live": "🗺️", "ATM Detail": "🏧", "Network": "🌐", "Cash": "💵", "Transactions": "💳", "Security": "🛡️",
         "Incidents": "🚨", "Vendors & Field": "🧰", "Reports": "📄", "Admin": "⚙️", "Assistant": "🤖"}

with st.sidebar:
    st.image("assets/logo_full.png", width="stretch")
    lang = st.radio("Language / ቋንቋ", ["English", "አማርኛ"], horizontal=True)
    role = st.selectbox("Signed in as (demo role)", list(ui.ROLES), key="role")
    st.session_state["user"] = role
    if ui.ROLES[role]["scope"] == "region":
        st.selectbox("My region", [r[0] for r in E.REGIONS], key="region_scope")
    allowed = list(PAGES) if ui.ROLES[role]["pages"] == "all" else ui.ROLES[role]["pages"]
    label = lambda p: f"{ICONS[p]} {E.AMHARIC.get(p, p) if lang != 'English' else p}"
    page = st.radio("Navigation", allowed, format_func=label, label_visibility="collapsed")
    st.toggle("Plain map (no basemap tiles)", key="plain_map", help="Use if the network blocks map tiles; pins are drawn on a plain lat/lon grid")
    st.divider()
    st.caption("Demo build · simulated data\nProduction: collectors → message bus → API")

st.markdown(f"""<div class="cbe-head"><img src="data:image/png;base64,{base64.b64encode(open('assets/logo_header.png','rb').read()).decode()}">
<div><h1>Bank Network &amp; ATM Status Monitoring System</h1>
<p>Commercial Bank of Ethiopia · የኢትዮጵያ ንግድ ባንክ · {role}{' – ' + st.session_state['region_scope'] if ui.ROLES[role]['scope']=='region' else ''}</p></div></div>""", unsafe_allow_html=True)

PAGES[page]()
