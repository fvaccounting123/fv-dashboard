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

# LINEAR ISOLATED DATA CAPTURE (Safe from display block indentation shifts)
try:
    master_clockify = pd.read_csv(urllib.request.urlopen(CLOCKIFY_URL, context=context))
    revenue_sheet = pd.read_csv(urllib.request.urlopen(REVENUE_URL, context=context))
    rates_sheet = pd.read_csv(urllib.request.urlopen(RATES_URL, context=context))
except Exception as e:
    st.error(f"Google Sheet Data Load Error: {e}")
    st.stop()

# Standardize Columns immediately upon loading
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
        
        if matching_rate_cols:
            for idx, row in rates_sheet.iterrows():
                raw_user = str(row['User']).strip().lower()
                u_name = raw_user.split('@')[0].split('.')[0]
                
                vals = []
                for c in matching_rate_cols:
                    if c in row:
                        vals.append(safe_float(row[c]))
                
                rates_map[u_name] = sum(vals) / len(vals) if vals else 15.0
        
        c_sum['Clean_User_Key'] = c_sum['User'].str.strip().str.lower().apply(lambda x: x.split('@')[0].split('.')[0])
        c_sum['Cost Rate'] = c_sum['Clean_User_Key'].map(rates_map).fillna(15.0)
        c_sum['Total Cost'] = c_sum['Duration (decimal)'].astype(float) * c_sum['Cost Rate']
        clockify_summary = c_sum.groupby('Client').agg(Hours_Spent=('Duration (decimal)', 'sum'), Labor_Cost=('Total Cost', 'sum')).reset_index()
        clockify_summary['match_key'] = clockify_summary['Client'].str.strip().str.lower()
    
    smoothed_revenue_map = {}
    raw_display_names = {}
    for idx, row in revenue_sheet.iterrows():
        raw_name = str(row[client_col_name]).strip()
        if pd.isna(row[client_col_name]) or raw_name == "" or "total" in raw_name.lower():
            continue
        c_name = raw_name.lower()
        raw_display_names[c_name] = raw_name
        
        total_range_revenue = 0.0
        for m_str in active_months:
            actual_rev_col = rev_date_map.get(m_str)
            if actual_rev_col and actual_rev_col in row:
                total_range_revenue += safe_float(row[actual_rev_col])
        smoothed_revenue_map[c_name] = total_range_revenue
    
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
        master_rows.append({'Client': name_val, 'Hours_Spent': hours_val, 'Labor_Cost': cost_val, 'Monthly_Revenue': rev_val, 'match_key': key})
    
    df_master = pd.DataFrame(master_rows)
    df_master['Net Profit ($)'] = df_master['Monthly_Revenue'] - df_master['Labor_Cost']
    df_master['Gross Margin (%)'] = (df_master['Net Profit ($)'] / df_master['Monthly_Revenue'] * 100).fillna(0)
    df_master['Effective Hourly Rate (EHR)'] = (df_master['Monthly_Revenue'] / df_master['Hours_Spent']).fillna(0)
    
    # 🔐 STABLE SECURITY ROUTER BLOCK
    if is_admin:
        st.markdown(f"### Financial Performance Leaderboard ({focus_start.strftime('%b %d')} - {focus_end.strftime('%b %d, %Y')})")
        t_rev = df_master['Monthly_Revenue'].sum()
        t_cost = df_master['Labor_Cost'].sum()
        f_prof = t_rev - t_cost
        f_marg = (f_prof / t_rev * 100) if t_rev > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Range Revenue", f"${t_rev:,.2f}")
        c2.metric("Labor Payroll Cost", f"${t_cost:,.2f}")
        c3.metric("True Gross Margin", f"{f_marg:.1f}%")
        c4.metric("Total Hours Logged", f"{df_master['Hours_Spent'].sum():,.1f} hrs")
        
        st.markdown("### Visual Firm Diagnostics")
        chart_df = df_master.sort_values(by='Monthly_Revenue', ascending=False).head(15)
        fig_compare = px.bar(chart_df, x='Client', y=['Monthly_Revenue', 'Labor_Cost'], barmode='group', title='Top 15 Clients: Revenue vs Labor Cost Drag', labels={'value': 'Amount ($)', 'variable': 'Financial Metric'}, color_discrete_sequence=['#2ecc71', '#e74c3c'])
        fig_compare.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_compare, use_container_width=True)
        
        margin_df = df_master[df_master['Monthly_Revenue'] > 0].sort_values(by='Gross Margin (%)', ascending=True)
        fig_margin = px.bar(margin_df, x='Gross Margin (%)', y='Client', orientation='h', title='Client Return on Investment (Gross Margin %)', color='Gross Margin (%)', color_continuous_scale='RdYlGn', labels={'Gross Margin (%)': 'Profit Margin %'}, height=max(400, len(margin_df) * 20))
        st.plotly_chart(fig_margin, use_container_width=True)
        
        df_disp = df_master.drop(columns=['match_key']).sort_values(by='Gross Margin (%)', ascending=False)
        st.dataframe(df_disp, use_container_width=True, hide_index=True, column_config={
            "Client": st.column_config.TextColumn("Client"),
            "Hours_Spent": st.column_config.NumberColumn("Hours Spent", format="%.2f hrs"),
            "Labor_Cost": st.column_config.NumberColumn("Labor Cost", format="$%.2f"),
            "Monthly_Revenue": st.column_config.NumberColumn("Monthly Revenue", format="$%.2f"),
            "Net Profit ($)": st.column_config.NumberColumn("Net Profit ($)", format="$%.2f"),
            "Gross Margin (%)": st.column_config.NumberColumn("Gross Margin (%)", format="%.1f%%"),
            "Effective Hourly Rate (EHR)": st.column_config.NumberColumn("Effective Hourly Rate (EHR)", format="$%.2f/hr")
        })
        
        # --- EMPLOYEE CAPACITY & UTILIZATION TRACKER WORKSPACE ---
        st.markdown("---")
        st.markdown("### Employee Capacity & Utilization Tracker")
        
        if not month_clockify.empty:
            m_clock_cp = month_clockify.copy()
            m_clock_cp['Is_Internal'] = m_clock_cp['Client'].str.strip().str.lower() == 'internal'
            
            emp_summary = m_clock_cp.groupby(['User', 'Is_Internal'])['Duration (decimal)'].unstack(fill_value=0).reset_index()
            emp_summary.columns = [str(c) for c in emp_summary.columns]
            
            c_h_col = 'False' if 'False' in emp_summary.columns else None
            i_h_col = 'True' if 'True' in emp_summary.columns else None
            
            emp_summary['Client_Hours'] = emp_summary[c_h_col].astype(float) if c_h_col else 0.0
            emp_summary['Internal_Hours'] = emp_summary[i_h_col].astype(float) if i_h_col else 0.0
            
            emp_summary['Total_Hours'] = emp_summary['Client_Hours'] + emp_summary['Internal_Hours']
            emp_summary['Utilization_%'] = (emp_summary['Client_Hours'] / emp_summary['Total_Hours'] * 100).fillna(0)
            
            delta_days = (focus_end - focus_start).days + 1
            total_weeks = max(0.1, delta_days / 7.0)
            emp_summary['Avg_Hours_Per_Week'] = emp_summary['Total_Hours'] / total_weeks
            
            # Dynamic Commitment Mapping Engine (Substring & Email Subtraction)
            commit_map = {}
            if commit_col_name in rates_sheet.columns:
                for idx, row in rates_sheet.iterrows():
                    raw_cell_user = str(row['User']).strip().lower()
                    clean_sheet_key = raw_cell_user.split('@')[0].split('.')[0]
                    raw_cell_str = str(row[commit_col_name]).strip().replace('.0', '')
                    commit_map[clean_sheet_key] = raw_cell_str
            
            emp_summary['Clean_Clockify_Key'] = emp_summary['User'].str.strip().str.lower().apply(lambda x: x.split('@')[0].split('.')[0])
            emp_summary['Commitment'] = emp_summary['Clean_Clockify_Key'].map(commit_map).fillna('Variable')
            emp_summary['Commitment'] = emp_summary['Commitment'].apply(lambda x: 'Variable' if x.lower() in ['variable', 'nan', ''] else x)
            
            # NATIVE VECTORIZED VARIANCE CALCULATIONS
            emp_summary['Commitment_Numeric'] = pd.to_numeric(emp_summary['Commitment'], errors='coerce').fillna(0.0)
            emp_summary['Weekly_Variance'] = emp_summary['Avg_Hours_Per_Week'] - emp_summary['Commitment_Numeric']
            emp_summary.loc[emp_summary['Commitment'].str.lower() == 'variable', 'Weekly_Variance'] = 0.0
            
            emp_disp = emp_summary[['User', 'Client_Hours', 'Internal_Hours', 'Total_Hours', 'Utilization_%', 'Commitment', 'Avg_Hours_Per_Week', 'Weekly_Variance']].sort_values(by='Weekly_Variance', ascending=True)
            
            st.dataframe(emp_disp, use_container_width=True, hide_index
