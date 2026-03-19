import streamlit as st
import pandas as pd
import os

# File settings
CSV_FILE = 'Artwork Status.csv'
REF_FILE = 'ProjectTrackerPP_Cleaned_NA.csv'

def format_date(date_val):
    """Formats date objects to DD.MM.YYYY string."""
    if date_val:
        return date_val.strftime('%d.%m.%Y')
    return ""

def clean_val(val):
    """Cleans up IDs and Text: removes .0 from numbers and strips spaces."""
    if pd.isna(val): return ""
    s = str(val).strip().replace(',', '')
    if s.endswith('.0'): s = s[:-2]
    return s

def main():
    st.set_page_config(page_title="Artwork Status Portal", layout="wide")
    st.title("🎨 Artwork Status Entry Form")

    # Persistent storage for the found data
    if "found_client" not in st.session_state:
        st.session_state.found_client = ""
    if "found_desc" not in st.session_state:
        st.session_state.found_desc = ""

    # --- STEP 1: LOOKUP ---
    st.subheader("Step 1: Project Lookup")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Use text_input to keep IDs exactly as typed
        search_no = st.text_input("Enter Pre-Prod No. to fetch details", placeholder="e.g. 12326")
    
    if st.button("Search Tracker"):
        if not search_no:
            st.warning("Please enter a number first.")
        elif os.path.exists(REF_FILE):
            try:
                # 1. 'sep=None' tells Python to automatically detect if it's ; or ,
                # 2. 'encoding=utf-8-sig' removes hidden Excel formatting (BOM)
                df_ref = pd.read_csv(REF_FILE, sep=None, engine='python', encoding='utf-8-sig')
                
                # 3. Clean all column names (removes invisible spaces)
                df_ref.columns = [str(c).strip() for c in df_ref.columns]
                
                # 4. Define the ID column to search
                id_col = 'Pre-Prod No.'
                
                if id_col in df_ref.columns:
                    # Clean the data in the file and the search term for a perfect match
                    df_ref[id_col] = df_ref[id_col].apply(clean_val)
                    target = clean_val(search_no)
                    
                    match = df_ref[df_ref[id_col] == target]
                    
                    if not match.empty:
                        # Success: Populate session state
                        st.session_state.found_client = clean_val(match.iloc[0].get('Client', ''))
                        
                        # Fetch 'Project Description' specifically
                        st.session_state.found_desc = clean_val(match.iloc[0].get('Project Description', ''))
                        
                        st.success(f"✅ Found: {st.session_state.found_client}")
                    else:
                        st.error(f"❌ ID '{target}' not found in the tracker.")
                else:
                    st.error(f"Could not find ID column. Available: {list(df_ref.columns)[:5]}...")
            except Exception as e:
                st.error(f"Error reading tracker file: {e}")
        else:
            st.error(f"Tracker file '{REF_FILE}' was not found.")

    st.divider()

    # --- STEP 2: ENTRY FORM ---
    st.subheader("Step 2: Complete Record Information")
    # Using 'clear_on_submit=True' to reset the form after each upload
    with st.form("main_form", clear_on_submit=True):
        left, right = st.columns(2)
        
        with left:
            st.info(f"Adding entry for ID: **{search_no}**")
            # Auto-filled from Step 1
            client = st.text_input("Client", value=st.session_state.found_client)
            description = st.text_input("Description", value=st.session_state.found_desc)
            
            artwork_req = st.selectbox("Artwork Required", ["", "X"])
            status = st.text_input("Status")
            comments = st.text_area("Comments")
            date_rec = st.date_input("Artwork Received", value=None, format="DD/MM/YYYY")
            date_wtsp = st.date_input("Sent Proof for WT_SP", value=None, format="DD/MM/YYYY")

        with right:
            date_client = st.date_input("Sent Proof to Client", value=None, format="DD/MM/YYYY")
            date_appr = st.date_input("Proof Approved", value=None, format="DD/MM/YYYY")
            date_plates = st.date_input("Ordered Plates", value=None, format="DD/MM/YYYY")
            date_arr = st.date_input("Plates Arrived", value=None, format="DD/MM/YYYY")
            date_foil = st.date_input("Ordered Foil Block", value=None, format="DD/MM/YYYY")
            date_farr = st.date_input("Foil Block Arrived", value=None, format="DD/MM/YYYY")
            quoted = st.date_input("Quoted", value=None, format="DD/MM/YYYY")
            spec = st.selectbox("Spec Supplied", ["", "X"])

        if st.form_submit_button("Upload Information"):
            if not search_no:
                st.error("Please enter a Pre-Prod No. in Step 1 first.")
            else:
                new_row = {
                    "Pre-Prod No.": search_no, "Client": client, "Description": description,
                    "Artwork required": artwork_req, "STATUS": status, "Comments": comments,
                    "Artwork Received": format_date(date_rec), "Sent Proof for WT_SP": format_date(date_wtsp),
                    "Sent Proof to Client": format_date(date_client), "Proof Approved (Conventional)": format_date(date_appr),
                    "Ordered Plates": format_date(date_plates), "Plates Arrived": format_date(date_arr),
                    "Ordered Foil Block": format_date(date_foil), "Foil Block Arrived": format_date(date_farr),
                    "Quoted": format_date(quoted), "Spec Supplied": spec
                }
                try:
                    df_to_save = pd.DataFrame([new_row])
                    # Using ';' for the output file to match your 'Artwork Status.csv' format
                    df_to_save.to_csv(CSV_FILE, mode='a', index=False, header=not os.path.exists(CSV_FILE), sep=';')
                    st.success(f"🎉 Successfully added {search_no} to {CSV_FILE}!")
                    
                    # Clear session state for next round
                    st.session_state.found_client = ""
                    st.session_state.found_desc = ""
                except Exception as e:
                    st.error(f"Error saving data: {e}")

if __name__ == "__main__":
    main()