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
    if pd.isna(val) or str(val).strip() == '': 
        return ""
    val_str = str(val).strip().split('.')[0]
    if '_' in val_str:
        parts = val_str.split('_', 1)
        base, suffix = parts[0], parts[1]
        return f"{base.zfill(5)}_{suffix}"
    return val_str.zfill(5)

def get_auto_next_no(df):
    if df.empty or 'Pre-Prod No.' not in df.columns: return "00001"
    nums = []
    for i in df['Pre-Prod No.'].tolist():
        match = re.match(r"(\d+)", str(i))
        if match: nums.append(int(match.group(1)))
    return str(max(nums) + 1).zfill(5) if nums else "00001"

def get_next_available_id(requested_id, existing_ids):
    requested_id = str(requested_id).strip()
    if requested_id not in existing_ids: return requested_id
    base_id = requested_id.split('_')[0]
    pattern = re.compile(rf"^{re.escape(base_id)}(_(\d+))?$")
    suffixes = [int(m.group(2)) if m.group(2) else 0 for eid in existing_ids for m in [pattern.match(str(eid))] if m]
    return f"{base_id}_{max(suffixes) + 1}"

def clean_column_names(df):
    df.columns = [str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') for c in df.columns]
    return df

def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        comp_date = str(row.get('Completion date', '')).strip()
        end_date = pd.to_datetime(comp_date, dayfirst=True, errors='coerce') if comp_date and comp_date.lower() != 'nan' else pd.to_datetime(datetime.now().date())
        if pd.isnull(start_date) or pd.isnull(end_date): return "N/A", 0
        days = (end_date - start_date).days
        cat = "< 6 Weeks" if days < 42 else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        return cat, days
    except: return "Error", 0

# --- 4. DATA LOADING & SAVING ---

def load_db(force_refresh=False):
    if force_refresh or not os.path.exists(FILENAME_PARQUET):
        if os.path.exists(TRACKER_ADJ_FILE) and os.path.exists(DIGITALPREPROD_FILE):
            df_d = pd.read_csv(DIGITALPREPROD_FILE, sep=';', encoding='utf-8-sig')
            df_t = pd.read_csv(TRACKER_ADJ_FILE, sep=';', encoding='utf-8-sig')
            combined = pd.merge(df_t, df_d, on='Pre-Prod No.', how='outer', suffixes=('', '_digital'))
            combined['Pre-Prod No.'] = combined['Pre-Prod No.'].apply(pad_preprod_id)
            combined.to_parquet(FILENAME_PARQUET, index=False)
    
    if not os.path.exists(FILENAME_PARQUET): return pd.DataFrame()
    df = pd.read_parquet(FILENAME_PARQUET)
    df = clean_column_names(df)
    df['Pre-Prod No.'] = df['Pre-Prod No.'].apply(pad_preprod_id)
    if 'Date' in df.columns:
        res = df.apply(calculate_age_category, axis=1)
        df['Age Category'], df['Project Age (Open and Closed)'] = [r[0] for r in res], [r[1] for r in res]
    return df

def save_db(df_to_save):
    df_to_save['Pre-Prod No.'] = df_to_save['Pre-Prod No.'].apply(pad_preprod_id)
    df_to_save.to_parquet(FILENAME_PARQUET, index=False)
    st.cache_data.clear()

@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='latin1', errors='ignore') as f:
            lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
            return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
    return []

# --- 5. INITIALIZE ---
df = load_db()

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}

# FULL VERIFIED LIST
DESIRED_ORDER = [
    "Date", "Age Category", "Client", "Description", "Project Description", "Diameter", 
    "New Mould_Client or Product", "Product Code", "Machine", "Sales Rep", 
    "Category", "Status", "Open or closed", "Completion date", "Material", 
    "Product Material Colour (tube, jar etc.)", "Artwork Required", "Artwork Received", 
    "Order Qty x1000", "Unit Order No", "Length", "Cap_Lid Style", "Cap_Lid Material", 
    "Cap_Lid Diameter", "Orifice", "Other Cap_Lid Info", "Tube Shoulder colour", 
    "Dust Controlled Area", "Date Sent on Proof", "Size of Eyemark", 
    "Proof Approved (Conventional)", "Proof Approved (Digital)", "Ordered Plates", 
    "Plates Arrived", "Sent on Trial", "Digital trial received", 
    "Revised Artwork After Trialling", "Masterbatch received", "Extrusion requested", 
    "Extrusion received", "Injection trial requested", "Injection Trial Received", 
    "Blowmould trial requested", "Blowmould trial received", "Comments"
]

# --- 6. CRITICAL SUMMARY ---
if not df.empty:
    pp_open = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
    critical_df = pp_open[pp_open['Age Category'] == "> 12 Weeks"].copy()
    
    st.subheader("📊 Pre-Prod Age Analysis Summary")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    c1.metric("Total Open", len(pp_open))
    c2.metric("Critical (>12w)", len(critical_df), delta_color="inverse")
    c3.metric("Mid (6-12w)", len(pp_open[pp_open['Age Category'] == "6-12 Weeks"]))
    with c4:
        dist = pp_open['Age Category'].value_counts().reindex(["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"], fill_value=0)
        st.bar_chart(dist, height=150)

    if not critical_df.empty:
        with st.expander(f"⚠️ View {len(critical_df)} Critical Projects", expanded=False):
            d_list = critical_df[['Pre-Prod No.', 'Client', 'Description', 'Project Age (Open and Closed)', 'Sales Rep']].sort_values('Project Age (Open and Closed)', ascending=False)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer: d_list.to_excel(writer, index=False)
            st.download_button("📂 Export Overdue List", data=buf.getvalue(), file_name="Critical_Projects.xlsx")
            st.table(d_list)

st.divider()

# --- 7. NAVIGATION ---
tab_nav = st.radio("Navigation", ["🔍 Search & Edit", "➕ Add New Job"], horizontal=True)

if tab_nav == "🔍 Search & Edit":
    search_val = st.text_input("Search Pre-Prod No.")
    search_id = pad_preprod_id(search_val) if search_val else ""
    match = df[df['Pre-Prod No.'] == search_id] if not df.empty else pd.DataFrame()

    if not match.empty:
        idx, row = match.index[0], match.iloc[0]
        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("👯 Clone Project"):
            st.session_state.form_data = row.to_dict()
            st.session_state.form_data['Pre-Prod No.'] = get_next_available_id(search_id, df['Pre-Prod No.'].tolist())
            st.info("Project details copied to 'Add New Job' tab.")
        
        with st.expander("Edit All Details", expanded=True):
            updated = {}
            edit_cols = st.columns(3)
            for i, col in enumerate(DESIRED_ORDER):
                if col == "Age Category": continue
                cur = str(row.get(col, "")) if str(row.get(col, "")).lower() != 'nan' else ""
                with edit_cols[i % 3]:
                    if col in DROPDOWN_DATA and DROPDOWN_DATA[col]:
                        opts = sorted(list(set([""] + DROPDOWN_DATA[col] + [cur])))
                        updated[col] = st.selectbox(col, opts, index=opts.index(cur))
                    else:
                        updated[col] = st.text_input(col, value=cur)
            
            if st.button("💾 Save Changes", type="primary"):
                for k,v in updated.items(): df.at[idx, k] = v
                save_db(df)
                st.success("Record Updated!")
                st.rerun()

elif tab_nav == "➕ Add New Job":
    with st.form("new_job_form"):
        st.subheader("Register New Project")
        new_id = st.text_input("Pre-Prod No.", value=st.session_state.form_data.get('Pre-Prod No.', get_auto_next_no(df)))
        new_data = {}
        form_cols = st.columns(3)
        for i, col in enumerate(DESIRED_ORDER):
            if col in ["Age Category", "Pre-Prod No."]: continue
            default = st.session_state.form_data.get(col, "")
            with form_cols[i % 3]:
                if col in DROPDOWN_DATA and DROPDOWN_DATA[col]:
                    opts = sorted(list(set([""] + DROPDOWN_DATA[col] + [default])))
                    new_data[col] = st.selectbox(col, opts, index=opts.index(default) if default in opts else 0)
                else:
                    new_data[col] = st.text_input(col, value=default)
        
        if st.form_submit_button("✅ Save New Project"):
            new_data['Pre-Prod No.'] = pad_preprod_id(new_id)
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df)
            st.session_state.form_data = {}
            st.success("Project Saved!")
            st.rerun()

st.divider()
if st.checkbox("Show Master Table"):
    st.dataframe(df, use_container_width=True)