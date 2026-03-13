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
    st.error("Missing dependency: Please run 'pip install xlsxwriter' to enable Excel exports.")

st.set_page_config(page_title="Project Tracker", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATHS ---
BASE_DIR = os.getcwd() 
FILENAME = os.path.join(BASE_DIR, "ProjectTracker_Combined.csv")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv") 
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")

# --- 3. HELPER FUNCTIONS ---

def clean_column_names(df):
    df.columns = [str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') for c in df.columns]
    return df

def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        comp_date = str(row.get('Completion date', '')).strip()
        if comp_date and comp_date.lower() != 'nan':
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
            if m.group(2):
                suffixes.append(int(m.group(2)))
            else:
                suffixes.append(0)
    
    next_s = max(suffixes) + 1 if suffixes else 1
    return f"{base_id}_{next_s}"

def get_auto_next_no(df):
    if df.empty: return "10001"
    nums = []
    for i in df['Pre-Prod No.'].tolist():
        match = re.match(r"(\d+)", str(i))
        if match: nums.append(int(match.group(1)))
    return str(max(nums) + 1) if nums else "10001"

def combine_digital_and_tracker(digital_path, tracker_path, output_path):
    if not os.path.exists(digital_path) or not os.path.exists(tracker_path): return None
    try:
        df_d = pd.read_csv(digital_path, sep=';', encoding='utf-8-sig', on_bad_lines='warn')
        df_t = pd.read_csv(tracker_path, sep=';', encoding='utf-8-sig', on_bad_lines='warn')
        df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].apply(clean_key)
        df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].apply(clean_key)
        combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), df_d.dropna(subset=['Pre-Prod No.']), 
                           on='Pre-Prod No.', how='outer', suffixes=('', '_digital_info'))
        for col in df_t.columns:
            suffix = f"{col}_digital_info"
            if suffix in combined.columns:
                combined[col] = combined[col].fillna(combined[suffix])
                combined.drop(columns=[suffix], inplace=True)
        combined.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig')
        return combined
    except Exception as e:
        st.error(f"Merge Error: {e}")
        return None

def load_db():
    combine_digital_and_tracker(DIGITALPREPROD_FILE, TRACKER_ADJ_FILE, FILENAME)
    if not os.path.exists(FILENAME): return pd.DataFrame()
    try:
        df = pd.read_csv(FILENAME, sep=';', encoding='utf-8-sig', quoting=3, on_bad_lines='warn')
        df = clean_column_names(df)
        df = df.map(lambda x: str(x).strip().replace('"', '') if isinstance(x, str) else x)
        if 'Pre-Prod No.' in df.columns:
            df['Pre-Prod No.'] = df['Pre-Prod No.'].astype(str)
            df = df[df['Pre-Prod No.'] != 'nan']
        if 'Date' in df.columns:
            results = df.apply(calculate_age_category, axis=1)
            df['Age Category'] = [r[0] for r in results]
            df['Project Age (Open and Closed)'] = [r[1] for r in results]
        df['Project Age (Open and Closed)'] = pd.to_numeric(df['Project Age (Open and Closed)'], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Load Error: {e}")
        return pd.DataFrame()

def save_db(df_to_save):
    df_to_save.to_csv(FILENAME, index=False, sep=';', encoding='utf-8-sig')

def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
                return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
        except: return []
    return []

# --- 4. DATA LOADING ---
df = load_db()

if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if 'selected_combo' not in st.session_state:
    st.session_state.selected_combo = {}

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", 
    "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}

DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}

DESIRED_ORDER = [
    "Date", "Age Category", "Client", "Description", "Diameter", "Project Description", "New Mould_Client or Product", 
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

# --- 5. INTERFACE ---
st.title("🚀 Project Management Dashboard")

# Metric Dashboard
if not df.empty:
    open_mask = df['Open or closed'].str.lower().str.contains('open', na=False)
    open_df = df[open_mask]
    avg_age = open_df['Project Age (Open and Closed)'].mean() if not open_df.empty else 0
    overdue_count = len(open_df[open_df['Age Category'] == "> 12 Weeks"])
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Projects", len(df))
    m2.metric("Open Projects", len(open_df))
    m3.metric("Closed Projects", len(df[~open_mask]))
    m4.metric("Avg. Age (Open)", f"{int(avg_age)} Days")
    m5.metric("Critical (>12 Wks)", overdue_count)

st.divider()

tab_nav = st.radio("Navigation", ["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis"], 
                   index=["🔍 Search & Edit", "➕ Add New Job", "📊 Detailed Age Analysis"].index(st.session_state.active_tab),
                   key="nav_radio", horizontal=True)
st.session_state.active_tab = tab_nav

# --- SHARED UI COMPONENT: COMBINATION TABLE ---
def display_combination_table(key_prefix):
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Click to browse Tube & Cap Combinations", expanded=False):
            try:
                # Use semicolon separator as per typical file structure
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig')
                combo_df = clean_column_names(combo_df)
                
                search = st.text_input(f"🔍 Filter Combinations", key=f"{key_prefix}_search")
                if search:
                    mask = combo_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
                    combo_df = combo_df[mask]
                
                st.info("Select a row below to auto-fill Diameter, Cap Style, and Cap Diameter.")
                event = st.dataframe(
                    combo_df, 
                    use_container_width=True, 
                    hide_index=True, 
                    on_select="rerun", 
                    selection_mode="single-row",
                    key=f"{key_prefix}_table"
                )
                
                if event.selection.rows:
                    selected_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    # Map combo columns to form columns
                    st.session_state.selected_combo = {
                        "Diameter": str(selected_row.get("Diameter", "")),
                        "Cap_Lid Style": str(selected_row.get("Cap_Lid_Style", selected_row.get("Cap_Lid Style", ""))),
                        "Cap_Lid Diameter": str(selected_row.get("Cap_Lid_Diameter", selected_row.get("Cap_Lid Diameter", "")))
                    }
                    st.success("Combination selected! Details updated below.")
            except Exception as e:
                st.error(f"Error loading combinations: {e}")

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    search_no = st.text_input("Search Pre-Prod No. (e.g. 9143)").strip()
    match = df[df['Pre-Prod No.'] == search_no] if 'Pre-Prod No.' in df.columns else pd.DataFrame()
    
    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        
        display_combination_table("edit")

        with st.expander("Edit Details", expanded=True):
            updated_vals = {}
            edit_cols = st.columns(3)
            
            for i, col_name in enumerate(DESIRED_ORDER):
                if col_name == "Age Category": continue
                
                # Check if we have a selection from the table to override the current row value
                if col_name in st.session_state.selected_combo and st.session_state.selected_combo[col_name]:
                    cur_val = st.session_state.selected_combo[col_name]
                else:
                    cur_val = str(row.get(col_name, "")) if str(row.get(col_name, "")).lower() != 'nan' else ""

                with edit_cols[i % 3]:
                    if col_name == 'Completion date':
                        try: d = pd.to_datetime(cur_val, dayfirst=True).date() if cur_val else None
                        except: d = None
                        sel_d = st.date_input(f"Edit {col_name}", value=d, key=f"ed_{col_name}")
                        updated_vals[col_name] = sel_d.strftime('%d/%m/%Y') if sel_d else ""
                    elif col_name in ["Status", "Open or closed"]: continue
                    elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                        opts = sorted(list(set([""] + DROPDOWN_DATA[col_name] + ([cur_val] if cur_val else []))))
                        idx_sel = opts.index(cur_val) if cur_val in opts else 0
                        updated_vals[col_name] = st.selectbox(f"Edit {col_name}", options=opts, index=idx_sel, key=f"sel_{col_name}")
                    else:
                        updated_vals[col_name] = st.text_input(f"Edit {col_name}", value=cur_val, key=f"txt_{col_name}")

            if st.button("💾 Save Changes", type="primary"):
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df)
                st.session_state.selected_combo = {} # Clear after save
                st.success("Updated!")
                st.rerun()

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    display_combination_table("new")
    
    with st.form("new_job_form", clear_on_submit=True):
        st.subheader("Register Project")
        default_id = st.session_state.form_data.get('Pre-Prod No.', get_auto_next_no(df))
        new_id_input = st.text_input("Pre-Prod No.", value=default_id)
        
        new_data = {}
        cols = st.columns(3)
        
        for i, col_name in enumerate(DESIRED_ORDER):
            if col_name == "Age Category": continue
            
            # Form priority: 1. Manual Session state (cloning) 2. Table Selection 3. Empty
            val = st.session_state.form_data.get(col_name, "")
            if col_name in st.session_state.selected_combo and st.session_state.selected_combo[col_name]:
                val = st.session_state.selected_combo[col_name]

            with cols[i % 3]:
                if col_name == 'Date':
                    new_data[col_name] = st.date_input(col_name, value=datetime.now()).strftime('%d/%m/%Y')
                elif col_name == 'Completion date':
                    res = st.date_input(col_name, value=None)
                    new_data[col_name] = res.strftime('%d/%m/%Y') if res else ""
                elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                    opts = sorted(list(set([""] + DROPDOWN_DATA[col_name] + ([val] if val else []))))
                    new_data[col_name] = st.selectbox(col_name, options=opts, index=opts.index(val) if val in opts else 0)
                elif col_name in ['Status', 'Open or closed']:
                    status = "Open"
                    new_data[col_name] = status
                    st.text_input(col_name, value=status, disabled=True)
                else:
                    new_data[col_name] = st.text_input(col_name, value=val)

        if st.form_submit_button("✅ Save Project"):
            existing_ids = df['Pre-Prod No.'].tolist()
            final_id = get_next_available_id(new_id_input, existing_ids)
            new_data['Pre-Prod No.'] = final_id
            final_status = "Closed" if new_data.get('Completion date') else "Open"
            new_data['Status'] = final_status
            new_data['Open or closed'] = final_status
            cat, days = calculate_age_category(new_data)
            new_data.update({'Age Category': cat, 'Project Age (Open and Closed)': days})
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df)
            st.session_state.form_data = {}
            st.session_state.selected_combo = {}
            st.success(f"Project {final_id} Saved!")
            st.rerun()

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

# --- 6. GLOBAL DATA TABLE ---
st.divider()
if st.checkbox("Show Master Project Table", value=True):
    search_q = st.text_input("🔍 Global Search").lower()
    disp_df = df.copy()
    if search_q:
        disp_df = disp_df[disp_df.apply(lambda r: r.astype(str).str.contains(search_q, case=False).any(), axis=1)]
    st.dataframe(disp_df, use_container_width=True)