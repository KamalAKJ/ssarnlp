import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
import matplotlib.pyplot as plt
import seaborn as sns

# ---------------- Constants ----------------
ISSUE_TOPICS = {
    "Divorce Grounds": [...],  # same as before
    "Matrimonial Asset Division": [...],
    "Child Matters": [...],
    "Jurisdiction": [...],
    "Marriage": [...]
}
SHORTFORM_MAP = {
    "Administration of Muslim Law Act": "AMLA",
    "Women’s Charter": "WC",
    "Women's Charter": "WC"
}
DATA_PATH = "case_data.pkl"

# ---------------- Extraction helpers (paste full tested versions here) ----------------
# All your extract_* and search_* functions unchanged from the working version above

# ---------------- Save / Load / Clear ----------------
def save_df(df):
    df.to_pickle(DATA_PATH)

@st.cache_data(show_spinner=False)
def load_df_cached():
    if os.path.exists(DATA_PATH):
        return pd.read_pickle(DATA_PATH)
    return None

def clear_database():
    if os.path.exists(DATA_PATH):
        os.remove(DATA_PATH)
    st.session_state.df = None
    st.success("Database cleared.")
    st.rerun()

# ---------------- App Setup ----------------
st.set_page_config(page_title="Syariah Appeal Case Search", layout="wide")
st.title("Syariah Appeal Board Case Database")

if "df" not in st.session_state:
    st.session_state.df = load_df_cached()

df = st.session_state.df

# ---- Database Management ----
with st.expander("Database Management"):
    if st.button("Clear Database"):
        clear_database()

# ---- Upload PDFs ----
with st.expander("Upload PDFs (to update database)", expanded=(df is None)):
    uploaded_files = st.file_uploader("Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        records = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing {uploaded_file.name}...")
            with pdfplumber.open(uploaded_file) as pdf:
                text = "\n".join([page.extract_text() or "" for page in pdf.pages])

            # --- Extraction ---
            try:
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
            except Exception as e:
                st.warning(f"Error processing {uploaded_file.name}: {e}")

            progress_bar.progress(int(100*(idx+1)/len(uploaded_files)))

        status_text.text("Done.")

        # --- Save + Reload ---
        new_df = pd.DataFrame(records)
        save_df(new_df)
        st.session_state.df = load_df_cached()
        df = st.session_state.df

        if df is not None and not df.empty:
            st.success(f"Processed and saved {len(df)} cases.")
        else:
            st.error("No cases were processed. Please check your PDFs.")

# ---- Display + Download ----
if df is not None and not df.empty:
    if st.checkbox("Show full database table"):
        st.dataframe(df)

    excel_data = io.BytesIO()
    df.to_excel(excel_data, index=False)
    st.download_button("Download database (.xlsx)",
                       data=excel_data.getvalue(),
                       file_name="ssar_cases.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ---- Visualisations ----
    st.subheader("📊 Yearly Topic Group Trends: Number of Cases")
    if "Year" in df and "Topic Groups" in df:
        count_data = df.explode("Topic Groups").groupby(["Year", "Topic Groups"]).size().reset_index(name="count")
        plt.figure(figsize=(10,6))
        sns.lineplot(data=count_data, x="Year", y="count", hue="Topic Groups", marker="o")
        plt.title("Yearly Topic Group Trends: Number of Cases")
        plt.grid(True)
        st.pyplot(plt)

        st.subheader("📊 Yearly Topic Group Trends: Proportion of Cases")
        prop_data = count_data.copy()
        totals = prop_data.groupby("Year")["count"].transform("sum")
        prop_data["proportion"] = prop_data["count"] / totals
        plt.figure(figsize=(10,6))
        sns.lineplot(data=prop_data, x="Year", y="proportion", hue="Topic Groups", marker="o")
        plt.title("Yearly Topic Group Trends: Proportion of Cases")
        plt.grid(True)
        st.pyplot(plt)

    # ---- Search ----
    st.subheader("🔍 Search Cases")
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
