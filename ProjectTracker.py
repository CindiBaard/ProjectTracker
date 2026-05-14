import os
import re
import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. INITIAL SETUP ---
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATHS & CONFIG ---
BASE_DIR = os.getcwd()
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv")
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"
TRACKER_FILE_ID = "1LA9F5mD67vR9yYKqQ39CS-tAZ9QgCgn5KBWaY_RfFKM"
MOULD_ASSETS_ID = "1Ix1aq6Ze63Vhqh9Pm98BegUnDaLgKC6H9vTMKafjc44"

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

DROPDOWN_FILES = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Cap_Lid Style": "Cap_Lid style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "CapMaterial.csv"
}

# --- 3. SESSION STATE ---
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}

# --- 4. CORE UTILITIES ---

def get_gspread_client():
    creds_info = st.secrets.get("gcp_service_account", st.secrets.get("connections", {}).get("gsheets"))
    if isinstance(creds_info, dict) and "private_key" in creds_info:
         creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))

@st.cache_data(ttl=600)
def get_mould_lookup_data():
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(MOULD_ASSETS_ID).get_worksheet(0)
        raw = sheet.get_all_values()
        if len(raw) < 2: return {}
        df_assets = pd.DataFrame(raw[1:], columns=[str(h).strip() for h in raw[0]])
        # Fix for AttributeError: str by ensuring string conversion first
        desc_col = next((c for c in df_assets.columns if "description" in c.lower()), df_assets.columns[0])
        mould_col = next((c for c in df_assets.columns if "mould" in c.lower()), df_assets.columns[1])
        df_assets[desc_col] = df_assets[desc_col].astype(str).str.strip()
        df_assets[mould_col] = df_assets[mould_col].astype(str).str.strip()
        return dict(zip(df_assets[desc_col], df_assets[mould_col]))
    except: return {}

def smart_read(path):
    if not os.path.exists(path): return pd.DataFrame()
    try:
        df = pd.read_csv(path, sep=';', on_bad_lines='skip', encoding='utf-8-sig')
        if len(df.columns) <= 1:
            df = pd.read_csv(path, sep=',', on_bad_lines='skip', encoding='utf-8-sig')
        return df
    except: return pd.DataFrame()

def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == '': return ""
    return str(val).strip().split('.')[0].zfill(5)

def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                return sorted(list(set([l.strip() for l in f.readlines() if l.strip()])))
        except: return []
    return []

# --- 5. DATA MERGING & CLEANING LOGIC ---

def merge_and_clean_data():
    df_conv = smart_read(TRACKER_ADJ_FILE)
    df_digi = smart_read(DIGITALPREPROD_FILE)
    
    if df_conv.empty and df_digi.empty:
        return pd.DataFrame(columns=DESIRED_ORDER)

    # Standardize Pre-Prod Numbers
    for d in [df_conv, df_digi]:
        if not d.empty:
            col = 'Pre-Prod No.' if 'Pre-Prod No.' in d.columns else d.columns[0]
            d.rename(columns={col: 'Pre-Prod No.'}, inplace=True)
            d['Pre-Prod No.'] = d['Pre-Prod No.'].apply(pad_preprod_id)

    combined = pd.concat([df_conv, df_digi], ignore_index=True).drop_duplicates(subset=['Pre-Prod No.'], keep='last')
    
    # Re-order and fill missing
    for col in DESIRED_ORDER:
        if col not in combined.columns: combined[col] = ""
    
    return combined[DESIRED_ORDER]

@st.cache_data
def load_db():
    if os.path.exists(FILENAME_PARQUET):
        return pd.read_parquet(FILENAME_PARQUET)
    return merge_and_clean_data()

# --- 6. MAIN APP INTERFACE ---

df = load_db()
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_FILES.items()}

tabs = st.tabs(["🔍 Search & Edit", "➕ Add New", "📊 Analysis", "🧪 Trials", "⚙️ Admin"])

with tabs[0]:
    search_query = st.text_input("Search Pre-Prod No.", placeholder="e.g. 12345").strip()
    if search_query:
        search_id = pad_preprod_id(search_query)
        match = df[df['Pre-Prod No.'] == search_id]
        
        if not match.empty:
            idx, row = match.index[0], match.iloc[0]
            with st.form("edit_project_form"):
                st.subheader(f"Editing Project {search_id}")
                
                # Mould Assets Logic
                m_lookup = get_mould_lookup_data()
                selected_mould_desc = st.selectbox("Quick-Select Mould Asset", options=[""] + list(m_lookup.keys()))
                
                c1, c2 = st.columns(2)
                with c1:
                    m_no = st.text_input("Mould No.", value=m_lookup.get(selected_mould_desc, str(row.get('Mould No.', ''))))
                with c2:
                    d_no = st.text_input("Drawing No.", value=str(row.get('Drawing No.', '')))

                updates = {"Mould No.": m_no, "Drawing No.": d_no}
                
                # Dynamic Layout for the rest of DESIRED_ORDER
                remaining = [c for c in DESIRED_ORDER if c not in ["Pre-Prod No.", "Mould No.", "Drawing No."]]
                cols = st.columns(3)
                for i, col_name in enumerate(remaining):
                    with cols[i % 3]:
                        current_val = str(row.get(col_name, "")).replace('nan', '')
                        if col_name in DROPDOWN_DATA:
                            opts = sorted(list(set(["", current_val] + DROPDOWN_DATA[col_name])))
                            updates[col_name] = st.selectbox(col_name, opts, index=opts.index(current_val))
                        else:
                            updates[col_name] = st.text_input(col_name, value=current_val)

                if st.form_submit_button("💾 Update Database"):
                    for k, v in updates.items(): df.at[idx, k] = v
                    save_db(df)
                    st.success("Record Updated Locally.")
        else:
            st.error("No project found with that ID.")

with tabs[1]:
    st.subheader("Register New Pre-Production Project")
    with st.form("add_new_form"):
        # Auto-increment logic
        existing_ids = df['Pre-Prod No.'].dropna().astype(int, errors='ignore').tolist()
        next_id = str(max([int(x) for x in existing_ids if str(x).isdigit()] or [0]) + 1).zfill(5)
        
        new_data = {"Pre-Prod No.": st.text_input("Pre-Prod No.", value=next_id)}
        a_cols = st.columns(3)
        for i, col in enumerate([c for c in DESIRED_ORDER if c != "Pre-Prod No."]):
            with a_cols[i % 3]:
                if col in DROPDOWN_DATA:
                    new_data[col] = st.selectbox(f"New {col}", [""] + DROPDOWN_DATA[col])
                else:
                    new_data[col] = st.text_input(col)
        
        if st.form_submit_button("➕ Create Project"):
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df)
            st.success("New Project Added.")

with tabs[2]:
    st.subheader("Project Aging & Status Analysis")
    if 'Age Category' in df.columns:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**By Age Category**")
            st.bar_chart(df['Age Category'].value_counts())
        with c2:
            st.write("**By Status**")
            st.bar_chart(df['Status'].value_counts())
    
    st.dataframe(df.style.highlight_null(color='lightyellow'), use_container_width=True)

with tabs[3]:
    st.subheader("Weekly Trial Performance")
    trial_df = smart_read(TRIALS_FILE_CURRENT)
    if not trial_df.empty:
        st.dataframe(trial_df)
        # Add plotting logic for trials here
    else:
        st.info("No trial data found in local directory.")

with tabs[4]:
    st.subheader("System Administration")
    if st.button("🔄 Force Re-merge from CSVs"):
        df = merge_and_clean_data()
        save_db(df)
        st.success("Re-merged from CSV files.")
        
    if st.button("☁️ Sync to Google Sheets"):
        try:
            client = get_gspread_client()
            sh = client.open_by_key(TRACKER_FILE_ID).get_worksheet(0)
            sh.clear()
            sh.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
            st.success("Cloud Sync Complete!")
        except Exception as e:
            st.error(f"Cloud Sync Failed: {e}")

    st.download_button("📥 Export to CSV", df.to_csv(index=False), "export.csv", "text/csv")import os
import re
import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. INITIAL SETUP ---
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATHS & CONFIG ---
BASE_DIR = os.getcwd()
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv")
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")
TRIALS_FILE_CURRENT = "Combined_Weekly_Trials_Weeks_3_12_2026.csv"
TRACKER_FILE_ID = "1LA9F5mD67vR9yYKqQ39CS-tAZ9QgCgn5KBWaY_RfFKM"
MOULD_ASSETS_ID = "1Ix1aq6Ze63Vhqh9Pm98BegUnDaLgKC6H9vTMKafjc44"

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

DROPDOWN_FILES = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Cap_Lid Style": "Cap_Lid style.csv", "Machine": "Machine.csv", 
    "Sales Rep": "Sales Rep.csv", "Cap_Lid Material": "CapMaterial.csv"
}

# --- 3. SESSION STATE ---
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}

# --- 4. CORE UTILITIES ---

def get_gspread_client():
    creds_info = st.secrets.get("gcp_service_account", st.secrets.get("connections", {}).get("gsheets"))
    if isinstance(creds_info, dict) and "private_key" in creds_info:
         creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))

@st.cache_data(ttl=600)
def get_mould_lookup_data():
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(MOULD_ASSETS_ID).get_worksheet(0)
        raw = sheet.get_all_values()
        if len(raw) < 2: return {}
        df_assets = pd.DataFrame(raw[1:], columns=[str(h).strip() for h in raw[0]])
        # Fix for AttributeError: str by ensuring string conversion first
        desc_col = next((c for c in df_assets.columns if "description" in c.lower()), df_assets.columns[0])
        mould_col = next((c for c in df_assets.columns if "mould" in c.lower()), df_assets.columns[1])
        df_assets[desc_col] = df_assets[desc_col].astype(str).str.strip()
        df_assets[mould_col] = df_assets[mould_col].astype(str).str.strip()
        return dict(zip(df_assets[desc_col], df_assets[mould_col]))
    except: return {}

def smart_read(path):
    if not os.path.exists(path): return pd.DataFrame()
    try:
        df = pd.read_csv(path, sep=';', on_bad_lines='skip', encoding='utf-8-sig')
        if len(df.columns) <= 1:
            df = pd.read_csv(path, sep=',', on_bad_lines='skip', encoding='utf-8-sig')
        return df
    except: return pd.DataFrame()

def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == '': return ""
    return str(val).strip().split('.')[0].zfill(5)

def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)

@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                return sorted(list(set([l.strip() for l in f.readlines() if l.strip()])))
        except: return []
    return []

# --- 5. DATA MERGING & CLEANING LOGIC ---

def merge_and_clean_data():
    df_conv = smart_read(TRACKER_ADJ_FILE)
    df_digi = smart_read(DIGITALPREPROD_FILE)
    
    if df_conv.empty and df_digi.empty:
        return pd.DataFrame(columns=DESIRED_ORDER)

    # Standardize Pre-Prod Numbers
    for d in [df_conv, df_digi]:
        if not d.empty:
            col = 'Pre-Prod No.' if 'Pre-Prod No.' in d.columns else d.columns[0]
            d.rename(columns={col: 'Pre-Prod No.'}, inplace=True)
            d['Pre-Prod No.'] = d['Pre-Prod No.'].apply(pad_preprod_id)

    combined = pd.concat([df_conv, df_digi], ignore_index=True).drop_duplicates(subset=['Pre-Prod No.'], keep='last')
    
    # Re-order and fill missing
    for col in DESIRED_ORDER:
        if col not in combined.columns: combined[col] = ""
    
    return combined[DESIRED_ORDER]

@st.cache_data
def load_db():
    if os.path.exists(FILENAME_PARQUET):
        return pd.read_parquet(FILENAME_PARQUET)
    return merge_and_clean_data()

# --- 6. MAIN APP INTERFACE ---

df = load_db()
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_FILES.items()}

tabs = st.tabs(["🔍 Search & Edit", "➕ Add New", "📊 Analysis", "🧪 Trials", "⚙️ Admin"])

with tabs[0]:
    search_query = st.text_input("Search Pre-Prod No.", placeholder="e.g. 12345").strip()
    if search_query:
        search_id = pad_preprod_id(search_query)
        match = df[df['Pre-Prod No.'] == search_id]
        
        if not match.empty:
            idx, row = match.index[0], match.iloc[0]
            with st.form("edit_project_form"):
                st.subheader(f"Editing Project {search_id}")
                
                # Mould Assets Logic
                m_lookup = get_mould_lookup_data()
                selected_mould_desc = st.selectbox("Quick-Select Mould Asset", options=[""] + list(m_lookup.keys()))
                
                c1, c2 = st.columns(2)
                with c1:
                    m_no = st.text_input("Mould No.", value=m_lookup.get(selected_mould_desc, str(row.get('Mould No.', ''))))
                with c2:
                    d_no = st.text_input("Drawing No.", value=str(row.get('Drawing No.', '')))

                updates = {"Mould No.": m_no, "Drawing No.": d_no}
                
                # Dynamic Layout for the rest of DESIRED_ORDER
                remaining = [c for c in DESIRED_ORDER if c not in ["Pre-Prod No.", "Mould No.", "Drawing No."]]
                cols = st.columns(3)
                for i, col_name in enumerate(remaining):
                    with cols[i % 3]:
                        current_val = str(row.get(col_name, "")).replace('nan', '')
                        if col_name in DROPDOWN_DATA:
                            opts = sorted(list(set(["", current_val] + DROPDOWN_DATA[col_name])))
                            updates[col_name] = st.selectbox(col_name, opts, index=opts.index(current_val))
                        else:
                            updates[col_name] = st.text_input(col_name, value=current_val)

                if st.form_submit_button("💾 Update Database"):
                    for k, v in updates.items(): df.at[idx, k] = v
                    save_db(df)
                    st.success("Record Updated Locally.")
        else:
            st.error("No project found with that ID.")

with tabs[1]:
    st.subheader("Register New Pre-Production Project")
    with st.form("add_new_form"):
        # Auto-increment logic
        existing_ids = df['Pre-Prod No.'].dropna().astype(int, errors='ignore').tolist()
        next_id = str(max([int(x) for x in existing_ids if str(x).isdigit()] or [0]) + 1).zfill(5)
        
        new_data = {"Pre-Prod No.": st.text_input("Pre-Prod No.", value=next_id)}
        a_cols = st.columns(3)
        for i, col in enumerate([c for c in DESIRED_ORDER if c != "Pre-Prod No."]):
            with a_cols[i % 3]:
                if col in DROPDOWN_DATA:
                    new_data[col] = st.selectbox(f"New {col}", [""] + DROPDOWN_DATA[col])
                else:
                    new_data[col] = st.text_input(col)
        
        if st.form_submit_button("➕ Create Project"):
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            save_db(df)
            st.success("New Project Added.")

with tabs[2]:
    st.subheader("Project Aging & Status Analysis")
    if 'Age Category' in df.columns:
        c1, c2 = st.columns(2)
        with c1:
            st.write("**By Age Category**")
            st.bar_chart(df['Age Category'].value_counts())
        with c2:
            st.write("**By Status**")
            st.bar_chart(df['Status'].value_counts())
    
    st.dataframe(df.style.highlight_null(color='lightyellow'), use_container_width=True)

with tabs[3]:
    st.subheader("Weekly Trial Performance")
    trial_df = smart_read(TRIALS_FILE_CURRENT)
    if not trial_df.empty:
        st.dataframe(trial_df)
        # Add plotting logic for trials here
    else:
        st.info("No trial data found in local directory.")

with tabs[4]:
    st.subheader("System Administration")
    if st.button("🔄 Force Re-merge from CSVs"):
        df = merge_and_clean_data()
        save_db(df)
        st.success("Re-merged from CSV files.")
        
    if st.button("☁️ Sync to Google Sheets"):
        try:
            client = get_gspread_client()
            sh = client.open_by_key(TRACKER_FILE_ID).get_worksheet(0)
            sh.clear()
            sh.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
            st.success("Cloud Sync Complete!")
        except Exception as e:
            st.error(f"Cloud Sync Failed: {e}")

    st.download_button("📥 Export to CSV", df.to_csv(index=False), "export.csv", "text/csv")