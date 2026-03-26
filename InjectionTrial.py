import streamlit as st
import pandas as pd
from datetime import datetime

# Page configuration for a professional, wide layout
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

st.title("Injection Trial Data Entry")
st.info("Please ensure all fields match the current Trial Sheet (Injection.xlsm)")

# Use a form to group all data and prevent constant app refreshes
with st.form("injection_xlsm_form", clear_on_submit=True):
    
    # --- SECTION 1: IDENTITY & REFERENCE ---
    st.subheader("1. General Information")
    r1_col1, r1_col2, r1_col3 = st.columns(3)
    with r1_col1:
        date = st.date_input("Date", datetime.now())
        job_no = st.text_input("Job Number")
    with r1_col2:
        customer = st.text_input("Customer")
        part_desc = st.text_input("Part Description / Number")
    with r1_col3:
        machine = st.text_input("Machine")
        operator = st.text_input("Operator")

    st.divider()

    # --- SECTION 2: MATERIAL & MASTERBATCH ---
    st.subheader("2. Material Specifications")
    r2_col1, r2_col2, r2_col3 = st.columns(3)
    with r2_col1:
        mat_type = st.text_input("Material Type / Grade")
        mat_batch = st.text_input("Material Batch No.")
    with r2_col2:
        mb_code = st.text_input("Masterbatch Code")
        mb_batch = st.text_input("Masterbatch Batch No.")
    with r2_col3:
        mb_ratio = st.number_input("MB Ratio (%)", format="%.2f", step=0.01)
        regrind_pct = st.number_input("Regrind (%)", step=1.0)

    st.divider()

    # --- SECTION 3: TECHNICAL PROCESS PARAMETERS ---
    st.subheader("3. Machine Process Settings")
    
    # Temperature Zones
    st.write("**Temperature Profile (°C)**")
    t1, t2, t3, t4, t5 = st.columns(5)
    with t1: zone_1 = st.number_input("Zone 1", step=1)
    with t2: zone_2 = st.number_input("Zone 2", step=1)
    with t3: zone_3 = st.number_input("Zone 3", step=1)
    with t4: zone_4 = st.number_input("Zone 4", step=1)
    with t5: nozzle = st.number_input("Nozzle", step=1)

    # Pressures and Times
    st.write("**Pressures, Speeds & Times**")
    p1, p2, p3, p4 = st.columns(4)
    with p1:
        inj_pressure = st.number_input("Injection Pressure (bar)", step=1)
        hold_pressure = st.number_input("Holding Pressure (bar)", step=1)
    with p2:
        inj_speed = st.number_input("Injection Speed (mm/s)", step=1)
        back_pressure = st.number_input("Back Pressure (bar)", step=1)
    with p3:
        cycle_time = st.number_input("Total Cycle Time (s)", format="%.2f")
        cool_time = st.number_input("Cooling Time (s)", format="%.2f")
    with p4:
        dosage_stroke = st.number_input("Dosage Stroke (mm)", step=1)
        decompression = st.number_input("Decompression (mm)", step=1)

    st.divider()

    # --- SECTION 4: TRIAL OBSERVATIONS ---
    st.subheader("4. Observations & Quality Checks")
    notes = st.text_area("Observations (e.g., Short shots, flash, burning, dimensions)")

    # Form Submission
    submit_trial = st.form_submit_button("Submit Trial Entry to Database")

if submit_trial:
    # Creating a structured record matching the xlsm column layout
    trial_data = {
        "Date": [date],
        "Job Number": [job_no],
        "Machine": [machine],
        "Material": [mat_type],
        "MB Ratio": [mb_ratio],
        "Inj Pressure": [inj_pressure],
        "Cycle Time": [cycle_time],
        "Observations": [notes]
    }
    
    # Display success and summary for the user
    st.success(f"Trial data for Job {job_no} has been captured.")
    st.table(pd.DataFrame(trial_data))