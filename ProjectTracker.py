import io
import os
from datetime import datetime
import re
import gspread
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

# =====================================================================
# 1. FILE CONFIGURATIONS & GLOBAL PATHS (Moved to top to prevent NameErrors)
# =====================================================================
BASE_DIR = os.getcwd()
FILENAME_PARQUET = os.path.join(BASE_DIR, "ProjectTracker_Combined.parquet")
TRACKER_ADJ_FILE = os.path.join(BASE_DIR, "ProjectTrackerPP_Cleaned_NA.csv")
DIGITALPREPROD_FILE = os.path.join(BASE_DIR, "DigitalPreProd.csv")
COMBINATIONS_FILE = os.path.join(BASE_DIR, "TubeAndCapCombinations.csv")
TRIALS_FILE_CURRENT = "https://raw.githubusercontent.com/CindiBaard/ProjectTracker/refs/heads/main/Merged_Weekly_Trackers_Layout_Preserved.csv"
SUBMISSIONS_FILE = "Submissions_History.parquet"
TRACKER_FILE_ID = "1LA9F5mD67vR9yYKqQ39CS-tAZ9QgCgn5KBWaY_RfFKM"
MOULD_ASSETS = "1NoA6JvnxkqCpeBF8OZNcrdWhD2SF7umM7lPBVyWDoT8"

# Point this directly to your variable or local filename fallback
tracker_file = "Merged_Weekly_Trackers_Layout_Preserved.csv" 


# =====================================================================
# 2. DATA EXTRACTION HELPERS
# =====================================================================

def get_pp_dates(file_path, pp_number):
    """
    Searches for a specific PP # in the dataset and extracts 
    the corresponding PP Number, 'Date Log', and 'Complete' dates.
    """
    try:
        import pandas as pd
        import os

        # Safety check: make sure the file exists before reading it
        if not os.path.exists(file_path):
            return pd.DataFrame()

        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        elif file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            return pd.DataFrame()
        
        df.columns = df.columns.str.strip()
        
        if 'PP #' not in df.columns:
            return pd.DataFrame()
            
        df['PP #_str'] = df['PP #'].astype(str)
        search_term = str(pp_number).strip()
        
        filtered_df = df[df['PP #_str'].str.contains(search_term, na=False)].copy()
        
        # Check for flexible column naming
        date_log_col = 'Date_Log' if 'Date_Log' in df.columns else 'Date Log'
        complete_col = 'Promise_Complete' if 'Promise_Complete' in df.columns else 'Promise Complete'
        
        
        # Build the list of columns to extract dynamically
        columns_to_extract = ['PP #']
        rename_mapping = {'PP #': 'PP Number'}
        
            
        columns_to_extract.extend([date_log_col, complete_col])
        rename_mapping.update({
            date_log_col: 'Date Log',
            complete_col: 'Complete Date'
        })
        
        # Extract and rename
        result = filtered_df[columns_to_extract].rename(columns=rename_mapping)
        
        return result

    except Exception:
        return pd.DataFrame()


# --- 3. LOAD DATA AND CALCULATE METRICS ---

avg_days_display = "N/A"
total_completed = 0
active_backlog = 0

# Initialize layout baseline structures to prevent NameErrors down the line
df_clean = pd.DataFrame(columns=["Date_Logged_dt", "Complete_dt", "Days_To_Complete"])
log_col = "Date_Log"
comp_col = "Promise_Complete"

# If pulling down from GitHub URL instead of checking local path presence:
if tracker_file.startswith("http") or os.path.exists(tracker_file):
    try:
        raw_lines = []
        # Support reading directly via URL or local file path
        if tracker_file.startswith("http"):
            import urllib.request
            with urllib.request.urlopen(tracker_file) as response:
                lines = response.read().decode('utf-8', errors='ignore').splitlines()
                for line in lines:
                    cols = [c.strip() for c in line.split(",")]
                    if len(cols) >= 5 and any(cols):
                        raw_lines.append(cols)
        else:
            with open(tracker_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    cols = [c.strip() for c in line.split(",")]
                    if len(cols) >= 5 and any(cols):
                        raw_lines.append(cols)
        
        if raw_lines:
            max_cols = max(len(row) for row in raw_lines)
            padded_rows = [r + [""] * (max_cols - len(r)) for r in raw_lines]
            temp_df = pd.DataFrame(padded_rows)
            
            header_row_idx = None
            for idx, row in temp_df.iterrows():
                row_list = [str(x).lower() for x in row]
                if any("date_log" in x or "date log" in x for x in row_list):
                    header_row_idx = idx
                    break
            
            if header_row_idx is not None:
                temp_df.columns = temp_df.iloc[header_row_idx].str.strip()
                df_tracker = temp_df.iloc[header_row_idx + 1:].copy()
            else:
                temp_df.columns = temp_df.iloc[0].str.strip()
                df_tracker = temp_df.iloc[1:].copy()
                
            df_tracker.columns = df_tracker.columns.astype(str).str.strip()
            
            log_col = next((c for c in df_tracker.columns if any(h in c.lower() for h in ["date_log", "date logged", "date log"])), "Date_Log")
            comp_col = next((c for c in df_tracker.columns if any(h in c.lower() for h in ["complete", "promise_complete", "promise complete"])), "Promise_Complete")
            
            if log_col in df_tracker.columns and comp_col in df_tracker.columns:
                df_clean = df_tracker[
                    (df_tracker[log_col] != "") & 
                    (~df_tracker[log_col].str.lower().str.contains("date", na=False))
                ].copy()
                
                df_clean["Date_Logged_dt"] = pd.to_datetime(df_clean[log_col], errors="coerce", format="mixed")
                df_clean["Complete_dt"] = pd.to_datetime(df_clean[comp_col], errors="coerce", format="mixed")
                df_clean["Days_To_Complete"] = (df_clean["Complete_dt"] - df_clean["Date_Logged_dt"]).dt.days
                
                valid_days = df_clean[df_clean["Days_To_Complete"] >= 0]["Days_To_Complete"]
                if not valid_days.empty:
                    avg_days_display = f"{int(valid_days.mean())} Days"
                    total_completed = int(valid_days.count())
                
                active_backlog = int((df_clean["Date_Logged_dt"].notna() & df_clean["Complete_dt"].isna()).sum())
                
    except Exception as e:
        st.warning(f"Metrics loading fallback enabled: {e}")

# --- 4. INITIAL SETUP & DEPENDENCIES ---
st.set_page_config(page_title="Project Tracker Dashboard", layout="wide")
pd.set_option("styler.render.max_elements", 1000000)

# (Leave the rest of your DESIRED_ORDER array and Tab definitions exactly as they are)


# --- 2. FIXED DESIRED ORDER ---
DESIRED_ORDER = [
    "Pre-Prod No.",
    "Date",
    "Age Category",
    "Client",
    "Project Description",
    "New Mould_ Client or Product",
    "Product Code",
    "Machine",
    "Sales Rep",
    "Category",
    "Status",
    "Open or closed",
    "Completion date",
    "Material",
    "Product Material Colour (tube, jar etc.)",
    "Artwork required",
    "Artwork Received",
    "Order Qty x1000",
    "Unit Order No",
    "Length",
    "Cap_Lid Style",
    "Cap_Lid Material",
    "Cap_Lid Diameter",
    "Orifice",
    "Other Cap_Lid Info",
    "Tube Shoulder colour",
    "Dust Controlled Area",
    "Date Sent on Proof",
    "Size of Eyemark",
    "Proof Approved (Conventional)",
    "Proof Approved (Digital)",
    "Ordered Plates",
    "Plates Arrived",
    "Sent on Trial",
    "Digital trial sent",
    "Revised Artwork After Trialling",
    "Masterbatch received",
    "Extrusion requested",
    "Extrusion received",
    "Injection trial requested",
    "Injection trial received",
    "Blowmould trial requested",
    "Blowmould trial received",
    "Trial Comments"
]

# --- 3. SESSION STATE INITIALIZATION ---
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "🔍 Search & Edit"
if "form_data" not in st.session_state:
    st.session_state.form_data = {}
if "selected_combo" not in st.session_state:
    st.session_state.selected_combo = {}
if "last_search_no" not in st.session_state:
    st.session_state.last_search_no = ""

if "mould_df" not in st.session_state:
    st.session_state.mould_df = None
if "mould_descriptions" not in st.session_state:
    st.session_state.mould_descriptions = []


# --- 4. UTILITY FUNCTIONS FOR MOULD INFO ---
def load_mould_assets_data():
    """Loads and dynamically aligns the complex Mould Assets CSV for Streamlit drop-downs."""
    csv_filename = "Mould Assets.csv"

    if not os.path.exists(csv_filename):
        return

    try:
        mould_df = None
        target_row_index = None
        
        # 1. Clean read and search for header row location
        with open(csv_filename, "r", encoding="utf-8-sig", errors="ignore") as f:
            lines = f.readlines()
            for idx, line in enumerate(lines):
                cleaned_line = line.replace(" ", "").lower()
                if "mouldnumber" in cleaned_line or "moulddescription" in cleaned_line:
                    target_row_index = idx
                    break
        
        skips_to_try = [target_row_index] if target_row_index is not None else [3, 4, 2, 0]
        
        for skip in skips_to_try:
            for separator in [",", ";"]:
                try:
                    df_temp = pd.read_csv(csv_filename, skiprows=skip, sep=separator, encoding="utf-8-sig")
                    df_temp.columns = [str(c).strip() for c in df_temp.columns]
                    mould_df = df_temp
                    break
                except Exception:
                    continue
            if mould_df is not None:
                break

        if mould_df is None:
            st.sidebar.error("Could not locate headers in Mould Assets.csv")
            return

        # 2. Map columns using safe case/space-insensitive normalization
        desc_data = None
        num_data = None
        draw_data = None

        for col in mould_df.columns:
            norm = col.replace(" ", "").replace("_", "").replace(".", "").lower()
            
            # Extract out the data series safely, catching any duplicated columns
            if "moulddescription" in norm or "description" in norm:
                if desc_data is None:
                    desc_data = mould_df[col].iloc[:, 0] if isinstance(mould_df[col], pd.DataFrame) else mould_df[col]
            elif "mouldnumber" in norm or "mouldno" in norm:
                if num_data is None:
                    num_data = mould_df[col].iloc[:, 0] if isinstance(mould_df[col], pd.DataFrame) else mould_df[col]
            elif "drawing" in norm or "drawno" in norm:
                if draw_data is None:
                    draw_data = mould_df[col].iloc[:, 0] if isinstance(mould_df[col], pd.DataFrame) else mould_df[col]

        # Fallbacks if columns weren't hit by exact string names
        if desc_data is None:
            desc_data = mould_df.iloc[:, 0]
        if num_data is None:
            num_data = pd.Series([""] * len(mould_df))
        if draw_data is None:
            draw_data = pd.Series([""] * len(mould_df))

        # 3. Rebuild an isolated, clean dataframe
        clean_df = pd.DataFrame({
            "Mould Description": desc_data,
            "MouldNumber": num_data,
            "Drawing No.": draw_data
        })

        # 4. Enforce clean text formatting across all values
        for col in clean_df.columns:
            clean_df[col] = clean_df[col].astype(str).str.strip().replace("nan", "")

        # Remove rows missing descriptions
        clean_df = clean_df[clean_df["Mould Description"] != ""]
        
        # Build strict lookup keys
        clean_df["_match_key"] = clean_df["Mould Description"].str.replace(" ", "").str.lower()

        # Save to Streamlit state cache variables
        st.session_state.mould_df = clean_df
        st.session_state.mould_descriptions = sorted(
            [str(d) for d in clean_df["Mould Description"].unique() if str(d).strip()]
        )

    except Exception as e:
        st.sidebar.error(f"Failed parsing Mould Assets.csv system: {e}")

def clean_column_names(df):
    df.columns = [
        str(c).replace("\ufeff", "").replace("ï»¿", "").strip()
        for c in df.columns
    ]

    if (
        len(df.columns) > 0
        and "," in df.columns[0]
        and "Pre-Prod" in df.columns[0]
    ):
        new_headers = df.columns[0].split(",")
        if len(new_headers) > 5:
            data = df.iloc[:, 0].str.split(",", expand=True)
            df = data
            df.columns = new_headers[: len(df.columns)]

    rename_map = {
        "Pre-Prod No": "Pre-Prod No.",
        "Pre Prod No.": "Pre-Prod No.",
        "Pre-Prod No. ": "Pre-Prod No.",
        "Pre Prod No": "Pre-Prod No.",
    }
    df = df.rename(columns=rename_map)
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        cols[cols == dup] = [
            f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))
        ]
    df.columns = cols

    return df


def get_auto_next_no(df):
    if df is None or df.empty or "Pre-Prod No." not in df.columns:
        return "00001"
    try:
        nums = (
            df["Pre-Prod No."]
            .astype(str)
            .str.extract(r"(\d+)")[0]
            .dropna()
            .astype(int)
        )
        if nums.empty:
            return "00001"
        return str(int(nums.max()) + 1).zfill(5)
    except:
        return "00001"


def get_next_available_id(search_no, existing_ids):
    base = str(search_no).split("_")[0]
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = f"{base}_{char}"
        if candidate not in existing_ids.values:
            return candidate
    return f"{base}_NEW"


def pad_preprod_id(val):
    if pd.isna(val) or str(val).strip() == "":
        return ""
    val_str = str(val).strip().split(".")[0]
    if "_" in val_str:
        parts = val_str.split("_", 1)
        return f"{parts[0]}_{parts[1]}"
    return val_str


def update_tracker_status(pre_prod_no, updated_row_dict):
    """
    Finds the row corresponding to pre_prod_no in Google Sheets and updates 
    all columns present in updated_row_dict matching the sheet's headers.
    """
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_info = st.secrets.get(
            "gcp_service_account", st.secrets.get("connections", {}).get("gsheets")
        )
        if isinstance(creds_info, dict) and "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace(
                "\\n", "\n"
            )
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        tracker_spreadsheet = client.open_by_key(TRACKER_FILE_ID)
        tracker_worksheet = tracker_spreadsheet.get_worksheet(0)

        search_id = str(pre_prod_no).strip().split(".")[0]
        cell = tracker_worksheet.find(search_id, in_column=1)
        if not cell:
            return False, f"ID {search_id} not found on Google Sheets."

        # Fetch headers to locate column coordinates dynamically
        headers = [h.strip() for h in tracker_worksheet.row_values(1)]
        
        # Build a batch update payload to optimize execution speed
        updates = []
        for col_name, value in updated_row_dict.items():
            if col_name in headers:
                col_idx = headers.index(col_name) + 1
                updates.append({
                    'range': gspread.utils.rowcol_to_a1(cell.row, col_idx),
                    'values': [[str(value)]]
                })
        
        if updates:
            tracker_worksheet.batch_update(updates)
            return True, "Google Sheet sync successful!"
        return False, "No matching columns found to update."
        
    except Exception as e:
        return False, f"Google Sheet update failed: {str(e)}"


def calculate_age_category(row):
    try:
        start_date = pd.to_datetime(row["Date"], dayfirst=True, errors="coerce")
        comp_date = str(row.get("Completion date", "")).strip()
        end_date = (
            pd.to_datetime(comp_date, dayfirst=True, errors="coerce")
            if comp_date and comp_date.lower() != "nan"
            else pd.to_datetime(datetime.now().date())
        )
        if pd.isnull(start_date):
            return "N/A", 0
        days = (end_date - start_date).days
        cat = (
            "< 6 Weeks"
            if days < 42
            else "6-12 Weeks" if days < 84 else "> 12 Weeks"
        )
        return cat, max(0, days)
    except:
        return "Error", 0


def save_db(df):
    df.to_parquet(FILENAME_PARQUET, index=False)


@st.cache_data
def get_options(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="latin1", errors="ignore") as f:
                lines = [
                    line.strip().replace('"', "")
                    for line in f.readlines()
                    if line.strip()
                ]
                return sorted(
                    list(
                        set(
                            [
                                l.split(";")[0].split(",")[0].strip()
                                for l in lines
                                if l
                            ]
                        )
                    )
                )
        except:
            return []
    return []


def load_trial_data():
    if os.path.exists(TRIALS_FILE_CURRENT):
        try:
            return pd.read_csv(TRIALS_FILE_CURRENT)
        except:
            return pd.DataFrame()
    return pd.DataFrame()


def smart_read(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(
            path, sep=",", on_bad_lines="skip", encoding="utf-8-sig", low_memory=False
        )
        if len(df.columns) <= 1:
            df = pd.read_csv(
                path, sep=";", on_bad_lines="skip", encoding="utf-8-sig", low_memory=False
            )

        df = df.replace("#REF!", np.nan)
        return clean_column_names(df)
    except Exception as e:
        st.error(f"Error reading {path}: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner="Refreshing Database...")
def load_db_v2(tracker_path, digital_path, parquet_path):
    if os.path.exists(parquet_path):
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass

    try:
        df_t = smart_read(tracker_path)
        df_d = smart_read(digital_path)

        if df_t.empty:
            return pd.DataFrame()

        if "Pre-Prod No." in df_t.columns:
            df_t["Pre-Prod No."] = (
                df_t["Pre-Prod No."]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.strip()
            )

        if not df_d.empty and "Pre-Prod No." in df_d.columns:
            df_d["Pre-Prod No."] = (
                df_d["Pre-Prod No."]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.strip()
            )
            df_d = df_d.drop(
                columns=[c for c in df_d.columns if c.endswith("_dig")],
                errors="ignore",
            )
            df_d = df_d.loc[:, ~df_d.columns.duplicated()]

            combined = pd.merge(
                df_t.dropna(subset=["Pre-Prod No."]),
                df_d.dropna(subset=["Pre-Prod No."]),
                on="Pre-Prod No.",
                how="outer",
                suffixes=("", "_dig"),
            )
        else:
            combined = df_t

        existing_cols = [c for c in DESIRED_ORDER if c in combined.columns]
        combined = combined[existing_cols]
        combined.to_parquet(parquet_path, index=False)
        return combined

    except Exception as e:
        st.error(f"Load Error. Use Cloud Sync: {e}")
        return pd.DataFrame()


def display_combination_table(key_prefix):
    if os.path.exists(COMBINATIONS_FILE):
        with st.expander("📂 Browse Tube & Cap Combinations", expanded=False):
            try:
                combo_df = pd.read_csv(
                    COMBINATIONS_FILE, sep=";", encoding="utf-8-sig"
                )
                combo_df = clean_column_names(combo_df)
                search = st.text_input(
                    "🔍 Filter List", key=f"{key_prefix}_search"
                )
                if search:
                    combo_df = combo_df[
                        combo_df.apply(
                            lambda r: r.astype(str)
                            .str.contains(search, case=False)
                            .any(),
                            axis=1,
                        )
                    ]

                event = st.dataframe(
                    combo_df,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"{key_prefix}_table",
                )

                if event.selection.rows:
                    sel_row = combo_df.iloc[event.selection.rows[0]].to_dict()
                    st.session_state.selected_combo = {
                        "Diameter": str(sel_row.get("Diameter", "")),
                        "Cap_Lid Style": str(sel_row.get("Cap_Lid Style", "")),
                        "Cap_Lid Diameter": str(
                            sel_row.get("Cap_Lid Diameter", "")
                        ),
                        "Cap_Lid Material": str(
                            sel_row.get("Cap_Lid Material", "")
                        ),
                    }
                    st.toast("✅ Specs Selected")
            except Exception as e:
                st.error(f"Combo Error: {e}")


# --- 5. APP EXECUTION START ---
try:
    df = load_db_v2(TRACKER_ADJ_FILE, DIGITALPREPROD_FILE, FILENAME_PARQUET)
except Exception as e:
    st.error(f"Error loading database: {e}")

if df.empty:
    df = pd.DataFrame(columns=DESIRED_ORDER)

load_mould_assets_data()

st.title("Project Tracker Dashboard")

# DROPDOWN SETUP
DROPDOWN_CONFIG = {
    "Category": "Category.csv",
    "Length": "Length.csv",
    "Material": "Material.csv",
    "Orifice": "Orifice.csv",
    "Diameter": "TubeDia.csv",
    "Foiling": "Foiling.csv",
    "Cap_Lid Style": "Cap_Lid Style.csv",
    "Machine": "Machine.csv",
    "Sales Rep": "Sales Rep.csv",
    "Cap_Lid Material": "Cap_Material.csv",
    "Cap_Lid Diameter": "Cap_Lid Diameter.csv",
}
DROPDOWN_DATA = {k: get_options(v) for k, v in DROPDOWN_CONFIG.items()}
if not df.empty and "Client" in df.columns:
    DROPDOWN_DATA["Client"] = sorted(
        [
            str(c)
            for c in df["Client"].unique()
            if str(c).strip() and str(c).lower() != "nan"
        ]
    )

# NAVIGATION
tabs_list = [
    "🔍 Search & Edit",
    "➕ Add New Job",
    "📊 Detailed Age Analysis",
    "🧪 Trial Trends",
    "🌐 Cloud Sync",
]
tab_nav = st.radio(
    "Navigation",
    tabs_list,
    index=tabs_list.index(st.session_state.active_tab),
    horizontal=True,
)
st.session_state.active_tab = tab_nav

# --- SIDEBAR ---

# --- DASHBOARD INSIGHT METRICS DISPLAY ---
st.markdown("### 📊 Trial Performance Insights")
m_col1, m_col2, m_col3 = st.columns(3)

with m_col1:
    st.metric(label="⏱️ Avg. Turnaround Time", value=avg_days_display)
with m_col2:
    st.metric(label="✅ Total Logged Closures", value=total_completed)
with m_col3:
    st.metric(label="⏳ Open / Active Projects", value=active_backlog)

st.divider()

# --- VALIDATION VIEW PANEL ---
st.markdown("### Trial Turnaround Performance")
if 'df_clean' in locals() and not df_clean.empty and "Days_To_Complete" in df_clean.columns:
    
    # 1. Dynamically find the Description column name if it exists
    desc_col = next((c for c in df_clean.columns if c.lower() in ['description', 'desc']), None)
    
    # 2. Build the display columns list, putting PP # and Description at the front
    preview_cols = []
    if 'PP #' in df_clean.columns:
        preview_cols.append('PP #')
    if desc_col:
        preview_cols.append(desc_col)
        
    # Append the original date logging and metric columns
    for c in [log_col, comp_col, "Days_To_Complete"]:
        if c in df_clean.columns and c not in preview_cols:
            preview_cols.append(c)
            
    # 3. Render the updated dataframe preview
    st.dataframe(
        df_clean[preview_cols].dropna(subset=["Days_To_Complete"]).head(10), 
        use_container_width=True, 
        hide_index=True
    )
else:
    st.info("💡 Data layout processed successfully. Enter a 'Complete' timestamp in your project tracking records to compile active cycle speeds.")

with st.sidebar:
    st.title("Navigation")
    st.page_link(
        "https://injectiontrial-996rcfrtn9rkgafzsejzrn.streamlit.app/",
        label="🧪 Go to Injection Trial App",
        icon="🚀",
    )
    st.divider()
    if st.button("🔄 Rebuild Local DB", use_container_width=True):
        st.cache_data.clear()
        if os.path.exists(FILENAME_PARQUET):
            os.remove(FILENAME_PARQUET)
        st.rerun()

    # --- QUICK PP # DATE LOOKUP (SIDEBAR DISPATCH) ---
    st.markdown("---")
    st.subheader("Quick PP# Date Lookup")
    search_pp = st.text_input("Enter PP Number to view logs:", key="sidebar_pp_search")

    if search_pp:
        results = get_pp_dates("Combined_Weekly_Trials_3_51_2025.csv", search_pp)
        if not results.empty:
            st.dataframe(results, hide_index=True)
        else:
            st.warning(f"No records found for PP # {search_pp}")

# --- TAB 1: SEARCH & EDIT ---
if tab_nav == "🔍 Search & Edit":

    def clear_search():
        st.session_state["search_input_box"] = ""
        st.session_state.last_search_no = ""

    c_s, c_cl = st.columns([4, 1])
    raw_search = c_s.text_input(
        "Search Pre-Prod No.", key="search_input_box"
    ).strip()
    c_cl.button("♻️ Clear", use_container_width=True, on_click=clear_search)

    search_no = pad_preprod_id(raw_search)
    match = (
        df[df["Pre-Prod No."] == search_no] if not df.empty else pd.DataFrame()
    )

    if search_no and not match.empty:
        idx, row = match.index[0], match.iloc[0]
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("👯 Clone Project", use_container_width=True):
                new_clone = row.to_dict()
                new_clone.update(
                    {
                        "Pre-Prod No.": get_next_available_id(
                            search_no, df["Pre-Prod No."]
                        ),
                        "Date": datetime.now().strftime("%d/%m/%Y"),
                    }
                )
                st.session_state.form_data = new_clone
                st.session_state.active_tab = "➕ Add New Job"
                st.rerun()

        with btn_col2:
            if st.checkbox(f"Confirm Delete {search_no}"):
                if st.button(
                    "🗑️ Delete Project", type="primary", use_container_width=True
                ):
                    df = df.drop(idx)
                    save_db(df)
                    st.cache_data.clear()
                    st.rerun()

        display_combination_table("edit")

        st.subheader(f"Editing: {search_no}")
        updated_vals = {}
        sel_combo = st.session_state.get("selected_combo", {})

        status_fields = ["Status", "Open or closed", "Completion date"]
        plate_fields = ["Ordered Plates", "Plates Arrived"]
        proof_fields = [
            "Date Sent on Proof",
            "Proof Approved (Conventional)",
            "Proof Approved (Digital)",
        ]
        trial_fields = [
            "Sent on Trial",
            "Digital trial sent",
            "Revised Artwork After Trialling",
            "Extrusion requested",
            "Extrusion received",
            "Injection trial requested",
            "Injection trial received",
            "Blowmould trial requested",
            "Blowmould trial received",
        ]

        st.markdown("### 📋 General Details")
        edit_cols = st.columns(3)
        excluded = (
            status_fields
            + trial_fields
            + proof_fields
            + plate_fields
            + ["Age Category"]
        )
        remaining_fields = [
            c
            for c in DESIRED_ORDER
            if c not in excluded
            and c != "Pre-Prod No."
            and c not in ["Mould Description", "MouldNumber", "Drawing No."]
        ]

        for i, col in enumerate(remaining_fields):
            cur_val = sel_combo.get(
                col, str(row.get(col, "")).replace("nan", "")
            )
            with edit_cols[i % 3]:
                if "date" in col.lower() or col == "Date":
                    try:
                        d_parsed = pd.to_datetime(
                            cur_val, dayfirst=True, errors="coerce"
                        )
                        d_val = (
                            d_parsed.date()
                            if pd.notnull(d_parsed)
                            else datetime.now().date()
                        )
                    except:
                        d_val = datetime.now().date()
                    d_input = st.date_input(
                        col, value=d_val, key=f"ed_gen_{col}"
                    )
                    updated_vals[col] = d_input.strftime("%d/%m/%Y")
                elif col in DROPDOWN_DATA:
                    opts = sorted(
                        list(set([""] + DROPDOWN_DATA[col] + [cur_val]))
                    )
                    updated_vals[col] = st.selectbox(
                        col,
                        opts,
                        index=opts.index(cur_val),
                        key=f"sel_{col}",
                    )
                else:
                    updated_vals[col] = st.text_input(
                        col, value=cur_val, key=f"txt_{col}"
                    )

        # --- SEARCHABLE MOULD ASSETS ROW (SEARCH & EDIT) ---
        st.divider()
        st.markdown("### 🏗️ Mould Information")
        mould_cols = st.columns(3)

        if hasattr(row, "get"):
            raw_desc = row.get("Mould Description", "")
        elif hasattr(row, "Mould_Description"):
            raw_desc = getattr(row, "Mould_Description")
    
    mould_opts = [""] + st.session_state.mould_descriptions
    
    # =====================================================================
    # FIX: Define the local layout columns for the Injection Molding form
    # =====================================================================
    m_cols = st.columns(3)
    
    # Line 892 (The line currently causing the application crash):
    with m_cols[0]:
        selected_mould_desc = st.selectbox(
            "Mould Description",
            mould_opts,
            key="mould_desc_selector"
        )

        # 1. Initialize the dictionary FIRST
        new_entry = {}

        # 2. Assign the form values to it
        new_entry["Mould Description"] = selected_mould_desc
        # ... other fields like new_entry["Machine Process Settings"], etc.

        # 3. Then append or save it when the button is clicked
        if st.button("Save Trial Data"):
            # Save logic here (e.g., convert to DataFrame, save to parquet/csv)
            st.success("Data saved successfully!")

   # --- SESSION STATE OVERRIDE LOGIC FOR NEW ENTRIES ---
    st.divider()
    st.markdown("### 🏗️ Mould Information")
    
    mould_opts = [""] + st.session_state.mould_descriptions
    
    # =====================================================================
    # FIX: Change from st.columns([1, 1]) to st.columns(3)
    # =====================================================================
    m_cols = st.columns(3) 
    
    # Line 894:
    with m_cols[0]:
        selected_mould_desc = st.selectbox(
            "Mould Description",
            mould_opts,
            index=0,
            key="mould_desc_select_new"
        )
        new_entry["Mould Description"] = selected_mould_desc
    # --- SESSION STATE OVERRIDE LOGIC FOR NEW ENTRIES ---
    if "mould_num_input_new" not in st.session_state:
        st.session_state["mould_num_input_new"] = ""
    if "drawing_input_new" not in st.session_state:
        st.session_state["drawing_input_new"] = ""
    
    # Force update the tracking context fields if a match is picked
    if selected_mould_desc and st.session_state.mould_df is not None:
        lookup_key = selected_mould_desc.replace(" ", "").lower()
        df_lookup = st.session_state.mould_df
        match_rows = df_lookup[df_lookup["_match_key"] == lookup_key]
        
        if not match_rows.empty:
            m_num = str(match_rows.iloc[0].get("MouldNumber", ""))
            m_drw = str(match_rows.iloc[0].get("Drawing No.", ""))
            st.session_state["mould_num_input_new"] = "" if m_num == "nan" else m_num
            st.session_state["drawing_input_new"] = "" if m_drw == "nan" else m_drw
    elif not selected_mould_desc:
        st.session_state["mould_num_input_new"] = ""
        st.session_state["drawing_input_new"] = ""

    with m_cols[1]:
        new_entry["MouldNumber"] = st.text_input("Mould Number", key="mould_num_input_new")
    with m_cols[2]:
        new_entry["Drawing No."] = st.text_input("Drawing No.", key="drawing_input_new")

    if st.button("➕ Create Project", use_container_width=True, type="primary"):
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        save_db(df)
        st.cache_data.clear()
        st.session_state.form_data = {}
        st.success("Project Created Locally!")
        st.rerun()

# --- TAB 3: AGE ANALYSIS ---
elif tab_nav == "📊 Detailed Age Analysis":
    st.subheader("Project Age Distribution")
    if not df.empty and "Age Category" in df.columns:
        st.bar_chart(df["Age Category"].value_counts())
        st.dataframe(
            df[
                [
                    "Pre-Prod No.",
                    "Client",
                    "Project Description",
                    "Age Category",
                ]
            ],
            use_container_width=True,
        )


# --- TAB 4: TRIAL TRENDS ---
elif tab_nav == "🧪 Trial Trends":
    st.subheader("Trial Turnaround Performance")
    
    trial_df = load_trial_data()
    
    if not trial_df.empty:
        # 1. Clean up column names to avoid hidden whitespace issues
        trial_df.columns = [str(c).strip() for c in trial_df.columns]
        
        # 2. Dynamic Calculation Fallback: If 'Days_Taken' isn't in your CSV, calculate it from dates
        if 'Days_Taken' not in trial_df.columns and 'Trial Date' in trial_df.columns and 'Request Date' in trial_df.columns:
            try:
                t_date = pd.to_datetime(trial_df['Trial Date'], dayfirst=True, errors='coerce')
                r_date = pd.to_datetime(trial_df['Request Date'], dayfirst=True, errors='coerce')
                trial_df['Days_Taken'] = (t_date - r_date).dt.days
            except Exception as e:
                st.error(f"Could not calculate turnaround days: {e}")

        # 3. Force conversion to numeric to ensure .mean() doesn't fail on mixed data types
        if 'Days_Taken' in trial_df.columns:
            trial_df['Days_Taken'] = pd.to_numeric(trial_df['Days_Taken'], errors='coerce')

        # 4. Safe calculation of the average metrics
        if 'Days_Taken' in trial_df.columns and not trial_df['Days_Taken'].dropna().empty:
            avg_days = trial_df['Days_Taken'].mean()
            avg_days_str = f"{avg_days:.1f} Days" if not pd.isna(avg_days) else "N/A"
        else:
            avg_days_str = "N/A"
            
        # =====================================================================
        # DEFINE COLUMNS HERE FOR THE TAB 4 LAYOUT
        # =====================================================================
        m_cols = st.columns([1, 1]) # Splitting layout: left for metric, right for distribution chart
        
        with m_cols[0]:
            # 5. Displaying Metrics cleanly in the first column
            st.metric(label="Average Turnaround Time", value=avg_days_str)
        
        with m_cols[1]:
            # Simple rendering fallback for your charts in the second column
            if 'Days_Taken' in trial_df.columns:
                st.markdown("### Turnaround Distribution")
                st.bar_chart(trial_df['Days_Taken'].value_counts())
        
        # This full dataframe print can sit outside the columns across the full width
        st.markdown("---")
        st.dataframe(trial_df, use_container_width=True)
        
    else:
        st.info("No trial data available. Check if Merged_Weekly_Trackers_Layout_Preserved.csv exists.")

# --- TAB 5: CLOUD SYNC ---
elif tab_nav == "🌐 Cloud Sync":
    st.subheader("Google Sheets Sync")

    if st.button("📥 Fetch from Cloud", use_container_width=True):
        with st.spinner("Syncing..."):
            try:
                scope = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ]
                creds_info = st.secrets.get(
                    "gcp_service_account",
                    st.secrets.get("connections", {}).get("gsheets"),
                )

                if isinstance(creds_info, dict) and "private_key" in creds_info:
                    creds_info["private_key"] = creds_info[
                        "private_key"
                    ].replace("\\n", "\n")

                creds = Credentials.from_service_account_info(
                    creds_info, scopes=scope
                )
                client = gspread.authorize(creds)
                ws = client.open_by_key(TRACKER_FILE_ID).get_worksheet(0)
                raw_data = ws.get_all_values()

                if raw_data:
                    new_df = pd.DataFrame(raw_data[1:], columns=raw_data[0])
                    new_df.to_parquet(FILENAME_PARQUET, index=False)
                    st.cache_data.clear()
                    st.success("Fetched successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    st.divider()
    st.subheader("Local Database Preview")

    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "No local data found. Click 'Fetch from Cloud' to download data."
        )


