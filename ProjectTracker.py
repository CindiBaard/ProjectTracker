import os
import re
import io
import pandas as pd
import streamlit as st
from datetime import datetime

# --- 1. INITIAL SETUP & DEPENDENCIES ---
try:
    import matplotlib.pyplot as plt
except ImportError:
    st.error("Matplotlib is not installed. Please check your requirements.txt.")

try:
    import xlsxwriter
except ImportError:
    st.error("Missing dependency: Please run 'pip install xlsxwriter'")

try:
    import pyarrow
except ImportError:
    st.error("Missing dependency: Please run 'pip install pyarrow'")

# Google Auth Imports
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    st.error("Google Auth dependencies missing. Run: pip install gspread google-auth")

# Page Config
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATHS ---
BASE_DIR = os.getcwd() 
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv") 
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"

# --- 3. SESSION STATE INITIALIZATION ---
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'selected_combo' not in st.session_state:
    st.session_state.selected_combo = {}
if 'last_search_no' not in st.session_state:
    st.session_state.last_search_no = ""

# --- 4. UTILITY FUNCTIONS ---

def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == '': 
        return ""
    val_str = str(val).strip().split('.')[0]
    if '_' in val_str:
        parts = val_str.split('_', 1)
        return f"{parts[0].zfill(5)}_{parts[1]}"
    return val_str.zfill(5)

def clean_column_names(df):
    df.columns = [str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') for c in df.columns]
    return df

def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        comp_date = str(row.get('Completion date', '')).strip()
        if comp_date and comp_date.lower() != 'nan' and comp_date != '':
            end_date = pd.to_datetime(comp_date, dayfirst=True, errors='coerce')
        else:
            end_date = pd.to_datetime(datetime.now().date())
        if pd.isnull(start_date) or pd.isnull(end_date):
            return "N/A", 0
        days = (end_date - start_date).days
        cat = "< 6 Weeks" if days < 42 else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        return cat, days
    except: 
        return "Error", 0

def clean_key(val):
    if pd.isna(val) or str(val).strip() == '': return None
    s_val = str(val).strip()
    return s_val[:-2] if s_val.endswith('.0') else s_val

@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
                return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
        except: return []
    return []

# --- 5. DATA LOADING ---

@st.cache_data(show_spinner="Loading High-Performance Database...")
def load_db(tracker_file, digital_file, parquet_path, force_refresh=False):
    if force_refresh or not os.path.exists(parquet_path):
        if os.path.exists(tracker_file) and os.path.exists(digital_file):
            try:
                df_t = pd.read_csv(tracker_file, sep=None, engine='python', encoding='utf-8-sig')
                df_d = pd.read_csv(digital_file, sep=None, engine='python', encoding='utf-8-sig')
                df_d, df_t = clean_column_names(df_d), clean_column_names(df_t)
                
                # Align Column Names
                rename_map = {'Pre-Prod No': 'Pre-Prod No.', 'Pre Prod No.': 'Pre-Prod No.'}
                df_d = df_d.rename(columns=rename_map)
                
                df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].apply(clean_key)
                df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].apply(clean_key)
                
                combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), 
                                    df_d.dropna(subset=['Pre-Prod No.']), 
                                    on='Pre-Prod No.', how='outer', suffixes=('', '_digital_info'))
                
                combined['Pre-Prod No.'] = combined['Pre-Prod No.'].apply(pad_preprod_id)
                combined.to_parquet(parquet_path, index=False)
            except Exception as e: st.error(f"Merge Error: {e}")
                
    if not os.path.exists(parquet_path): return pd.DataFrame()
    df = pd.read_parquet(parquet_path)
    if 'Date' in df.columns:
        results = df.apply(calculate_age_category, axis=1)
        df['Age Category'], df['Project Age (Open and Closed)'] = [r[0] for r in results], [r[1] for r in results]
    return df

def load_from_google_sheets():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        # Use Streamlit Secrets for Auth
        creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M")
        return pd.DataFrame(spreadsheet.get_worksheet(0).get_all_records())
    except Exception as e:
        st.error(f"❌ Google Sheet Error: {e}")
        return pd.DataFrame()

# --- 6. UI CONFIGURATION ---
DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", 
    "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}

# --- 7. MAIN LOGIC ---
if st.sidebar.button("🔄 Force Refresh Database"):
    df = load_db(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET, force_refresh=True)
    st.sidebar.success("Database Rebuilt!")
else:
    df = load_db(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET)

# Navigation
tabs = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Google DB View"]
tab_nav = st.radio("Navigation", tabs, index=tabs.index(st.session_state.active_tab) if st.session_state.active_tab in tabs else 0, horizontal=True)
st.session_state.active_tab = tab_nav

st.title("🚀 Project Tracker Dashboard")

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    raw_search = st.text_input("Enter Pre-Prod No. (e.g. 9143)", key="search_box").strip()
    search_no = pad_preprod_id(raw_search)

    if search_no != st.session_state.last_search_no:
        st.session_state.last_search_no = search_no
        for key in list(st.session_state.keys()):
            if key.startswith("ed_"): del st.session_state[key]

    if search_no and not df.empty:
        match = df[df['Pre-Prod No.'] == search_no]
        if not match.empty:
            row = match.iloc[0]
            st.success(f"Found: {row.get('Client', 'Unknown Client')} - {row.get('Project Description', '')}")
            
            with st.form("edit_form"):
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input("Client", value=str(row.get('Client', '')), key="ed_client")
                    st.selectbox("Status", ["Open", "Closed", "On Hold"], index=0, key="ed_status")
                with c2:
                    st.text_input("Project Description", value=str(row.get('Project Description', '')), key="ed_desc")
                
                if st.form_submit_button("💾 Save Changes"):
                    st.info("Database saving logic (CSV/Parquet Write) would trigger here.")
        else:
            st.warning("No record found with that ID.")

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    st.subheader("Register New Manufacturing Trial")
    with st.form("add_job_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Client Name", key="new_client")
            st.selectbox("Machine", DROPDOWN_DATA.get("Machine", []), key="new_machine")
        with col2:
            st.date_input("Start Date", value=datetime.now(), key="new_date")
            st.selectbox("Sales Rep", DROPDOWN_DATA.get("Sales Rep", []), key="new_sales")
        
        if st.form_submit_button("➕ Create Project"):
            st.success("Project added to queue (Local Preview Only)")

# --- TAB: GOOGLE DB VIEW ---
elif tab_nav == "🌐 Google DB View":
    if st.button("🔄 Fetch Latest from Google"):
        with st.spinner("Connecting..."):
            st.session_state.google_data = load_from_google_sheets()
    
    if "google_data" in st.session_state:
        st.dataframe(st.session_state.google_data, use_container_width=True)

# --- GLOBAL SUMMARY METRICS ---
if not df.empty:
    st.divider()
    open_jobs = df[df['Open or closed'].str.lower().str.contains('open', na=False)]
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Open Jobs", len(open_jobs))
    m2.metric("Critical (>12w)", len(open_jobs[open_jobs['Age Category'] == "> 12 Weeks"]))
    m3.metric("Database Rows", len(df))
