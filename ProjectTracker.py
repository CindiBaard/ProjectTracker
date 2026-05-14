import os
import re
import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. INITIAL SETUP & CONFIG ---
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")

BASE_DIR = os.getcwd()
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv")
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"
TRACKER_FILE_ID = "1LA9F5mD67vR9yYKqQ39CS-tAZ9QgCgn5KBWaY_RfFKM"
MOULD_ASSETS_ID = "1Ix1aq6Ze63Vhqh9Pm98BegUnDaLgKC6H9vTMKafjc44"

DESIRED_ORDER = [
    "Pre-Prod No.", "Date", "Age Category", "Client", "Project Description", 
    "New Mould_ Client or Product", "Product Code", "Machine", "Sales Rep", 
    "Category", "Status", "Open or closed", "Completion date", "Material", 
    "Product Material Colour (tube, jar etc.)", "Artwork required", "Artwork Received", 
    "Order Qty x1000", "Unit Order No", "Length", "Cap_Lid Style", "Cap_Lid Material", 
    "Cap_Lid Diameter", "Orifice", "Other Cap_Lid Info", "Tube Shoulder colour", 
    "Dust Controlled Area", "Date Sent on Proof", "Size of Eyemark", 
    "Proof Approved (Conventional)", "Proof Approved (Digital)", "Ordered Plates", 
    "Plates Arrived", "Sent on Trial", "Digital trial sent", 
    "Revised Artwork After Trialling", "Masterbatch received", "Extrusion requested", 
    "Extrusion received", "Injection trial requested", "Injection trial received", 
    "Blowmould trial requested", "Blowmould trial received", "Comments"
]

DROPDOWN_FILES = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Cap_Lid Style": "Cap_Lid style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "CapMaterial.csv"
}

# --- 2. CORE UTILITIES & GOOGLE SYNC ---

def get_gspread_client():
    try:
        creds_info = st.secrets.get("gcp_service_account", st.secrets.get("connections", {}).get("gsheets"))
        if isinstance(creds_info, dict) and "private_key" in creds_info:
             creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))
    except Exception as e:
        st.error(f"Credentials Error: {e}")
        return None

@st.cache_data(ttl=600)
def get_mould_lookup_data():
    try:
        client = get_gspread_client()
        if not client: return {}
        sheet = client.open_by_key(MOULD_ASSETS_ID).get_worksheet(0)
        raw = sheet.get_all_values()
        if len(raw) < 2: return {}
        df_assets = pd.DataFrame(raw[1:], columns=[str(h).strip() for h in raw[0]])
        desc_col = next((c for c in df_assets.columns if "description" in c.lower()), df_assets.columns[0])
        mould_col = next((c for c in df_assets.columns if "mould" in c.lower()), df_assets.columns[1])
        return dict(zip(df_assets[desc_col].astype(str).str.strip(), df_assets[mould_col].astype(str).str.strip()))
    except: return {}

def smart_read(path):
    if not os.path.exists(path): return pd.DataFrame()
    try:
        # Prevent the mixed-type warning found in logs
        df = pd.read_csv(path, sep=';', on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
        if len(df.columns) <= 1:
            df = pd.read_csv(path, sep=',', on_bad_lines='skip', encoding='utf-8-sig', low_memory=False)
        return df
    except: return pd.DataFrame()

def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == '': return ""
    clean = str(val).split('.')[0].strip()
    return clean.zfill(5) if clean.isdigit() else clean

def save_db(df_to_save):
    df_to_save.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                return sorted(list(set([l.strip() for l in f.readlines() if l.strip()])))
        except: return []
    return []

# --- 3. DATA MERGING LOGIC ---

def merge_and_clean_data():
    df_conv = smart_read(TRACKER_ADJ_FILE)
    df_digi = smart_read(DIGITALPREPROD_FILE)
    if df_conv.empty and df_digi.empty:
        return pd.DataFrame(columns=DESIRED_ORDER)

    for d in [df_conv, df_digi]:
        if not d.empty:
            col = 'Pre-Prod No.' if 'Pre-Prod No.' in d.columns else d.columns[0]
            d.rename(columns={col: 'Pre-Prod No.'}, inplace=True)
            d['Pre-Prod No.'] = d['Pre-Prod No.'].apply(pad_preprod_id)

    combined = pd.concat([df_conv, df_digi], ignore_index=True).drop_duplicates(subset=['Pre-Prod No.'], keep='last')
    for col in DESIRED_ORDER:
        if col not in combined.columns: combined[col] = ""
    return combined[DESIRED_ORDER]

@st.cache_data
def load_db():
    if os.path.exists(FILENAME_PARQUET):
        return pd.read_parquet(FILENAME_PARQUET)
    return merge_and_clean_data()

# --- 4. BUSINESS LOGIC & STYLE ---

def apply_status_logic(row):
    """Missing Logic: Auto-calculates status based on project dates."""
    if pd.notna(row.get('Completion date')) and str(row.get('Completion date')).strip() != "":
        return "Closed"
    if pd.notna(row.get('Digital trial sent')) or pd.notna(row.get('Sent on Trial')):
        return "Trialing"
    if pd.notna(row.get('Artwork Received')):
        return "In Progress"
    return row.get('Status', 'Pending')

def style_df(df_to_style):
    """Fix for the Styler error: Simple styling that won't crash Arrow."""
    return df_to_style.astype(str)

# --- 5. APP INITIALIZATION ---
if 'active_tab' not in st.session_state: st.session_state.active_tab = "🔍 Search & Edit"
df = load_db()
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_FILES.items()}

# --- 6. TAB INTERFACE ---
tabs = st.tabs(["🔍 Search & Edit", "➕ Add New", "📊 Analysis", "🧪 Trials", "⚙️ Admin"])

with tabs[0]:
    st.subheader("Advanced Project Lookup")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search_query = st.text_input("Global Search", placeholder="ID, Client, or Product...").strip()
    with c2:
        st_list = ["All"] + sorted([str(x) for x in df['Status'].unique() if pd.notna(x)])
        st_filter = st.selectbox("Filter Status", st_list)
    with c3:
        rep_list = ["All"] + sorted([str(x) for x in df['Sales Rep'].unique() if pd.notna(x)])
        rep_filter = st.selectbox("Filter Sales Rep", rep_list)

    # Filter Logic
    view_df = df.copy()
    if search_query:
        mask = view_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
        view_df = view_df[mask]
    if st_filter != "All": view_df = view_df[view_df['Status'] == st_filter]
    if rep_filter != "All": view_df = view_df[view_df['Sales Rep'] == rep_filter]

    st.write(f"Results: {len(view_df)}")
    
    if not view_df.empty:
        selected_id = st.selectbox("Select Project to View/Edit", view_df['Pre-Prod No.'].values)
        row_idx = df.index[df['Pre-Prod No.'] == selected_id][0]
        row_data = df.loc[row_idx]

        with st.form("main_edit_form"):
            st.info(f"Editing Project: {selected_id}")
            
            # Mould Asset Logic Integration
            m_lookup = get_mould_lookup_data()
            selected_mould_desc = st.selectbox("Quick-Select Mould (Lookup)", options=[""] + list(m_lookup.keys()))
            
            f_c1, f_c2, f_c3 = st.columns(3)
            updated_vals = {}
            
            # Custom field groupings for better UI
            important_fields = ["Client", "Project Description", "Status", "Sales Rep", "Category"]
            for i, col in enumerate(important_fields):
                with [f_c1, f_c2, f_c3][i % 3]:
                    val = str(row_data.get(col, "")).replace('nan', '')
                    if col in DROPDOWN_DATA:
                        opts = sorted(list(set(["", val] + DROPDOWN_DATA[col])))
                        updated_vals[col] = st.selectbox(col, opts, index=opts.index(val))
                    else:
                        updated_vals[col] = st.text_input(col, value=val)

            st.divider()
            st.write("**Technical & Trial Specifications**")
            t_c1, t_c2, t_c3 = st.columns(3)
            tech_fields = [c for c in DESIRED_ORDER if c not in important_fields and c != "Pre-Prod No."]
            
            for i, col in enumerate(tech_fields):
                with [t_c1, t_c2, t_c3][i % 3]:
                    curr = str(row_data.get(col, "")).replace('nan', '')
                    if col in DROPDOWN_DATA:
                        opts = sorted(list(set(["", curr] + DROPDOWN_DATA[col])))
                        updated_vals[col] = st.selectbox(col, opts, index=opts.index(curr))
                    elif "date" in col.lower() or "sent" in col.lower():
                        updated_vals[col] = st.text_input(col, value=curr, help="YYYY-MM-DD")
                    else:
                        updated_vals[col] = st.text_input(col, value=curr)

            if st.form_submit_button("💾 Save Changes to Local Database"):
                # Apply Mould Lookup if chosen
                if selected_mould_desc:
                    updated_vals["New Mould_ Client or Product"] = m_lookup[selected_mould_desc]
                
                # Update Master DF
                for k, v in updated_vals.items():
                    df.at[row_idx, k] = v
                
                # Auto-status check
                df.at[row_idx, 'Status'] = apply_status_logic(df.loc[row_idx])
                
                save_db(df)
                st.success("Project updated successfully.")

with tabs[1]:
    st.subheader("New Project Registration")
    with st.form("new_entry_form"):
        # Auto-ID Logic
        existing_nums = [int(x) for x in df['Pre-Prod No.'].values if str(x).isdigit()]
        suggested_id = str(max(existing_nums) + 1).zfill(5) if existing_nums else "00001"
        
        new_id = st.text_input("New Pre-Prod No.", value=suggested_id)
        n_c1, n_c2 = st.columns(2)
        new_entry = {"Pre-Prod No.": new_id}
        
        for i, col in enumerate([c for c in DESIRED_ORDER if c != "Pre-Prod No."]):
            with [n_c1, n_c2][i % 2]:
                if col in DROPDOWN_DATA:
                    new_entry[col] = st.selectbox(f"New {col}", [""] + DROPDOWN_DATA[col])
                else:
                    new_entry[col] = st.text_input(f"New {col}")
        
        if st.form_submit_button("➕ Register Project"):
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            save_db(df)
            st.success(f"Project {new_id} created.")

with tabs[2]:
    st.subheader("Project Status Heatmap")
    # Using use_container_width=True as standard for styled DFs
    st.dataframe(style_df(df), use_container_width=True)
    
    if 'Age Category' in df.columns:
        st.write("**Summary by Age**")
        st.bar_chart(df['Age Category'].value_counts())

with tabs[3]:
    st.subheader("Weekly Trial Performance")
    trials = smart_read(TRIALS_FILE_CURRENT)
    if not trials.empty:
        st.dataframe(trials, use_container_width=True)
    else:
        st.info("Local trial summary file not detected.")

with tabs[4]:
    st.subheader("System Administration")
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        if st.button("🔄 Reload & Re-merge CSVs"):
            df = merge_and_clean_data()
            save_db(df)
            st.rerun()
            
    with col_a2:
        if st.button("☁️ Sync to Google Sheets"):
            try:
                client = get_gspread_client()
                if client:
                    sh = client.open_by_key(TRACKER_FILE_ID).get_worksheet(0)
                    sh.clear()
                    sh.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
                    st.success("Cloud Sync Complete!")
            except Exception as e:
                st.error(f"Sync failed: {e}")

    st.divider()
    csv_out = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Master CSV", data=csv_out, file_name="ProjectTracker_Export.csv", mime="text/csv")

