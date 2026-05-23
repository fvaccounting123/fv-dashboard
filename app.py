import streamlit as st
import pandas as pd
import datetime
import ssl
import urllib.request
import plotly.express as px

st.set_page_config(page_title="FV | Master Dashboard", layout="wide")
st.title("📊 First Valley | Master Profitability Dashboard")

# --- SIDEBAR ACCESS CONTROL ---
st.sidebar.header("🔑 Access Control")
admin_password = st.sidebar.text_input("Enter Admin Password", type="password")

is_admin = (admin_password.strip().upper() == "FV2026")

if is_admin:
    st.sidebar.success("🔓 Admin Access Granted")
elif admin_password:
    st.sidebar.error("❌ Incorrect Password")

# --- FILE UPLOADER ---
uploaded_files = st.file_uploader("📥 Drag and drop Clockify CSV files here", type=["csv"], accept_multiple_files=True)

if uploaded_files:
    all_months_data = []
    for file in uploaded_files:
        try:
            df = pd.read_csv(file)
            df['Parsed Date'] = pd.to_datetime(df['Start Date'], errors='coerce')
            df['Report Column'] = df['Parsed Date'].dt.strftime('%Y-%m-01')
            all_months_data.append(df)
        except:
            st.error(f"Error reading {file.name}")
            
    if all_months_data:
        master_clockify = pd.concat(all_months_data, ignore_index=True)
        
        min_log_date = master_clockify['Parsed Date'].min().date()
        max_log_date = master_clockify['Parsed Date'].max().date()
        
        st.markdown("### 📅 Filter Dashboard Scope")
        selected_range = st.date_input(
            "Select custom date window to analyze:",
            value=(min_log_date, max_log_date),
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
            
            SHEET_ID = "1maGLtLBdDj7_uxFoeMMuvqEU5pLfdwH6mGrhx9V4B-c"
            REVENUE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=2026"
            RATES_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Employee+Hourly+Rates"
            
            try:
                context = ssl._create_unverified_context()
                revenue_sheet = pd.read_csv(urllib.request.urlopen(REVENUE_URL, context=context))
                rates_sheet = pd.read_csv(urllib.request.urlopen(RATES_URL, context=context))
                
                revenue_sheet.columns = revenue_sheet.columns.str.strip()
                rates_sheet.columns = rates_sheet.columns.str.strip()
                
                client_col_name = next((c for c in revenue_sheet.columns if 'client' in c.lower()), revenue_sheet.columns[1])
                freq_col_name = next((c for c in revenue_sheet.columns if 'freq' in c.lower()), 'Frequency')
                
                rev_date_map = {}
                for col in revenue_sheet.columns:
                    parsed = pd.to_datetime(col, errors='coerce')
                    if pd.notnull(parsed):
                        rev_date_map[parsed.strftime('%Y-%m-%01')] = col

                rates_date_map = {}
                for col in rates_sheet.columns:
                    parsed = pd.to_datetime(col, errors='coerce')
                    if pd.notnull(parsed):
                        rates_date_map[parsed.strftime('%Y-%m-%01')] = col
                
                internal_mask = month_clockify['Client'].str.strip().str.lower() == 'internal'
                client_df = month_clockify[~internal_mask]
                
                # 1. Compute basic clockify summaries if entries exist
                clockify_summary = pd.DataFrame(columns=['Client', 'Hours_Spent', 'Labor_Cost', 'match_key'])
                if not client_df.empty:
                    c_sum = client_df.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
                    
                    rates_map = {}
                    matching_rate_cols = [rates_date_map.get(m) for m in active_months if rates_date_map.get(m)]
                    
                    if matching_rate_cols:
                        for idx, row in rates_sheet.iterrows():
                            u_name = str(row['User']).strip()
                            vals = []
                            for c in matching_rate_cols:
                                try:
                                    v = str(row[c]).replace('$', '').replace(',', '').strip()
                                    vals.append(float(v))
                                except: pass
                            rates_map[u_name] = sum(vals) / len(vals) if vals else 15.0
                    
                    c_sum['Cost Rate'] = c_sum['User'].str.strip().map(rates_map).fillna(15.0)
                    c_sum['Total Cost'] = c_sum['Duration (decimal)'].astype(float) * c_sum['Cost Rate']
                    
                    clockify_summary = c_sum.groupby('Client').agg(Hours_Spent=('Duration (decimal)', 'sum'), Labor_Cost=('Total Cost', 'sum')).reset_index()
                    clockify_summary['match_key'] = clockify_summary['Client'].str.strip().str.lower()
                
                # 2. Extract and smooth all Google Sheet revenue numbers
                smoothed_revenue_map = {}
                raw_display_names = {}
                
                for idx, row in revenue_sheet.iterrows():
                    raw_name = str(row[client_col_name]).strip()
                    if pd.isna(row[client_col_name]) or raw_name == "" or "total" in raw_name.lower():
                        continue
                    
                    c_name = raw_name.lower()
                    raw_display_names[c_name] = raw_name
                    frequency = str(row[freq_col_name]).strip().lower() if freq_col_name in revenue_sheet.columns else 'monthly'
                    
                    total_range_revenue = 0.0
                    for m_str in active_months:
                        actual_rev_col = rev_date_map.get(m_str)
                        if actual_rev_col:
                            try:
                                val = str(row[actual_rev_col]).replace('$', '').replace(',', '').strip()
                                month_val = float(val)
                                
                                if 'quarter' in frequency:
                                    total_range_revenue += (month_val / 3.0)
                                else:
                                    total_range_revenue += month_val
                            except: pass
                    smoothed_revenue_map[c_name] = total_range_revenue
                
                # 3. 🚨 MASTER UNION ENGINE: Merges completely so no client revenue is ever lost
                all_unique_keys = set(smoothed_revenue_map.keys()).union(set(clockify_summary['match_key'].unique()) if not clockify_summary.empty else set())
                
                master_rows = []
                for key in all_unique_keys:
                    rev_val = smoothed_revenue_map.get(key, 0.0)
                    hours_val = 0.0
                    cost_val = 0.0
                    name_val = raw_display_names.get(key, None)
                    
                    if not clockify_summary.empty:
                        matching_row = clockify_summary[clockify_summary['match_key'] == key]
                        if not matching_row.empty:
                            hours_val = float(matching_row['Hours_Spent'].values[0])
                            cost_val = float(matching_row['Labor_Cost'].values[0])
                            if not name_val:
                                name_val = str(matching_row['Client'].values[0]).strip()
                                
                    if not name_val:
                        name_val = key.title()
                        
                    master_rows.append({
                        'Client': name_val,
                        'Hours_Spent': hours_val,
                        'Labor_Cost': cost_val,
                        'Monthly_Revenue': rev_val,
                        'match_key': key
                    })
                    
                df_master = pd.DataFrame(master_rows)
                
                df_master['Net Profit ($)'] = df_master['Monthly_Revenue'] - df_master['Labor_Cost']
                df_master['Gross Margin (%)'] = (df_master['Net Profit ($)'] / df_master['Monthly_Revenue'] * 100).fillna(0)
                df_master['Effective Hourly Rate (EHR)'] = (df_master['Monthly_Revenue'] / df_master['Hours_Spent']).fillna(0)
                
                if is_admin:
                    st.markdown(f"### 👑 Financial Performance Leaderboard ({focus_start.strftime('%b %d')} - {focus_end.strftime('%b %d, %Y')})")
                    t_rev = df_master['Monthly_Revenue'].sum()
                    t_cost = df_master['Labor_Cost'].sum()
                    f_prof = t_rev - t_cost
                    f_marg = (f_prof / t_rev * 100) if t_rev > 0 else 0
                    
                    c
