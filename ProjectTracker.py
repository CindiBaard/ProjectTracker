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

# --- 2. FILE PATHS & CONFIG ---
BASE_DIR = os.getcwd() 
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv") 
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"

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
    if pd.isna(val) or str(val).strip() == '': return ""
    val_str = str(val).strip().split('.')[0]
    if '_' in val_str:
        parts = val_str.split('_', 1)
        return f"{parts[0].zfill(5)}_{parts[1]}"
    return val_str.zfill(5)

def get_auto_next_no(df):
    if df.empty or 'Pre-Prod No.' not in df.columns: return "00001"
    nums = []
    for i in df['Pre-Prod No.'].tolist():
        match = re.match(r"(\d+)", str(i))
        if match: nums.append(int(match.group(1)))
    return str(max(nums) + 1).zfill(5) if nums else "00001"

def get_next_available_id(requested_id, existing_ids):
    base_id = str(requested_id).split('_')[0].zfill(5)
    pattern = re.compile(rf"^{re.escape(base_id)}(_(\d+))?$")
    suffixes = [int(m.group(2)) if m.group(2) else 0 for eid in existing_ids if (m := pattern.match(str(eid)))]
    return f"{base_id}_{max(suffixes) + 1 if suffixes else 1}"

def clean_column_names(df):
    df.columns = [str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') for c in df.columns]
    return df

def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        comp_date = str(row.get('Completion date', '')).strip()
        end_date = pd.to_datetime(comp_date, dayfirst=True, errors='coerce') if comp_date and comp_date.lower() != 'nan' else pd.to_datetime(datetime.now().date())
        if pd.isnull(start_date): return "N/A", 0
        days = (end_date - start_date).days
        cat = "< 6 Weeks" if days < 42 else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        return cat, max(0, days)
    except: return "Error", 0

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

# --- 5. DATA LOADING (Local & Google) ---

def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data(show_spinner="Refreshing Database...")
def load_db(tracker_file, digital_file, parquet_path, force_refresh=False):
    if force_refresh or not os.path.exists(parquet_path):
        try:
            df_t = pd.read_csv(tracker_file, sep=None, engine='python', encoding='utf-8-sig')
            df_d = pd.read_csv(digital_file, sep=None, engine='python', encoding='utf-8-sig')
            df_d, df_t = clean_column_names(df_d), clean_column_names(df_t)
            df_d = df_d.rename(columns={'Pre-Prod No': 'Pre-Prod No.', 'Pre Prod No.': 'Pre-Prod No.'})
            combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), df_d.dropna(subset=['Pre-Prod No.']), on='Pre-Prod No.', how='outer', suffixes=('', '_dig'))
            combined['Pre-Prod No.'] = combined['Pre-Prod No.'].astype(str).apply(pad_preprod_id)
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
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
        # DNS Fix: ensure private key formatting
        if isinstance(creds_info, dict) and "private_key" in creds_info:
             creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M")
        return pd.DataFrame(spreadsheet.get_worksheet(0).get_all_records())
    except Exception as e:
        st.error(f"🌐 Google Sheet Error: {e}")
        return pd.DataFrame()

# --- 6. UI HELPERS ---

def display_combination_table(key_prefix):
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Browse Tube & Cap Combinations", expanded=False):
            try:
                combo_df = clean_column_names(pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig'))
                search = st.text_input(f"🔍 Filter List", key=f"{key_prefix}_search")
                if search:
                    combo_df = combo_df[combo_df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
                event = st.dataframe(combo_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key=f"{key_prefix}_table")
                if event.selection.rows:
                    sel_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    st.session_state.selected_combo = {
                        "Diameter": str(sel_row.get("Diameter", "")),
                        "Cap_Lid Style": str(sel_row.get("Cap_Lid Style", "")),
                        "Cap_Lid Diameter": str(sel_row.get("Cap_Lid Diameter", "")),
                        "Cap_Lid Material": str(sel_row.get("Cap_Lid Material", ""))
                    }
                    st.toast("✅ Specs Selected")
            except Exception as e: st.error(f"Combo Error: {e}")

# --- 7. MAIN LOGIC ---
df = load_db(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET, force_refresh=st.sidebar.button("🔄 Rebuild Local DB"))

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
if not df.empty:
    DROPDOWN_DATA['Client'] = sorted([str(c) for c in df['Client'].unique() if str(c).strip() and str(c).lower() != 'nan'])

# Navigation
tabs_list = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Google DB View"]
tab_nav = st.radio("Navigation", tabs_list, index=tabs_list.index(st.session_state.active_tab), horizontal=True)
st.session_state.active_tab = tab_nav

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    c_s, c_cl = st.columns([4, 1])
    raw_search = c_s.text_input("Search Pre-Prod No.", key="search_input_box").strip()
    if c_cl.button("♻️ Clear", use_container_width=True):
        st.session_state.last_search_no = ""
        st.rerun()

    search_no = pad_preprod_id(raw_search)
    if search_no != st.session_state.last_search_no:
        st.session_state.last_search_no = search_no
        st.rerun()

    match = df[df['Pre-Prod No.'] == search_no] if not df.empty else pd.DataFrame()
    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        
        # Actions
        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("👯 Clone for Repeat Order", use_container_width=True):
            new_clone = row.to_dict()
            new_clone.update({'Pre-Prod No.': get_next_available_id(search_no, df['Pre-Prod No.']), 'Date': datetime.now().strftime('%d/%m/%Y'), 'Completion date': ""})
            st.session_state.form_data = new_clone
            st.session_state.active_tab = "➕ Add New Job"
            st.rerun()
        
        display_combination_table("edit")
        with st.form("edit_form"):
            st.subheader(f"Editing: {search_no}")
            edit_cols = st.columns(3)
            updated_vals = {}
            selected = st.session_state.get("selected_combo", {})
            
            for i, col in enumerate(DESIRED_ORDER):
                if col == "Age Category": continue
                cur_val = selected.get(col, str(row.get(col, "")).replace('nan', ''))
                with edit_cols[i % 3]:
                    if col == 'Completion date' or col == 'Date':
                        try: d_val = pd.to_datetime(cur_val, dayfirst=True).date() if cur_val else None
                        except: d_val = None
                        d_input = st.date_input(col, value=d_val, key=f"ed_{col}")
                        updated_vals[col] = d_input.strftime('%d/%m/%Y') if d_input else ""
                    elif col in DROPDOWN_DATA:
                        opts = sorted(list(set([""] + DROPDOWN_DATA[col] + [cur_val])))
                        updated_vals[col] = st.selectbox(col, opts, index=opts.index(cur_val), key=f"sel_{col}")
                    else:
                        updated_vals[col] = st.text_input(col, value=cur_val, key=f"txt_{col}")

            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                status = "Closed" if updated_vals.get("Completion date") else "Open"
                updated_vals.update({"Status": status, "Open or closed": status})
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df)
                st.session_state.selected_combo = {}
                st.success("Saved!")
                st.rerun()

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    display_combination_table("new")
    selected = st.session_state.get("selected_combo", {})
    default_id = st.session_state.form_data.get('Pre-Prod No.', get_auto_next_no(df))
    
    with st.form("new_job_form"):
        st.subheader("New Project Entry")
        new_id = st.text_input("Pre-Prod No.", value=default_id)
        new_cols = st.columns(3)
        new_entry = {"Pre-Prod No.": new_id}
        
        for i, col in enumerate(DESIRED_ORDER):
            if col == "Age Category": continue
            val = selected.get(col, st.session_state.form_data.get(col, ""))
            with new_cols[i % 3]:
                if col == 'Date':
                    new_entry[col] = st.date_input(col, value=datetime.now()).strftime('%d/%m/%Y')
                elif col in DROPDOWN_DATA:
                    opts = sorted(list(set([""] + DROPDOWN_DATA[col] + ([val] if val else []))))
                    new_entry[col] = st.selectbox(col, opts, index=opts.index(val) if val in opts else 0)
                else:
                    new_entry[col] = st.text_input(col, value=val)

        if st.form_submit_button("➕ Create Project", use_container_width=True):
            status = "Closed" if new_entry.get("Completion date") else "Open"
            new_entry.update({"Status": status, "Open or closed": status})
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            save_db(df)
            st.session_state.form_data = {}
            st.session_state.selected_combo = {}
            st.success("Job Added!")

# --- TAB: GOOGLE VIEW ---
elif tab_nav == "🌐 Google DB View":
    if st.button("🔄 Fetch Cloud Data"):
        st.session_state.google_data = load_from_google_sheets()
    if "google_data" in st.session_state:
        st.dataframe(st.session_state.google_data, use_container_width=True)

# Summary Metrics (Bottom)
if not df.empty:
    st.divider()
    open_jobs = df[df['Open or closed'].str.lower().str.contains('open', na=False)]
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Open Jobs", len(open_jobs))
    m2.metric("Critical (>12w)", len(open_jobs[open_jobs['Age Category'] == "> 12 Weeks"]))
    m3.metric("Avg Age (Days)", int(open_jobs['Project Age (Open and Closed)'].mean()) if not open_jobs.empty else 0)
