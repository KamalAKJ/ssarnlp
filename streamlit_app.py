import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os

# ================= Constants =================
ISSUE_TOPICS = {
    "Divorce Grounds": [
        "talak", "fasakh", "khuluk", "nusyuz", "irretrievable breakdown",
        "judicial separation", "taklik", "pronouncement", "divorce",
        "fault", "reconciliation", "nullity", "consent order", "bain", "rajii"
    ],
    "Matrimonial Asset Division": [
        "division", "apportion", "matrimonial asset", "matrimonial property", "property",
        "assets", "cpf", "hdb", "sale of flat", "valuation", "uplift", "refund", "ownership",
        "net sale proceeds", "structured approach", "direct financial",
        "indirect contribution", "asset pool"
    ],
    "Child Matters": [
        "custody", "care and control", "access", "maintenance (child)", "parenting",
        "joint custody", "variation of custody", "hadhanah", "wilayah",
        "school", "accommodation", "child maintenance", "welfare",
        "guardianship", "minor child", "children"
    ],
    "Jurisdiction": [
        "jurisdiction", "forum", "appeal board powers", "court jurisdiction",
        "s 35", "section 35", "s 526", "legal capacity", "variation", "procedural", "intervener"
    ],
    "Marriage": [
        "marriage", "wali", "nikah", "consent", "registration",
        "polygamy", "remarry", "solemnisation", "validation", "dissolution"
    ]
}
SHORTFORM_MAP = {
    "Administration of Muslim Law Act": "AMLA",
    "Women’s Charter": "WC",
    "Women's Charter": "WC"
}
DATA_PATH = "case_data.pkl"

# ============== Helper Functions (unchanged from your last version) ==============
# [All your extract/search functions here unchanged: extract_case_name_first_block, extract_year, etc.]

# Save / Load / Clear Functions
def save_df(df):
    df.to_pickle(DATA_PATH)

@st.cache_data(show_spinner=False)
def load_df_cached():
    if os.path.exists(DATA_PATH):
        return pd.read_pickle(DATA_PATH)
    return None

def clear_database():
    if "df" in st.session_state:
        del st.session_state.df
    if os.path.exists(DATA_PATH):
        os.remove(DATA_PATH)
    st.session_state.df = None
    st.success("Database cleared. Upload PDFs to create a new one.")

# ============== Streamlit UI ==============
st.set_page_config(page_title="Syariah Appeal Case Search", layout="wide")
st.title("Syariah Appeal Board Case Database")

# Always initialise DF in session_state
if "df" not in st.session_state:
    st.session_state.df = load_df_cached()
df = st.session_state.get("df", None)

# --- Database Management ---
with st.expander("Database Management"):
    if st.button("Clear Database"):
        clear_database()
        df = None

# --- Upload PDFs ---
with st.expander("Upload PDFs (only if you want to update database)", expanded=(df is None)):
    uploaded_files = st.file_uploader("Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        records = []
        for uploaded_file in uploaded_files:
            with pdfplumber.open(uploaded_file) as pdf:
                text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            case_name = extract_case_name_first_block(text, uploaded_file.name)
            year = extract_year(text)
            headnotes = extract_headnotes(text)
            topic_groups = assign_topic_groups(headnotes)
            legislation = extract_legislation_block(text)
            cases_referred = extract_cases_referred_block(text)
            quranic_verses = extract_quranic_verses_block(text)
            main_body = extract_main_body(text)
            records.append({
                "Case Name": case_name,
                "Year": year,
                "Issues (headnotes)": headnotes,
                "Topic Groups": topic_groups,
                "Legislation referred": legislation,
                "Cases referred to": cases_referred,
                "Quranic verse(s) referred": quranic_verses,
                "Main Body": main_body
            })
        # Save and reload so it's optimised for search
        save_df(pd.DataFrame(records))
        st.session_state.df = load_df_cached()
        df = st.session_state.df
        st.success(f"Processed and saved {len(df)} cases.")

# --- Display / Search ---
if df is not None and not df.empty:
    if st.checkbox("Show full database table"):
        st.dataframe(df[["Case Name", "Year", "Topic Groups", 
                         "Legislation referred", "Quranic verse(s) referred"]])

    excel_data = io.BytesIO()
    df.to_excel(excel_data, index=False)
    st.download_button("Download database (.xlsx)", 
                       data=excel_data.getvalue(),
                       file_name="ssar_cases.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("### Search Cases")
    col1, col2 = st.columns(2)
    with col1:
        keywords = st.text_input("Act name/short form", "AMLA")
        section = st.text_input("Section (e.g. 52, 52(8))", "")
        if section:
            if "(" in section:
                results = search_legislation_exact_subsection(df, keywords, section)
            else:
                results = search_legislation_section_strict(df, keywords, section)
            st.write(results if results else "No matches found.")
    with col2:
        verse = st.text_input("Quranic Verse (Surah:Verse, e.g. 2:282)", "")
        if verse:
            results = search_quranic(df, verse)
            st.write(results if results else "No matches found.")
else:
    st.info("No database found. Please upload PDFs to create one.")
