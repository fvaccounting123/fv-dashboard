import streamlit as st
import pandas as pd
import datetime
import ssl
import urllib.request
import plotly.express as px
import os

st.set_page_config(page_title="FVA | Dashboard", layout="wide")

# --- COMPANY LOGO ENGINE ---
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

st.title("First Valley Accounting | Dashboard")

# --- SIDEBAR ACCESS CONTROL ---
st.sidebar.header("Access Control")
admin_password = st.sidebar.text_input("Enter Admin Password", type="password")
is_admin = (admin_password.strip().upper() == "FV2026")

if is_admin:
    st.sidebar.success("Admin Access Granted")
elif admin_password:
    st.sidebar.error("Incorrect Password")

# --- CONNECT TO MASTER GOOGLE SHEET ---
SHEET_ID = "1maGLtLBdDj7_uxFoeMMuvqEU5pLfdwH6mGrhx9V4B-c"
REVENUE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=2026"
RATES_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Employee+Hourly+Rates"
CLOCKIFY_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Clockify_Data"

context = ssl._create_unverified_context()

try:
    master_clockify = pd.read_csv(urllib.request.urlopen(CLOCKIFY_URL, context=context))
    revenue_sheet = pd.read_csv(urllib.request.urlopen(REVENUE_URL, context=context))
    rates_sheet = pd.read_csv(urllib.request.urlopen(RATES_URL, context=context))
except Exception as e:
    st.error(f"Google Sheet Data Load Error: {e}")
    st.stop()

revenue_sheet.columns = revenue_sheet.columns.str.strip()
rates_sheet.columns = rates_sheet.columns.str.strip()
master_clockify.columns = master_clockify.columns.str.strip()

# Format and parse Clockify dates automatically from the sheet tab
master_clockify['Parsed Date'] = pd.to_datetime(master_clockify['Start Date'], errors='coerce')
master_clockify = master_clockify.dropna(subset=['Parsed Date'])

# --- AUTOMATED PREVIOUS MONTH CALCULATION ---
today = datetime.date.today()
first_this_month = today.replace(day=1)
last_prev_month = first_this_month - datetime.timedelta(days=1)
first_prev_month = last_prev_month.replace(day=1)

min_log_date = master_clockify['Parsed Date'].min().date()
max_log_date = master_clockify['Parsed Date'].max().date()

st.markdown("### Filter Dashboard Scope")
selected_range = st.date_input(
    "Select custom date window to analyze:",
    value=(first_prev_month, last_prev_month), 
    min_value=min_log_date,
    max_value=max_log_date
)

if isinstance(selected_range, tuple) and len(selected_range) == 2:
    focus_start, focus_end = selected_range
    focus_start_dt = pd.to_datetime(focus_start)
    focus_end_dt = pd.to_datetime(focus_end)
    
    month_clockify = master_clockify[
        (master_clockify['Parsed Date'] >= focus_start_dt) & 
        (master_clockify['Parsed Date'] <= focus_end_dt)
    ]
    
    active_months = []
    curr = focus_start_dt.replace(day=1)
    while curr <= focus_end_dt:
        active_months.append(curr.strftime('%Y-%m-%01'))
        if curr.month == 12:
            curr = curr.replace(year=curr.year + 1, month=1)
        else:
            curr = curr.replace(month=curr.month + 1)
            
    client_col_name = next((c for c in revenue_sheet.columns if 'client' in c.lower()), revenue_sheet.columns[1])
    commit_col_name = next((c for c in rates_sheet.columns if 'commit' in c.lower() or 'comit' in c.lower()), "Commitment")
    
    def safe_float(value):
        try:
            if pd.isna(value): return 0.0
            cleaned = str(value).replace('$', '').replace(',', '').strip()
            return float(cleaned) if cleaned else 0.0
        except: return 0.0
        
    rev_date_map = {pd.to_datetime(col, errors='coerce').strftime('%Y-%m-%01'): col for col in revenue_sheet.columns if pd.notnull(pd.to_datetime(col, errors='coerce'))}
    rates_date_map = {pd.to_datetime(col, errors='coerce').strftime('%Y-%m-%01'): col for col in rates_sheet.columns if pd.notnull(pd.to_datetime(col, errors='coerce'))}
    
    internal_mask = month_clockify['Client'].str.strip().str.lower() == 'internal'
    client_df = month_clockify[~internal_mask]
    
    clockify_summary = pd.DataFrame(columns=['Client', 'Hours_Spent', 'Labor_Cost', 'match_key'])
    if not client_df.empty:
        c_sum = client_df.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
        rates_map = {}
        matching_rate_cols = [rates_date_map.get(m) for m in active_months if rates_date_map.get(m)]
