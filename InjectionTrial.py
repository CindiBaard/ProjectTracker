import streamlit as st
import pandas as pd
from datetime import datetime

# Page configuration
st.set_page_config(layout="wide", page_title="Injection Trial Data Entry")

st.title("Injection Trial Data Entry")
st.info("Form fields matched to Injection.xlsm requirements.")

with st.form("injection_xlsm_form", clear_on_submit=True):
    
    # --- SECTION 1: SALES & LOGISTICS ---
    st.subheader("1. Sales & Administration")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        date = st.date_input("Date", datetime.now())
        sales_rep = st.text_input("Sales Rep")
    with s2:
        job_no = st.text_input("Pre-Prod No.")
        target_to = st.text_input("Target to")
    with s3:
        customer = st.text_input("Client")
        trial_qty = st.number_input("Trial Quantity", step=1)
    with s4:
        operator = st.text_input("Operator")
        machine_used = st.text_input("Machine used for Trial")

    st.divider()

    # --- SECTION 2: PRODUCT & COMPONENT SPECIFICATIONS ---
    st.subheader("2. Product Specifications")
    p1, p2, p3 = st.columns(3)
    with p1:
        part_desc = st.text_input("Part Description / Number")
        length = st.text_input("Length")
        orifice = st.text_input("Orifice")
    with p2:
        cap_lid_style = st.text_input("Cap_Lid Style")
        cap_lid_material = st.text_input("Cap_Lid Material")
        cap_lid_diameter = st.text_input("Cap_Lid Diameter")
    with p3:
        product_material_colour = st.text_input("Product Material Colour (tube, jar etc.)")
        mat_type = st.text_input("Material Type / Grade")
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
    trial_record = {
        "Date": [date],
        "Sales Rep": [sales_rep],
        "Pre-Prod No.": [preprod_no],
        "Target to": [target_to],
        "Client": [client],
        "Trial Quantity": [trial_qty],
        "Description": [description],
        "Machine used for Trial": [machine_used],
        "Length": [length],
        "Cap_Lid Style": [cap_lid_style],
        "Cap_Lid Material": [cap_lid_material],
        "Cap_Lid Diameter": [cap_lid_diameter],
        "Orifice": [orifice],
        "Product Material Colour": [product_material_colour],
        "Pigment_MB Grade": [pigment_mb_grade],
        "Observations": [notes]
    }
    
    st.success(f"Trial for Job {preprod_no} successfully captured.")
    st.table(pd.DataFrame(trial_record))