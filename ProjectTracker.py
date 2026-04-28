import os
import re
import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime

# --- 1. INITIAL SETUP & DEPENDENCIES ---
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATHS & CONFIG ---
BASE_DIR = os.getcwd() 
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv") 
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")

# --- 3. FIXED DESIRED ORDER ---
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

# --- 4. SESSION STATE ---
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'selected_combo' not in st.session_state:
    st.session_state.selected_combo = {}

# --- 5. UTILITY FUNCTIONS ---
def get_auto_next_no(df):
    if df is None or df.empty or 'Pre-Prod No.' not in df.columns: return "00001"
    try:
        nums = df['Pre-Prod No.'].str.extract(r'(\d+)')[0].dropna().astype(int)
        return str(int(nums.max()) + 1).zfill(5) if not nums.empty else "00001"
    except: return "00001"

def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == '': return ""
    return str(val).strip().split('.')[0]

def clean_column_names(df):
    df.columns = [str(c).replace('\ufeff', '').replace('ï»¿', '').strip() for c in df.columns]
    return df.rename(columns={'Pre-Prod No': 'Pre-Prod No.', 'Pre Prod No.': 'Pre-Prod No.'})

def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        comp_val = str(row.get('Completion date', '')).strip()
        end_date = pd.to_datetime(comp_val, dayfirst=True, errors='coerce') if comp_val and comp_val.lower() != 'nan' else pd.to_datetime(datetime.now().date())
        if pd.isnull(start_date): return "N/A", 0
        days = (end_date - start_date).days
        cat = "< 6 Weeks" if days < 42 else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        return cat, max(0, days)
    except: return "Error", 0

@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='latin1', errors='ignore') as f:
            lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
            return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
    return []

def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data(show_spinner="Loading...")
def load_db_v2(tracker_path, digital_path, parquet_path):
    if os.path.exists(parquet_path): return pd.read_parquet(parquet_path)
    try:
        df_t = clean_column_names(pd.read_csv(tracker_path, on_bad_lines='skip').replace('#REF!', np.nan))
        df_d = clean_column_names(pd.read_csv(digital_path, on_bad_lines='skip').replace('#REF!', np.nan))
        combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), df_d.dropna(subset=['Pre-Prod No.']), on='Pre-Prod No.', how='outer', suffixes=('', '_dig'))
        if not combined.empty and 'Date' in combined.columns:
            res = combined.apply(calculate_age_category, axis=1)
            combined['Age Category'], combined['Project Age (Open and Closed)'] = [r[0] for r in res], [r[1] for r in res]
        combined.to_parquet(parquet_path, index=False)
        return combined
    except: return pd.DataFrame()

# --- 6. MAIN UI ---
df = load_db_v2(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET)
if df.empty: df = pd.DataFrame(columns=DESIRED_ORDER)

st.title("Project Tracker Dashboard")

# DROPDOWNS
DROPDOWN_CONFIG = {"Category": "Category.csv", "Machine": "Machine.csv", "Sales Rep": "Sales Rep.csv", "Material": "Material.csv"}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}

tabs_list = ["🔍 Search & Edit", "➕ Add New Job", "🌐 Cloud Sync"]
tab_nav = st.radio("Navigation", tabs_list, index=tabs_list.index(st.session_state.active_tab), horizontal=True)
st.session_state.active_tab = tab_nav

if tab_nav == "🔍 Search & Edit":
    raw_search = st.text_input("Search Pre-Prod No.").strip()
    search_no = pad_preprod_id(raw_search)
    match = df[df['Pre-Prod No.'].astype(str) == search_no] if search_no else pd.DataFrame()

    if not match.empty:
        idx, row = match.index[0], match.iloc[0]
        
        # FORM START
        with st.form("edit_form"):
            st.subheader(f"Editing: {search_no}")
            edit_cols = st.columns(3)
            updated_vals = {}
            
            for i, col in enumerate(DESIRED_ORDER):
                if col in ["Age Category", "Project Age (Open and Closed)"]: continue
                cur_val = str(row.get(col, "")).replace('nan', '')
                
                with edit_cols[i % 3]:
                    if "date" in col.lower() or col == "Date":
                        # Safety check for date values to prevent ValueError
                        try:
                            d_parsed = pd.to_datetime(cur_val, dayfirst=True, errors='coerce')
                            d_val = d_parsed.date() if pd.notnull(d_parsed) else datetime.now().date()
                        except:
                            d_val = datetime.now().date()
                        
                        d_input = st.date_input(col, value=d_val, key=f"ed_{col}")
                        updated_vals[col] = d_input.strftime('%d/%m/%Y')
                    elif col in DROPDOWN_DATA:
                        opts = sorted(list(set([""] + DROPDOWN_DATA[col] + [cur_val])))
                        updated_vals[col] = st.selectbox(col, opts, index=opts.index(cur_val), key=f"sel_{col}")
                    else:
                        updated_vals[col] = st.text_input(col, value=cur_val, key=f"txt_{col}")

            # Correctly indented submit button
            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df)
                st.cache_data.clear()
                st.success("Saved!")
                st.rerun()
    elif search_no:
        st.warning("No project found.")

elif tab_nav == "➕ Add New Job":
    with st.form("new_job_form"):
        st.subheader("New Project Entry")
        new_id = st.text_input("Pre-Prod No.", value=get_auto_next_no(df))
        if st.form_submit_button("➕ Create Project"):
            st.success(f"Job {new_id} added (Simulated)")

elif tab_nav == "🌐 Cloud Sync":
    st.info("Cloud Sync Module Active")