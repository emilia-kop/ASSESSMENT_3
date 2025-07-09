import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st 
import os

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]  

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

client = gspread.authorize(credentials)

SHEET_ID = "1upIq9XxNUhR4Uo1iC0fPtJqDCqDizX5HoQKoEOuzFqM"
sheet = client.open_by_key(SHEET_ID)

st.title("COST ESTIMATOR (Tinkering, R&R, Painting)")

# Read each worksheet
ws_paint = sheet.worksheet("DATABASE_PAINT")
ws_lab = sheet.worksheet("DATABASE_LAB")
ws_tink = sheet.worksheet("TINKERING")
ws_rnr = sheet.worksheet("R&R")

# Handle potentially bad headers for LABOUR sheet
def clean_headers(data):
    headers = data[0]
    fixed_headers = []
    seen = set()
    for i, h in enumerate(headers):
        h_clean = h.strip().upper() if h.strip() else f"COL_{i}"
        suffix = 1
        base = h_clean
        while h_clean in seen:
            h_clean = f"{base}_{suffix}"
            suffix += 1
        seen.add(h_clean)
        fixed_headers.append(h_clean)
    return fixed_headers


def load_paint_data():
    return pd.DataFrame(ws_paint.get_all_records())

@st.cache_data(ttl=300)
def load_labour_data():
    data = ws_lab.get_all_values()
    headers = clean_headers(data)
    return pd.DataFrame(data[1:], columns=headers)

@st.cache_data(ttl=300)
def load_tinkering_data():
    return pd.DataFrame(ws_tink.get_all_values())

@st.cache_data(ttl=300)
def load_rnr_data():
    return pd.DataFrame(ws_rnr.get_all_values())

# Load all data
df_paint = load_paint_data()
df_labour = load_labour_data()
df_tinkering = load_tinkering_data()
df_rnr = load_rnr_data()

st.write("LABOUR COLUMNS:", df_labour.columns.tolist())


# Drop fully empty rows
for df in [df_paint, df_labour, df_tinkering, df_rnr]:
    df.dropna(how='all', inplace=True)

# Standardize column names
if not df_paint.empty:
    df_paint.columns = df_paint.columns.str.strip().str.upper()
if not df_labour.empty:
    df_labour.columns = df_labour.columns.str.strip().str.upper()
df_tinkering.iloc[:, 0] = df_tinkering.iloc[:, 0].astype(str).str.strip().str.upper()
df_rnr.iloc[:, 0] = df_rnr.iloc[:, 0].astype(str).str.strip().str.upper()

# Convert YEAR columns to string for consistency
if "YEAR" in df_paint.columns:
    df_paint["YEAR"] = df_paint["YEAR"].astype(str)
if "YEAR" in df_labour.columns:
    df_labour["YEAR"] = df_labour["YEAR"].astype(str)

# Extract parts list from tinkering and R&R
tinkering_parts = df_tinkering.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
rnr_parts = df_rnr.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()



# Continue your original app logic from here...


labour_parts = [col for col in df_labour.columns if col not in ["MAKER", "MODEL", "YEAR", "CITY"]]
valid_parts = sorted(set(labour_parts))

makers = sorted(set(df_paint["MAKER"]) | set(df_labour["MAKER"]))
selected_maker = st.selectbox("🚗 Select Car Maker", makers)

model = sorted(set(df_paint[df_paint["MAKER"] == selected_maker]["MODEL"]).union(
    df_labour[df_labour["MAKER"] == selected_maker]["MODEL"]
))
selected_model = st.selectbox("🚙 Select Car Model", model)

years = sorted(set(
    df_paint[(df_paint["MODEL"] == selected_model)]["YEAR"]
).union(
    df_labour[(df_labour["MODEL"] == selected_model)]["YEAR"]
), reverse=True)
selected_year = st.selectbox("📆 Select Schedule Year", years)

cities = sorted(set(df_paint["CITY"]) | set(df_labour["CITY"]))
selected_city = st.selectbox("📍 Select City", cities)

paint_types = sorted(df_paint["W_METALLIC/SOLID"].dropna().unique())
selected_paint_type = st.selectbox("🎨 Select Paint Type", paint_types)

garage_type = st.radio("🏭 Select Garage Type", ["A", "B", "C", "D"])
st.subheader("🧹 Select Damaged Parts")

selected_parts_list = st.multiselect(
    "🔧 Choose parts from database",
    options=valid_parts,
    help="Start typing to search from known parts",
    key="part_selector"
)

if "manual_parts_df" not in st.session_state:
    st.session_state.manual_parts_df = pd.DataFrame(columns=[
        "Part", "Disc%", "R&R?", "Cost(optional)_R&R", "Tinkering?", "Cost(optional)_Tinkering"
    ])

def safe_float(val, fallback=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return fallback

if selected_parts_list:
    existing_df = st.session_state.manual_parts_df
    new_rows = []
    for part in selected_parts_list:
        if part not in existing_df["Part"].values:
            new_rows.append({
                "Part": part,
                "Disc%": 0.0,
                "R&R?": "Yes",
                "Cost(optional)_R&R": 0.0,
                "Tinkering?": "Yes",
                "Cost(optional)_Tinkering": 0.0
            })

    updated_df = pd.concat([existing_df, pd.DataFrame(new_rows)], ignore_index=True)
    updated_df = updated_df[updated_df["Part"].isin(selected_parts_list)].reset_index(drop=True)

    updated_df["Disc%"] = updated_df["Disc%"].apply(safe_float)
    updated_df["Cost(optional)_R&R"] = updated_df["Cost(optional)_R&R"].apply(safe_float)
    updated_df["Cost(optional)_Tinkering"] = updated_df["Cost(optional)_Tinkering"].apply(safe_float)

    user_parts_df = st.data_editor(
        updated_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Part": st.column_config.TextColumn("Part", disabled=True),
            "Disc%": st.column_config.NumberColumn("Paint Discount (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.0f"),
            "R&R?": st.column_config.SelectboxColumn("R&R?", options=["Yes", "No"]),
            "Cost(optional)_R&R": st.column_config.NumberColumn("Cost(optional)", min_value=0.0, step=0.1),
            "Tinkering?": st.column_config.SelectboxColumn("Tinkering?", options=["Yes", "No"]),
            "Cost(optional)_Tinkering": st.column_config.NumberColumn("Cost(optional)", min_value=0.0, step=0.1)
        },
        key="manual_parts_editor"
    )

    confirm_input = st.checkbox("✅ Confirm Parts and Costs", key="confirm_input")

    if confirm_input:
        st.session_state.manual_parts_df = user_parts_df.copy()

    user_parts_df["Part"] = user_parts_df["Part"].astype(str).str.strip().str.upper()
    selected_parts = user_parts_df[user_parts_df["Part"] != ""]

    if confirm_input and not selected_parts.empty:
        st.markdown("### ✅ Selected Parts")
        st.table(selected_parts[["Part", "Disc%", "R&R?", "Tinkering?"]])

        paint_row = df_paint[
            (df_paint["MAKER"] == selected_maker) &
            (df_paint["MODEL"] == selected_model) &
            (df_paint["YEAR"] == selected_year) &
            (df_paint["CITY"] == selected_city) &
            (df_paint["W_METALLIC/SOLID"] == selected_paint_type)
        ]

        labour_row = df_labour[
            (df_labour["MAKER"] == selected_maker) &
            (df_labour["MODEL"] == selected_model) &
            (df_labour["YEAR"] == selected_year) &
            (df_labour["CITY"] == selected_city)
        ]

        if paint_row.empty or labour_row.empty:
            st.error("❌ No matching data found for the selected inputs.")
        else:
            paint_row = paint_row.iloc[0].copy()
            labour_row = labour_row.iloc[0].copy()
            paint_row.index = paint_row.index.str.strip().str.upper()
            labour_row.index = labour_row.index.str.strip().str.upper()

            results = []
            total_painting = 0.0
            total_tinkering = 0.0
            total_rnr = 0.0

            for _, row in selected_parts.iterrows():
                part = row["Part"].strip().upper()
                custom_discount = safe_float(row.get("Disc%", 0)) / 100
                paint_schedule = safe_float(paint_row.get(part, 0))
                base_cost = safe_float(labour_row.get(part, 0))
                paint_cost = paint_schedule * custom_discount

                tinkering_cost = 0
                if row.get("Tinkering?") == "Yes":
                    tinkering_cost = safe_float(row.get("Cost(optional)_Tinkering"))
                    if tinkering_cost == 0 and part in tinkering_parts:
                        tinkering_cost = base_cost * 3300

                rnr_cost = 0
                if row.get("R&R?") == "Yes":
                    rnr_cost = safe_float(row.get("Cost(optional)_R&R"))
                    if rnr_cost == 0 and part in rnr_parts:
                        rnr_cost = base_cost * 3300

                total_tinkering += tinkering_cost
                total_rnr += rnr_cost
                total_painting += paint_cost

                results.append({
                    "Description": part,
                    "R&R": round(rnr_cost, 2),
                    "Tinkering": round(tinkering_cost, 2),
                    "Painting": round(paint_cost, 2),
                    "Disc %": round(custom_discount * 100, 2),
                    "Schedule": round(paint_schedule, 2)
                })

            final_df = pd.DataFrame(results)
            final_df.index = range(1, len(final_df) + 1)
            final_df.index.name = "S.No"

            st.markdown("### 💰 Final Estimate")
            st.dataframe(final_df, use_container_width=True)

            st.subheader("🧾 Summary")
            summary_df = pd.DataFrame([
                {
                    "Description": "Sub Total",
                    "R&R": round(total_rnr, 2),
                    "Tinkering": round(total_tinkering, 2),
                    "Painting": round(total_painting, 2)
                },
                {
                    "Description": "Grand Total",
                    "R&R": "",
                    "Tinkering": "",
                    "Painting": round(total_rnr + total_tinkering + total_painting, 2)
                }
            ])
            st.table(summary_df)
else:
    st.info("ℹ️ Please select parts to begin.")
