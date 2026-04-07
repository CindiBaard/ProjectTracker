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

# RESTORED: Google Auth Imports
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

def get_auto_next_no(df):
    if df is None or df.empty or 'Pre-Prod No.' not in df.columns: 
        return "00001"
    try:
        # 1. Extract digits into a Series
        # squeeze=True ensures we get a Series back, not a 1-column DataFrame
        nums = df['Pre-Prod No.'].str.extract(r'(\d+)')[0].dropna().astype(int)
        
        if nums.empty: 
            return "00001"
            
        # 2. Get the actual integer value using .max()
        # .max() on a Series returns a single number
        next_val = int(nums.max()) + 1
        
        # 3. Format it back to 5 digits
        return str(next_val).zfill(5)
    except Exception as e:
        # Optional: st.write(f"Debug ID Error: {e}") 
        return "00001"

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

# --- 5. DATA LOADING (Local & Google) ---

def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data(show_spinner="Refreshing Database...")
def load_db(tracker_file, digital_file, parquet_path, force_refresh=False):
    # 1. If Parquet exists AND we aren't forcing a hard rebuild from CSV...
    if os.path.exists(parquet_path) and not force_refresh:
        df = pd.read_parquet(parquet_path)
        # (Keep your existing age calculation logic here...)
        return df

    # 2. ONLY if the file is missing or we click "Rebuild", do the CSV merge
    
        try:
            df_t = pd.read_csv(tracker_file, sep=None, engine='python', encoding='utf-8-sig')
            df_d = pd.read_csv(digital_file, sep=None, engine='python', encoding='utf-8-sig')
            df_d, df_t = clean_column_names(df_d), clean_column_names(df_t)
            df_d = df_d.rename(columns={'Pre-Prod No': 'Pre-Prod No.', 'Pre Prod No.': 'Pre-Prod No.'})
            
            # Preserve the Merge Fix
            df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

            combined = pd.merge(
                df_t.dropna(subset=['Pre-Prod No.']), 
                df_d.dropna(subset=['Pre-Prod No.']), 
                on='Pre-Prod No.', 
                how='outer', 
                suffixes=('', '_dig')
            )

            # ALL OF THIS MUST BE INDENTED TO STAY INSIDE THE TRY BLOCK
            combined['Pre-Prod No.'] = combined['Pre-Prod No.'].apply(pad_preprod_id)
            
            if 'Date' in combined.columns:
                results = combined.apply(calculate_age_category, axis=1)
                combined['Age Category'] = [r[0] for r in results]
                combined['Project Age (Open and Closed)'] = [r[1] for r in results]
            
            if 'Project Age (Open and Closed)' in combined.columns:
                combined['Project Age (Open and Closed)'] = pd.to_numeric(combined['Project Age (Open and Closed)'], errors='coerce').fillna(0)

            combined.to_parquet(parquet_path, index=False)
            return combined
            
        except Exception as e: 
            st.error(f"Merge Error: {e}")
            return pd.DataFrame()
                
    # Loading from existing parquet
    if os.path.exists(parquet_path):
        df = pd.read_parquet(parquet_path)
        if 'Date' in df.columns and 'Age Category' not in df.columns:
            results = df.apply(calculate_age_category, axis=1)
            df['Age Category'], df['Project Age (Open and Closed)'] = [r[0] for r in results], [r[1] for r in results]
        
        # Ensure numeric type on load
        if 'Project Age (Open and Closed)' in df.columns:
            df['Project Age (Open and Closed)'] = pd.to_numeric(df['Project Age (Open and Closed)'], errors='coerce').fillna(0)
        return df
    
    return pd.DataFrame()
                
    # If file exists and we aren't forcing a refresh, load from parquet
    if os.path.exists(parquet_path):
        df = pd.read_parquet(parquet_path)
        # Ensure age categories exist even when loading from cache
        if 'Date' in df.columns and 'Age Category' not in df.columns:
            results = df.apply(calculate_age_category, axis=1)
            df['Age Category'], df['Project Age (Open and Closed)'] = [r[0] for r in results], [r[1] for r in results]
        return df
    
    return pd.DataFrame()


# 1. Define the filename at the top with your other file paths
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"

# 2. Define the loading function in your DATA LOADING section
@st.cache_data
def load_trial_data():
    """Loads and processes the weekly trial CSV file for turnaround analysis."""
    trials_path = os.path.join(BASE_DIR, TRIALS_FILE_CURRENT)
    if os.path.exists(trials_path):
        try:
            # Read the CSV (adjust encoding if you get a UnicodeDecodeError)
            df = pd.read_csv(trials_path)
            
            # Convert date columns to datetime objects
            df['Date_Log'] = pd.to_datetime(df['Date_Log'], dayfirst=True, errors='coerce')
            df['Completion_Date'] = pd.to_datetime(df['Completion_Date'], dayfirst=True, errors='coerce')
            
            # Calculate the turnaround time in days
            df['Days_Taken'] = (df['Completion_Date'] - df['Date_Log']).dt.days
            
            # Extract the Week Number for the trend chart
            # This looks for a column with 'week' in the name (e.g., 'Week No')
            wk_col = next((c for c in df.columns if 'week' in c.lower()), None)
            if wk_col:
                df['Week_Num'] = df[wk_col].astype(str).str.extract(r'(\d+)').fillna(0).astype(int)
            else:
                df['Week_Num'] = 0
                
            return df
        except Exception as e:
            st.error(f"Error processing trial dates: {e}")
            return pd.DataFrame()
    else:
        # Silently return empty DF if file isn't there yet to avoid crashing the app
        return pd.DataFrame()

# RESTORED: Google Sheets Loading logic
def load_from_google_sheets():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
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
                # Note: Sep is ';' per old code
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

# --- NEW: RESTORED DROPDOWN CONFIGURATION ---
DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
if not df.empty:
    DROPDOWN_DATA['Client'] = sorted([str(c) for c in df['Client'].unique() if str(c).strip() and str(c).lower() != 'nan'])

# --- NAVIGATION ---
tabs_list = ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis", "🧪 Trial Trends", "🌐 Google DB View"]
tab_nav = st.radio("Navigation", tabs_list, index=tabs_list.index(st.session_state.active_tab), horizontal=True)
st.session_state.active_tab = tab_nav

# --- 1. TAB: SEARCH & EDIT ---
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
        if btn_col1.button("👯 Clone for Repeat Order", use_container_width=True):
            # Cloning logic uses get_next_available_id from utility functions
            new_clone = row.to_dict()
            new_clone.update({
                'Pre-Prod No.': get_next_available_id(search_no, df['Pre-Prod No.']), 
                'Date': datetime.now().strftime('%d/%m/%Y'), 
                'Completion date': ""
            })
            st.session_state.form_data = new_clone
            st.session_state.active_tab = "➕ Add New Job"
            st.rerun()

        pass

        # --- NEW: DELETE SECTION ---
        with btn_col2:
            st.markdown("---") # Visual separator
            confirm_delete = st.checkbox(f"Confirm Delete {search_no}")
            if st.button("🗑️ Delete Project", use_container_width=True, type="primary", disabled=not confirm_delete):
                # 1. Remove the row from the current dataframe
                df = df.drop(idx)
                
                # 2. Save the updated dataframe to the Parquet file
                save_db(df)
                
                # 3. Clear cache so the app doesn't remember the deleted row
                st.cache_data.clear()
                
                # 4. Reset search and refresh
                st.session_state.last_search_no = ""
                st.success(f"Project {search_no} has been deleted.")
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
                st.success("Saved!")
                st.rerun()

# --- 2. TAB: ADD NEW JOB ---
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

        # THIS BUTTON MUST BE INDENTED INSIDE THE "WITH" BLOCK
        if st.form_submit_button("➕ Create Project", use_container_width=True):
            status = "Closed" if new_entry.get("Completion date") else "Open"
            new_entry.update({"Status": status, "Open or closed": status})
            
            # 1. Update the local dataframe
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            
            # 2. Save to file
            save_db(df)
            
            # 3. Clear the cache so load_db() sees the new file
            st.cache_data.clear() 
            
            # 4. Clean up session state
            st.session_state.form_data = {}
            st.session_state.selected_combo = {}
            
            st.success("Job Added! Re-loading database...")
            st.rerun()

# --- 3. TAB: DETAILED AGE ANALYSIS ---
elif tab_nav == "📊 Detailed Age Analysis":
    if not df.empty:
        open_only = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Open Projects by Age Category**")
            age_dist = open_only['Age Category'].value_counts().reindex(["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"], fill_value=0)
            st.bar_chart(age_dist)
        with c2:
            st.markdown("**Top Clients with Open Projects**")
            st.bar_chart(open_only['Client'].value_counts().head(10))

# --- 4. TAB: TRIAL TRENDS ---
elif tab_nav == "🧪 Trial Trends":
    st.subheader("🧪 Trial Turnaround Time (2026)")
    df_trials = load_trial_data()
    if not df_trials.empty:
        weekly_stats = df_trials.dropna(subset=['Days_Taken']).groupby('Week_Num')['Days_Taken'].mean().sort_index()
        if not weekly_stats.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(weekly_stats.index, weekly_stats.values, marker='o', color='#2ca02c')
            ax.set_ylabel("Average Days")
            ax.set_xlabel("Week Number")
            st.pyplot(fig)
            
            m1, m2 = st.columns(2)
            m1.metric("Latest Week Avg", f"{weekly_stats.iloc[-1]:.1f} Days")
            m2.metric("Overall 2026 Avg", f"{df_trials['Days_Taken'].mean():.1f} Days")

# --- 5. TAB: GOOGLE VIEW ---
elif tab_nav == "🌐 Google DB View":
    if st.button("🔄 Fetch Cloud Data"):
        st.session_state.google_data = load_from_google_sheets()
    if "google_data" in st.session_state:
        st.dataframe(st.session_state.google_data, use_container_width=True)

# --- SUMMARY METRICS (FOOTER) ---
if not df.empty:
    st.divider()
    
    # 1. First, define what "open_jobs" is
    open_jobs = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
    
    # 2. Create the layout columns
    m1, m2, m3 = st.columns(3)
    
    # 3. Calculate the metrics safely
    total_open = len(open_jobs)
    critical_jobs = len(open_jobs[open_jobs['Age Category'] == "> 12 Weeks"])
    
    # Convert to numeric to avoid the "string dtype" error
    avg_age_series = pd.to_numeric(open_jobs['Project Age (Open and Closed)'], errors='coerce')
    avg_age_val = avg_age_series.mean()
    
    # 4. Display the metrics
    m1.metric("Total Open Jobs", total_open)
    m2.metric("Critical (>12w)", critical_jobs)
    m3.metric("Avg Age (Days)", int(avg_age_val) if not p
    if "google_data" in st.session_state:
        st.dataframe(st.session_state.google_data, use_container_width=True)
