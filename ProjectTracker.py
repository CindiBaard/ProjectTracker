import os
import pandas as pd
import streamlit as st
from datetime import datetime
import io
import re

if "selected_combo" not in st.session_state:
    st.session_state.selected_combo = {}

# This is where the fix happens
try:
    import matplotlib.pyplot as plt
except ImportError:
    st.error("Matplotlib is not installed. Please check your requirements.txt.")

# --- 1. INITIAL SETUP ---
try:
    import xlsxwriter
except ImportError:
    st.error("Missing dependency: Please run 'pip install xlsxwriter'")

try:
    import pyarrow
except ImportError:
    st.error("Missing dependency: Please run 'pip install pyarrow'")

st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# Initialize session state keys
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'selected_combo' not in st.session_state:
    st.session_state.selected_combo = {}

# --- 2. FILE PATHS ---
BASE_DIR = os.getcwd() 
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv") 
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")

# Updated Trial Data File
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"

# --- 3. HELPER FUNCTIONS ---

def pad_preprod_id(val):
    """Standardizes IDs: '9143' -> '09143' and '9143_1' -> '09143_1'."""
    if pd.isna(val) or str(val).strip() == '': 
        return ""
    val_str = str(val).strip().split('.')[0]
    if '_' in val_str:
        parts = val_str.split('_', 1)
        base = parts[0]
        suffix = parts[1]
        return f"{base.zfill(5)}_{suffix}"
    else:
        return val_str.zfill(5)

def reset_form_state():
    """Clears form data and resets the UI state."""
    st.session_state.form_data = {}
    st.session_state.selected_combo = {}
    for key in list(st.session_state.keys()):
        if key.startswith("txt_") or key.startswith("sel_") or key.startswith("ed_"):
            del st.session_state[key]
    st.rerun()

def get_auto_next_no(df):
    """Generates the next logical integer ID with 5-digit padding."""
    if df.empty or 'Pre-Prod No.' not in df.columns: 
        return "00001"
    nums = []
    for i in df['Pre-Prod No.'].tolist():
        match = re.match(r"(\d+)", str(i))
        if match: 
            nums.append(int(match.group(1)))
    if not nums:
        return "00001"
    next_val = max(nums) + 1
    return str(next_val).zfill(5)

def get_next_available_id(requested_id, existing_ids):
    requested_id = str(requested_id).strip()
    if requested_id not in existing_ids:
        return requested_id
    base_id = requested_id.split('_')[0]
    pattern = re.compile(rf"^{re.escape(base_id)}(_(\d+))?$")
    suffixes = []
    for eid in existing_ids:
        m = pattern.match(str(eid))
        if m:
            if m.group(2): suffixes.append(int(m.group(2)))
            else: suffixes.append(0)
    next_s = max(suffixes) + 1 if suffixes else 1
    return f"{base_id}_{next_s}"

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
    """Reads a CSV file and returns a sorted list of unique values for dropdowns."""
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
                return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
            return []
    return []

def save_db(df):
    """Saves the dataframe to parquet for performance."""
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data(show_spinner="Loading High-Performance Database...")
def load_db(tracker_file, digital_file, parquet_path, force_refresh=False):
    if force_refresh or not os.path.exists(parquet_path):
        if os.path.exists(tracker_file) and os.path.exists(digital_file):
            try:
                df_t = pd.read_csv(tracker_file, sep=None, engine='python', encoding='utf-8-sig', on_bad_lines='warn')
                df_d = pd.read_csv(digital_file, sep=None, engine='python', encoding='utf-8-sig', on_bad_lines='warn')
                
                df_d = clean_column_names(df_d)
                df_t = clean_column_names(df_t)
                
                if 'Pre-Prod No' in df_d.columns: df_d = df_d.rename(columns={'Pre-Prod No': 'Pre-Prod No.'})
                elif 'Pre Prod No.' in df_d.columns: df_d = df_d.rename(columns={'Pre Prod No.': 'Pre-Prod No.'})
                
                df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].apply(clean_key)
                df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].apply(clean_key)
                
                combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), df_d.dropna(subset=['Pre-Prod No.']), on='Pre-Prod No.', how='outer', suffixes=('', '_digital_info'))
                
                if 'Pre-Prod No.' in combined.columns: combined['Pre-Prod No.'] = combined['Pre-Prod No.'].apply(pad_preprod_id)
                
                for col in combined.columns:
                    if combined[col].dtype == 'object' or col == 'Diameter': 
                        combined[col] = combined[col].astype(str).replace('nan', '')
                
                combined.to_parquet(parquet_path, index=False)
            except Exception as e: 
                st.error(f"Merge Error: {e}")
                
    if not os.path.exists(parquet_path): 
        return pd.DataFrame()
        
    df = pd.read_parquet(parquet_path)
    df = clean_column_names(df)
    
    if 'Pre-Prod No.' in df.columns:
        df['Pre-Prod No.'] = df['Pre-Prod No.'].apply(pad_preprod_id)
        df = df.sort_values(by='Pre-Prod No.', ascending=True).reset_index(drop=True)
    
    if 'Date' in df.columns:
        results = df.apply(calculate_age_category, axis=1)
        df['Age Category'] = [r[0] for r in results]
        df['Project Age (Open and Closed)'] = [r[1] for r in results]
        df['Project Age (Open and Closed)'] = pd.to_numeric(df['Project Age (Open and Closed)'], errors='coerce').fillna(0)
    return df

def load_from_google_sheets():
    """
    Connects to Google Sheets and returns the data as a DataFrame.
    """
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        
        # Re-use your existing auth logic
        if "gcp_service_account" in st.secrets:
            creds_info = st.secrets["gcp_service_account"]
        else:
            creds_info = {
                "type": "service_account",
                "project_id": "projecttracker-491911",
                "private_key_id": "113bbec16cec5c007a64e24ab4c84faf55ce7733",
                "private_key": st.secrets["private_key"],
                "client_email": "projecttracker@projecttracker-491911.iam.gserviceaccount.com",
                "client_id": "115177684337876407555",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.google.com/token",
            }

        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)

        sheet_id = "1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M"
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        
        # Get all records and convert to DataFrame
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
        
    except Exception as e:
        st.error(f"❌ Could not read Google Sheet: {e}")
        return pd.DataFrame()

# --- 4. TRIAL DATA CONFIG ---
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"

@st.cache_data
def load_trial_data():
    """Helper to load and process the trials trending data."""
    if os.path.exists(TRIALS_FILE_CURRENT):
        try:
            # Added sep=None and engine='python' so it detects semicolons OR commas automatically
            df = pd.read_csv(TRIALS_FILE_CURRENT, sep=None, engine='python', encoding='utf-8-sig')
            df = clean_column_names(df)
            
            # Convert dates - ensuring the column names match your CSV exactly
            # If your CSV uses 'Date Log' (with a space), clean_column_names changes it to 'Date_Log'
            df['Date_Log'] = pd.to_datetime(df['Date_Log'], dayfirst=True, errors='coerce')
            df['Completion_Date'] = pd.to_datetime(df['Completion_Date'], dayfirst=True, errors='coerce')
            
            # Remove rows where dates failed to parse
            df = df.dropna(subset=['Date_Log', 'Completion_Date'])
            
            # Calculate metrics
            df['Days_Taken'] = (df['Completion_Date'] - df['Date_Log']).dt.days
            df['Week_Num'] = df['Date_Log'].dt.isocalendar().week
            
            # Sort by date so the line chart flows chronologically
            df = df.sort_values('Date_Log')
            
            return df
        except Exception as e:
            st.error(f"Error loading trial data: {e}")
            return pd.DataFrame()
    else:
        st.warning(f"File not found: {TRIALS_FILE_CURRENT}")
        return pd.DataFrame()

# --- 5. CONFIGURATIONS & DROPDOWN DATA ---
DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", 
    "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}

DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}

DESIRED_ORDER = [
    "Date", "Age Category", "Client", "Project Description", "New Mould_Client or Product", 
    "Product Code", "Machine", "Sales Rep", "Category", "Status", "Open or closed", 
    "Completion date", "Material", "Product Material Colour (tube, jar etc.)", 
    "Artwork Required", "Artwork Received", "Order Qty x1000", "Unit Order No", 
    "Length", "Cap_Lid Style", "Cap_Lid Material", "Cap_Lid Diameter", "Orifice", "Other Cap_Lid Info", 
    "Tube Shoulder colour", "Dust Controlled Area", "Date Sent on Proof", "Size of Eyemark", 
    "Proof Approved (Conventional)", "Proof Approved (Digital)", "Ordered Plates", 
    "Plates Arrived", "Sent on Trial", "Digital trial received", 
    "Revised Artwork After Trialling", "Masterbatch received", "Extrusion requested", 
    "Extrusion received", "Injection trial requested", "Injection Trial Received", 
    "Blowmould trial requested", "Blowmould trial received", "Comments"
]

# --- 6. INITIALIZE DATA & UI HELPERS ---

def display_combination_table(key_prefix):
    """The expandable helper for Tube & Cap combinations."""
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Browse Tube & Cap Combinations", expanded=False):
            try:
                # FIX: Added sep=';' to correctly split the columns
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig')
                
                # Clean column names to remove any invisible characters
                combo_df = clean_column_names(combo_df)
                
                search = st.text_input(f"🔍 Filter List", key=f"{key_prefix}_search")
                if search:
                    mask = combo_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
                    combo_df = combo_df[mask]
                
                # Display as a clean, interactive table
                event = st.dataframe(
                    combo_df, 
                    use_container_width=True, 
                    hide_index=True, 
                    on_select="rerun", 
                    selection_mode="single-row", 
                    key=f"{key_prefix}_table"
                )
                
                if event.selection.rows:
                    sel_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    
                    # Logic: Map the CSV columns to your app's internal keys
                    # Ensure the keys here match your DESIRED_ORDER list exactly
                    st.session_state.selected_combo = {
                        "Diameter": str(sel_row.get("Diameter", "")),
                        "Cap_Lid Style": str(sel_row.get("Cap_Lid Style", "")),
                        "Cap_Lid Diameter": str(sel_row.get("Cap_Lid Diameter", "")),
                        "Cap_Lid Material": str(sel_row.get("Cap_Lid Material", ""))
                    }
                    st.toast("✅ Combination Selected")
                    
            except Exception as e: 
                st.error(f"Error loading combos: {e}")

# FIX: Corrected variable name TRACKER_ADJ_FILE
if st.sidebar.button("🔄 Force Refresh from CSVs"):
    df = load_db(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET, force_refresh=True)
    st.sidebar.success("Database Rebuilt!")
else:
    df = load_db(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET)

if not df.empty and 'Client' in df.columns:
    client_list = sorted([str(c) for c in df['Client'].unique() if str(c).strip() and str(c).lower() != 'nan'])
    DROPDOWN_DATA['Client'] = client_list

# --- 7. UI: DASHBOARD SUMMARY ---
col_title, col_export = st.columns([4, 1])
with col_title:
    st.title("🚀 Project Tracker Dashboard")

if not df.empty:
    pp_open = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
    
    with st.container():
        st.subheader("📊 Pre-Prod Age Analysis Summary")
        total_open_pp = len(pp_open)
        critical_pp = len(pp_open[pp_open['Age Category'] == "> 12 Weeks"])
        mid_pp = len(pp_open[pp_open['Age Category'] == "6-12 Weeks"])
        
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1: st.metric("Total Open PP", total_open_pp)
        with c2: 
            pct_crit = (critical_pp / total_open_pp * 100) if total_open_pp > 0 else 0
            st.metric("Critical (>12w)", critical_pp, delta=f"{pct_crit:.1f}%", delta_color="inverse")
        with c3: st.metric("Mid-Term (6-12w)", mid_pp)
        with c4:
            age_dist = pp_open['Age Category'].value_counts().reindex(["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"], fill_value=0)
            st.bar_chart(age_dist, height=150)

        if critical_pp > 0:
            with st.expander(f"⚠️ View {critical_pp} Critical Projects (>12 Weeks Old)", expanded=False):
                critical_list = pp_open[pp_open['Age Category'] == "> 12 Weeks"][['Pre-Prod No.', 'Client', 'Project Age (Open and Closed)', 'Sales Rep']]
                st.table(critical_list.sort_values('Project Age (Open and Closed)', ascending=False))

with col_export:
    if not df.empty:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Projects')
        st.download_button(label="📥 Download Excel", data=output.getvalue(), file_name=f"Project_Database_{datetime.now().strftime('%Y%m%d')}.xlsx")

st.divider()

## --- 8. UI: TABS & NAVIGATION ---
tabs = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Google DB View"]
tab_nav = st.radio("Navigation", tabs, index=tabs.index(st.session_state.active_tab) if st.session_state.active_tab in tabs else 0, horizontal=True)
st.session_state.active_tab = tab_nav

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    col_search, col_clear_btn = st.columns([4, 1])
    with col_search:
        raw_search = st.text_input("Search Pre-Prod No.", key="search_input_box").strip()
    
    with col_clear_btn:
        st.write("##") 
        if st.button("♻️ Clear Search", use_container_width=True):
            if "search_input_box" in st.session_state:
                del st.session_state["search_input_box"]
            st.session_state.last_search_no = ""
            st.rerun()

    search_no = pad_preprod_id(raw_search) if raw_search else ""
    match = df[df['Pre-Prod No.'] == search_no] if 'Pre-Prod No.' in df.columns else pd.DataFrame()
    
    if search_no and not match.empty:
        # ... (Your existing Edit Details code goes here, indented once) ...
        st.write(f"Editing: {search_no}") 
    elif search_no:
        st.info(f"No results found for {search_no}")

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    display_combination_table("new")
    # ... (Your existing Add New Job form code goes here, indented once) ...

# --- TAB: DETAILED AGE ANALYSIS ---
elif tab_nav == "📊 Detailed Age Analysis":
    if not df.empty:
        open_only = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
        st.bar_chart(open_only['Age Category'].value_counts())

# --- TAB: TRIAL TRENDS ---
elif tab_nav == "🧪 Trial Trends":
    st.subheader("🧪 Weekly Average Trial Turnaround (2026)")
    df_trials = load_trial_data()
    if not df_trials.empty:
        st.line_chart(df_trials.groupby(df_trials['Date_Log'].dt.isocalendar().week)['Days_Taken'].mean())
    else:
        st.warning("No trial data found.")

# --- TAB: GOOGLE DB VIEW ---
elif tab_nav == "🌐 Google DB View":
    st.subheader("🌐 Live Google Sheets Database")
    st.info("This shows data currently in the cloud.")

    if st.button("🔄 Fetch Latest from Google"):
        with st.spinner("Accessing Google Sheets..."):
            gs_df = load_from_google_sheets()
            if not gs_df.empty:
                st.session_state.google_data = gs_df
                st.success("Data fetched!")

    if "google_data" in st.session_state:
        gs_search = st.text_input("🔍 Filter Cloud Data")
        display_df = st.session_state.google_data
        if gs_search:
            mask = display_df.apply(lambda row: row.astype(str).str.contains(gs_search, case=False).any(), axis=1)
            display_df = display_df[mask]
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)