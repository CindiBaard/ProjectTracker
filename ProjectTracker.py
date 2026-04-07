import os
import re
import io
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime

# --- 1. INITIAL SETUP & DEPENDENCIES ---
# (Imports are handled at the top; ensured dependencies are checked in your environment)

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

def get_auto_next_no(df):
    if df is None or df.empty or 'Pre-Prod No.' not in df.columns: 
        return "00001"
    try:
        nums = df['Pre-Prod No.'].str.extract(r'(\d+)')[0].dropna().astype(int)
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
    if pd.isna(val) or str(val).strip() == '': return ""
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

# --- 5. DATA LOADING ---

def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data(show_spinner="Refreshing Database...")
def load_db(tracker_file, digital_file, parquet_path, force_refresh=False):
    if os.path.exists(parquet_path) and not force_refresh:
        return pd.read_parquet(parquet_path)
    
    try:
        df_t = pd.read_csv(tracker_file, sep=None, engine='python', encoding='utf-8-sig')
        df_d = pd.read_csv(digital_file, sep=None, engine='python', encoding='utf-8-sig')
        df_d, df_t = clean_column_names(df_d), clean_column_names(df_t)
        df_d = df_d.rename(columns={'Pre-Prod No': 'Pre-Prod No.', 'Pre Prod No.': 'Pre-Prod No.'})
        
        df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), df_d.dropna(subset=['Pre-Prod No.']), on='Pre-Prod No.', how='outer', suffixes=('', '_dig'))
        combined['Pre-Prod No.'] = combined['Pre-Prod No.'].apply(pad_preprod_id)
        
        if 'Date' in combined.columns:
            results = combined.apply(calculate_age_category, axis=1)
            combined['Age Category'] = [r[0] for r in results]
            combined['Project Age (Open and Closed)'] = [r[1] for r in results]
        
        combined.to_parquet(parquet_path, index=False)
        return combined
    except Exception as e:
        st.error(f"Merge Error: {e}")
        return pd.DataFrame()

@st.cache_data
def load_trial_data():
    trials_path = os.path.join(BASE_DIR, TRIALS_FILE_CURRENT)
    if not os.path.exists(trials_path): return pd.DataFrame()
    try:
        df = pd.read_csv(trials_path)
        df['Date_Log'] = pd.to_datetime(df['Date_Log'], dayfirst=True, errors='coerce')
        df['Completion_Date'] = pd.to_datetime(df['Completion_Date'], dayfirst=True, errors='coerce')
        df['Days_Taken'] = (df['Completion_Date'] - df['Date_Log']).dt.days
        wk_col = next((c for c in df.columns if 'week' in c.lower()), None)
        df['Week_Num'] = df[wk_col].astype(str).str.extract(r'(\d+)').fillna(0).astype(int) if wk_col else 0
        return df
    except: return pd.DataFrame()

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
DROPDOWN_DATA = {k: get_options(v) fo# --- NAVIGATION ---
tabs_list = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Cloud Sync"]
tab_nav = st.radio("Navigation", tabs_list, index=tabs_list.index(st.session_state.active_tab), horizontal=True)
st.session_state.active_tab = tab_nav

# --- TAB 1: SEARCH & EDIT ---
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
        btn_col1, btn_col2 = st.columns(2)
        
        with btn_col1:
            if st.button("👯 Clone for Repeat Order", use_container_width=True):
                new_clone = row.to_dict()
                new_clone.update({
                    'Pre-Prod No.': get_next_available_id(search_no, df['Pre-Prod No.']), 
                    'Date': datetime.now().strftime('%d/%m/%Y'), 
                    'Completion date': ""
                })
                st.session_state.form_data = new_clone
                st.session_state.active_tab = "➕ Add New Job"
                st.rerun()
        
        with btn_col2:
            confirm_delete = st.checkbox(f"Confirm Delete {search_no}")
            if st.button("🗑️ Delete Project", type="primary", disabled=not confirm_delete, use_container_width=True):
                df = df.drop(idx)
                save_db(df)
                st.cache_data.clear()
                st.session_state.last_search_no = ""
                st.success("Deleted!")
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
                    if col in ['Completion date', 'Date']:
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
                st.success("Saved locally!")
                st.rerun()
    elif search_no:
        st.warning("No project found.")

# --- TAB 2: ADD NEW JOB ---
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
            st.cache_data.clear() 
            st.session_state.form_data = {}
            st.session_state.selected_combo = {}
            st.success("Job Added!")
            st.rerun()

# --- TAB 5: GOOGLE CLOUD SYNC ---
elif tab_nav == "🌐 Cloud Sync":
    st.subheader("🌐 Google Sheets Database Sync")
    
    col_a, col_b = st.columns(2)
    
    if col_a.button("📥 Fetch from Google (Read Only)", use_container_width=True):
        cloud_df = load_from_google_sheets()
        if not cloud_df.empty:
            st.session_state.google_data = cloud_df
            st.success("Data fetched from Google Sheets!")

    if col_b.button("📤 Push Local Data to Google", use_container_width=True, type="primary"):
        try:
            # Re-authorize and open sheet
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
            if isinstance(creds_info, dict) and "private_key" in creds_info:
                 creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_info, scopes=scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key("1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M")
            worksheet = spreadsheet.get_worksheet(0)
            
            # Clear and update with current local 'df'
            worksheet.clear()
            # Handle NaNs and convert to list for Gspread
            export_df = df.fillna("")
            worksheet.update([export_df.columns.values.tolist()] + export_df.values.tolist())
            st.success("Successfully synced local database to Google Sheets!")
        except Exception as e:
            st.error(f"Sync failed: {e}")

    if "google_data" in st.session_state:
        st.write("### Preview: Cloud Data")
       if "google_data" in st.session_state:
        st.write("### Preview: Cloud Data")
        st.dataframe(st.session_state.google_data, use_container_width=True)

# --- TAB 3: AGE ANALYSIS ---
elif tab_nav == "📊 Detailed Age Analysis":
    st.subheader("Project Age Distribution")
    if not df.empty and 'Age Category' in df.columns:
        age_counts = df['Age Category'].value_counts()
        st.bar_chart(age_counts)
        st.dataframe(df[['Pre-Prod No.', 'Client', 'Project Description', 'Age Category', 'Project Age (Open and Closed)']], use_container_width=True)

# --- TAB 4: TRIAL TRENDS ---
elif tab_nav == "🧪 Trial Trends":
    st.subheader("Trial Turnaround Performance")
    trial_df = load_trial_data()
    
    if not trial_df.empty:
        # Group data by week and calculate the mean of Days_Taken
        weekly_stats = trial_df.groupby('Week_Num')['Days_Taken'].mean().sort_index()
        
        col1, col2 = st.columns([1, 3])
        with col1:
            avg_val = trial_df['Days_Taken'].mean()
            st.metric("Avg Turnaround (Total)", f"{avg_val:.1f} Days")
            st.write("Weekly Averages:")
            st.dataframe(weekly_stats.rename("Avg Days"), use_container_width=True)
        
        with col2:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(weekly_stats.index, weekly_stats.values, marker='o', linestyle='-', color='#2ca02c')
            ax.set_title("Average Days Taken per Week")
            ax.set_ylabel("Days")
            ax.set_xlabel("Week Number")
            ax.grid(True, alpha=0.3)
            st.pyplot(fig)
    else:
        st.info("No trial data found to analyze.")

# --- END OF FILE ---_Taken'].mean().sort_index()
        if not weekly_stats.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(weekly_stats.index, weekly_stats.values, marker='o', color='#2ca02c')
            ax.set_ylabel("Average Days")
            ax.set_xlabel("Week Number")
            st.pyplot(fig)