import streamlit as st
import pandas as pd
from datetime import datetime
import os

# Page configuration
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

st.title("Injection Trial Data Entry")

# --- DATA LOOKUP FUNCTION ---
def get_project_data(pre_prod_no):
    # Adjust the filename if your parquet file has a different name
    file_path = "ProjectTracker.parquet"
    if os.path.exists(file_path):
        df_tracker = pd.read_parquet(file_path)
        # Search for the Pre-Prod No. (handling potential string/int mismatches)
        result = df_tracker[df_tracker['Pre-Prod No.'].astype(str) == str(pre_prod_no)]
        if not result.empty:
            return result.iloc[0].to_dict()
    return None

# --- INITIALIZE SESSION STATE ---
# This ensures data stays in the boxes after the lookup button is clicked
if 'lookup_data' not in st.session_state:
    st.session_state.lookup_data = {}

# --- LOOKUP SECTION ---
st.subheader("Search Project Tracker")
col_search1, col_search2 = st.columns([1, 3])
with col_search1:
    search_no = st.text_input("Enter Pre-Prod No. to pull data:")
with col_search2:
    st.write(" ") # Spacing
    if st.button("Pull Information"):
        data = get_project_data(search_no)
        if data:
            st.session_state.lookup_data = data
            st.success(f"Found data for {search_no}")
        else:
            st.error("Pre-Prod No. not found in ProjectTracker.")

st.divider()

# --- MAIN FORM ---
with st.form("injection_xlsm_form", clear_on_submit=True):
    # Using .get() to safely pull data from session state or leave blank if not found
    ld = st.session_state.lookup_data

    # --- SECTION 1: SALES & ADMINISTRATION ---
    st.subheader("1. Sales & Administration")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        date = st.date_input("Date", datetime.now())
        sales_rep = st.text_input("Sales Rep", value=ld.get('Sales Rep', ''))
    with s2:
        job_no = st.text_input("Job Number", value=search_no) # Uses searched No.
        target_to = st.text_input("Target to", value=ld.get('Target to', ''))
    with s3:
        customer = st.text_input("Customer", value=ld.get('Client', ''))
        trial_qty = st.number_input("Trial Quantity", step=1)
    with s4:
        operator = st.text_input("Operator")
        machine_used = st.text_input("Machine used for Trial")

    st.divider()

    # --- SECTION 2: PRODUCT & COMPONENT SPECIFICATIONS ---
    st.subheader("2. Product Specifications")
    p1, p2, p3 = st.columns(3)
    with p1:
        part_desc = st.text_input("Part Description / Number", value=ld.get('Project Description', ''))
        length = st.text_input("Length", value=ld.get('Length', ''))
        orifice = st.text_input("Orifice", value=ld.get('Orifice', ''))
    with p2:
        cap_lid_style = st.text_input("Cap_Lid Style", value=ld.get('Cap_Lid Style', ''))
        cap_lid_material = st.text_input("Cap_Lid Material", value=ld.get('Cap_Lid Material', ''))
        cap_lid_diameter = st.text_input("Cap_Lid Diameter", value=ld.get('Diameter', ''))
    with p3:
        product_material_colour = st.text_input("Product Material Colour (tube, jar etc.)")
        mat_type = st.text_input("Material Type / Grade", value=ld.get('Material', ''))
        pigment_mb_grade = st.text_input("Pigment_MB Grade")

    st.divider()

    # --- SECTION 3: TECHNICAL PROCESS PARAMETERS ---
    st.subheader("3. Machine Process Settings")
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
    notes = st.text_area("Observations")

    submit_trial = st.form_submit_button("Submit Trial Entry")

if submit_trial:
    # Logic to save the trial record
    st.success(f"Trial for {search_no} captured.")
    # Clear the lookup data for the next entry
    st.session_state.lookup_data = {}