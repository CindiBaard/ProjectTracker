import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

# --- DATA LOOKUP FUNCTION ---
def get_project_data(pre_prod_no):
    """Searches ProjectTracker.parquet for the Pre-Prod number."""
    file_path = "ProjectTracker.parquet"
    if not os.path.exists(file_path):
        st.error(f"File not found: {file_path}. Please ensure it is in the repository.")
        return None

    try:
        df_tracker = pd.read_parquet(file_path)
        # Clean search term and column for comparison
        search_term = str(pre_prod_no).strip()
        
        # Check for various possible column name variations
        possible_cols = ['Pre-Prod No.', 'Pre-Prod No', 'Pre-Prod_No']
        col_name = next((c for c in possible_cols if c in df_tracker.columns), None)

        if not col_name:
            st.error("Could not find Pre-Prod No. column in ProjectTracker.")
            return None

        # Filter for the record
        result = df_tracker[df_tracker[col_name].astype(str).str.strip() == search_term]
        
        if not result.empty:
            return result.iloc[0].to_dict()
    except Exception as e:
        st.error(f"Error reading database: {e}")
    return None

# --- INITIALIZE SESSION STATE ---
if 'lookup_data' not in st.session_state:
    st.session_state.lookup_data = {}

# --- HEADER & SEARCH ---
st.title("Injection Trial Data Entry")

st.subheader("Search Project Tracker")
col_s1, col_s2 = st.columns([1, 3])
with col_s1:
    search_input = st.text_input("Enter Pre-Prod No. (e.g. 9143):")
with col_s2:
    st.write("##") # Vertical alignment
    if st.button("Pull Information"):
        if search_input:
            data = get_project_data(search_input)
            if data:
                st.session_state.lookup_data = data
                st.success(f"Data found for {search_input}")
                st.rerun()
            else:
                st.warning(f"No record found for '{search_input}'")

st.divider()

# --- MAIN FORM ---
with st.form("injection_xlsm_form", clear_on_submit=True):
    ld = st.session_state.lookup_data

    # --- SECTION 1: SALES & ADMINISTRATION ---
    st.subheader("1. Sales & Administration")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        date = st.date_input("Date", datetime.now())
        sales_rep = st.text_input("Sales Rep", value=ld.get('Sales Rep', ''))
    with s2:
        # Pre-Prod No. acts as the Job Number here
        job_no = st.text_input("Job Number", value=search_input if search_input else "")
        target_to = st.text_input("Target to", value=ld.get('Target to', ''))
    with s3:
        customer = st.text_input("Customer", value=ld.get('Client', ''))
        trial_qty = st.number_input("Trial Quantity", step=1)
    with s4:
        operator = st.text_input("Operator")
        machine_used = st.text_input("Machine used for Trial", value=ld.get('Machine', ''))

    st.divider()

    # --- SECTION 2: PRODUCT & COMPONENT SPECIFICATIONS ---
    st.subheader("2. Product Specifications")
    p1, p2, p3 = st.columns(3)
    with p1:
        part_desc = st.text_input("Part Description / Number", value=ld.get('Project Description', ''))
        length = st.text_input("Length", value=str(ld.get('Length', '')))
        orifice = st.text_input("Orifice", value=str(ld.get('Orifice', '')))
    with p2:
        cap_lid_style = st.text_input("Cap_Lid Style", value=ld.get('Cap_Lid Style', ''))
        cap_lid_material = st.text_input("Cap_Lid Material", value=ld.get('Cap_Lid Material', ''))
        cap_lid_diameter = st.text_input("Cap_Lid Diameter", value=str(ld.get('Diameter', '')))
    with p3:
        product_material_colour = st.text_input("Product Material Colour (tube, jar etc.)", value=ld.get('Product Code', ''))
        mat_type = st.text_input("Material Type / Grade", value=ld.get('Material', ''))
        pigment_mb_grade = st.text_input("Pigment_MB Grade")

    st.divider()

    # --- SECTION 3: TECHNICAL PROCESS PARAMETERS ---
    st.subheader("3. Machine Process Settings")
    st.write("**Temperature Profile (°C)**")
    t1, t2, t3, t4, t5 = st.columns(5)
    with t1: zone_1 = st.number_input("Zone 1", step=1)
    with t2: zone_2 = st.number_input("Zone 2", step=1)
    with t3: zone_3 = st.number_input("Zone 3", step=1)
    with t4: zone_4 = st.number_input("Zone 4", step=1)
    with t5: nozzle = st.number_input("Nozzle", step=1)

    st.write("**Pressures, Speeds & Times**")
    pr1, pr2, pr3, pr4 = st.columns(4)
    with pr1:
        inj_pressure = st.number_input("Injection Pressure (bar)", step=1)
        hold_pressure = st.number_input("Holding Pressure (bar)", step=1)
    with pr2:
        inj_speed = st.number_input("Injection Speed (mm/s)", step=1)
        back_pressure = st.number_input("Back Pressure (bar)", step=1)
    with pr3:
        cycle_time = st.number_input("Total Cycle Time (s)", format="%.2f")
        cool_time = st.number_input("Cooling Time (s)", format="%.2f")
    with pr4:
        dosage_stroke = st.number_input("Dosage Stroke (mm)", step=1)
        decompression = st.number_input("Decompression (mm)", step=1)

    st.divider()

    # --- SECTION 4: OBSERVATIONS ---
    st.subheader("4. Trial Observations")
    notes = st.text_area("Observations (e.g., Short shots, flash, burning, dimensions)")

    submit_trial = st.form_submit_button("Submit Trial Entry")

if submit_trial:
    # Final data object
    final_record = {
        "Date": [date],
        "Sales Rep": [sales_rep],
        "Job Number": [job_no],
        "Target to": [target_to],
        "Customer": [customer],
        "Trial Quantity": [trial_qty],
        "Machine used for Trial": [machine_used],
        "Part Description": [part_desc],
        "Length": [length],
        "Cap_Lid Style": [cap_lid_style],
        "Cap_Lid Material": [cap_lid_material],
        "Cap_Lid Diameter": [cap_lid_diameter],
        "Orifice": [orifice],
        "Product Material Colour": [product_material_colour],
        "Pigment_MB Grade": [pigment_mb_grade],
        "Observations": [notes]
    }
    
    st.success(f"Success! Trial entry for {job_no} recorded.")
    st.table(pd.DataFrame(final_record))
    # Clear session state for next lookup
    st.session_state.lookup_data = {}