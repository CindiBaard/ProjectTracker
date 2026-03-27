import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

# --- DIRECTORY SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")

# --- DATA LOOKUP FUNCTION ---
def get_project_data(pre_prod_no):
    """Searches the combined parquet file for the Pre-Prod number."""
    if not os.path.exists(FILENAME_PARQUET):
        st.error(f"Database file not found at: {FILENAME_PARQUET}")
        return None

    try:
        df_tracker = pd.read_parquet(FILENAME_PARQUET)
        
        # 1. Manually set the correct column name
        col_name = "Pre-Prod No." 
        
        if col_name not in df_tracker.columns:
            st.error(f"Column '{col_name}' not found. Available columns: {df_tracker.columns.tolist()}")
            return None

        # 2. Clean both the search term and the database column
        search_term = str(pre_prod_no).strip()
        
        df_tracker[col_name] = (
            df_tracker[col_name]
            .astype(str)
            .str.replace(r'\.0$', '', regex=True)
            .str.strip()
        )

        # 3. Search
        result = df_tracker[df_tracker[col_name] == search_term]
        
        if not result.empty:
            return result.iloc[0].to_dict()
        else:
            st.warning(f"No record found for '{search_term}' in column '{col_name}'.")
            return None
            
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
    search_input = st.text_input("Enter Pre-Prod No. (e.g. 11925):")
with col_s2:
    st.write("##") 
    if st.button("Pull Information"):
        if search_input:
            data = get_project_data(search_input)
            if data:
                st.session_state.lookup_data = data
                st.success(f"Data found for {search_input}")
                st.rerun()

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
        job_no = st.text_input("Form Pre-Prod No.", value=search_input if search_input else "")
        target_to = st.text_input("Target to", value=ld.get('Target to', ''))
    with s3:
        client = st.text_input("Client", value=ld.get('Client', ''))
        trial_qty = st.number_input("Trial Quantity", step=1)
    with s4:
        operator = st.text_input("Operator")
        machine_used = st.text_input("Machine used for Trial", value=ld.get('Machine', ''))

    st.divider()

    # --- SECTION 2: PRODUCT SPECIFICATIONS ---
    st.subheader("2. Product Specifications")
    p1, p2, p3 = st.columns(3)
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
        dosing_fitted = st.text_input("Is Dosing Unit Fitted", value=ld.get('Is Dosing Unit Fitted', ''))

    st.divider()
    
    # --- SECTION 3: DOSING UNIT SETTINGS ---
    st.subheader("3. Dosing Unit Settings")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        colour_set = st.text_input("Colour_Set_Value", value=ld.get('Colour Set Value', ''))
    with d2:
        colour_act = st.text_input("Colour_Actual", value=ld.get('Colour Actual', ''))
    with d3:
        colour_perc = st.text_input("Colour_Percentage", value=ld.get('Colour Percentage', ''))
    with d4:
        shot_w = st.text_input("Shot_Weight", value=ld.get('Shot Weight', ''))

    st.divider()

    # --- SECTION 4: MACHINE PROCESS SETTINGS ---
    st.subheader("4. Machine Process Settings")
    t1, t2, t3, t4, t5 = st.columns(5)
    with t1: zone_1 = st.number_input("Zone 1", step=1)
    with t2: zone_2 = st.number_input("Zone 2", step=1)
    with t3: zone_3 = st.number_input("Zone 3", step=1)
    with t4: zone_4 = st.number_input("Zone 4", step=1)
    with t5: nozzle = st.number_input("Nozzle", step=1)

    st.write("**Pressures, Speeds & Times**")
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

    # --- SECTION 5: OBSERVATIONS ---
    st.subheader("5. Trial Observations")
    notes = st.text_area("Observations")

    submit_trial = st.form_submit_button("Submit Trial Entry")

if submit_trial:
    st.success(f"Success! Trial entry for {job_no} recorded.")
    st.session_state.lookup_data = {}