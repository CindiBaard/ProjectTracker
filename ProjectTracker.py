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
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"
SUBMISSIONS_FILE = "Submissions_History.parquet" 
TRACKER_FILE_ID = "1u_TVVSnWNMpN1kUtKtBprr_ybUggTZfsfg06EcU6YOQ"

# --- 2. FIXED DESIRED ORDER ---
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

def clean_column_names(df):
    """Fixes merged headers, removes whitespace, and handles duplicates."""
    # 1. Strip whitespace and remove BOM characters
    df.columns = [str(c).replace('\ufeff', '').replace('ï»¿', '').strip() for c in df.columns]
    
    # 2. Fix the 'All headers in one column' issue (Delimiter mismatch)
    if len(df.columns) > 0 and "," in df.columns[0] and "Pre-Prod" in df.columns[0]:
        new_headers = df.columns[0].split(',')
        if len(new_headers) > 5:
            data = df.iloc[:, 0].str.split(',', expand=True)
            df = data
            df.columns = new_headers[:len(df.columns)]

    # 3. Standardize naming
    rename_map = {
        'Pre-Prod No': 'Pre-Prod No.', 
        'Pre Prod No.': 'Pre-Prod No.', 
        'Pre-Prod No. ': 'Pre-Prod No.',
        'Pre Prod No': 'Pre-Prod No.'
    }
    df = df.rename(columns=rename_map)
    
    # 4. Drop completely empty/unnamed columns
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # 5. Handle duplicate column names (prevents pandas crashes)
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    
    return df

def get_auto_next_no(df):
    if df is None or df.empty or 'Pre-Prod No.' not in df.columns: 
        return "00001"
    try:
        nums = df['Pre-Prod No.'].astype(str).str.extract(r'(\d+)')[0].dropna().astype(int)
        if nums.empty: return "00001"
        return str(int(nums.max()) + 1).zfill(5)
    except: return "00001"

def get_next_available_id(search_no, existing_ids):
    base = str(search_no).split('_')[0]
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = f"{base}_{char}"
        if candidate not in existing_ids.values: return candidate
    return f"{base}_NEW"

def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == '': 
        return ""
    val_str = str(val).strip().split('.')[0]
    if '_' in val_str:
        parts = val_str.split('_', 1)
        return f"{parts[0]}_{parts[1]}"
    return val_str

def update_tracker_status(pre_prod_no, current_trial_ref, manual_date=None):
    import gspread
    from google.oauth2.service_account import Credentials
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets.get("gcp_service_account", st.secrets.get("connections", {}).get("gsheets"))
        if isinstance(creds_info, dict) and "private_key" in creds_info:
             creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        tracker_spreadsheet = client.open_by_key(TRACKER_FILE_ID)
        tracker_worksheet = tracker_spreadsheet.get_worksheet(0) 

        search_id = str(pre_prod_no).strip().split('.')[0]
        cell = tracker_worksheet.find(search_id, in_column=1)
        if not cell: return False, f"ID {search_id} not found."
            
        trial_suffix = current_trial_ref.split('_')[-1] if '_' in current_trial_ref else current_trial_ref
        date_str = manual_date if manual_date else datetime.now().strftime('%d/%m/%Y')
        combined_value = f"{trial_suffix} - {date_str}"

        headers = [h.strip() for h in tracker_worksheet.row_values(1)]
        col_name = "Injection trial requested"
        if col_name in headers:
            col_idx = headers.index(col_name) + 1
            tracker_worksheet.update_cell(cell.row, col_idx, combined_value)
            return True, combined_value
        return False, "Column not found."
    except Exception as e: return False, str(e)

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

def load_trial_data():
    if os.path.exists(TRIALS_FILE_CURRENT):
        try: return pd.read_csv(TRIALS_FILE_CURRENT)
        except: return pd.DataFrame()
    return pd.DataFrame()

# --- 5. DATA LOADING HELPERS ---

def smart_read(path):
    """Helper function to read CSVs with flexible delimiters."""
    if not os.path.exists(path): 
        return pd.DataFrame()
    try:
        # Try reading with comma first
        df = pd.read_csv(path, sep=',', on_bad_lines='skip', encoding='utf-8-sig')
        # If it failed to split (only 1 column), try semicolon
        if len(df.columns) <= 1:
            df = pd.read_csv(path, sep=';', on_bad_lines='skip', encoding='utf-8-sig')
        
        df = df.replace('#REF!', np.nan)
        return clean_column_names(df)
    except Exception as e:
        st.error(f"Error reading {path}: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner="Refreshing Database...")
def load_db_v2(tracker_path, digital_path, parquet_path):
    # 1. Try loading existing local Parquet first
    if os.path.exists(parquet_path): 
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass
    
# 2. If no parquet, read from CSVs
    try:
        df_t = smart_read(tracker_path)
        df_d = smart_read(digital_path)
        
        if df_t.empty: 
            return pd.DataFrame()

        # Clean the Main Tracker IDs
        if 'Pre-Prod No.' in df_t.columns:
            df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # --- REVISED MERGE LOGIC ---
        if not df_d.empty and 'Pre-Prod No.' in df_d.columns:
            # A. Clean Digital IDs
            df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
            # B. Drop any column that ALREADY ends in '_dig' to prevent suffix collision
            # This is why you got the duplicate column error.
            df_d = df_d.drop(columns=[c for c in df_d.columns if c.endswith('_dig')], errors='ignore')
            
            # C. Remove literal duplicate column names (e.g., two 'Project' columns)
            df_d = df_d.loc[:, ~df_d.columns.duplicated()]
            
            # D. Perform Merge
            combined = pd.merge(
                df_t.dropna(subset=['Pre-Prod No.']), 
                df_d.dropna(subset=['Pre-Prod No.']), 
                on='Pre-Prod No.', 
                how='outer', 
                suffixes=('', '_dig')
            )
        else:
            # If digital is empty or missing key column, just use tracker
            combined = df_t
        
        # 3. Final Polish
        # Reorder columns based on DESIRED_ORDER (only those that actually exist)
        existing_cols = [c for c in DESIRED_ORDER if c in combined.columns]
        combined = combined[existing_cols]

        # Save to local parquet for faster next load
        combined.to_parquet(parquet_path, index=False)
        return combined
        
    except Exception as e:
        st.error(f"Load Error: {e}")
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Load Error: {e}")
        return pd.DataFrame()    

# --- 6. UI HELPERS ---
def display_combination_table(key_prefix):
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Browse Tube & Cap Combinations", expanded=False):
            try:
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig')
                combo_df = clean_column_names(combo_df)
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

# --- 7. MAIN APP START ---
df = load_db_v2(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET)
if df.empty: df = pd.DataFrame(columns=DESIRED_ORDER)

st.title("Project Tracker Dashboard")

# DROPDOWN SETUP
DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
if not df.empty and 'Client' in df.columns:
    DROPDOWN_DATA['Client'] = sorted([str(c) for c in df['Client'].unique() if str(c).strip() and str(c).lower() != 'nan'])

# NAVIGATION
tabs_list = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Cloud Sync"]
tab_nav = st.radio("Navigation", tabs_list, index=tabs_list.index(st.session_state.active_tab), horizontal=True)
st.session_state.active_tab = tab_nav

# --- SIDEBAR ---
with st.sidebar:
    st.title("Navigation")
    st.page_link("https://injectiontrial-996rcfrtn9rkgafzsejzrn.streamlit.app/", label="🧪 Go to Injection Trial App", icon="🚀")
    st.divider()
    if st.button("🔄 Rebuild Local DB", use_container_width=True):
        st.cache_data.clear()
        if os.path.exists(FILENAME_PARQUET): os.remove(FILENAME_PARQUET)
        st.rerun()

# --- TAB 1: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    c_s, c_cl = st.columns([4, 1])
    raw_search = c_s.text_input("Search Pre-Prod No.", key="search_input_box").strip()
    if c_cl.button("♻️ Clear", use_container_width=True):
        st.session_state.last_search_no = ""
        st.rerun()

    search_no = pad_preprod_id(raw_search)
    match = df[df['Pre-Prod No.'] == search_no] if not df.empty else pd.DataFrame()
    
    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        btn_col1, btn_col2 = st.columns(2)
        
        with btn_col1:
            if st.button("👯 Clone Project", use_container_width=True):
                new_clone = row.to_dict()
                new_clone.update({'Pre-Prod No.': get_next_available_id(search_no, df['Pre-Prod No.']), 'Date': datetime.now().strftime('%d/%m/%Y')})
                st.session_state.form_data = new_clone
                st.session_state.active_tab = "➕ Add New Job"
                st.rerun()
        
        with btn_col2:
            if st.checkbox(f"Confirm Delete {search_no}"):
                if st.button("🗑️ Delete Project", type="primary", use_container_width=True):
                    df = df.drop(idx)
                    save_db(df); st.cache_data.clear(); st.rerun()

        display_combination_table("edit")
        
        with st.form("edit_form"):
            st.subheader(f"Editing: {search_no}")
            updated_vals = {}
            sel_combo = st.session_state.get("selected_combo", {})

            # Fields Grouping
            status_fields = ["Status", "Open or closed", "Completion date"]
            plate_fields = ["Ordered Plates", "Plates Arrived"]
            proof_fields = ["Date Sent on Proof", "Proof Approved (Conventional)", "Proof Approved (Digital)"]
            trial_fields = [
                "Sent on Trial", "Digital trial sent", "Revised Artwork After Trialling",
                "Extrusion requested", "Extrusion received", "Injection trial requested", 
                "Injection trial received", "Blowmould trial requested", "Blowmould trial received"
            ]

            st.markdown("### 📋 General Details")
            edit_cols = st.columns(3)
            excluded = status_fields + trial_fields + proof_fields + plate_fields + ["Age Category"]
            remaining_fields = [c for c in DESIRED_ORDER if c not in excluded and c != "Pre-Prod No."]
            
            for i, col in enumerate(remaining_fields):
                cur_val = sel_combo.get(col, str(row.get(col, "")).replace('nan', ''))
                with edit_cols[i % 3]:
                    if "date" in col.lower() or col == "Date":
                        try:
                            d_parsed = pd.to_datetime(cur_val, dayfirst=True, errors='coerce')
                            d_val = d_parsed.date() if pd.notnull(d_parsed) else datetime.now().date()
                        except: d_val = datetime.now().date()
                        d_input = st.date_input(col, value=d_val, key=f"ed_gen_{col}")
                        updated_vals[col] = d_input.strftime('%d/%m/%Y')
                    elif col in DROPDOWN_DATA:
                        opts = sorted(list(set([""] + DROPDOWN_DATA[col] + [cur_val])))
                        updated_vals[col] = st.selectbox(col, opts, index=opts.index(cur_val), key=f"sel_{col}")
                    else:
                        updated_vals[col] = st.text_input(col, value=cur_val, key=f"txt_{col}")

            st.divider()
            st.markdown("### 🧪 Trials & Progress")
            t_cols = st.columns(3)
            for i, col in enumerate(trial_fields + status_fields + plate_fields + proof_fields):
                cur_val = str(row.get(col, "")).replace('nan', '')
                with t_cols[i % 3]:
                    updated_vals[col] = st.text_input(col, value=cur_val, key=f"flow_{col}")

            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df)
                if updated_vals.get("Injection trial requested"):
                    update_tracker_status(search_no, updated_vals["Injection trial requested"])
                st.session_state.selected_combo = {}
                st.cache_data.clear()
                st.success("Saved successfully!")
                st.rerun()

    elif search_no:
        st.warning("No project found.")

# --- TAB 2: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    display_combination_table("new")
    sel = st.session_state.get("selected_combo", {})
    default_id = st.session_state.form_data.get('Pre-Prod No.', get_auto_next_no(df))
    with st.form("new_job_form"):
        st.subheader("New Project Entry")
        new_id = st.text_input("Pre-Prod No.", value=default_id).strip()
        new_cols = st.columns(3); new_entry = {"Pre-Prod No.": new_id}
        for i, col in enumerate(DESIRED_ORDER):
            if col in ["Age Category", "Pre-Prod No."]: continue
            val = sel.get(col, st.session_state.form_data.get(col, ""))
            with new_cols[i % 3]:
                if col == 'Date': new_entry[col] = st.date_input(col, value=datetime.now()).strftime('%d/%m/%Y')
                elif col in DROPDOWN_DATA:
                    opts = sorted(list(set([""] + DROPDOWN_DATA[col] + ([val] if val else []))))
                    new_entry[col] = st.selectbox(col, opts, index=opts.index(val) if val in opts else 0)
                else: new_entry[col] = st.text_input(col, value=val)
        
        if st.form_submit_button("➕ Create Project", use_container_width=True):
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            save_db(df); st.cache_data.clear(); st.session_state.form_data = {}; st.rerun()

# --- TAB 3: AGE ANALYSIS ---
elif tab_nav == "📊 Detailed Age Analysis":
    st.subheader("Project Age Distribution")
    if not df.empty and 'Age Category' in df.columns:
        st.bar_chart(df['Age Category'].value_counts())
        st.dataframe(df[['Pre-Prod No.', 'Client', 'Project Description', 'Age Category']], use_container_width=True)

# --- TAB 4: TRIAL TRENDS ---
elif tab_nav == "🧪 Trial Trends":
    st.subheader("Trial Turnaround Performance")
    trial_df = load_trial_data()
    if not trial_df.empty:
        st.metric("Avg Turnaround", f"{trial_df['Days_Taken'].mean():.1f} Days")
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(trial_df.index, trial_df['Days_Taken'], marker='o', color='#2ca02c')
        st.pyplot(fig)
    else: st.info("No trial data found.")

# --- TAB 5: CLOUD SYNC ---
elif tab_nav == "🌐 Cloud Sync":
    st.subheader("Google Sheets Sync")
    
    # 1. Sync Button Logic
    if st.button("📥 Fetch from Cloud", use_container_width=True):
        with st.spinner("Syncing..."):
            try:
                import gspread
                from google.oauth2.service_account import Credentials
                
                scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds_info = st.secrets.get("gcp_service_account", st.secrets.get("connections", {}).get("gsheets"))
                
                # Format private key for Streamlit Cloud
                if isinstance(creds_info, dict) and "private_key" in creds_info:
                    creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
                
                creds = Credentials.from_service_account_info(creds_info, scopes=scope)
                client = gspread.authorize(creds)
                ws = client.open_by_key(TRACKER_FILE_ID).get_worksheet(0)
                raw_data = ws.get_all_values() 
                
                if raw_data:
                    new_df = pd.DataFrame(raw_data[1:], columns=raw_data[0])
                    # Ensure FILENAME_PARQUET is defined at the top of your script
                    new_df.to_parquet(FILENAME_PARQUET, index=False)
                    st.cache_data.clear()
                    st.success("Fetched successfully!")
                    st.rerun()
            except Exception as e: 
                st.error(f"Sync failed: {e}")

    st.divider()
    st.subheader("Local Database Preview")
    
    # 2. Preview Logic (This is where your syntax error was)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No local data found. Click 'Fetch from Cloud' to download data.")