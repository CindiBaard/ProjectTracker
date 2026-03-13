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

def get_combination_options():
    if os.path.exists(COMBINATIONS_FILE):
        try:
            comb_df = pd.read_csv(COMBINATIONS_FILE, encoding='latin1', on_bad_lines='skip')
            return sorted(comb_df.apply(lambda x: ' | '.join(x.astype(str).str.strip()), axis=1).tolist())
        except: return []
    return []

# --- 4. DATA LOADING ---
df = load_db()

if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", 
    "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}

DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
COMBINATION_LIST = get_combination_options()

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

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    search_no = st.text_input("Search Pre-Prod No. (e.g. 9143)").strip()
    match = df[df['Pre-Prod No.'] == search_no]
    
    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        c1, c2 = st.columns(2)
        with c1:
            if st.button("👯 Clone as Repeat Order", use_container_width=True):
                existing_ids = df['Pre-Prod No.'].tolist()
                new_id = get_next_available_id(search_no, existing_ids)
                new_clone = row.to_dict()
                new_clone['Pre-Prod No.'] = new_id
                new_clone['Date'] = datetime.now().strftime('%d/%m/%Y')
                new_clone['Completion date'] = ""
                new_clone['Status'] = "Open"
                new_clone['Open or closed'] = "Open"
                st.session_state.form_data = new_clone
                st.session_state.active_tab = "➕ Add New Job"
                st.rerun()
        with c2:
            with st.popover("🗑️ Delete Project", use_container_width=True):
                if st.button("❌ Confirm Delete", type="primary"):
                    df = df.drop(idx)
                    save_db(df)
                    st.rerun()

        with st.expander("Edit Details", expanded=True):
            updated_vals = {}
            
            # Logic for Combination Select in Edit
            selected_comb = st.selectbox("Update from Tube/Cap Combinations", options=[""] + COMBINATION_LIST, key="edit_comb_select")
            
            edit_cols = st.columns(3)
            for i, col_name in enumerate(DESIRED_ORDER):
                if col_name == "Age Category": continue
                cur_val = str(row.get(col_name, "")) if str(row.get(col_name, "")).lower() != 'nan' else ""
                
                # Auto-fill values if a combination is selected
                if selected_comb:
                    parts = [p.strip() for p in selected_comb.split('|')]
                    if col_name == "Diameter" and len(parts) > 0: cur_val = parts[0]
                    if col_name == "Cap_Lid Style" and len(parts) > 1: cur_val = parts[1]
                    if col_name == "Cap_Lid Diameter" and len(parts) > 2: cur_val = parts[2]

                with edit_cols[i % 3]:
                    if col_name == 'Completion date':
                        try: d = pd.to_datetime(cur_val, dayfirst=True).date() if cur_val else None
                        except: d = None
                        sel_d = st.date_input(f"Edit {col_name}", value=d)
                        updated_vals[col_name] = sel_d.strftime('%d/%m/%Y') if sel_d else ""
                    elif col_name in ["Status", "Open or closed"]: continue
                    elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                        opts = [""] + sorted(list(set(DROPDOWN_DATA[col_name] + [cur_val])))
                        updated_vals[col_name] = st.selectbox(f"Edit {col_name}", options=opts, index=opts.index(cur_val))
                    else:
                        updated_vals[col_name] = st.text_input(f"Edit {col_name}", value=cur_val)
            
            updated_vals["Status"] = "Closed" if updated_vals.get("Completion date") else "Open"
            updated_vals["Open or closed"] = updated_vals["Status"]
            if st.button("💾 Save Changes"):
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df)
                st.success("Updated!")
                st.rerun()

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    # Selection outside form triggers a rerun, allowing the form logic to catch the new 'val'
    selected_comb = st.selectbox("Quick Select: Tube & Cap Combination", options=[""] + COMBINATION_LIST, key="new_job_comb_select")
    
    with st.form("new_job_form", clear_on_submit=True):
        st.subheader("Register Project")
        
        default_id = st.session_state.form_data.get('Pre-Prod No.', get_auto_next_no(df))
        new_id_input = st.text_input("Pre-Prod No.", value=default_id)
        new_data = {}
        cols = st.columns(3)
        
        for i, col_name in enumerate(DESIRED_ORDER):
            if col_name == "Age Category": continue
            val = st.session_state.form_data.get(col_name, "")
            
            # Apply Combination Auto-fill logic before creating widgets
            if selected_comb:
                parts = [p.strip() for p in selected_comb.split('|')]
                if col_name == "Diameter" and len(parts) > 0: val = parts[0]
                if col_name == "Cap_Lid Style" and len(parts) > 1: val = parts[1]
                if col_name == "Cap_Lid Diameter" and len(parts) > 2: val = parts[2]

            with cols[i % 3]:
                if col_name == 'Date':
                    new_data[col_name] = st.date_input(col_name, value=datetime.now()).strftime('%d/%m/%Y')
                elif col_name == 'Completion date':
                    res = st.date_input(col_name, value=None)
                    new_data[col_name] = res.strftime('%d/%m/%Y') if res else ""
                elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                    opts = [""] + DROPDOWN_DATA[col_name]
                    # Dynamically add the auto-filled value to options if not present
                    if val and val not in opts: opts.append(val)
                    new_data[col_name] = st.selectbox(col_name, options=opts, index=opts.index(val) if val in opts else 0)
                elif col_name in ['Status', 'Open or closed']:
                    # Auto-calculate status based on Completion date presence
                    status = "Open"
                    new_data[col_name] = status
                    st.text_input(col_name, value=status, disabled=True)
                else:
                    new_data[col_name] = st.text_input(col_name, value=val)

        if st.form_submit_button("✅ Save Project"):
            existing_ids = df['Pre-Prod No.'].tolist()
            final_id = get_next_available_id(new_id_input, existing_ids)
            new_data['Pre-Prod No.'] = final_id
            
            # Recalculate status one last time for the final save
            final_status = "Closed" if new_data.get('Completion date') else "Open"
            new_data['Status'] = final_status
            new_data['Open or closed'] = final_status
            
            cat, days = calculate_age_category(new_data)
            new_data.update({'Age Category': cat, 'Project Age (Open and Closed)': days})
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df)
            st.session_state.form_data = {} 
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