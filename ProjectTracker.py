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
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTracker_adj.csv")
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")

# --- 3. HELPER FUNCTIONS ---

def clean_column_names(df):
    df.columns = [str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') for c in df.columns]
    return df

def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        end_date = pd.to_datetime(row['Completion date'], dayfirst=True, errors='coerce') if pd.notnull(row.get('Completion date')) and str(row['Completion date']).strip() != "" else pd.to_datetime(datetime.now().date())
        if pd.isnull(start_date) or pd.isnull(end_date): return "N/A", 0
        days = (end_date - start_date).days
        cat = "< 6 Weeks" if days < 42 else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        return cat, days
    except: return "Error", 0

def clean_key(val):
    if pd.isna(val) or str(val).strip() == '': return None
    s_val = str(val).strip()
    return s_val[:-2] if s_val.endswith('.0') else s_val

def combine_digital_and_tracker(digital_path, tracker_path, output_path):
    if not os.path.exists(digital_path) or not os.path.exists(tracker_path): return None
    try:
        df_d = pd.read_csv(digital_path, sep=';', encoding='utf-8-sig', on_bad_lines='warn')
        df_t = pd.read_csv(tracker_path, sep=';', encoding='utf-8-sig', on_bad_lines='warn')
        df_d['Pre-Prod No.'] = df_d['Pre-Prod No.'].apply(clean_key)
        df_t['Pre-Prod No.'] = df_t['Pre-Prod No.'].apply(clean_key)
        combined = pd.merge(df_t.dropna(subset=['Pre-Prod No.']), df_d.dropna(subset=['Pre-Prod No.']), on='Pre-Prod No.', how='outer', suffixes=('', '_digital_info'))
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
            df['Age Category'], df['Project Age (Open and Closed)'] = [r[0] for r in results], [r[1] for r in results]
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

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", "Sales Rep": "Sales Rep.csv",
    "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
DYNAMIC_CLIENTS = sorted(df['Client'].dropna().unique().tolist()) if not df.empty else []
DYNAMIC_SALES = sorted(list(set(df['Sales Rep'].dropna().unique().tolist() + DROPDOWN_DATA.get('Sales Rep', [])))) if not df.empty else []

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
st.title("🚀 Project Tracker")

tab_nav = st.radio("Navigation", ["🔍 Search & Edit", "➕ Add New Job"], horizontal=True)

# --- TAB: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":
    search_no = st.text_input("Enter Pre-Prod No. (e.g., 9143 or 9143_1)").strip()
    match = df[df['Pre-Prod No.'] == search_no]
    
    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        
        # Cloning Logic
        if st.button("👯 Clone as Repeat Order", use_container_width=True):
            base_no = search_no.split('_')[0]
            existing = df[df['Pre-Prod No.'].str.startswith(f"{base_no}_")]
            suffixes = [int(s.split('_')[1]) for s in existing['Pre-Prod No.'] if '_' in s]
            next_s = max(suffixes) + 1 if suffixes else 1
            
            new_clone = row.to_dict()
            new_clone['Pre-Prod No.'] = f"{base_no}_{next_s}"
            new_clone['Date'] = datetime.now().strftime('%d/%m/%Y')
            new_clone['Completion date'] = ""
            st.session_state.form_data = new_clone
            st.success(f"Clone {base_no}_{next_s} ready in 'Add New Job' tab!")

        # Edit Form
        with st.expander("Edit Details", expanded=True):
            updated_vals = {}
            edit_cols = st.columns(3)
            for i, col_name in enumerate(DESIRED_ORDER):
                if col_name == "Age Category": continue
                cur_val = str(row.get(col_name, "")) if str(row.get(col_name, "")).lower() != 'nan' else ""
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

            if st.button("💾 Update Project"):
                for k, v in updated_vals.items(): df.at[idx, k] = v
                save_db(df)
                st.success("Updated!")
                st.rerun()

# --- TAB: ADD NEW JOB ---
elif tab_nav == "➕ Add New Job":
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("🔍 Tube & Cap Combination Lookup"):
            combo_df = clean_column_names(pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig'))
            s = st.text_input("Filter Combinations")
            if s: combo_df = combo_df[combo_df.apply(lambda r: r.astype(str).str.contains(s, case=False).any(), axis=1)]
            
            # FIXED SELECTION LOGIC HERE
            ev = st.dataframe(combo_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="lookup")
            
            # Use .selection['rows'] to get index
            if ev.selection and ev.selection['rows']:
                selected_idx = ev.selection['rows'][0]
                selected_row_dict = combo_df.iloc[selected_idx].to_dict()
                st.session_state.form_data = {k: (str(v) if str(v).lower() != 'nan' else "") for k, v in selected_row_dict.items()}

    def get_next_no(df):
        if df.empty: return "10001"
        nums = [int(re.match(r"(\d+)", str(i)).group(1)) for i in df['Pre-Prod No.'].tolist() if re.match(r"(\d+)", str(i))]
        return str(max(nums) + 1) if nums else "10001"

    with st.form("new_job"):
        default_id = st.session_state.form_data.get('Pre-Prod No.', get_next_no(df))
        new_id = st.text_input("Pre-Prod No.", value=default_id)
        new_data = {'Pre-Prod No.': new_id}
        
        cols = st.columns(3)
        for i, col_name in enumerate(DESIRED_ORDER):
            if col_name == "Age Category": continue
            val = st.session_state.form_data.get(col_name, "")
            with cols[i % 3]:
                if col_name == 'Date':
                    new_data[col_name] = st.date_input(col_name, value=datetime.now()).strftime('%d/%m/%Y')
                elif col_name == 'Completion date':
                    res = st.date_input(col_name, value=None)
                    new_data[col_name] = res.strftime('%d/%m/%Y') if res else ""
                elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                    opts = [""] + DROPDOWN_DATA[col_name]
                    if val and val not in opts: opts.append(val)
                    new_data[col_name] = st.selectbox(col_name, options=opts, index=opts.index(val) if val in opts else 0)
                elif col_name in ['Status', 'Open or closed']:
                    new_data[col_name] = "Open" if not new_data.get('Completion date') else "Closed"
                    st.text_input(col_name, value=new_data[col_name], disabled=True)
                else:
                    new_data[col_name] = st.text_input(col_name, value=val)

        if st.form_submit_button("✅ Save Project"):
            cat, days = calculate_age_category(new_data)
            new_data.update({'Age Category': cat, 'Project Age (Open and Closed)': days})
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df)
            st.session_state.form_data = {}
            st.success("Saved!")
            st.rerun()

# --- 6. DATA TABLE ---
st.divider()
if st.checkbox("Show Data Table", value=True):
    st.dataframe(df, use_container_width=True)