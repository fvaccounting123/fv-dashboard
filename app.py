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
                
                if not client_df.empty:
                    clockify_summary = client_df.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
                    
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
                    
                    clockify_summary['Cost Rate'] = clockify_summary['User'].str.strip().map(rates_map).fillna(15.0)
                    clockify_summary['Total Cost'] = clockify_summary['Duration (decimal)'].astype(float) * clockify_summary['Cost Rate']
                    
                    client_rollup = clockify_summary.groupby('Client').agg(Hours_Spent=('Duration (decimal)', 'sum'), Labor_Cost=('Total Cost', 'sum')).reset_index()
                    
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
                    
                    client_rollup['match_key'] = client_rollup['Client'].str.strip().str.lower()
                    client_rollup['Monthly_Revenue'] = client_rollup['match_key'].map(smoothed_revenue_map).fillna(0.0)
                    
                    client_rollup['Net Profit ($)'] = client_rollup['Monthly_Revenue'] - client_rollup['Labor_Cost']
                    client_rollup['Gross Margin (%)'] = (client_rollup['Net Profit ($)'] / client_rollup['Monthly_Revenue'] * 100).fillna(0)
                    client_rollup['Effective Hourly Rate (EHR)'] = (client_rollup['Monthly_Revenue'] / client_rollup['Hours_Spent']).fillna(0)
                    
                    if is_admin:
                        st.markdown(f"### 👑 Financial Performance Leaderboard ({focus_start.strftime('%b %d')} - {focus_end.strftime('%b %d, %Y')})")
                        t_rev = client_rollup['Monthly_Revenue'].sum()
                        t_cost = client_rollup['Labor_Cost'].sum()
                        f_prof = t_rev - t_cost
                        f_marg = (f_prof / t_rev * 100) if t_rev > 0 else 0
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Blended Range Revenue", f"${t_rev:,.2f}")
                        c2.metric("Labor Payroll Cost", f"${t_cost:,.2f}")
                        c3.metric("True Gross Margin", f"{f_marg:.1f}%")
                        c4.metric("Total Hours Logged", f"{client_rollup['Hours_Spent'].sum():,.1f} hrs")
                        
                        st.markdown("### 📈 Visual Firm Diagnostics")
                        chart_col1, chart_col2 = st.columns(2)
                        
                        with chart_col1:
                            chart_df = client_rollup.sort_values(by='Monthly_Revenue', ascending=False).head(12)
                            fig_compare = px.bar(
                                chart_df, 
                                x='Client', 
                                y=['Monthly_Revenue', 'Labor_Cost'],
                                barmode='group',
                                title='Top 12 Clients: Revenue vs Labor Cost Drag',
                                labels={'value': 'Amount ($)', 'variable': 'Financial Metric'},
                                color_discrete_sequence=['#2ecc71', '#e74c3c']
                            )
                            fig_compare.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig_compare, use_container_width=True)
                            
                        with chart_col2:
                            margin_df = client_rollup[client_rollup['Monthly_Revenue'] > 0].sort_values(by='Gross Margin (%)', ascending=True)
                            fig_margin = px.bar(
                                margin_df,
                                x='Gross Margin (%)',
                                y='Client',
                                orientation='h',
                                title='Client Return on Investment (Gross Margin %)',
                                color='Gross Margin (%)',
                                color_continuous_scale='RdYlGn',
                                labels={'Gross Margin (%)': 'Profit Margin %'}
                            )
                            st.plotly_chart(fig_margin, use_container_width=True)
                        
                        # Clean display dataframe keeping data as actual numeric floats
                        df_disp =
