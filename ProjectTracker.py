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
# Updated to match your actual filename
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Clean_NA.csv") 
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
    """Checks if an ID exists and increments an underscore suffix if needed."""
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
    """Determines the next sequential base ID."""
    if df.empty:
        return "10001"
    nums = []
    for i in df['Pre-Prod No.'].tolist():
        match = re.match(r"(\d+)", str(i))
        if match:
            nums.append(int(match.group(1)))
    if nums:
        return str(max(nums) + 1)
    return "10001"

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
    # Fixed typo: TRACKER_AD_FILE -> TRACKER_ADJ_FILE
    combine_digital_and_tracker(DIGITALPREPROD_FILE, TRACKER_ADJ_FILE, FILENAME)
    if not os.path.exists(FILENAME): return pd.DataFrame()
    try:
        df = pd.read_csv(FILENAME, sep=';', encoding='utf-8-sig', quoting=3, on_bad_lines='warn')
        df = clean_column_names(df)
        df = df.map(lambda x: str(x).strip().replace('"', '') if isinstance(x, str) else x)
        if 'Pre-Prod No.' in df.columns:
            df['Pre-Prod No.' ] = df['Pre-Prod No.'].astype(str)
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
        except: 
            return []
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
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", "Sales Rep": "Sales Rep.csv",
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

if not df.empty:
    open_mask = df['Open or closed'].str.lower().str.contains('open', na=False)
    open_df = df[open_mask]
    avg_age = open_df['Project Age (Open and Closed)'].mean() if not open_df.empty else 0
    overdue_count = len(open_df[open_df['Age Category'] == "> 12 Weeks"])
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Projects", len(df))
    m2.metric("Open Projects", len(open_df))
    m3.metric("Closed Projects