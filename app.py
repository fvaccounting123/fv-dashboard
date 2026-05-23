import streamlit as st
import pandas as pd
import datetime
import ssl
import urllib.request

st.set_page_config(page_title="FV | Master Dashboard", layout="wide")
st.title("📊 First Valley | Master Profitability Dashboard")

# --- SIDEBAR ACCESS CONTROL ---
st.sidebar.header("🔑 Access Control")
admin_password = st.sidebar.text_input("Enter Admin Password", type="password")

# Bulletproof password matching
is_admin = (admin_password.strip() == "FV2026")

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
        unique_cols = sorted(master_clockify['Report Column'].dropna().unique())
        month_labels = {col: datetime.datetime.strptime(col, '%Y-%m-%d').strftime('%B %Y') for col in unique_cols}
        
        focus_col = st.selectbox("📅 Select Month Range", options=unique_cols, format_func=lambda x: month_labels[x], index=len(unique_cols)-1)
        
        # Pull live sheets data using your exact sheet link
        SHEET_ID = "1maGLtLBdDj7_uxFoeMMuvqEU5pLfdwH6mGrhx9V4B-c"
        REVENUE_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=2026"
        RATES_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Employee+Hourly+Rates"
        
        try:
            # Cloud/Mac universal secure connection bypass
            context = ssl._create_unverified_context()
            revenue_sheet = pd.read_csv(urllib.request.urlopen(REVENUE_URL, context=context))
            rates_sheet = pd.read_csv(urllib.request.urlopen(RATES_URL, context=context))
            
            revenue_sheet.columns = revenue_sheet.columns.str.strip()
            rates_sheet.columns = rates_sheet.columns.str.strip()
            
            # Smart dynamic naming checks
            client_col_name = next((c for c in revenue_sheet.columns if 'client' in c.lower()), revenue_sheet.columns[1])
            freq_col_name = next((c for c in revenue_sheet.columns if 'freq' in c.lower()), 'Frequency')
            
            # Standardize sheet column headers to dates (FIXED TYPO HERE)
            rev_date_map = {}
            for col in revenue_sheet.columns:
                parsed = pd.to_datetime(col, errors='coerce')
                if pd.notnull(parsed):
                    rev_date_map[parsed.strftime('%Y-%m-01')] = col

            rates_date_map = {}
            for col in rates_sheet.columns:
                parsed = pd.to_datetime(col, errors='coerce')
                if pd.notnull(parsed):
                    rates_date_map[parsed.strftime('%Y-%m-01')] = col
            
            month_clockify = master_clockify[master_clockify['Report Column'] == focus_col]
            internal_mask = month_clockify['Client'].str.strip().str.lower() == 'internal'
            client_df = month_clockify[~internal_mask]
            
            if not client_df.empty:
                clockify_summary = client_df.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
                
                actual_rates_col = rates_date_map.get(focus_col)
                rates_map = dict(zip(rates_sheet['User'].str.strip(), rates_sheet[actual_rates_col])) if actual_rates_col else {}
                
                clockify_summary['Cost Rate'] = clockify_summary['User'].str.strip().map(rates_map).fillna(15.0)
                clockify_summary['Total Cost'] = clockify_summary['Duration (decimal)'] * clockify_summary['Cost Rate']
                
                client_rollup = clockify_summary.groupby('Client').agg(Hours_Spent=('Duration (decimal)', 'sum'), Labor_Cost=('Total Cost', 'sum')).reset_index()
                
                focus_date = pd.to_datetime(focus_col)
                focus_quarter = (focus_date.month - 1) // 3 + 1
                
                smoothed_revenue_map = {}
                for idx, row in revenue_sheet.iterrows():
                    c_name = str(row[client_col_name]).strip().lower()
                    frequency = str(row[freq_col_name]).strip().lower() if freq_col_name in revenue_sheet.columns else 'monthly'
                    
                    if 'quarter' in frequency:
                        total_quarter_rev = 0.0
                        for standard_date_str, actual_col in rev_date_map.items():
                            col_date = pd.to_datetime(standard_date_str)
                            col_quarter = (col_date.month - 1) // 3 + 1
                            if col_date.year == focus_date.year and col_quarter == focus_quarter:
                                try:
                                    val = str(row[actual_col]).replace('$', '').replace(',', '').strip()
                                    total_quarter_rev += float(val)
                                except: pass
                        smoothed_revenue_map[c_name] = total_quarter_rev / 3.0
                    else:
                        actual_rev_col = rev_date_map.get(focus_col)
                        if actual_rev_col:
                            try:
                                val = str(row[actual_rev_col]).replace('$', '').replace(',', '').strip()
                                smoothed_revenue_map[c_name] = float(val)
                            except:
                                smoothed_revenue_map[c_name] = 0.0
                        else:
                            smoothed_revenue_map[c_name] = 0.0
                
                client_rollup['match_key'] = client_rollup['Client'].str.strip().str.lower()
                client_rollup['Monthly_Revenue'] = client_rollup['match_key'].map(smoothed_revenue_map).fillna(0.0)
                
                client_rollup['Net Profit ($)'] = client_rollup['Monthly_Revenue'] - client_rollup['Labor_Cost']
                client_rollup['Gross Margin (%)'] = (client_rollup['Net Profit ($)'] / client_rollup['Monthly_Revenue'] * 100).fillna(0)
                client_rollup['Effective Hourly Rate (EHR)'] = (client_rollup['Monthly_Revenue'] / client_rollup['Hours_Spent']).fillna(0)
                
                if is_admin:
                    st.markdown(f"### 👑 Financial Performance Leaderboard ({month_labels[focus_col]})")
                    t_rev = client_rollup['Monthly_Revenue'].sum()
                    t_cost = client_rollup['Labor_Cost'].sum()
                    f_prof = t_rev - t_cost
                    f_marg = (f_prof / t_rev * 100) if t_rev > 0 else 0
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Blended Revenue", f"${t_rev:,.2f}")
                    c2.metric("Labor Payroll Cost", f"${t_cost:,.2f}")
                    c3.metric("True Gross Margin", f"{f_marg:.1f}%")
                    c4.metric("Total Hours Logged", f"{client_rollup['Hours_Spent'].sum():,.1f} hrs")
                    
                    df_disp = client_rollup.drop(columns=['match_key']).sort_values(by='Gross Margin (%)', ascending=False)
                    df_disp['Monthly_Revenue'] = df_disp['Monthly_Revenue'].map('${:,.2f}'.format)
                    df_disp['Labor_Cost'] = df_disp['Labor_Cost'].map('${:,.2f}'.format)
                    df_disp['Net Profit ($)'] = df_disp['Net Profit ($)'].map('${:,.2f}'.format)
                    df_disp['Gross Margin (%)'] = df_disp['Gross Margin (%)'].map('{:.1f}%'.format)
                    df_disp['Effective Hourly Rate (EHR)'] = df_disp['Effective Hourly Rate (EHR)'].map('${:,.2f}/hr'.format)
                    st.dataframe(df_disp, use_container_width=True, hide_index=True)
                    
                    st.markdown("### ⚠️ Account Profitability Alerts")
                    underpriced = client_rollup[(client_rollup['Gross Margin (%)'] < 40) & (client_rollup['Hours_Spent'] > 0)]
                    if not underpriced.empty:
                        for idx, row in underpriced.iterrows():
                            if row['Monthly_Revenue'] == 0:
                                st.error(f"**Write-off Alert on {row['Client']}:** Logged {row['Hours_Spent']:.2f} hrs with $0.00 Revenue.")
                            else:
                                st.warning(f"**Low Margin Alert on {row['Client']}:** Margin is {row['Gross Margin (%)']:.1f}%. EHR is ${row['Effective Hourly Rate (EHR)']:.2f}/hr.")
                else:
                    st.info("🔒 Employee view active. Enter Admin Password in sidebar to reveal financials.")
                    staff = month_clockify.groupby(['Client', 'User'])['Duration (decimal)'].sum().reset_index()
                    st.dataframe(staff.rename(columns={'Duration (decimal)': 'Hours Tracked'}), use_container_width=True, hide_index=True)
            else:
                st.warning("No time entries found matching this month range.")
        except Exception as e:
            st.error(f"Google Sheet error: {e}")
