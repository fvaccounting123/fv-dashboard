import streamlit as st
import pandas as pd
import datetime
import ssl
import urllib.request
import plotly.express as px
import os

st.set_page_config(page_title="FVA | Dashboard", layout="wide")

# --- CUSTOM CORPORATE BRANDING ENGINE ---
st.markdown("""
<style>
    /* Global Typography Reset to Editorial Sans-Serif */
    html, body, [class*="css"], .stMarkdown, p, span, label {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
    }
    /* Brand Accent Background Fills using Custom Forest Green */
    .stMetric {
        background-color: #F8F9FA !important;
        padding: 20px !important;
        border-radius: 6px !important;
        border-left: 5px solid #3D5234 !important;
    }
    /* #3D5234 Forest Green Highlights for Metrics */
    div[data-testid="stMetricValue"] div {
        color: #3D5234 !important;
        font-weight: 700 !important;
    }
    /* Muted Labels */
    div[data-testid="stMetricLabel"] p {
        color: #5A626A !important;
        font-size: 14px !important;
        letter-spacing: 0.5px !important;
        text-transform: uppercase !important;
    }
</style>
""", unsafe_allow_html=True)

if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

st.title("First Valley Accounting | Corporate Performance Analytics")

# --- SIDEBAR ACCESS CONTROL ---
st.sidebar.header("Access Control")
admin_password = st.sidebar.text_input("Enter Admin Password", type="password")
is_admin = (admin_password.strip().upper() == "FV2026")

if is_admin:
    st.sidebar.success("Admin Access Verified")
elif admin_password:
    st.sidebar.error("Invalid Administrative Key")

# --- CONNECT TO MASTER REPOSITORY ---
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
    st.error(f"Data Link Execution Fault: {e}")
    st.stop()

revenue_sheet.columns = revenue_sheet.columns.str.strip()
rates_sheet.columns = rates_sheet.columns.str.strip()
master_clockify.columns = master_clockify.columns.str.strip()

master_clockify['Parsed Date'] = pd.to_datetime(master_clockify['Start Date'], errors='coerce')
master_clockify = master_clockify.dropna(subset=['Parsed Date'])

today = datetime.date.today()
first_this_month = today.replace(day=1)
last_prev_month = first_this_month - datetime.timedelta(days=1)
first_prev_month = last_prev_month.replace(day=1)

min_log_date = master_clockify['Parsed Date'].min().date()
max_log_date = master_clockify['Parsed Date'].max().date()

st.markdown("### Temporal Parameters")
selected_range = st.date_input(
    "Analyze operational data across this window:",
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
    commit_col_name = next((c for c in rates_sheet.columns if 'commit' in c.lower() or 'comit' in c.lower() or 'target' in c.lower()), rates_sheet.columns[1])
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
        st.markdown("### Client Account Financial Ledger")
        t_rev = df_master['Monthly_Revenue'].sum()
        t_cost = df_master['Labor_Cost'].sum()
        f_prof = t_rev - t_cost
        f_marg = (f_prof / t_rev * 100) if t_rev > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Captured Revenue", f"${t_rev:,.2f}")
        c2.metric("Allocated Project Labor Cost", f"${t_cost:,.2f}")
        c3.metric("Project Gross Margin", f"{f_marg:.1f}%")
        c4.metric("Total Billable Hours Logged", f"{df_master['Hours_Spent'].sum():,.1f} hrs")
        
        df_disp = df_master.drop(columns=['match_key']).sort_values(by='Gross Margin (%)', ascending=False)
        st.dataframe(df_disp, use_container_width=True, hide_index=True, column_config={
            "Client": st.column_config.TextColumn("Client", help="Registered identity of the client account."),
            "Hours_Spent": st.column_config.NumberColumn("Billable Hours Spent", format="%.2f hrs", help="Total cumulative client fulfillment hours recorded over this window."),
            "Labor_Cost": st.column_config.NumberColumn("Allocated Labor Cost", format="$%.2f", help="Fulfillment hours scaled by historical wage allocations."),
            "Monthly_Revenue": st.column_config.NumberColumn("Monthly Revenue", format="$%.2f", help="Total recognized firm billing fees generated over the timeline parameters."),
            "Net Profit ($)": st.column_config.NumberColumn("Project Net Profit ($)", format="$%.2f", help="Gross revenue generation minus corresponding delivery cost footprints."),
            "Gross Margin (%)": st.column_config.NumberColumn("Project Gross Margin", format="%.1f%%", help="Proportional delivery return performance of the engagement portfolio."),
            "Effective Hourly Rate (EHR)": st.column_config.NumberColumn("Realized Client Hourly Return", format="$%.2f/hr", help="The absolute hourly return yield achieved for every unit of production delivered.")
        })

        st.markdown("### Portfolio Performance Matrix")
        chart_df = df_master.sort_values(by='Monthly_Revenue', ascending=False).head(15)
        # Calibrated bar chart to use your #3D5234 Forest Green Palette
        fig_compare = px.bar(chart_df, x='Client', y=['Monthly_Revenue', 'Labor_Cost'], barmode='group', title='Top 15 Clients: Fee Yield vs Production Delivery Cost Drag', labels={'value': 'Amount ($)', 'variable': 'Financial Metric'}, color_discrete_sequence=['#3D5234', '#E74C3C'])
        fig_compare.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_compare, use_container_width=True)
        
        # --- REVENUE CONTRIBUTION MATRICES ENGINE ---
        if not client_df.empty:
            raw_client_totals = client_df.groupby('Client')['Duration (decimal)'].sum().to_dict()
            
            def calculate_user_revenue_weight(row):
                c_lbl = row['Client']
                tot_c_hours = raw_client_totals.get(c_lbl, 0.0)
                if tot_c_hours == 0: return 0.0
                c_key_clean = str(c_lbl).strip().lower()
                c_rev_lookup = smoothed_revenue_map.get(c_key_clean, 0.0)
                user_share = row['Duration (decimal)'] / tot_c_hours
                return user_share * c_rev_lookup
                
            client_df_cp = client_df.copy()
            client_df_cp['Weighted_Revenue_Credit'] = client_df_cp.apply(calculate_user_revenue_weight, axis=1)
            user_rev_aggregates = client_df_cp.groupby('User')['Weighted_Revenue_Credit'].sum().to_dict()
        else:
            user_rev_aggregates = {}

        # --- EMPLOYEE CAPACITY & UTILIZATION TRACKER WORKSPACE ---
        st.markdown("---")
        st.markdown("### Human Capital Capacity & Revenue Support Matrix")
        
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
            
            def match_commitment_row(clockify_name):
                c_clean = str(clockify_name).strip().lower().split('@')[0].split('.')[0].strip()
                if not c_clean: return "Variable"
                for _, r_row in rates_sheet.iterrows():
                    r_clean = str(r_row['User']).strip().lower().split('@')[0].split('.')[0].strip()
                    if c_clean == r_clean or c_clean in r_clean or r_clean in c_clean:
                        if commit_col_name in r_row:
                            val_str = str(r_row[commit_col_name]).strip().replace('.0', '')
                            if val_str.lower() in ['variable', 'nan', '', 'none']: return "Variable"
                            return val_str
                return "Variable"
                
            def match_internal_limit_row(clockify_name):
                c_clean = str(clockify_name).strip().lower().split('@')[0].split('.')[0].strip()
                if not c_clean: return 5.0
                for _, r_row in rates_sheet.iterrows():
                    r_clean = str(r_row['User']).strip().lower().split('@')[0].split('.')[0].strip()
                    if c_clean == r_clean or c_clean in r_clean or r_clean in c_clean:
                        if internal_limit_col in r_row:
                            try:
                                return float(str(r_row[internal_limit_col]).strip())
                            except:
                                return 5.0
                return 5.0
            
            emp_summary['Weekly_Hour_Target'] = emp_summary['User'].apply(match_commitment_row)
            emp_summary['Allowed_Internal_Limit'] = emp_summary['User'].apply(match_internal_limit_row)
            
            delta_days = (focus_end - focus_start).days + 1
            total_weeks = max(0.1, delta_days / 7.0)
            
            emp_summary['Clean_Key'] = emp_summary['User'].str.strip().str.lower().apply(lambda x: x.split('@')[0].split('.')[0])
            emp_summary['Hourly_Rate'] = emp_summary['Clean_Key'].map(rates_map).fillna(15.0)
            
            emp_summary['Client_Labor_Cost'] = emp_summary['Client_Hours'] * emp_summary['Hourly_Rate']
            emp_summary['Internal_Labor_Cost'] = emp_summary['Internal_Hours'] * emp_summary['Hourly_Rate']
            
            emp_summary['Total_Hours_Logged'] = emp_summary['Client_Hours'] + emp_summary['Internal_Hours']
            emp_summary['True_Utilization_Rate'] = (emp_summary['Client_Hours'] / emp_summary['Total_Hours_Logged'] * 100).fillna(0)
            
            emp_summary['Avg_Client_Hours_Per_Week'] = emp_summary['Client_Hours'] / total_weeks
            emp_summary['Avg_Internal_Hours_Per_Week'] = emp_summary['Internal_Hours'] / total_weeks
            emp_summary['Target_Numeric'] = pd.to_numeric(emp_summary['Weekly_Hour_Target'], errors='coerce').fillna(0.0)
            
            emp_summary['Supported_Revenue_Credit'] = emp_summary['User'].map(user_rev_aggregates).fillna(0.0)
            emp_summary['Realized_Revenue_Value_Rate'] = (emp_summary['Supported_Revenue_Credit'] / emp_summary['Total_Hours_Logged']).fillna(0.0)
            
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
            
            emp_disp = emp_summary[['User', 'Client_Hours', 'Internal_Hours', 'True_Utilization_Rate', 'Weekly_Hour_Target', 'Available_Weekly_Bandwidth', 'Supported_Revenue_Credit', 'Realized_Revenue_Value_Rate', 'Capacity_Status']].sort_values(by='Realized_Revenue_Value_Rate', ascending=False)
            
            st.dataframe(emp_disp, use_container_width=True, hide_index=True, column_config={
                "User": st.column_config.TextColumn("Resource Name", help="Employee identity mapped from tracked workspace files."),
                "Client_Hours": st.column_config.NumberColumn("Client Hours", format="%.2f hrs", help="Cumulative core client project assignment delivery hours logged."),
                "Internal_Hours": st.column_config.NumberColumn("Internal Overhead", format="%.2f hrs", help="Cumulative administrative operations and training overhead time units."),
                "True_Utilization_Rate": st.column_config.NumberColumn("True Utilization Rate", format="%.1f%%", help="Fulfillment hours scaled against total logged timeline activity footprint."),
                "Weekly_Hour_Target": st.column_config.TextColumn("Weekly Hours Target", help="Contractual baseline threshold allocation parameters."),
                "Available_Weekly_Bandwidth": st.column_config.NumberColumn("Open Weekly Bandwidth", format="%.2f open hrs/wk", help="Remaining open hours available for direct onboarding before target milestones are met."),
                "Supported_Revenue_Credit": st.column_config.NumberColumn("Supported Revenue Credit", format="$%.2f", help="Portfolio revenue weight attributed to this resource proportional to their logged labor share across accounts."),
                "Realized_Revenue_Value_Rate": st.column_config.NumberColumn("Realized Revenue Value Rate", format="$%.2f/hr", help="The absolute value density rate generated by this professional. Formula: Supported Revenue Credit divided by total logged hours."),
                "Capacity_Status": st.column_config.TextColumn("Hiring Status Allocation")
            })
            
            st.info("Hiring and Resource Allocation Guide: Resources are ranked by their Realized Revenue Value Rate. High value rates isolate high-efficiency performers across valuable retainers; low value rates pinpoint margin leaks where substantial delivery hours are assigned to accounts generating minimal relative fee income.")
            
            # --- STRATEGIC INSIGHTS TAKEAWAYS BLOCK ---
            st.markdown("---")
            st.markdown("### Executive Insights and Top Strategic Takeaways")
            col_tk1, col_tk2 = st.columns(2)
            
            with col_tk1:
                st.markdown("#### Top 3 Client Profitability Leaks")
                valid_leaks = df_master[(df_master['Hours_Spent'] > 0) & (df_master['Monthly_Revenue'] > 0)]
                leak_df = valid_leaks.sort_values(by='Gross Margin (%)', ascending=True).head(3)
                if not leak_df.empty:
                    for _, r in leak_df.iterrows():
                        st.warning(f"**{r['Client']}**: Running at a low **{r['Gross Margin (%)']:.1f}%** margin. Realized return is **${r['Effective Hourly Rate (EHR)']:.2f}/hr** on **{r['Hours_Spent']:.2f} hrs** of work.")
                else:
                    st.write("No active client accounts met the insight threshold parameters within this timeframe window.")
                    
            with col_tk2:
                st.markdown("#### Top 3 Employee Capacity and Overhead Focuses")
                takeaways_emp = []
                
                low_value_performers = emp_summary[(emp_summary['Client_Hours'] > 5.0)].sort_values(by='Realized_Revenue_Value_Rate', ascending=True)
                for _, r in low_value_performers.head(1).iterrows():
                    if r['Realized_Revenue_Value_Rate'] < 30.0:
                        takeaways_emp.append(f"Resource **{r['User']}** is logging substantial time but yields a low Realized Revenue Value Rate of **${r['Realized_Revenue_Value_Rate']:.2f}/hr** (Total: {r['Total_Hours_Logged']:.1f} hrs supporting **${r['Supported_Revenue_Credit']:.2f}** in weighted revenue).")
                
                high_cap = emp_summary[emp_summary['Weekly_Hour_Target'].str.lower() != 'variable'].sort_values(by='Available_Weekly_Bandwidth', ascending=False)
                for _, r in high_cap.head(1).iterrows():
                    if r['Available_Weekly_Bandwidth'] > 2.0:
                        takeaways_emp.append(f"Resource **{r['User']}** has **{r['Available_Weekly_Bandwidth']:.2f} open hrs/wk** available. Prime resource allocation candidate for new accounts.")
                
                high_int = emp_summary.sort_values(by='Avg_Internal_Hours_Per_Week', ascending=False)
                for _, r in high_int.head(1).iterrows():
                    if r['Avg_Internal_Hours_Per_Week'] > (r['Allowed_Internal_Limit'] + 1.0):
                        excess = r['Avg_Internal_Hours_Per_Week'] - r['Allowed_Internal_Limit']
                        takeaways_emp.append(f"Resource **{r['User']}** is logging heavy administrative time at **{r['Avg_Internal_Hours_Per_Week']:.2f} hrs/wk** (Exceeds baseline limit by **{excess:.2f} hrs/wk**).")
                
                for t in takeaways_emp[:3]:
                    st.write(t)
        else:
            st.info("No timeline logs available to generate employee summaries.")

        # --- DATA RECONCILIATION ROOM ---
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
        
except Exception as main_err:
    st.error(f"System Matrix Execution Fault: {main_err}")
