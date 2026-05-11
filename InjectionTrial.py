import streamlit as st
import pandas as pd
from datetime import datetime
import os
import time
from fpdf import FPDF
import io
import gspread
from google.oauth2.service_account import Credentials

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

# --- CONFIGURATION ---
MASTER_TRACKER_ID = "1LA9F5mD67vR9yYKqQ39CS-tAZ9QgCgn5KBWaY_RfFKM"
TRIAL_TIMELINE_ID = "1UtoZnl8vLKmP47UhxdPDzCZABhccWcyEnC-YV5mTW-Y"

# --- DIRECTORY SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
SUBMISSIONS_FILE = os.path.join(BASE_DIR, "Trial_Submissions.parquet")

# --- 1. GOOGLE SHEETS AUTH (Fixed for KeyError) ---
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Try both common secret structures to prevent KeyError
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        creds_info = st.secrets["connections"]["gsheets"]
    elif "gcp_service_account" in st.secrets:
        creds_info = st.secrets["gcp_service_account"]
    else:
        st.error("Secrets not found! Check your .streamlit/secrets.toml or Streamlit Cloud settings.")
        st.stop()

    if isinstance(creds_info, dict) and "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))

# --- 2. DATA HELPERS ---
def get_project_data(pre_prod_no):
    if not os.path.exists(FILENAME_PARQUET):
        return None
    try:
        df = pd.read_parquet(FILENAME_PARQUET)
        search_id = str(pre_prod_no).strip().split('.')[0]
        df['Pre-Prod No.'] = df['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        result = df[df['Pre-Prod No.'] == search_id]
        return result.iloc[0].to_dict() if not result.empty else None
    except:
        return None

def get_next_trial_reference(pre_prod_no):
    if not os.path.exists(SUBMISSIONS_FILE):
        return f"{pre_prod_no}_T1"
    df = pd.read_parquet(SUBMISSIONS_FILE)
    count = len(df[df['Pre-Prod No.'] == str(pre_prod_no)])
    return f"{pre_prod_no}_T{count + 1}"

def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, txt=f"Trial Report: {data.get('Trial Reference', 'N/A')}", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", size=9)
    for key, value in data.items():
        pdf.set_font("Arial", "B", 9)
        pdf.cell(55, 7, txt=f"{key}:", border=0)
        pdf.set_font("Arial", size=9)
        pdf.cell(0, 7, txt=f"{str(value)}", border=0, ln=True)
    return pdf.output(dest='S').encode('latin-1')

def update_tracker_status(pre_prod_no, current_trial_ref, manual_date=None):
    """Helper to update the Master Project Tracker sheet"""
    try:
        client = get_gspread_client()
        # Use the Master Tracker ID from your config
        tracker_spreadsheet = client.open_by_key(MASTER_TRACKER_ID)
        tracker_worksheet = tracker_spreadsheet.get_worksheet(0) 

        search_id = str(pre_prod_no).strip().split('.')[0]
        cell = tracker_worksheet.find(search_id, in_column=1)
        
        if not cell:
            return False, f"ID {search_id} not found."
            
        # Construct the display string: "T1 - 10/04/2026" or "None -  "
        trial_suffix = current_trial_ref.split('_')[-1] if '_' in current_trial_ref else current_trial_ref
        date_str = manual_date if manual_date else datetime.now().strftime('%d/%m/%Y')
        combined_value = f"{trial_suffix} - {date_str}"

        headers = [h.strip() for h in tracker_worksheet.row_values(1)]
        col_name = "Injection trial requested"
        
        if col_name in headers:
            col_idx = headers.index(col_name) + 1
            tracker_worksheet.update_cell(cell.row, col_idx, combined_value)
            return True, combined_value
        return False, "Column not found."
    except Exception as e:
        return False, str(e)

def sync_last_trial_to_cloud(pre_prod_no):
    if not os.path.exists(SUBMISSIONS_FILE):
        return False, "No history file found."
    
    try:
        df_history = pd.read_parquet(SUBMISSIONS_FILE)
        df_history['Pre-Prod No.'] = df_history['Pre-Prod No.'].astype(str)
        project_history = df_history[df_history['Pre-Prod No.'] == str(pre_prod_no)].copy()
        
        if project_history.empty:
            return update_tracker_status(pre_prod_no, "None", manual_date=" ") 

        # Corrected column name to match your trial data structure
        project_history['Trial_Num'] = project_history['Trial Reference'].str.extract(r'(\d+)$').astype(int)
        latest_trial = project_history.sort_values(by=['Trial_Num'], ascending=False).iloc[0]
        
        return update_tracker_status(
            pre_prod_no, 
            latest_trial['Trial Reference'], 
            manual_date=datetime.strptime(latest_trial['Date'], '%Y-%m-%d').strftime('%d/%m/%Y')
        )
    except Exception as e:
        return False, f"Sync Error: {str(e)}"

# --- 3. SIDEBAR (With Admin Controls & Navigation) ---
with st.sidebar:
    st.header("Navigation")
    # Link to the Project Tracker App
    st.page_link(
        "https://projecttracker-kc2ksaezfqxarnv96ugzdk.streamlit.app/", 
        label="📋 Go to Project Tracker", 
        icon="🚀"
    )
    
    st.divider()
    
    st.header("Admin Controls")
    if st.button("♻️ Refresh Cache"):
        st.cache_data.clear()
        st.success("Cache Cleared")
    
    st.divider()
    st.subheader("Manage Trials")
    
    if os.path.exists(SUBMISSIONS_FILE):
        hist_df = pd.read_parquet(SUBMISSIONS_FILE)
        
        if not hist_df.empty:
            # Create labels for the dropdown
            trial_labels = hist_df.apply(lambda x: f"{x['Trial Reference']} ({x['Date']})", axis=1).tolist()
            selected_label = st.selectbox("Select Trial to Remove", options=trial_labels)
            selected_ref = str(selected_label).split(" (")[0]
            
            if st.button("🗑️ Delete from Local & Cloud", type="primary"):
                with st.spinner(f"Removing {selected_ref}..."):
                    try:
                        # 1. DELETE FROM GOOGLE SHEETS (Trial Timeline)
                        client_gs = get_gspread_client()
                        t_sheet = client_gs.open_by_key(TRIAL_TIMELINE_ID).get_worksheet(0)
                        
                        # Find the cell containing the unique Trial Reference
                        cell = t_sheet.find(selected_ref)
                        
                        if cell:
                            t_sheet.delete_rows(cell.row)
                            st.toast(f"Cloud row {cell.row} removed.")
                        else:
                            st.warning("Trial Reference not found in Google Sheets.")

                        # 2. DELETE FROM LOCAL PARQUET
                        updated_df = hist_df[hist_df['Trial Reference'] != selected_ref]
                        updated_df.to_parquet(SUBMISSIONS_FILE, index=False)
                        
                        # 3. TRIGGER MASTER SYNC
                        pre_id = selected_ref.split('_')[0]
                        success, msg = sync_last_trial_to_cloud(pre_id)
                        
                        if success:
                            st.success(f"Deleted {selected_ref}. Master updated: {msg}")
                        else:
                            st.warning(f"Deleted locally, but Master Sync failed: {msg}")

                        time.sleep(1)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error during deletion: {e}")
        else:
            st.info("Local database is empty.")
    else:
        st.info("No submissions found.")
# --- 4. MAIN INTERFACE ---
st.title("Injection Trial Data Entry")
search_input = st.text_input("Enter Pre-Prod No. (e.g. 11925):")

if search_input:
    ld = get_project_data(search_input)
    if not ld:
        st.error("Project ID not found in local database.")
    else:
        current_trial_ref = get_next_trial_reference(search_input)

        # --- SUCCESS AREA ---
        if st.session_state.get('submitted', False):
            st.success(f"Success! {current_trial_ref} has been recorded.")
            if 'last_submission' in st.session_state:
                pdf_bytes = create_pdf(st.session_state.last_submission)
                st.download_button("📥 Download PDF", pdf_bytes, f"Report_{current_trial_ref}.pdf")
            if st.button("Start Next Entry"):
                st.session_state.submitted = False
                st.rerun()
            st.divider()

        # --- THE 39-COLUMN FORM ---
        with st.form("trial_entry_form", clear_on_submit=True):
            st.subheader(f"Current Phase: {current_trial_ref}")
            
            # Row 1: Basic Admin
            c1, c2, c3, c4 = st.columns(4)
            t_date = c1.date_input("Trial Date", datetime.now())
            s_rep = c2.text_input("Sales Rep", value=ld.get('Sales Rep', ''))
            client = c3.text_input("Client", value=ld.get('Client', ''))
            operator = c4.text_input("Operator Name")

            # Row 2: Machine/Targets
            c1, c2, c3, c4 = st.columns(4)
            target = c1.text_input("Target To", value=ld.get('Target to', ''))
            qty = c2.number_input("Trial Qty", step=1)
            m_prod = c3.text_input("Prod Machine", value=ld.get('Machine', ''))
            m_trial = c4.text_input("Trial Machine")

            # Row 3: Product Details
            st.markdown("### Product Specifications")
            c1, c2, c3, c4 = st.columns(4)
            desc = c1.text_input("Description", value=ld.get('Project Description', ''))
            p_code = c2.text_input("Product Code", value=ld.get('Product Code', ''))
            mat = c3.text_input("Material", value=ld.get('Material', ''))
            supp = c4.text_input("Supplier", value=ld.get('Supplier', ''))

            c1, c2, c3, c4 = st.columns(4)
            length = c1.text_input("Length", value=str(ld.get('Length', '')))
            orf = c2.text_input("Orifice", value=str(ld.get('Orifice', '')))
            diam = c3.text_input("Diameter", value=str(ld.get('Diameter', '')))
            mix = c4.text_input("Mix %", value=str(ld.get('Mix_%', '')))

            # Row 4: Caps & Colors
            c1, c2, c3, c4 = st.columns(4)
            c_style = c1.text_input("Cap Style", value=ld.get('Cap_Lid Style', ''))
            c_mat = c2.text_input("Cap Material", value=ld.get('Cap_Lid Material', ''))
            pigment = c3.text_input("Pigment Grade", value=ld.get('Pigment_MB Grade', ''))
            pre_mix = c4.text_input("Pre-Mix %")

            # Row 5: Radios
            c1, c2, c3 = st.columns(3)
            tinuvin = c1.radio("Tinuvin?", ["Yes", "No"], horizontal=True)
            d_fit = c2.radio("Dosing Unit Fitted?", ["Yes", "No"], horizontal=True)
            d_cal = c3.radio("Dosing Calibrated?", ["Yes", "No"], horizontal=True)

            # Row 6: Dosing Settings
            st.markdown("### Dosing & Machine Settings")
            c1, c2, c3, c4, c5 = st.columns(5)
            c_set = c1.text_input("Colour Set")
            c_act = c2.text_input("Colour Act")
            c_per = c3.text_input("Colour %")
            s_weight = c4.text_input("Shot Weight")
            d_time = c5.text_input("Dosing Time")

            # Row 7: Pressures & Speeds
            c1, c2, c3, c4 = st.columns(4)
            inj_p = c1.number_input("Inj Pressure (bar)", step=1)
            hold_p = c2.number_input("Hold Pressure (bar)", step=1)
            inj_s = c3.number_input("Inj Speed (mm/s)", step=1)
            back_p = c4.number_input("Back Pressure (bar)", step=1)

            # Row 8: Timings
            c1, c2, c3, c4 = st.columns(4)
            cyc_t = c1.number_input("Cycle Time (s)", format="%.2f")
            cool_t = c2.number_input("Cooling Time (s)", format="%.2f")
            d_stroke = c3.number_input("Dosage Stroke (mm)", step=1)
            decomp = c4.number_input("Decompression (mm)", step=1)

            obs = st.text_area("Observations")

            # --- SUBMISSION LOGIC ---
            if st.form_submit_button("Submit Trial Entry"):
                # Construct 39-column data mapping
                full_row = {
                    "Trial Reference": current_trial_ref,
                    "Pre-Prod No.": search_input,
                    "Date": t_date.strftime("%Y-%m-%d"),
                    "Sales Rep": s_rep,
                    "Target to": target,
                    "Client": client,
                    "Trial Qty": qty,
                    "Operator": operator,
                    "Prod Machine": m_prod,
                    "Trial Machine": m_trial,
                    "Description": desc,
                    "Length": length,
                    "Orifice": orf,
                    "Supplier": supp,
                    "Cap Style": c_style,
                    "Cap Material": c_mat,
                    "Diameter": diam,
                    "Mix %": mix,
                    "Product Code": p_code,
                    "Material": mat,
                    "Pigment Grade": pigment,
                    "Pre-Mix %": pre_mix,
                    "Tinuvin": tinuvin,
                    "Dosing Fitted": d_fit,
                    "Dosing Calib": d_cal,
                    "Colour Set": c_set,
                    "Colour Act": c_act,
                    "Colour %": c_per,
                    "Shot Weight": s_weight,
                    "Dosing Time": d_time,
                    "Inj Pressure": inj_p,
                    "Hold Pressure": hold_p,
                    "Inj Speed": inj_s,
                    "Back Pressure": back_p,
                    "Cycle Time": cyc_t,
                    "Cooling Time": cool_t,
                    "Dosage Stroke": d_stroke,
                    "Decompression": decomp,
                    "Observations": obs
                }

                # Save Local Parquet
                df_new = pd.DataFrame([full_row]).astype(str)
                if os.path.exists(SUBMISSIONS_FILE):
                    df_hist = pd.read_parquet(SUBMISSIONS_FILE)
                    pd.concat([df_hist, df_new], ignore_index=True).to_parquet(SUBMISSIONS_FILE, index=False)
                else:
                    df_new.to_parquet(SUBMISSIONS_FILE, index=False)

                # Sync Cloud
                try:
                    client_gs = get_gspread_client()
                    # 1. Update Tracker
                    m_sheet = client_gs.open_by_key(MASTER_TRACKER_ID).get_worksheet(0)
                    m_cell = m_sheet.find(search_input, in_column=1)
                    if m_cell:
                        headers = [h.strip() for h in m_sheet.row_values(1)]
                        if "Injection trial requested" in headers:
                            idx = headers.index("Injection trial requested") + 1
                            val = f"{current_trial_ref.split('_')[-1]} - {datetime.now().strftime('%d/%m/%Y')}"
                            m_sheet.update_cell(m_cell.row, idx, val)
                    
                    # 2. Append Timeline
                    t_sheet = client_gs.open_by_key(TRIAL_TIMELINE_ID).get_worksheet(0)
                    t_sheet.append_row(list(full_row.values()))
                    
                    st.session_state.last_submission = full_row
                    st.session_state.submitted = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Cloud Sync failed: {e}")