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

# Standardize column labels immediately
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
    
    # Target Column C explicitly by name match
    internal_limit_col = next((c for c in rates_sheet.columns if 'allowed' in c.lower() or 'limit' in c.lower() or 'internal' in c.lower()), rates_sheet.columns[2])
    
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
    
    # Process base cost mappings from your monthly cost columns
    rates_map = {}
    matching_rate_cols = [rates_date_map.get(m) for m in active_months if rates_date_map.get(m)]
    if matching_rate_cols:
        for idx, row in rates_sheet.iterrows():
            raw_user = str(row['User']).strip().lower()
            u_name = raw_user.split('@')[0].split('.')[0]
            vals = [safe_float(row[col]) for col in matching_rate_cols if col in row]
            rates_map[u_name] = sum(vals) / len(vals) if vals else 15.0
            
    clockify_summary = pd.DataFrame(columns=['Client', 'Hours_Spent', 'Labor_Cost', 'match_key'])
    if not client_df.empty:
        c_sum = client_df.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
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
    
    if is_admin:
        st.markdown(f"### Client Financial Profitability Leaderboard ({focus_start.strftime('%b %d')} - {focus_end.strftime('%b %d, %Y')})")
        t_rev = df_master['Monthly_Revenue'].sum()
        t_cost = df_master['Labor_Cost'].sum()
        f_prof = t_rev - t_cost
        f_marg = (f_prof / t_rev * 100) if t_rev > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Captured Revenue", f"${t_rev:,.2f}")
        c2.metric("Allocated Project Labor Cost", f"${t_cost:,.2f}")
        c3.metric("Project Gross Margin", f"{f_marg:.1f}%")
        c4.metric("Total Billable Hours Logged", f"{df_master['Hours_Spent'].sum():,.1f} hrs")
        
        st.markdown("### Visual Client Diagnostics")
        chart_df = df_master.sort_values(by='Monthly_Revenue', ascending=False).head(15)
        fig_compare = px.bar(chart_df, x='Client', y=['Monthly_Revenue', 'Labor_Cost'], barmode='group', title='Top 15 Clients: Revenue vs Allocated Labor Drag', labels={'value': 'Amount ($)', 'variable': 'Financial Metric'}, color_discrete_sequence=['#2ecc71', '#e74c3c'])
        fig_compare.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_compare, use_container_width=True)
        
        margin_df = df_master[df_master['Monthly_Revenue'] > 0].sort_values(by='Gross Margin (%)', ascending=True)
        fig_margin = px.bar(margin_df, x='Gross Margin (%)', y='Client', orientation='h', title='Client Return on Investment (Gross Margin %)', color='Gross Margin (%)', color_continuous_scale='RdYlGn', labels={'Gross Margin (%)': 'Profit Margin %'}, height=max(400, len(margin_df) * 20))
        st.plotly_chart(fig_margin, use_container_width=True)
        
        df_disp = df_master.drop(columns=['match_key']).sort_values(by='Gross Margin (%)', ascending=False)
        st.dataframe(df_disp, use_container_width=True, hide_index=True, column_config={
            "Client": st.column_config.TextColumn("Client"),
            "Hours_Spent": st.column_config.NumberColumn("Billable Hours Spent", format="%.2f hrs"),
            "Labor_Cost": st.column_config.NumberColumn("Allocated Labor Cost", format="$%.2f"),
            "Monthly_Revenue": st.column_config.NumberColumn("Monthly Revenue", format="$%.2f"),
            "Net Profit ($)": st.column_config.NumberColumn("Project Net Profit ($)", format="$%.2f"),
            "Gross Margin (%)": st.column_config.NumberColumn("Project Gross Margin", format="%.1f%%"),
            "Effective Hourly Rate (EHR)": st.column_config.NumberColumn("Realized Client Hourly Return", format="$%.2f/hr")
        })
        
        # --- EMPLOYEE CAPACITY & UTILIZATION TRACKER WORKSPACE ---
        st.markdown("---")
        st.markdown("### Team Staff Capacity & Available Bandwidth Tracker")
        
        if not month_clockify.empty:
            m_clock_cp = month_clockify.copy()
            m_clock_cp['Is_Internal_Type'] = m_clock_cp['Client'].str.strip().str.lower().apply(lambda x: 'Internal Overhead' if x == 'internal' else 'Client Hours')
            
            emp_summary = pd.pivot_table(
                m_clock_cp, 
                values='Duration (decimal)', 
                index='User', 
                columns='Is_Internal_Type', 
                aggfunc='sum', 
                fill_value=0.0
            ).reset_index()
            
            if 'Client Hours' not in emp_summary.columns:
                emp_summary['Client Hours'] = 0.0
            if 'Internal Overhead' not in emp_summary.columns:
                emp_summary['Internal Overhead'] = 0.0
                
            emp_summary = emp_summary.rename(columns={'Client Hours': 'Client_Hours', 'Internal Overhead': 'Internal_Hours'})
            
            def get_sheet_row(clockify_name):
                c_clean = str(clockify_name).strip().lower().split('@')[0].split('.')[0].strip()
                if not c_clean: return None
                for _, r_row in rates_sheet.iterrows():
                    r_clean = str(r_row['User']).strip().lower().split('@')[0].split('.')[0].strip()
                    if c_clean == r_clean or c_clean in r_clean or r_clean in c_clean:
                        return r_row
                return None
            
            emp_summary['Sheet_Row'] = emp_summary['User'].apply(get_sheet_row)
            
            def get_commitment(row):
                if row['Sheet_Row'] is None: return "Variable"
                val = str(row['Sheet_Row'][commit_col_name]).strip().replace('.0', '')
                return "Variable" if val.lower() in ['variable', 'nan', '', 'none'] else val
                
            def get_internal_limit(row):
                if row['Sheet_Row'] is None: return 5.0
                try:
                    return float(str(row['Sheet_Row'][internal_limit_col]).strip())
                except:
                    return 5.0
            
            emp_summary['Weekly_Hour_Target'] = emp_summary.apply(get_commitment, axis=1)
            emp_summary['Allowed_Internal_Limit'] = emp_summary.apply(get_internal_limit, axis=1)
            
            delta_days = (focus_end - focus_start).days + 1
            total_weeks = max(0.1, delta_days / 7.0)
            
            emp_summary['Clean_Key'] = emp_summary['User'].str.strip().str.lower().apply(lambda x: x.split('@')[0].split('.')[0])
            emp_summary['Hourly_Rate'] = emp_summary['Clean_Key'].map(rates_map).fillna(15.0)
            
            emp_summary['Client_Labor_Cost'] = emp_summary['Client_Hours'] * emp_summary['Hourly_Rate']
            emp_summary['Internal_Labor_Cost'] = emp_summary['Internal_Hours'] * emp_summary['Hourly_Rate']
            
            emp_summary['Total_Hours_Logged'] = emp_summary['Client_Hours'] + emp_summary['Internal_Hours']
            emp_summary['True_Utilization_Rate'] = (emp_summary['Client_Hours'] / emp_summary['Total_Hours_Logged'] * 100).fillna(0)
            
            # --- ⚙️ DYNAMIC CAPACITY OVERHEAD MATH ENGINE ---
            emp_summary['Avg_Client_Hours_Per_Week'] = emp_summary['Client_Hours'] / total_weeks
            emp_summary['Avg_Internal_Hours_Per_Week'] = emp_summary['Internal_Hours'] / total_weeks
            emp_summary['Target_Numeric'] = pd.to_numeric(emp_summary['Weekly_Hour_Target'], errors='coerce').fillna(0.0)
            
            def calculate_firm_bandwidth(row):
                if row['Weekly_Hour_Target'].lower() == 'variable': return 0.0
                allowed_internal = min(row['Allowed_Internal_Limit'], row['Avg_Internal_Hours_Per_Week'])
                used_hours = row['Avg_Client_Hours_Per_Week'] + allowed_internal
                return max(0.0, row['Target_Numeric'] - used_hours)
                
            def set_firm_capacity_status(row):
                if row['Weekly_Hour_Target'].lower() == 'variable': return "Flexible / Variable"
                allowed_internal = min(row['Allowed_Internal_Limit'], row['Avg_Internal_Hours_Per_Week'])
                used_hours = row['Avg_Client_Hours_Per_Week'] + allowed_internal
                open_hours = row['Target_Numeric'] - used_hours
                if open_hours > 3.0: return "Available Capacity"
                elif open_hours >= -2.0: return "At Optimum Capacity"
                else: return "Maxed Out / Overextended"

            emp_summary['Available_Weekly_Bandwidth'] = emp_summary.apply(calculate_firm_bandwidth, axis=1)
            emp_summary['Capacity_Status'] = emp_summary.apply(set_firm_capacity_status, axis=1)
            
            emp_disp = emp_summary[['User', 'Client_Hours', 'Internal_Hours', 'Client_Labor_Cost', 'Internal_Labor_Cost', 'True_Utilization_Rate', 'Weekly_Hour_Target', 'Avg_Client_Hours_Per_Week', 'Avg_Internal_Hours_Per_Week', 'Available_Weekly_Bandwidth', 'Capacity_Status']].sort_values(by='Available_Weekly_Bandwidth', ascending=False)
            
            st.dataframe(emp_disp, use_container_width=True, hide_index=True, column_config={
                "User": st.column_config.TextColumn("Employee Name"),
                "Client_Hours": st.column_config.NumberColumn("Client Hours", format="%.2f hrs"),
                "Internal_Hours": st.column_config.NumberColumn("Internal Overhead", format="%.2f hrs"),
                "Client_Labor_Cost": st.column_config.NumberColumn("Client Labor Cost", format="$%.2f"),
                "Internal_Labor_Cost": st.column_config.NumberColumn("Internal Labor Cost", format="$%.2f"),
                "True_Utilization_Rate": st.column_config.NumberColumn("True Utilization Rate", format="%.1f%%"),
                "Weekly_Hour_Target": st.column_config.TextColumn("Weekly Target Milestone"),
                "Avg_Client_Hours_Per_Week": st.column_config.NumberColumn("Avg Billable Hours/Wk", format="%.2f hrs/wk"),
                "Avg_Internal_Hours_Per_Week": st.column_config.NumberColumn("Avg Internal Hours/Wk", format="%.2f hrs/wk"),
                "Available_Weekly_Bandwidth": st.column_config.NumberColumn("Open Weekly Bandwidth", format="%.2f open hrs/wk"),
                "Capacity_Status": st.column_config.TextColumn("Hiring Status Allocation")
            })
            
            st.info("💡 **Hiring & Resource Allocation Guide:** Look at the top rows of this tracker. These employees have open bandwidth available to take on more accounts right now because unapproved internal work past your Google Sheet limit is counted as free capacity.")
        else:
            st.info("No timeline logs available to generate employee summaries.")
        
        # --- ACCOUNT PROFITABILITY ALERTS BLOCK ---
        st.markdown("### Account Profitability Alerts")
        underpriced = df_master[(df_master['Gross Margin (%)'] < 40) & (df_master['Hours_Spent'] > 0)]
        if not underpriced.empty:
            for _, u_row in underpriced.iterrows():
                if u_row['Monthly_Revenue'] == 0:
                    st.error(f"Write-off Alert on {u_row['Client']}: Logged {u_row['Hours_Spent']:.2f} hrs with $0.00 Revenue.")
                else:
                    st.warning(f"Low Margin Alert on {u_row['Client']}: Margin is {u_row['Gross Margin (%)']:.1f}%. Realized Client Hourly Return is ${u_row['Effective Hourly Rate (EHR)']:.2f}/hr.")

        # --- DATA RECONCILIATION ROOM (BOTTOM) ---
        st.markdown("---")
        st.markdown("### Admin Bookkeeping & Data Reconciliation Room")
        sheet_total_revenue = sum(smoothed_revenue_map.values())
        col_audit1, col_audit2 = st.columns(2)
        with col_audit1:
            st.info(f"Total Revenue expected by Google Sheet calculations: ${sheet_total_revenue:,.2f}")
        with col_audit2:
            if abs(sheet_total_revenue - t_rev) < 0.01:
                st.success("Perfect Match! Every single dollar inside your Google Sheet is accounted for.")
            else:
                st.warning(f"Discrepancy Amount: ${sheet_total_revenue - t_rev:,.2f} is unmatched.")
        
        clockify_tracked_keys = set(client_df['Client'].str.strip().str.lower().unique()) if not client_df.empty else set()
        untracked_revenue_clients = []
        for key, revenue in smoothed_revenue_map.items():
            if key not in clockify_tracked_keys and revenue > 0:
                untracked_revenue_clients.append({"Google Sheet Name": raw_display_names.get(key, key), "Revenue Captured": f"${revenue:,.2f}", "Status": "Captured! Displayed on Leaderboard with 0 hrs logged."})
        if untracked_revenue_clients:
            st.write("#### Captured Revenue with 0 Hours Logged (e.g., Okeya Stationery)")
            st.dataframe(pd.DataFrame(untracked_revenue_clients), use_container_width=True, hide_index=True)
            
    else:
        # --- STAFF ONLY VIEW ---
        st.info("Employee view active. Enter Admin Password in sidebar to reveal financials.")
        if not client_df.empty:
            staff_view_df = client_df.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
            st.dataframe(staff_view_df.rename(columns={'Duration (decimal)': 'Hours Tracked'}), use_container_width=True, hide_index=True)
        else:
            st.warning("No time entries found.")
