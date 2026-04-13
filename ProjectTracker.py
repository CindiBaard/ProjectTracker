import os
import re
import io
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. INITIAL SETUP ---
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")

# --- 2. FILE PATHS & CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
if 'last_search_no' not in st.session_state:
    st.session_state.last_search_no = ""
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'selected_combo' not in st.session_state:
    st.session_state.selected_combo = {}

# --- 4. UTILITY FUNCTIONS ---
def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() in ['', 'None', 'nan', 'NaN']: return ""
    val_str = str(val).strip().split('.')[0]
    if '_' in val_str:
        parts = val_str.split('_', 1)
        return f"{parts[0].zfill(5)}_{parts[1]}"
    return val_str.zfill(5)

def clean_data_types(df):
    """Force everything to string and remove 'None' or 'nan' artifacts."""
    return df.astype(str).replace(['None', 'nan', 'NaN', '<NA>', 'nan.0'], '')

def save_db(df):
    try:
        df = clean_data_types(df)
        df.to_parquet(FILENAME_PARQUET, index=False)
    except Exception as e:
        st.error(f"Error saving database: {e}")

@st.cache_data
def load_db():
    if os.path.exists(FILENAME_PARQUET):
        try:
            df = pd.read_parquet(FILENAME_PARQUET)
            return clean_data_types(df)
        except: return pd.DataFrame()
    return pd.DataFrame()

def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
                return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
        except: return []
    return []

def get_auto_next_no(df):
    if df.empty or 'Pre-Prod No.' not in df.columns: return "00001"
    try:
        nums = df['Pre-Prod No.'].str.extract(r'(\d+)')[0].dropna().astype(int)
        return str(int(nums.max()) + 1).zfill(5) if not nums.empty else "00001"
    except: return "00001"

def display_combination_table(key_prefix):
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Browse Tube & Cap Combinations", expanded=False):
            try:
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig')
                search = st.text_input(f"🔍 Filter Specs", key=f"{key_prefix}_search")
                if search:
                    combo_df = combo_df[combo_df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
                # FIXED: Added quotes around "stretch"
                event = st.dataframe(combo_df, width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key=f"{key_prefix}_table")
                if event.selection.rows:
                    sel_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    st.session_state.selected_combo = {
                        "Cap_Lid Style": str(sel_row.get("Cap_Lid Style", "")),
                        "Cap_Lid Diameter": str(sel_row.get("Cap_Lid Diameter", "")),
                        "Cap_Lid Material": str(sel_row.get("Cap_Lid Material", ""))
                    }
                    st.toast("✅ Specs Selected")
            except Exception as e: st.error(f"Combo Error: {e}")

# --- 5. DATA LOADING ---
df = load_db()

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
if not df.empty and 'Client' in df.columns:
    DROPDOWN_DATA['Client'] = sorted([str(c) for c in df['Client'].unique() if str(c).strip() and str(c).lower() != 'nan'])

# --- 6. NAVIGATION ---
tabs_list = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Cloud Sync"]
tab_nav = st.radio("Navigation", tabs_list, index=tabs_list.index(st.session_state.active_tab), horizontal=True)
st.session_state.active_tab = tab_nav

# --- TAB 1: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    st.subheader("Search & Update Projects")
    c1, c2 = st.columns([4, 1])
    raw_search = c1.text_input("Enter Pre-Prod No.", value=st.session_state.last_search_no).strip()
    if c2.button("Clear Search", width="stretch"):
        st.session_state.last_search_no = ""
        st.rerun()

    if raw_search:
        search_no = pad_preprod_id(raw_search)
        st.session_state.last_search_no = search_no
        match = df[df['Pre-Prod No.'] == search_no] if not df.empty else pd.DataFrame()

        if not match.empty:
            idx, row = match.index[0], match.iloc[0]
            display_combination_table("edit")
            
            with st.form("edit_form"):
                st.write(f"### Editing Project: {search_no}")
                edit_cols = st.columns(3)
                updated_vals = {}
                selected = st.session_state.get("selected_combo", {})

                for i, col in enumerate(DESIRED_ORDER):
                    if col == "Age Category": continue
                    
                    cur_val = selected.get(col, str(row.get(col, ""))).replace('None', '').replace('nan', '').strip()
                    
                    with edit_cols[i % 3]:
                        if col == "Injection trial requested":
                            st.write(f"**{col}**")
                            if cur_val: st.info(cur_val)
                            else: st.write("No trials recorded.")
                            updated_vals[col] = cur_val
                        elif col in ['Completion date', 'Date']:
                            # FIXED: More robust date parsing for 2026
                            try: d_val = pd.to_datetime(cur_val, dayfirst=False, errors='coerce').date() if cur_val else None
                            except: d_val = None
                            d_input = st.date_input(col, value=d_val, key=f"ed_{col}")
                            updated_vals[col] = d_input.strftime('%d/%m/%Y') if d_input else ""
                        elif col in DROPDOWN_DATA:
                            opts = sorted(list(set([""] + DROPDOWN_DATA[col] + [cur_val])))
                            updated_vals[col] = st.selectbox(col, opts, index=opts.index(cur_val), key=f"sel_{col}")
                        else:
                            updated_vals[col] = st.text_input(col, value=cur_val, key=f"txt_{col}")

                if st.form_submit_button("💾 Save Changes", width="stretch"):
                    for k, v in updated_vals.items(): df.at[idx, k] = v
                    save_db(df)
                    st.session_state.selected_combo = {}
                    st.success("✅ Changes Saved Locally!")
                    st.rerun()
        else:
            st.warning(f"No project found for '{search_no}'")

# --- TAB 2: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    st.subheader("Add New Project")
    display_combination_table("new")
    selected = st.session_state.get("selected_combo", {})
    
    with st.form("new_job_form"):
        new_id = st.text_input("Pre-Prod No.", value=get_auto_next_no(df))
        new_cols = st.columns(3)
        new_entry = {"Pre-Prod No.": new_id}
        
        for i, col in enumerate(DESIRED_ORDER):
            if col == "Age Category": continue
            val = selected.get(col, "")
            with new_cols[i % 3]:
                if col == 'Date':
                    new_entry[col] = st.date_input(col, value=datetime.now()).strftime('%d/%m/%Y')
                elif col in DROPDOWN_DATA:
                    opts = sorted(list(set([""] + DROPDOWN_DATA[col] + ([val] if val else []))))
                    new_entry[col] = st.selectbox(col, opts, index=opts.index(val) if val in opts else 0)
                else:
                    new_entry[col] = st.text_input(col, value=val)

        if st.form_submit_button("➕ Create Project", width="stretch"):
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            save_db(df)
            st.session_state.selected_combo = {}
            st.success("✅ New Project Created!")
            st.rerun()

# --- TAB 5: CLOUD SYNC ---
elif tab_nav == "🌐 Cloud Sync":
    st.subheader("🌐 Google Sheets Database Sync")
    
    col_a, col_b = st.columns(2)
    
    if col_a.button("📥 Fetch & Sync from Google", width="stretch"):
        with st.status("Fetching from Cloud...") as status:
            try:
                scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                if "gcp_service_account" in st.secrets:
                    creds_dict = dict(st.secrets["gcp_service_account"])
                else:
                    creds_dict = dict(st.secrets["connections"]["gsheets"])

                if "private_key" in creds_dict:
                    pk = creds_dict["private_key"].strip().strip('"').strip("'").replace("\\n", "\n")
                    if not pk.startswith("-----BEGIN PRIVATE KEY-----"):
                        pk = "-----BEGIN PRIVATE KEY-----\n" + pk
                    if not pk.endswith("-----END PRIVATE KEY-----"):
                        pk = pk + "\n-----END PRIVATE KEY-----"
                    creds_dict["private_key"] = pk

                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                client = gspread.authorize(creds)
                spreadsheet = client.open_by_key("1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M")
                worksheet = spreadsheet.get_worksheet(0)
                
                cloud_data = pd.DataFrame(worksheet.get_all_records())
                if not cloud_data.empty:
                    cloud_data = clean_data_types(cloud_data)
                    cloud_data.to_parquet(FILENAME_PARQUET, index=False)
                    st.cache_data.clear()
                    status.update(label="✅ Sync Complete!", state="complete")
                    st.success("Local database updated from Google Sheets.")
                    st.rerun()
                else:
                    st.warning("Google Sheet was empty.")
            except Exception as e:
                st.error(f"Sync Error: {e}")

    if col_b.button("📤 Push Local Data to Google", width="stretch", type="primary"):
        with st.spinner("Pushing to Cloud..."):
            try:
                scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                if "gcp_service_account" in st.secrets:
                    creds_dict = dict(st.secrets["gcp_service_account"])
                else:
                    creds_dict = dict(st.secrets["connections"]["gsheets"])

                if "private_key" in creds_dict:
                    pk = creds_dict["private_key"].strip().strip('"').strip("'").replace("\\n", "\n")
                    creds_dict["private_key"] = pk

                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                client = gspread.authorize(creds)
                spreadsheet = client.open_by_key("1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M")
                worksheet = spreadsheet.get_worksheet(0)
                
                worksheet.clear()
                export_df = df.fillna("")
                worksheet.update([export_df.columns.values.tolist()] + export_df.values.tolist())
                st.success("✅ Local data pushed to Google Sheets!")
            except Exception as e:
                st.error(f"Push failed: {e}")

# --- ANALYTICS TABS ---
elif tab_nav == "📊 Detailed Age Analysis":
    st.subheader("Project Age Distribution")
    if not df.empty and 'Age Category' in df.columns:
        age_counts = df['Age Category'].value_counts()
        st.bar_chart(age_counts)
        st.dataframe(df, width="stretch")

elif tab_nav == "🧪 Trial Trends":
    st.subheader("Trial Turnaround Performance")
    if os.path.exists(TRIALS_FILE_CURRENT):
        trial_df = pd.read_csv(TRIALS_FILE_CURRENT)
        st.write("Trial Data Preview")
        st.dataframe(trial_df.head(), width="stretch")
    else:
        st.info("Trial trends data file not found.")