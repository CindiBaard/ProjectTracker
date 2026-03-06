import os
import pandas as pd
import streamlit as st
from datetime import datetime
import io

# --- 1. INITIAL SETUP & DEPENDENCIES ---
try:
    import xlsxwriter
except ImportError:
    st.error("Missing dependency: Please run 'pip install xlsxwriter' in your terminal to enable Excel exports.")

st.set_page_config(page_title="Project Tracker", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# --- 2. FILE PATHS ---
BASE_DIR = os.getcwd() 
FILENAME = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv")
ARTWORK_FILE = os.path.join(BASE_DIR, "Artwork Status.csv")
DIGITAL_ARTWORK_FILE = os.path.join(BASE_DIR, "Digital Artwork Status.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")

# --- 3. HELPER FUNCTIONS ---
def clean_column_names(df):
    """Strips BOM characters and hidden whitespace from headers."""
    df.columns = [
        str(c).strip().replace('\ufeff', '').replace('ï»¿', '').replace('"', '').replace('/', '_') 
        for c in df.columns
    ]
    return df

def calculate_age_category(row):
    """Calculates project age and categorizes it."""
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

def load_db():
    if not os.path.exists(FILENAME): return pd.DataFrame()
    try:
        df = pd.read_csv(FILENAME, sep=';', encoding='utf-8-sig', quoting=3, on_bad_lines='warn')
        df = clean_column_names(df)
        df = df.map(lambda x: str(x).strip().replace('"', '') if isinstance(x, str) else x)
        
        if 'Pre-Prod No.' in df.columns:
            df['Pre-Prod No.'] = pd.to_numeric(df['Pre-Prod No.'], errors='coerce')
            df = df.dropna(subset=['Pre-Prod No.'])

        if 'Date' in df.columns:
            results = df.apply(calculate_age_category, axis=1)
            df['Age Category'] = [r[0] for r in results]
            df['Project Age (Open and Closed)'] = [r[1] for r in results]
        return df
    except Exception as e:
        st.error(f"Error loading main database: {e}")
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

DROPDOWN_CONFIG = {
    "Category": "Category.csv", "Length": "Length.csv", "Material": "Material.csv",
    "Orifice": "Orifice.csv", "Diameter": "TubeDia.csv", "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv", "Machine": "Machine.csv", "Sales Rep": "Sales Rep.csv",
    "Cap_Lid Material": "Cap_Material.csv", "Cap_Lid Diameter": "Cap_Lid Diameter.csv"
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
DYNAMIC_CLIENTS = sorted(df['Client'].dropna().unique().tolist()) if not df.empty and 'Client' in df.columns else []
DYNAMIC_SALES = sorted(list(set(df['Sales Rep'].dropna().unique().tolist() + DROPDOWN_DATA.get('Sales Rep', [])))) if not df.empty else []

DESIRED_ORDER = [
    "Date", "Age Category", "Client", "Description", "Diameter", "Project Description", "New Mould_Client or Product", 
    "Product Code", "Machine", "Sales Rep", "Category", "Status", "Open or closed", 
    "Completion date", "Material", "Product Material Colour (tube,jar etc.)", 
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

tab1, tab2 = st.tabs(["➕ Add New Job", "🔍 Search & Edit"])

# --- TAB 1: ADD NEW JOB ---
with tab1:
    if 'selected_combo' not in st.session_state:
        st.session_state.selected_combo = {}

    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("🔍 Tube & Cap Combination Lookup", expanded=True):
            try:
                combo_df = pd.read_csv(COMBINATIONS_FILE, sep=';', encoding='utf-8-sig')
                combo_df = clean_column_names(combo_df)
                search = st.text_input("Filter Combinations (e.g. 35mm Flip Top)")
                if search:
                    mask = combo_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
                    combo_df = combo_df[mask]
                event = st.dataframe(combo_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="combo_table")
                if event.selection.rows:
                    selected_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    st.session_state.selected_combo = {k: (str(v) if str(v).lower() != 'nan' else "") for k, v in selected_row.items()}
            except: pass

    next_no = int(df['Pre-Prod No.'].max() + 1) if not df.empty else 1
    
    with st.form("new_job_form"):
        st.subheader(f"Project Registration: #{next_no}")
        new_data = {'Pre-Prod No.': next_no}
        cols = st.columns(3)
        
        for i, col_name in enumerate(DESIRED_ORDER):
            if col_name == "Age Category": continue
            val = st.session_state.selected_combo.get(col_name, "")
            with cols[i % 3]:
                if col_name == 'Date':
                    new_data[col_name] = st.date_input(col_name, value=datetime.now()).strftime('%d/%m/%Y')
                elif col_name == 'Completion date':
                    res_date = st.date_input(col_name, value=None)
                    new_data[col_name] = res_date.strftime('%d/%m/%Y') if res_date else ""
                elif col_name in ['Status', 'Open or closed']:
                    status_val = "Open" if not new_data.get('Completion date') else "Closed"
                    st.text_input(col_name, value=status_val, disabled=True, key=f"new_{col_name}")
                    new_data[col_name] = status_val
                elif col_name in ['Client', 'Sales Rep']:
                    opts = ["", "Add New..."] + (DYNAMIC_CLIENTS if col_name == 'Client' else DYNAMIC_SALES)
                    sel = st.selectbox(col_name, options=opts)
                    new_data[col_name] = st.text_input(f"New {col_name}") if sel == "Add New..." else sel
                elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                    opts = [""] + DROPDOWN_DATA[col_name]
                    new_data[col_name] = st.selectbox(col_name, options=opts, index=opts.index(val) if val in opts else 0)
                elif col_name == "Product Code":
                    new_data[col_name] = st.text_input(col_name, value=val).upper()
                else:
                    new_data[col_name] = st.text_input(col_name, value=val)

        if st.form_submit_button("✅ Save Project"):
            if not new_data.get("Client") or not new_data.get("Description"):
                st.error("Client and Description are required.")
            else:
                final_status = "Closed" if new_data.get('Completion date') else "Open"
                new_data['Status'] = final_status
                new_data['Open or closed'] = final_status
                new_row = pd.DataFrame([new_data])
                cat, days = calculate_age_category(new_data)
                new_row['Age Category'], new_row['Project Age (Open and Closed)'] = cat, days
                df = pd.concat([df, new_row], ignore_index=True)
                save_db(df)
                st.session_state.selected_combo = {}
                st.success("Project Saved!")
                st.rerun()

# --- TAB 2: SEARCH & EDIT ---
with tab2:
    search_no = st.number_input("Enter Pre-Prod No.", min_value=1, step=1)
    match = df[df['Pre-Prod No.'] == search_no]
    
    if not match.empty:
        idx, row = match.index[0], match.iloc[0]

        st.subheader(f"📊 Age Analysis for Pre-Prod #{search_no}")
        age_days = row.get('Project Age (Open and Closed)', 0)
        age_cat = row.get('Age Category', "N/A")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Current Project Age", f"{age_days} Days")
        m2.metric("Age Category", age_cat)
        m3.metric("Project Status", row.get('Open or closed', 'Open'))

        with st.expander(f"Editing Project #{search_no}", expanded=True):
            updated_vals = {}
            edit_cols = st.columns(3)
            comp_date_str = ""
            
            for i, col_name in enumerate(DESIRED_ORDER):
                if col_name == "Age Category": continue 
                
                cur_val = str(row.get(col_name, ""))
                if cur_val.lower() == 'nan': cur_val = ""
                
                with edit_cols[i % 3]:
                    if col_name == 'Completion date':
                        try:
                            default_date = pd.to_datetime(cur_val, dayfirst=True).date() if cur_val else None
                        except:
                            default_date = None
                        selected_date = st.date_input(f"Edit {col_name}", value=default_date)
                        comp_date_str = selected_date.strftime('%d/%m/%Y') if selected_date else ""
                        updated_vals[col_name] = comp_date_str
                    
                    elif col_name in ["Status", "Open or closed"]:
                        updated_vals[col_name] = cur_val 
                    
                    elif col_name in DROPDOWN_DATA and DROPDOWN_DATA[col_name]:
                        opts = [""] + sorted(list(set(DROPDOWN_DATA[col_name] + [cur_val])))
                        updated_vals[col_name] = st.selectbox(f"Edit {col_name}", options=opts, index=opts.index(cur_val) if cur_val in opts else 0)
                    
                    elif col_name == "Product Code":
                        updated_vals[col_name] = st.text_input(f"Edit {col_name}", value=cur_val).upper()
                    
                    else:
                        updated_vals[col_name] = st.text_input(f"Edit {col_name}", value=cur_val)

            determined_status = "Closed" if comp_date_str != "" else "Open"
            updated_vals["Status"] = determined_status
            updated_vals["Open or closed"] = determined_status
            
            st.info(f"Saving as: **{determined_status}**")

            col_save, col_del = st.columns([1, 1])
            with col_save:
                if st.button("💾 Save Changes", use_container_width=True):
                    for k, v in updated_vals.items(): 
                        df.at[idx, k] = v
                    cat, days = calculate_age_category(df.loc[idx])
                    df.at[idx, 'Age Category'], df.at[idx, 'Project Age (Open and Closed)'] = cat, days
                    save_db(df)
                    st.success("Changes Applied!")
                    st.rerun()

            # --- DELETE FUNCTIONALITY ---
            with col_del:
                st.markdown("---")
                st.warning("🗑️ Danger Zone")
                confirm_delete = st.checkbox(f"Confirm deletion of Project #{search_no}")
                if st.button("❌ Permanent Delete", disabled=not confirm_delete, use_container_width=True):
                    df = df.drop(idx)
                    save_db(df)
                    st.success(f"Project #{search_no} has been deleted.")
                    st.rerun()
    else:
        st.info("Enter a valid Pre-Prod number to see the analysis and edit.")

# --- 6. DATA TABLE & 7. CLIENT AGE ANALYSIS ---
st.divider()
if st.checkbox("Show Project Data Table", value=True):
    search_query = st.text_input("🔍 Global Search").lower()
    display_df = df.copy()
    if search_query:
        display_df = display_df[display_df.apply(lambda r: r.astype(str).str.contains(search_query, case=False).any(), axis=1)]
    st.dataframe(display_df, use_container_width=True)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        display_df.to_excel(writer, index=False)
    st.download_button("📥 Export Current View to Excel", data=buffer.getvalue(), file_name="Project_Export.xlsx")

st.header("📊 Client Age Analysis (Open Projects)")
if not df.empty:
    open_projects = df[df['Open or closed'].str.lower().str.contains('open', na=False)].copy()
    if not open_projects.empty:
        age_analysis = open_projects.groupby(['Client', 'Age Category']).size().unstack(fill_value=0)
        for cat in ["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"]:
            if cat not in age_analysis.columns: age_analysis[cat] = 0
        age_analysis = age_analysis[["< 6 Weeks", "6-12 Weeks", "> 12 Weeks"]]
        age_analysis['Total Open'] = age_analysis.sum(axis=1)
        st.dataframe(age_analysis.sort_values('Total Open', ascending=False), use_container_width=True)