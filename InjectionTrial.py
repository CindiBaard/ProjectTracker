import streamlit as st
import pandas as pd
from datetime import datetime
import os
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

# ---- CONFIGURATION
# The ID of your Project Tracker spreadsheet
TRACKER_FILE_ID = "1b7ksuTX2C7ns89AXc7Npki70KqjcXf1-oxIkZjTuq8M"

# --- DIRECTORY SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
SUBMISSIONS_FILE = os.path.join(BASE_DIR, "Trial_Submissions.parquet")

# --- HELPER FUNCTIONS ---

def get_project_data(pre_prod_no):
    """Searches the combined parquet file for the Pre-Prod number."""
    if not os.path.exists(FILENAME_PARQUET):
        st.error(f"Database file not found at: {FILENAME_PARQUET}")
        return None
    try:
        df_tracker = pd.read_parquet(FILENAME_PARQUET)
        col_name = "Pre-Prod No." 
        if col_name not in df_tracker.columns:
            st.error(f"Column '{col_name}' not found.")
            return None
        search_term = str(pre_prod_no).strip()
        df_tracker[col_name] = df_tracker[col_name].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        result = df_tracker[df_tracker[col_name] == search_term]
        return result.iloc[0].to_dict() if not result.empty else None
    except Exception as e:
        st.error(f"Error reading project database: {e}")
    return None

def get_next_trial_reference(pre_prod_no):
    """Calculates the next trial number by checking submission history."""
    if not os.path.exists(SUBMISSIONS_FILE):
        return f"{pre_prod_no}_T1"
    try:
        df_history = pd.read_parquet(SUBMISSIONS_FILE)
        existing_trials = df_history[df_history['Pre-Prod No.'] == str(pre_prod_no)]
        count = len(existing_trials)
        return f"{pre_prod_no}_T{count + 1}"
    except:
        return f"{pre_prod_no}_T1"

def delete_trial_entry(trial_ref):
    """Removes a specific trial reference from the submissions file."""
    if os.path.exists(SUBMISSIONS_FILE):
        try:
            df = pd.read_parquet(SUBMISSIONS_FILE)
            # Keep everything EXCEPT the trial reference we want to delete
            df_filtered = df[df['Trial Ref'] != trial_ref]
            df_filtered.to_parquet(SUBMISSIONS_FILE, index=False)
            return True
        except Exception as e:
            st.error(f"Error deleting entry: {e}")
            return False
    return False

def display_trial_history(pre_prod_no):
    if os.path.exists(SUBMISSIONS_FILE):
        df = pd.read_parquet(SUBMISSIONS_FILE)
        # Filter for the specific project
        history = df[df['Pre-Prod No.'] == str(pre_prod_no)].sort_values('Date', ascending=False)
        
        if not history.empty:
            st.info(f"Existing Trials Found: **{len(history)}**")
            
            # Create a clean display table
            display_df = history[['Trial Ref', 'Date', 'Operator', 'Observations']].copy()
            
            # Using columns to create a "Delete" interface
            for index, row in history.iterrows():
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.write(f"**{row['Trial Ref']}** | {row['Date']} | {row['Operator']}")
                    st.caption(f"Note: {row['Observations']}")
                with col2:
                    # Unique key required for each button in a loop
                    if st.button(f"Delete", key=f"del_{row['Trial Ref']}"):
                        if delete_trial_entry(row['Trial Ref']):
                            st.success(f"Deleted {row['Trial Ref']}")
                            time.sleep(1) # Brief pause so user sees success
                            st.rerun() # Refresh to update the list
                st.divider()
        else:
            st.write("No previous trial history found.")

def update_tracker_status(pre_prod_no, current_trial_ref, manual_date=None):
    """Updates the Project Tracker Google Sheet with 'T# - Date'"""
    import gspread
    from google.oauth2.service_account import Credentials

    # 1. Construct the value for the Google Sheet (e.g., T1 - 17/04/2026)
    trial_suffix = current_trial_ref.split('_')[-1] if '_' in current_trial_ref else current_trial_ref

    if manual_date:
        # If manual_date is coming from history (e.g. "2026-04-20"), 
        # you might need to format it to DD/MM/YYYY
        try:
            date_obj = datetime.strptime(manual_date, "%Y-%m-%d")
            date_str = date_obj.strftime('%d/%m/%Y')
        except:
            date_str = manual_date
        combined_value = f"{trial_suffix} - {date_str}"
    else:
        combined_value = f"{trial_suffix} - {datetime.now().strftime('%d/%m/%Y')}"

    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # Use your existing secrets logic
        creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
        if isinstance(creds_info, dict) and "private_key" in creds_info:
             creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        
        tracker_spreadsheet = client.open_by_key(TRACKER_FILE_ID)
        tracker_worksheet = tracker_spreadsheet.get_worksheet(0) 

        # Helper to match IDs
        def pad_id(input_val):
            if pd.isna(input_val) or str(input_val).strip() == '': 
                return ""
            return str(input_val).strip().split('.')[0]

        search_id = pad_id(pre_prod_no)
        cell = tracker_worksheet.find(search_id, in_column=1)
        row_idx = cell.row

        headers = [h.strip() for h in tracker_worksheet.row_values(1)]
        col_name = "Injection trial requested"
        
        if col_name in headers:
            col_idx = headers.index(col_name) + 1
            tracker_worksheet.update_cell(row_idx, col_idx, combined_value)
            return True, combined_value
        else:
            return False, f"Column '{col_name}' not found."

    except Exception as e:
        return False, str(e)

def sync_last_trial_to_cloud(pre_prod_no):
    """Finds the most recent trial in history and pushes it to Google Sheets."""
    if not os.path.exists(SUBMISSIONS_FILE):
        return False, "No history file found."
    
    try:
        df_history = pd.read_parquet(SUBMISSIONS_FILE)
        project_history = df_history[df_history['Pre-Prod No.'] == str(pre_prod_no)].copy()
        
        if project_history.empty:
            # If no trials left, you might want to clear the cell or set to "No Trials"
            return update_tracker_status(pre_prod_no, "None", manual_date="No Trials") 

        # Extract number to sort correctly (T10 comes after T2)
        project_history['Trial_Num'] = project_history['Trial Ref'].str.extract(r'(\d+)$').astype(int)
        latest_trial = project_history.sort_values(by=['Trial_Num'], ascending=False).iloc[0]
        
        return update_tracker_status(
            pre_prod_no, 
            latest_trial['Trial Ref'], 
            manual_date=latest_trial['Date']
        )
    except Exception as e:
        return False, str(e)  
    
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
        if isinstance(creds_info, dict) and "private_key" in creds_info:
             creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        
        tracker_spreadsheet = client.open_by_key(TRACKER_FILE_ID)
        tracker_worksheet = tracker_spreadsheet.get_worksheet(0) 
        
# FIX STARTS HERE
        def pad_id(input_val):
            if pd.isna(input_val) or str(input_val).strip() == '': 
                return ""
            val_str = str(input_val).strip().split('.')[0]
            if '_' in val_str:
                parts = val_str.split('_', 1)
                return f"{parts[0]}_{parts[1]}"
            return val_str

        # Pass the pre_prod_no into the helper function
        search_id = pad_id(pre_prod_no) 
        
        st.write(f"Searching for ID: {search_id}") # Helpful for debugging
        cell = tracker_worksheet.find(search_id, in_column=1)

        search_id = pad_id(pre_prod_no)
        cell = tracker_worksheet.find(search_id, in_column=1)
        row_idx = cell.row

        # Construct: T1 - 10/04/2026
        trial_suffix = current_trial_ref.split('_')[-1] if '_' in current_trial_ref else current_trial_ref
        current_date = datetime.now().strftime('%d/%m/%Y')
        combined_value = f"{trial_suffix} - {current_date}"

        headers = [h.strip() for h in tracker_worksheet.row_values(1)]
        col_name = "Injection trial requested"
        
        if col_name in headers:
            col_idx = headers.index(col_name) + 1
            tracker_worksheet.update_cell(row_idx, col_idx, combined_value)
            return True, combined_value
        else:
            return False, f"Column '{col_name}' not found."
    except Exception as e:
        return False, str(e)

from fpdf import FPDF
import io

# --- PDF GENERATION HELPER ---
def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    
    # Title
    pdf.cell(200, 10, txt="Injection Trial Report", ln=True, align='C')
    pdf.ln(10)
    
    # Table-like content
    pdf.set_font("Arial", size=12)
    for key, value in data.items():
        pdf.set_font("Arial", "B", 11)
        pdf.cell(50, 10, txt=f"{key}:", border=0)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 10, txt=f"{value}", border=0, ln=True)
    
    # Return as bytes
    return pdf.output(dest='S').encode('latin-1')

# ... [Keep all your existing code until the form submission] ...

# ... (Inside the 'with st.form' block)
        submit_trial = st.form_submit_button("Submit Trial Entry")

        if submit_trial:
            # 1. Prepare PDF data
            pdf_data = {
                "Trial Reference": current_trial_ref,
                "Pre-Prod No.": search_input,
                "Date": trial_date.strftime("%Y-%m-%d"),
                "Client": client,
                "Operator": operator,
                "Sales Rep": sales_rep,
                "Machine (Trial)": machine_trial,
                "Product": description,
                "Material": material,
                "Cycle Time": f"{cyc_t}s",
                "Inj Pressure": f"{inj_p} bar",
                "Observations": notes
            }
            st.session_state.last_submission_data = pdf_data

            with st.status("Saving Data...", expanded=True) as status:
                # ... [YOUR EXISTING SAVE LOGIC HERE] ...
                
                # After successful save:
                status.update(label="Submission Processed!", state="complete", expanded=False)
                st.session_state.submitted = True

    # --- PDF & RESET SECTION (OUTSIDE THE FORM) ---
    # Ensure this 'if' is aligned with the 'with st.form' block above
    if st.session_state.get('submitted', False):
        st.success("Entry Saved Successfully!")
        
        if 'last_submission_data' in st.session_state:
            # This requires 'from fpdf import FPDF' at the top of your file
            try:
                pdf_bytes = create_pdf(st.session_state.last_submission_data)
                
                st.download_button(
                    label="📥 Download Trial Report (PDF)",
                    data=pdf_bytes,
                    file_name=f"Trial_{st.session_state.last_submission_data['Trial Reference']}.pdf",
                    mime="application/pdf",
                    key="download_pdf"
                )
            except Exception as e:
                st.error(f"Error generating PDF: {e}")
        
        if st.button("Start Next Entry"):
            st.session_state.lookup_data = {}
            st.session_state.submitted = False 
            if 'last_submission_data' in st.session_state:
                del st.session_state.last_submission_data
            st.rerun()
# --- HEADER & SEARCH ---
st.title("Injection Trial Data Entry")
st.subheader("Search Project Tracker")

col_s1, col_s2 = st.columns([1, 3])
with col_s1:
    search_input = st.text_input("Enter Pre-Prod No. (e.g. 11925):")
with col_s2:
    st.write("##") 
    if st.button("Pull Information"):
        if search_input:
            data = get_project_data(search_input)
            if data:
                st.session_state.lookup_data = data
                st.success(f"Project details loaded for {search_input}")
            else:
                st.warning("No project data found.")
                st.session_state.lookup_data = {}

st.divider()

# --- TRIAL TIMELINE & SYNC SECTION ---
if search_input:
    st.subheader(f"Trial Timeline: {search_input}")
    
    # Add a Sync button at the top of the history section
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.caption("If you deleted entries, use the Sync button to update the Master Tracker.")
    with col_h2:
        if st.button("🔄 Sync Master Tracker"):
            # This calls the helper function you added earlier
            success, msg = sync_last_trial_to_cloud(search_input)
            if success:
                st.success("Master Tracker updated to last valid trial!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Sync failed: {msg}")

    # Display the actual history (with the delete buttons)
    display_trial_history(search_input)
    st.divider()

# --- SIDEBAR LOGIC ---
if st.sidebar.button("♻️ Refresh Data Sources"):
    st.cache_data.clear()
    st.success("Cache cleared! Try searching again.")

# --- NEW TRIAL ENTRY FORM ---
if search_input:
    ld = st.session_state.get('lookup_data', {})
    current_trial_ref = get_next_trial_reference(search_input)

    with st.form("injection_xlsm_form", clear_on_submit=True):
        st.subheader(f"New Trial Entry: {current_trial_ref}")
        
        st.subheader("1. Sales & Administration")
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            trial_date = st.date_input("Date", datetime.now())
            sales_rep = st.text_input("Sales Rep", value=ld.get('Sales Rep', ''))
        with s2:
            st.text_input("Base Pre-Prod No.", value=search_input, disabled=True)
            active_ref = st.text_input("Trial Reference", value=current_trial_ref, disabled=True)
            target_to = st.text_input("Target to", value=ld.get('Target to', ''))
        with s3:
            client = st.text_input("Client", value=ld.get('Client', ''))
            trial_qty = st.number_input("Trial Quantity", step=1)
        with s4:
            operator = st.text_input("Operator")
            machine_prod = st.text_input("Production Machine", value=ld.get('Machine', ''))
            machine_trial = st.text_input("Trial Machine", value=ld.get('Trial Machine', ''))

        st.divider()

        st.subheader("2. Product Specifications")
        p1, p2, p3, p4 = st.columns(4) 
        with p1:
            description = st.text_input("Description", value=ld.get('Project Description', ''))
            length = st.text_input("Length", value=str(ld.get('Length', '')))
            orifice = st.text_input("Orifice", value=str(ld.get('Orifice', '')))
            supplier = st.text_input("Supplier", value=str(ld.get('Supplier', '')))
        with p2:
            cap_lid_style = st.text_input("Cap_Lid Style", value=ld.get('Cap_Lid Style', ''))
            cap_lid_material = st.text_input("Cap_Lid Material", value=ld.get('Cap_Lid Material', ''))
            cap_lid_diameter = st.text_input("Cap_Lid Diameter", value=str(ld.get('Diameter', '')))
            mix = st.text_input("Mix_%", value=str(ld.get('Mix_%', '')))
        with p3:
            product_code = st.text_input("Product Code", value=ld.get('Product Code', ''))
            material = st.text_input("Material", value=ld.get('Material', ''))
            pigment = st.text_input("Pigment_MB Grade", value=ld.get('Pigment_MB Grade', ''))
            pre_mix_perc = st.text_input("If no dosing unit, what % pre-mixed?", 
                                      value=str(ld.get('if no_dosing unit, what percentage was material pre-mixed', '')))
        with p4:
            tinuvin_val = st.radio("Tinuvin", options=["Yes", "No"], horizontal=True)
            dosing_fitted = st.radio("Is dosing unit fitted", options=["Yes", "No"], horizontal=True)
            dosing_calib = st.radio("Is dosing unit calibrated", options=["Yes", "No"], horizontal=True)

        st.divider()
        
        st.subheader("3. Dosing Unit Settings")
        d1, d2, d3, d4, d5 = st.columns(5)
        with d1: colour_set = st.text_input("Colour Set Value", value=ld.get('Colour Set Value', ''))
        with d2: colour_act = st.text_input("Colour Actual", value=ld.get('Colour Actual', ''))
        with d3: colour_perc = st.text_input("Colour Percentage", value=ld.get('Colour Percentage', ''))
        with d4: shot_w = st.text_input("Shot Weight", value=ld.get('Shot Weight', ''))
        with d5: dosing_time = st.text_input("Dosing Time", value=ld.get('Dosing Time', ''))

        st.divider()

        st.subheader("4. Machine Process Settings")
        pr1, pr2, pr3, pr4 = st.columns(4)
        with pr1:
            inj_p = st.number_input("Injection Pressure (bar)", step=1)
            hold_p = st.number_input("Holding Pressure (bar)", step=1)
        with pr2:
            inj_s = st.number_input("Injection Speed (mm/s)", step=1)
            back_p = st.number_input("Back Pressure (bar)", step=1)
        with pr3:
            cyc_t = st.number_input("Total Cycle Time (s)", format="%.2f")
            cool_t = st.number_input("Cooling Time (s)", format="%.2f")
        with pr4:
            dos_s = st.number_input("Dosage Stroke (mm)", step=1)
            dec_m = st.number_input("Decompression (mm)", step=1)

        st.divider()

        st.subheader("5. Trial Observations")
        notes = st.text_area("Observations")

        submit_trial = st.form_submit_button("Submit Trial Entry")

        if submit_trial:
            with st.status("Saving Data...", expanded=True) as status:
                st.write("📝 Writing to trial history...")
                
                new_submission = {
                    "Trial Ref": current_trial_ref,
                    "Pre-Prod No.": str(search_input),
                    "Date": trial_date.strftime("%Y-%m-%d"),
                    "Sales Rep": sales_rep,
                    "Client": client,
                    "Operator": operator,
                    "Observations": notes,
                    "Cycle Time": cyc_t,
                    "Inj Pressure": inj_p,
                    "Tinuvin": tinuvin_val,
                    "Dosing Unit Fitted": dosing_fitted,
                    "Dosing Calibrated": dosing_calib,
                    "Colour Set": colour_set,
                    "Shot Weight": shot_w
                }

                # Save to Trial_Submissions.parquet
                df_new = pd.DataFrame([new_submission])
                if os.path.exists(SUBMISSIONS_FILE):
                    df_existing = pd.read_parquet(SUBMISSIONS_FILE)
                    df_final = pd.concat([df_existing, df_new], ignore_index=True)
                else:
                    df_final = df_new
                df_final.to_parquet(SUBMISSIONS_FILE, index=False)
                st.write("✅ Trial history log updated.")

                # --- UPDATE LOCAL TRACKER FILE ---
                st.write("💾 Updating local Project Tracker file...")
                if os.path.exists(FILENAME_PARQUET):
                    df_tracker = pd.read_parquet(FILENAME_PARQUET)
                    
                    def pad_id_local(val):
                        return str(val).strip().split('.')[0].zfill(5)
                    
                    search_id = pad_id_local(search_input)
                    df_tracker['Pre-Prod No.'] = df_tracker['Pre-Prod No.'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().apply(lambda x: x.zfill(5))
                    
                    trial_suffix = current_trial_ref.split('_')[-1] if '_' in current_trial_ref else current_trial_ref
                    combined_value = f"{trial_suffix} - {datetime.now().strftime('%d/%m/%Y')}"
                    
                    mask = df_tracker['Pre-Prod No.'] == search_id
                    if mask.any():
                        df_tracker.loc[mask, 'Injection trial requested'] = combined_value
                        df_tracker.to_parquet(FILENAME_PARQUET, index=False)
                        st.write("✅ Local Project Tracker updated.")
                    else:
                        st.warning("Could not find ID in local Parquet to update.")

                # --- GOOGLE SHEETS UPDATE ---
                st.write("🌐 Attempting Cloud Sync (Google Sheets)...")
                success, msg = update_tracker_status(search_input, current_trial_ref)
                
                if success:
                    st.write(f"✅ Cloud Sync Complete: {msg}")
                    status.update(label="Submission Processed & Synced!", state="complete", expanded=False)
                    st.session_state.submitted = True
                    st.cache_data.clear() 
                else:
                    st.error(f"❌ Cloud Sync Failed: {msg}")
                    status.update(label="Local Saved, Cloud Sync Failed", state="error", expanded=True)

    # UI Feedback and Reset
    if st.session_state.get('submitted', False):
        st.success("Entry Saved Successfully!")
        if st.button("Start Next Entry"):
            st.session_state.lookup_data = {}
            st.session_state.submitted = False 
            st.rerun()