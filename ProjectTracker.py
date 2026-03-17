import os
import pandas as pd
import streamlit as st
from datetime import datetime
import io
import re

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

# --- 4. DATA LOADING ---

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

@st.cache_data(show_spinner="Loading High-Performance Database...")
def load_db(force_refresh=False):
    if force_refresh or not os.path.exists(FILENAME_PARQUET):
        if os.path.exists(TRACKER_ADJ_FILE) and os.path.exists(DIGITALPREPROD_FILE):
            try:
                # 1. Load data
                # Change sep=';' to sep=',' for the Tracker file
                df_t = pd.read_csv(TRACKER_ADJ_FILE, sep=',', encoding='utf-8-sig', on_bad_lines='warn')

                # Check DigitalPreProd.csv as well - it likely uses commas too
                df_d = pd.read_csv(DIGITALPREPROD_FILE, sep=',', encoding='utf-8-sig', on_bad_lines='warn')
                
                # 2. CLEAN COLUMN NAMES IMMEDIATELY (Fixes the Merge Error)
                df_d = clean_column_names(df_d)
                df_t = clean_column_names(df_t)

                # 3. Ensure the key column exists in both after cleaning
                if 'Pre-Prod No.' not in df_d.columns or 'Pre-Prod No.' not in df_t.columns:
                    missing = "DigitalPreProd" if 'Pre-Prod No.' not in df_d.columns else "Tracker"
                    st.error(f"Critical Error: Column 'Pre-Prod No.' not found in {missing} file.")
                    return pd.DataFrame()

                # 4. Clean keys and merge
                df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].apply(clean_key)
                df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].apply(clean_key)
                
                combined = pd.merge(
                    df_t.dropna(subset=['Pre-Prod No.']), 
                    df_d.dropna(subset=['Pre-Prod No.']), 
                    on='Pre-Prod No.', 
                    how='outer', 
                    suffixes=('', '_digital_info')
                )
                
                if 'Pre-Prod No.' in combined.columns:
                    combined['Pre-Prod No.'] = combined['Pre-Prod No.'].apply(pad_preprod_id)

                for col in combined.columns:
                    if combined[col].dtype == 'object' or col == 'Diameter':
                        combined[col] = combined[col].astype(str).replace('nan', '')
                
                combined.to_parquet(FILENAME_PARQUET, index=False)
            except Exception as e:
                st.error(f"Merge Error: {e}")
    
    if not os.path.exists(FILENAME_PARQUET): return pd.DataFrame()
    df = pd.read_parquet(FILENAME_PARQUET)
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

def save_db(df_to_save):
    if 'Pre-Prod No.' in df_to_save.columns:
        df_to_save['Pre-Prod No.'] = df_to_save['Pre-Prod No.'].apply(pad_preprod_id)
    for col in df_to_save.select_dtypes(include=['object']).columns:
        df_to_save[col] = df_to_save[col].astype(str).replace('nan', '')
    df_to_save.to_parquet(FILENAME_PARQUET, index=False)
    st.cache_data.clear()

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

# --- 6. INITIALIZE DATA & DYNAMIC DROPDOWNS ---
if st.sidebar.button("🔄 Force Refresh from CSVs"):
    df = load_db(force_refresh=True)
    st.sidebar.success("Database Rebuilt!")
else:
    df = load_db()

# Update Client list from loaded data
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

# --- 8. UI: TABS & NAVIGATION ---
def display_combination_table(key_prefix):
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Browse Tube & Cap Combinations", expanded=False):
            try:
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=',', encoding='utf-8-sig')
                combo_df = clean_column_names(combo_df)
                search = st.text_input(f"🔍 Filter List", key=f"{key_prefix}_search")
                if search:
                    mask = combo_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
                    combo_df = combo_df[mask]
                
                event = st.dataframe(combo_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key=f"{key_prefix}_table")
                if event.selection.rows:
                    sel_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    st.session_state.selected_combo = {
                        "Diameter": str(sel_row.get("Diameter", "")),
                        "Cap_Lid Style": str(sel_row.get("Cap_Lid_Style", sel_row.get("Cap_Lid Style", ""))),
                        "Cap_Lid Diameter": str(sel_row.get("Cap_Lid_Diameter", sel_row.get("Cap_Lid Diameter", ""))),
                        "Cap_Lid Material": str(sel_row.get("Cap_Lid_Material", sel_row.get("Cap_Lid Material", "")))
                    }
                    st.toast("✅ Combination Selected")
            except Exception as e: st.error(f"Error loading combos: {e}")

tab_nav = st.radio("Navigation", ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis"], 
                   index=["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis"].index(st.session_state.active_tab),
                   horizontal=True)
st.session_state.active_tab = tab_nav

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    raw_search = st.text_input("Search Pre-Prod No.").strip()
    search_no = pad_preprod_id(raw_search) if raw_search else ""
    match = df[df['Pre-Prod No.'] == search_no] if 'Pre-Prod No.' in df.columns else pd.DataFrame()
    
    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        c_c, c_d = st.columns(2)
        with c_c:
            if st.button("👯 Clone as Repeat Order", use_container_width=True):
                new_id = get_next_available_id(search_no, df['Pre-Prod No.'].tolist())
                new_clone = row.to_dict()
                new_clone.update({'Pre-Prod No.': new_id, 'Date': datetime.now().strftime('%d/%m/%Y'), 'Completion date': ""})
                st.session_state.form_data = new_clone
                st.session_state.active_tab = "➕ Add New Job"
                st.rerun()
        with c_d:
            with st.popover("🗑️ Delete", use_container_width=True):
                if st.button("Confirm Delete"):
                    df = df.drop(idx); save_db(df); st.rerun()

        display_combination_table("edit")
        with st.expander("Edit Details", expanded=True):
            updated_vals = {}
            edit_cols = st.columns(3)
            for i, col_name in enumerate(DESIRED_ORDER):
                if col_name == "Age Category": continue
                cur_val = str(row.get(col_name, "")) if str(row.get(col_name, "")).lower() != 'nan' else ""
                if col_name in st.session_state.selected_combo: cur_val = st.session_state.selected_combo[col_name]
                
                with edit_cols[i % 3]:
                    if col_name == 'Completion date':
                        try: d = pd.to_datetime(cur_val, dayfirst=True).date() if cur_val else None
                        except: d = None
                        sel_d = st.date_input(col_name, value=d, key=f"ed_{col_name}")
                        updated_vals[col_name] = sel_d.strftime('%d/%m/%Y') if sel_d else ""
                    elif col_name in ["Status", "Open or closed"]: continue
                    elif col_name in DROPDOWN_DATA:
                        opts = sorted(list(set([""] + DROPDOWN_DATA[col_name] + ([cur_val] if cur_val else []))))
                        updated_vals[col_name] = st.selectbox(col_name, options=opts, index=opts.index(cur_val) if cur_val in opts else 0, key=f"sel_{col_name}")
                    else:
                        updated_vals[col_name] = st.text_input(col_name, value=cur_val, key=f"txt_{col_name}")

            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                final_status = "Closed" if updated_vals.get("Completion date") else "Open"
                updated_vals["Status"] = updated_vals["Open or closed"] = final_status
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df); st.session_state.selected_combo = {}; st.rerun()

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    display_combination_table("new")
    default_id = st.session_state.form_data.get('Pre-Prod No.', get_auto_next_no(df))
    
    with st.form("new_job_form", clear_on_submit=True):
        st.subheader("Register Project")
        new_id_input = st.text_input("Pre-Prod No.", value=default_id)
        new_data = {}; cols = st.columns(3)
        for i, col_name in enumerate(DESIRED_ORDER):
            if col_name == "Age Category": continue
            val = st.session_state.form_data.get(col_name, "")
            if col_name in st.session_state.selected_combo: val = st.session_state.selected_combo[col_name]

            with cols[i % 3]:
                if col_name == 'Date': new_data[col_name] = st.date_input(col_name, value=datetime.now()).strftime('%d/%m/%Y')
                elif col_name == 'Completion date':
                    res = st.date_input(col_name, value=None)
                    new_data[col_name] = res.strftime('%d/%m/%Y') if res else ""
                elif col_name in DROPDOWN_DATA:
                    opts = sorted(list(set([""] + DROPDOWN_DATA[col_name] + ([val] if val else []))))
                    new_data[col_name] = st.selectbox(col_name, options=opts, index=opts.index(val) if val in opts else 0)
                elif col_name in ['Status', 'Open or closed']: new_data[col_name] = "Open"
                else: new_data[col_name] = st.text_input(col_name, value=val)

        if st.form_submit_button("✅ Save Project"):
            padded_id = pad_preprod_id(new_id_input)
            new_data['Pre-Prod No.'] = get_next_available_id(padded_id, df['Pre-Prod No.'].tolist())
            new_data['Status'] = new_data['Open or closed'] = "Closed" if new_data.get('Completion date') else "Open"
            cat, days = calculate_age_category(new_data)
            new_data.update({'Age Category': cat, 'Project Age (Open and Closed)': days})
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df); st.session_state.selected_combo = {}; st.session_state.form_data = {}; st.rerun()

# --- TAB: DETAILED AGE ANALYSIS ---
elif tab_nav == "📊 Detailed Age Analysis":
    if not df.empty:
        open_only = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Open Projects by Age Category**")
            st.bar_chart(open_only['Age Category'].value_counts().reindex(["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"], fill_value=0))
        with c2:
            st.markdown("**Top Clients with Open Projects**")
            st.bar_chart(open_only['Client'].value_counts().head(10))

st.divider()
if st.checkbox("Show Master Table", value=True):
    st.dataframe(df, use_container_width=True)