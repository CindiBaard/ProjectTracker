import streamlit as st
import pandas as pd
from datetime import datetime
import os
import time
from fpdf import FPDF
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

# ---- CONFIGURATION
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
        history = df[df['Pre-Prod No.'] == str(pre_prod_no)].sort_values('Date', ascending=False)
        
        if not history.empty:
            st.info(f"Existing Trials Found: **{len(history)}**")
            for index, row in history.iterrows():
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.write(f"**{row['Trial Ref']}** | {row['Date']} | {row['Operator']}")
                    st.caption(f"Note: {row['Observations']}")
                with col2:
                    if st.button(f"Delete", key=f"del_{row['Trial Ref']}"):
                        if delete_trial_entry(row['Trial Ref']):
                            st.success(f"Deleted {row['Trial Ref']}")
                            time.sleep(1) 
                            st.rerun()
                st.divider()
        else:
            st.write("No previous trial history found.")

def update_tracker_status(pre_prod_no, current_trial_ref, manual_date=None):
    import gspread
    from google.oauth2.service_account import Credentials

    trial_suffix = current_trial_ref.split('_')[-1] if '_' in current_trial_ref else current_trial_ref

    if manual_date:
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
        creds_info = st.secrets["gcp_service_account"] if "gcp_service_account" in st.secrets else st.secrets["connections"]["gsheets"]
        if isinstance(creds_info, dict) and "private_key" in creds_info:
             creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        tracker_spreadsheet = client.open_by_key(TRACKER_FILE_ID)
        tracker_worksheet = tracker_spreadsheet.get_worksheet(0) 

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
    if not os.path.exists(SUBMISSIONS_FILE):
        return False, "No history file found."
    try:
        df_history = pd.read_parquet(SUBMISSIONS_FILE)
        df_history['Pre-Prod No.'] = df_history['Pre-Prod No.'].astype(str)
        project_history = df_history[df_history['Pre-Prod No.'] == str(pre_prod_no)].copy()
        
        if project_history.empty:
            return update_tracker_status(pre_prod_no, "None", manual_date="No Trials") 

        project_history['Trial_Num'] = project_history['Trial Ref'].str.extract(r'(\d+)$').astype(int)
        latest_trial = project_history.sort_values(by=['Trial_Num'], ascending=False).iloc[0]
        
        return update_tracker_status(pre_prod_no, latest_trial['Trial Ref'], manual_date=latest_trial['Date'])
    except Exception as e:
        return False, str(e)

def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("Arial", "B", 18)
    pdf.cell(0, 10, txt="Injection Trial Report", ln=True, align='C')
    pdf.set_draw_color(50, 50, 50)
    pdf.line(10, 22, 200, 22)
    pdf.ln(10)

    def add_section(title):
        pdf.set_font("Arial", "B", 12)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(0, 8, txt=f" {title}", ln=True, fill=True)
        pdf.ln(2)

    def add_row(label, value, label2="", value2=""):
        pdf.set_font("Arial", "B", 10)
        pdf.cell(45, 7, txt=f"{label}:", border=0)
        pdf.set_font("Arial", size=10)
        pdf.cell(50, 7, txt=f"{value}", border=0)
        
        if label2:
            pdf.set_font("Arial", "B", 10)
            pdf.cell(45, 7, txt=f"{label2}:", border=0)
            pdf.set_font("Arial", size=10)
            pdf.cell(0, 7, txt=f"{value2}", border=0)
        pdf.ln(7)

    # Section 1: Admin
    add_section("1. Sales & Administration")
    add_row("Trial Ref", data.get("Trial Reference"), "Date", data.get("Date"))
    add_row("Pre-Prod No.", data.get("Pre-Prod No."), "Sales Rep", data.get("Sales Rep"))
    add_row("Client", data.get("Client"), "Target To", data.get("Target to"))
    add_row("Operator", data.get("Operator"), "Trial Qty", data.get("Trial Quantity"))
    add_row("Prod Machine", data.get("Production Machine"), "Trial Machine", data.get("Trial Machine"))
    pdf.ln(5)

    # Section 2: Product Specs
    add_section("2. Product Specifications")
    add_row("Description", data.get("Description"), "Product Code", data.get("Product Code"))
    add_row("Material", data.get("Material"), "Supplier", data.get("Supplier"))
    add_row("Cap/Lid Style", data.get("Cap_Lid Style"), "Material", data.get("Cap_Lid Material"))
    add_row("Diameter", data.get("Diameter"), "Length", data.get("Length"))
    add_row("Orifice", data.get("Orifice"), "Mix %", data.get("Mix_%"))
    add_row("Pigment Grade", data.get("Pigment_MB Grade"), "Pre-mix %", data.get("Pre-mix %"))
    add_row("Tinuvin", data.get("Tinuvin"), "Dosing Fitted", data.get("Dosing Unit Fitted"))
    pdf.ln(5)

    # Section 3 & 4: Settings
    add_section("3. Dosing & 4. Process Settings")
    add_row("Colour Set", data.get("Colour Set"), "Colour Actual", data.get("Colour Actual"))
    add_row("Shot Weight", data.get("Shot Weight"), "Dosing Time", data.get("Dosing Time"))
    add_row("Inj Pressure", data.get("Inj Pressure"), "Hold Pressure", data.get("Holding Pressure"))
    add_row("Inj Speed", data.get("Injection Speed"), "Back Pressure", data.get("Back Pressure"))
    add_row("Cycle Time", data.get("Cycle Time"), "Cooling Time", data.get("Cooling Time"))
    pdf.ln(5)

    # Section 5: Observations
    add_section("5. Trial Observations")
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 7, txt=data.get("Observations", ""))

    return pdf.output(dest='S').encode('latin-1')

# --- INITIALIZE SESSION STATE ---
if 'lookup_data' not in st.session_state:
    st.session_state.lookup_data = {}
if 'submitted' not in st.session_state:
    st.session_state.submitted = False

# --- SIDEBAR LOGIC ---
if st.sidebar.button("♻️ Refresh Data Sources"):
    st.cache_data.clear()
    st.success("Cache cleared!")

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

# --- MAIN LOGIC (Only runs if search_input is provided) ---
if search_input:
    # 1. Trial History & Sync
    st.subheader(f"Trial Timeline: {search_input}")
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.caption("If you deleted entries, use the Sync button to update the Master Tracker.")
    with col_h2:
        if st.button("🔄 Sync Master Tracker"):
            success, msg = sync_last_trial_to_cloud(search_input)
            if success:
                st.success("Master Tracker updated!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Sync failed: {msg}")

    display_trial_history(search_input)
    st.divider()

    # 2. Success & PDF Download Section
    if st.session_state.get('submitted', False):
        st.success("🎉 Entry Saved Successfully!")
        if 'last_submission_data' in st.session_state:
            try:
                pdf_bytes = create_pdf(st.session_state.last_submission_data)
                st.download_button(
                    label="📥 Download Trial Report (PDF)",
                    data=pdf_bytes,
                    file_name=f"Trial_{st.session_state.last_submission_data['Trial Reference']}.pdf",
                    mime="application/pdf",
                    key="download_pdf_main"
                )
            except Exception as e:
                st.error(f"Error generating PDF: {e}")
        
        if st.button("Start Next Entry"):
            st.session_state.submitted = False 
            if 'last_submission_data' in st.session_state:
                del st.session_state.last_submission_data
            st.rerun()
        st.divider()

    # 3. New Trial Entry Form
    ld = st.session_state.get('lookup_data', {})
    current_trial_ref = get_next_trial_reference(search_input)

    with st.form("injection_xlsm_form", clear_on_submit=True):
        st.subheader(f"New Trial Entry: {current_trial_ref}")
        
        # Form Sections
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
            pre_mix_perc = st.text_input("Pre-mix %", value=str(ld.get('if no_dosing unit, what percentage was material pre-mixed', '')))
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
                # Create the full dictionary for the PDF and Parquet
                full_data = {
                    "Trial Reference": current_trial_ref,
                    "Pre-Prod No.": str(search_input), # Force string
                    "Date": trial_date.strftime("%Y-%m-%d"),
                    "Sales Rep": str(sales_rep),
                    "Target to": str(target_to),
                    "Client": str(client),
                    "Trial Quantity": str(trial_qty),
                    "Operator": str(operator),
                    "Production Machine": str(machine_prod),
                    "Trial Machine": str(machine_trial),
                    "Description": str(description),
                    "Length": str(length),
                    "Orifice": str(orifice),
                    "Supplier": str(supplier),
                    "Cap_Lid Style": str(cap_lid_style),
                    "Cap_Lid Material": str(cap_lid_material),
                    "Diameter": str(cap_lid_diameter),
                    "Mix_%": str(mix),
                    "Product Code": str(product_code),
                    "Material": str(material),
                    "Pigment_MB Grade": str(pigment),
                    "Pre-mix %": str(pre_mix_perc),
                    "Tinuvin": str(tinuvin_val),
                    "Dosing Unit Fitted": str(dosing_fitted),
                    "Dosing Calibrated": str(dosing_calib),
                    "Colour Set": str(colour_set),
                    "Colour Actual": str(colour_act),
                    "Colour Percentage": str(colour_perc),
                    "Shot Weight": str(shot_w),
                    "Dosing Time": str(dosing_time),
                    "Inj Pressure": f"{inj_p} bar",
                    "Holding Pressure": f"{hold_p} bar",
                    "Injection Speed": f"{inj_s} mm/s",
                    "Back Pressure": f"{back_p} bar",
                    "Cycle Time": f"{cyc_t}s",
                    "Cooling Time": f"{cool_t}s",
                    "Dosage Stroke": str(dos_s),
                    "Decompression": str(dec_m),
                    "Observations": str(notes)
                }
                
                st.session_state.last_submission_data = full_data

                # Parquet Save Logic with Type Safety
                df_new = pd.DataFrame([full_data])
                
                if os.path.exists(SUBMISSIONS_FILE):
                    try:
                        df_existing = pd.read_parquet(SUBMISSIONS_FILE)
                        # Ensure both dataframes have identical column types (Strings) to prevent Arrow errors
                        df_existing = df_existing.astype(str)
                        df_new = df_new.astype(str)
                        df_final = pd.concat([df_existing, df_new], ignore_index=True)
                    except Exception as e:
                        st.warning(f"Existing file schema mismatch. Starting fresh: {e}")
                        df_final = df_new
                else:
                    df_final = df_new

                # FINAL STEP: Ensure everything is string before writing to Parquet
                df_final = df_final.astype(str)
                df_final.to_parquet(SUBMISSIONS_FILE, index=False, engine='pyarrow')

                # Cloud Sync
                success, msg = update_tracker_status(search_input, current_trial_ref)
                if success:
                    st.session_state.submitted = True
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Cloud Sync Failed: {msg}")    

