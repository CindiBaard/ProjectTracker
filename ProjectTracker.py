import os
import pandas as pd
import streamlit as st
import re
from datetime import datetime
import io

# Explicitly import xlsxwriter to ensure it's present
try:
    import xlsxwriter
except ImportError:
    st.error("Missing dependency: Please run 'pip install xlsxwriter' in your terminal to enable Excel exports.")

# --- 1. SET PAGE CONFIG ---
st.set_page_config(page_title="Project Master Pro", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATH LOGIC ---
BASE_DIR = os.getcwd() 

FILENAME = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv")
ARTWORK_FILE = os.path.join(BASE_DIR, "Artwork Status.csv")
DIGITAL_ARTWORK_FILE = os.path.join(BASE_DIR, "Digital Artwork Status.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")

def get_local_path(filename):
    return os.path.join(BASE_DIR, filename)

def clean_column_names(df):
    # Fixed to explicitly remove BOM characters like ï»¿ or \ufeff
    df.columns = [str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') for c in df.columns]
    return df

# --- 3. AGE CALCULATION LOGIC ---
def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row['Date'], dayfirst=True, errors='coerce')
        if pd.notnull(row.get('Completion date')) and str(row['Completion date']).strip() != "":
            end_date = pd.to_datetime(row['Completion date'], dayfirst=True, errors='coerce')
        else:
            end_date = pd.to_datetime(datetime.now().date())
        if pd.isnull(start_date) or pd.isnull(end_date):
            return "N/A", 0
        days = (end_date - start_date).days
        cat = "< 6 Weeks" if days < 42 else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        return cat, days
    except:
        return "Error", 0

# --- 4. DATA LOADERS ---
def load_db():
    if not os.path.exists(FILENAME): return pd.DataFrame()
    try:
        # Use utf-8-sig to handle potential BOMs in the main database
        df = pd.read_csv(FILENAME, sep=';', encoding='utf-8-sig', quoting=3, on_bad_lines='warn')
        df = clean_column_names(df)
        df = df.map(lambda x: str(x).strip().replace('"', '') if isinstance(x, str) else x)
        
        if 'Pre-Prod No.' in df.columns:
            df['Pre-Prod No.'] = pd.to_numeric(df['Pre-Prod No.'], errors='coerce')
            df = df.dropna(subset=['Pre-Prod No.'])

        for art_file in [ARTWORK_FILE, DIGITAL_ARTWORK_FILE]:
            if os.path.exists(art_file):
                try:
                    art_df = pd.read_csv(art_file, sep=';', encoding='utf-8-sig', on_bad_lines='skip')
                    art_df = clean_column_names(art_df)
                    if 'Pre-Prod No.' in art_df.columns:
                        art_df['Pre-Prod No.'] = pd.to_numeric(art_df['Pre-Prod No.'], errors='coerce')
                        df.set_index('Pre-Prod No.', inplace=True)
                        art_df.set_index('Pre-Prod No.', inplace=True)
                        df = art_df.combine_first(df).reset_index()
                except: pass

        if 'Date' in df.columns:
            results = df.apply(calculate_age_category, axis=1)
            df['Age Category'] = [r[0] for r in results]
            df['Project Age (Open and Closed)'] = [r[1] for r in results]
        
        return df
    except Exception as e:
        st.error(f"Error reading {FILENAME}: {e}")
        return pd.DataFrame()

def save_db(df):
    df.to_csv(FILENAME, index=False, sep=';', encoding='utf-8-sig')

def get_options(filename):
    path = get_local_path(filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='latin1', errors='ignore') as f:
                lines = [line.strip().replace('"', '') for line in f.readlines() if line.strip()]
                return sorted(list(set([l.split(';')[0].split(',')[0].strip() for l in lines if l])))
        except: return []
    return []

# --- 5. DROPDOWNS ---
DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid style.csv", "Machine": "Machine.csv", "Sales Rep": "Sales Rep.csv",
    "Cap_Lid Material": "CapMaterial.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}

df = load_db()
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}

def get_combined_options(col_name, csv_list):
    db_vals = df[col_name].dropna().unique().tolist() if not df.empty and col_name in df.columns else []
    return sorted(list(set(db_vals + csv_list)))

DYNAMIC_CLIENTS = sorted(df['Client'].dropna().unique().tolist()) if not df.empty and 'Client' in df.columns else []
DYNAMIC_MACHINES = get_combined_options('Machine', DROPDOWN_DATA.get('Machine', []))
DYNAMIC_SALES = get_combined_options('Sales Rep', DROPDOWN_DATA.get('Sales Rep', []))

# --- 6. FIELD LAYOUT ORDER ---
DESIRED_ORDER = [
    "Date", "Age Category", "Client", "Description", "Diameter", "Project Description", "New Mould_Client or Product", 
    "Product Code", "Machine", "Sales Rep", "Category", "Status", "Open or closed", 
    "Completion date", "Material", "Product Material Colour (tube,jar etc.)", 
    "Artwork Required", "Artwork Received", "Order Qty x1000", "Unit Order No", 
    "Length", "Cap_Lid Style", "Cap_Lid Material", "Orifice", "Other Cap_Lid Info", 
    "Tube Shoulder colour", "Dust Controlled Area", "Date Sent on Proof", "Size of Eyemark", 
    "Proof Approved (Conventional)", "Proof Approved (Digital)", "Ordered Plates", 
    "Plates Arrived", "Sent on Trial", "Digital trial received", 
    "Revised Artwork After Trialling", "Masterbatch received", "Extrusion requested", 
    "Extrusion received", "Injection trial requested", "Injection Trial Received", 
    "Blowmould trial requested", "Blowmould trial received", "Comments"
]

# --- 7. SIDEBAR ---
with st.sidebar:
    st.header("📁 System Check")
    for f, label in [(FILENAME, "Main DB"), (ARTWORK_FILE, "Artwork"), (DIGITAL_ARTWORK_FILE, "Digital"), (COMBINATIONS_FILE, "Combinations")]:
        if os.path.exists(f): st.success(f"✅ {label} Found")
        else: st.warning(f"⚠️ {label} Missing")

if df.empty: 
    st.error("Database could not be loaded.")
    st.stop()

# --- 8. PROJECT SUMMARY & CHARTS ---
st.title("🚀 Project Tracker")

client_list_summary = ["All Clients"] + DYNAMIC_CLIENTS
selected_summary_client = st.selectbox("📊 Filter Summary by Client", options=client_list_summary)

summary_df = df.copy()
if selected_summary_client != "All Clients":
    summary_df = summary_df[summary_df['Client'].astype(str) == selected_summary_client]

def get_final_counts(target_df):
    status_col = 'Open or closed' if 'Open or closed' in target_df.columns else 'Status' if 'Status' in target_df.columns else None
    if status_col:
        s_series = target_df[status_col].astype(str).str.strip().str.lower()
        closed_mask = s_series.str.contains('closed', na=False)
        closed = closed_mask.sum()
        non_empty_mask = ~s_series.isin(['nan', 'none', '', ' '])
        open_projects = (non_empty_mask & ~closed_mask).sum()
        return open_projects, closed
    return 0, 0

open_projects, closed_projects = get_final_counts(summary_df)

col_metric1, col_metric2, col_metric3 = st.columns(3)
col_metric1.metric("Open Projects", open_projects)
col_metric2.metric("Closed Projects", closed_projects)
col_metric3.metric("Total Filtered Entries", len(summary_df))

if 'Age Category' in summary_df.columns:
    st.write(f"### 📈 Age Breakdown: {selected_summary_client}")
    age_counts = summary_df['Age Category'].value_counts().reindex(["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"], fill_value=0)
    st.bar_chart(age_counts)

st.divider()

tab1, tab2 = st.tabs(["➕ Add New Job", "🔍 Search & Edit Existing"])

# --- TAB 1: ADD NEW JOB ---
with tab1:
    st.header("Register New Project")
    
    # Persistent storage for selection
    if 'selected_combo' not in st.session_state:
        st.session_state.selected_combo = {}

    # --- TUBE AND CAP COMBINATION LOOKUP ---
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("🔍 Tube & Cap Combination Lookup"):
            try:
                # Use utf-8-sig to automatically strip BOM
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig')
                combo_df = clean_column_names(combo_df)
                
                # Validation: check for the specific columns requested
                required_cols = ["Diameter", "Cap_Lid Diameter", "Cap_Lid Style", "Cap_Lid Material"]
                missing = [c for c in required_cols if c not in combo_df.columns]
                if missing:
                    st.error(f"Validation Error: Columns {missing} not found in {COMBINATIONS_FILE}")
                    st.info(f"Available columns: {list(combo_df.columns)}")
                
                search_combo = st.text_input("Search Combinations (e.g. 35mm, Flip Top)")
                if search_combo:
                    combo_df = combo_df[combo_df.apply(lambda row: row.astype(str).str.contains(search_combo, case=False).any(), axis=1)]
                
                event = st.dataframe(
                    combo_df, 
                    use_container_width=True, 
                    hide_index=True, 
                    on_select="rerun", 
                    selection_mode="single-row"
                )
                
                if len(event.selection.rows) > 0:
                    selected_row_idx = event.selection.rows[0]
                    st.session_state.selected_combo = combo_df.iloc[selected_row_idx].to_dict()
                    st.success(f"Selected: {st.session_state.selected_combo.get('Diameter', '')}mm - {st.session_state.selected_combo.get('Cap_Lid Style', '')}")
            except Exception as e:
                st.error(f"Error loading combinations: {e}")

    next_no = int(df['Pre-Prod No.'].max() + 1) if not df.empty else 1
    st.info(f"🆕 **Next Project Number: {next_no}**")
    
    with st.form("new_job_form", clear_on_submit=True):
        new_data = {'Pre-Prod No.': next_no}
        cols = st.columns(3)
        
        # Fields to auto-fill
        auto_fill_fields = ["Diameter", "Cap_Lid Diameter", "Cap_Lid Style", "Cap_Lid Material"]

        for i, col_name in enumerate(DESIRED_ORDER):
            if col_name == "Age Category": continue
            
            # Fetch from session state if available
            default_val = str(st.session_state.selected_combo.get(col_name, "")).strip()
            
            with cols[i % 3]:
                if col_name == 'Date':
                    new_data[col_name] = st.date_input(col_name, value=datetime.now()).strftime('%d/%m/%Y')
                
                elif col_name in ['Client', 'Machine', 'Sales Rep']:
                    opts_map = {'Client': DYNAMIC_CLIENTS, 'Machine': DYNAMIC_MACHINES, 'Sales Rep': DYNAMIC_SALES}
                    current_opts = ["", "Add New " + col_name + "..."] + opts_map[col_name]
                    sel = st.selectbox(col_name, options=current_opts, key=f"new_{col_name}_sel")
                    if sel == "Add New " + col_name + "...":
                        new_data[col_name] = st.text_input(f"Enter New {col_name}", key=f"new_{col_name}_manual")
                    else:
                        new_data[col_name] = sel
                
                elif col_name == 'Status':
                    new_data[col_name] = "Open"
                    st.text_input(col_name, value="Open", disabled=True)
                elif col_name == 'Open or closed':
                    new_data[col_name] = st.text_input(col_name, value="Open")
                elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                    opts = [""] + DROPDOWN_DATA[col_name]
                    idx = 0
                    if default_val and default_val in opts:
                        idx = opts.index(default_val)
                    # Unique key ensures refresh when selection changes
                    new_data[col_name] = st.selectbox(col_name, options=opts, index=idx, key=f"new_dd_{col_name}")
                else:
                    if col_name == "Order Qty x1000":
                        new_data[col_name] = st.number_input(col_name, min_value=0, step=1, key="new_qty_num")
                    elif col_name == "Product Code":
                        p_code = st.text_input(col_name, key="new_pcode_entry")
                        new_data[col_name] = p_code.upper().strip()
                    else:
                        new_data[col_name] = st.text_input(col_name, value=default_val, key=f"new_txt_{col_name}")
        
        if st.form_submit_button("✅ Save New Project"):
            new_row = pd.DataFrame([new_data])
            cat, days = calculate_age_category(new_data)
            new_row['Age Category'] = cat
            new_row['Project Age (Open and Closed)'] = days
            
            df = pd.concat([df, new_row], ignore_index=True)
            save_db(df)
            st.session_state.selected_combo = {} # Clear selection
            st.success(f"Project #{next_no} saved!")
            st.rerun()

# --- TAB 2: SEARCH & EDIT ---
# (Rest of code remains unchanged as requested)
with tab2:
    st.header("Search & Edit Project")
    search_no = st.number_input("Enter Pre-Prod No.", min_value=1, step=1, key="search_input")
    
    match = df[df['Pre-Prod No.'] == search_no]
    if not match.empty:
        idx, row = match.index[0], match.iloc[0]
        st.metric("Project Age", f"{row.get('Project Age (Open and Closed)', 0)} Days")

        with st.expander("Update Project Details", expanded=True):
            updated_vals = {}
            edit_cols = st.columns(3)
            
            oc_val = st.text_input("Edit Open or closed", value=str(row.get("Open or closed", "")), key="oc_listener")
            is_closed = oc_val.strip().lower() == "closed"
            auto_status = "Closed" if is_closed else "Open"
            auto_comp_date = datetime.now().strftime('%d/%m/%Y') if is_closed and not str(row.get("Completion date", "")).strip() else str(row.get("Completion date", ""))

            for i, col_name in enumerate(DESIRED_ORDER):
                if col_name == "Open or closed":
                    updated_vals[col_name] = oc_val
                    continue
                
                with edit_cols[i % 3]:
                    if col_name == "Status":
                        updated_vals[col_name] = auto_status
                        st.text_input(f"Edit {col_name}", value=auto_status, disabled=True)
                    
                    elif col_name in ['Client', 'Machine', 'Sales Rep']:
                        current_val = str(row.get(col_name, ""))
                        opts_map = {'Client': DYNAMIC_CLIENTS, 'Machine': DYNAMIC_MACHINES, 'Sales Rep': DYNAMIC_SALES}
                        edit_opts = ["", "Add New " + col_name + "..."] + sorted(list(set(opts_map[col_name] + [current_val])))
                        
                        sel_edit = st.selectbox(f"Edit {col_name}", options=edit_opts, 
                                               index=edit_opts.index(current_val) if current_val in edit_opts else 0,
                                               key=f"edit_{col_name}_sel")
                        if sel_edit == "Add New " + col_name + "...":
                            updated_vals[col_name] = st.text_input(f"Enter New {col_name}", key=f"edit_{col_name}_manual")
                        else:
                            updated_vals[col_name] = sel_edit

                    elif col_name == "Completion date":
                        updated_vals[col_name] = st.text_input(f"Edit {col_name}", value=auto_comp_date)
                    elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                        val = str(row.get(col_name, ""))
                        opts = [""] + sorted(list(set(DROPDOWN_DATA[col_name] + ([val] if val else []))))
                        updated_vals[col_name] = st.selectbox(f"Edit {col_name}", options=opts, index=opts.index(val) if val in opts else 0)
                    else:
                        val = str(row.get(col_name, ""))
                        if col_name == "Order Qty x1000":
                            try:
                                current_qty = int(float(val)) if val and val != "nan" else 0
                            except:
                                current_qty = 0
                            updated_vals[col_name] = st.number_input(f"Edit {col_name}", min_value=0, step=1, value=current_qty, key=f"edit_qty_{i}")
                        elif col_name == "Product Code":
                            e_pcode = st.text_input(f"Edit {col_name}", value=val)
                            updated_vals[col_name] = e_pcode.upper().strip()
                        else:
                            updated_vals[col_name] = st.text_input(f"Edit {col_name}", value=val)
            
            col_save, col_delete = st.columns([1, 1])
            with col_save:
                if st.button("💾 Save Changes"):
                    for col, v in updated_vals.items(): 
                        df.at[idx, col] = v
                    cat, days = calculate_age_category(df.loc[idx])
                    df.at[idx, 'Age Category'] = cat
                    df.at[idx, 'Project Age (Open and Closed)'] = days
                    save_db(df)
                    st.success("Project Updated!")
                    st.rerun()
            
            with col_delete:
                confirm = st.checkbox(f"Confirm Delete Project #{search_no}")
                if confirm:
                    if st.button("🗑️ Delete Entry", type="primary"):
                        df = df.drop(index=idx)
                        save_db(df)
                        st.warning(f"Project #{search_no} deleted.")
                        st.rerun()

st.divider()

if "table_filter" not in st.session_state: st.session_state.table_filter = ""
if "sort_latest" not in st.session_state: st.session_state.sort_latest = False

def reset_view():
    st.session_state.table_filter = ""
    st.session_state.sort_latest = False

if st.checkbox("Show Project Data Table", value=True):
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    search_query = c1.text_input("🔍 Global Table Search", key="table_filter_input").lower()
    c2.button("🔄 Reset View", on_click=reset_view)
    if c3.button("🆕 View Latest"): st.session_state.sort_latest = True

    display_df = df.copy()
    if st.session_state.get("sort_latest", False):
        display_df = display_df.sort_values(by='Pre-Prod No.', ascending=False)
    
    if selected_summary_client != "All Clients":
        display_df = display_df[display_df['Client'].astype(str) == selected_summary_client]
        
    if search_query:
        mask = display_df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
        display_df = display_df[mask]

    try:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            display_df.to_excel(writer, index=False, sheet_name='Sheet1')
        c4.download_button(
            label="📥 Export to Excel",
            data=buffer.getvalue(),
            file_name=f"Project_Export_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except:
        c4.warning("Excel Engine Not Found")

    st.dataframe(display_df, use_container_width=True)