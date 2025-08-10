import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
import matplotlib.pyplot as plt
import seaborn as sns

# ---------- CONSTANTS ----------
ISSUE_TOPICS = {
    "Divorce Grounds": ["talak","fasakh","khuluk","nusyuz","irretrievable breakdown",
                        "judicial separation","taklik","pronouncement","divorce",
                        "fault","reconciliation","nullity","consent order","bain","rajii"],
    "Matrimonial Asset Division": ["division","apportion","matrimonial asset","matrimonial property",
                                   "property","assets","cpf","hdb","sale of flat","valuation",
                                   "uplift","refund","ownership","net sale proceeds","structured approach",
                                   "direct financial","indirect contribution","asset pool"],
    "Child Matters": ["custody","care and control","access","maintenance (child)","parenting",
                      "joint custody","variation of custody","hadhanah","wilayah",
                      "school","accommodation","child maintenance","welfare",
                      "guardianship","minor child","children"],
    "Jurisdiction": ["jurisdiction","forum","appeal board powers","court jurisdiction",
                     "s 35","section 35","s 526","legal capacity","variation","procedural","intervener"],
    "Marriage": ["marriage","wali","nikah","consent","registration",
                 "polygamy","remarry","solemnisation","validation","dissolution"]
}
SHORTFORM_MAP = {"Administration of Muslim Law Act": "AMLA", "Women’s Charter": "WC", "Women's Charter": "WC"}
DATA_PATH = "case_data.pkl"

# ---------- EXTRACT HELPERS ----------
def extract_case_name_first_block(text, filename):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:7]:
        if re.match(r"^[A-Z]{2,} v [A-Z]{2,}$", line) or (line.startswith("Re ") and re.match(r"^Re [A-Z]{2,}$", line)):
            return line
    return os.path.splitext(filename)[0]

def extract_year(text):
    years = re.findall(r"(20\d{2}|19\d{2})", text)
    return int(years[0]) if years else None

def extract_headnotes(text):
    lines = text.split('\n')[:160]
    headnotes = []
    for line in lines:
        if re.search(r'[—–-]', line):
            for item in re.split(r'[—–-]', line):
                cleaned = item.strip()
                if cleaned and len(cleaned.split()) > 2:
                    headnotes.append(cleaned)
    return sorted(set(headnotes))

def assign_topic_groups(headnotes):
    assigned = set()
    for h in headnotes:
        for group, keywords in ISSUE_TOPICS.items():
            if any(k.lower() in h.lower() for k in keywords):
                assigned.add(group)
    return sorted(assigned) if assigned else ["Other"]

# simple stubs for these to avoid crashes
def extract_legislation_block(text): return []
def extract_cases_referred_block(text): return []
def extract_quranic_verses_block(text): return []
def extract_main_body(text): return text

# ---------- SEARCH ----------
def normalize(s): return re.sub(r'[\s\(\)\[\]\.,:\-]', '', str(s).lower())
def search_legislation_section_strict(df,k,sec):
    section_clean=str(sec)
    keywords=[normalize(k) for k in ([k] if isinstance(k,str) else k)]
    pat = re.compile(rf'(s|ss|section)\s*{re.escape(section_clean)}', re.I)
    mask=df["Legislation referred"].apply(lambda lst: any(any(k in normalize(leg) and pat.search(leg) for k in keywords) for leg in lst))
    return sorted(df.loc[mask,"Case Name"])
def search_legislation_exact_subsection(df,k,subsec):
    pat = re.compile(rf'(s|ss|section)\s*{re.escape(subsec)}', re.I)
    keywords=[normalize(k) for k in ([k] if isinstance(k,str) else k)]
    mask=df["Legislation referred"].apply(lambda lst: any(any(k in normalize(leg) and pat.search(leg) for k in keywords) for leg in lst))
    return sorted(df.loc[mask,"Case Name"])
def search_quranic(df,verse_query):
    verse_norm=normalize(verse_query)
    mask=df["Quranic verse(s) referred"].apply(lambda lst: any(verse_norm==normalize(v) for v in lst))
    return sorted(df.loc[mask,"Case Name"])

# ---------- SAVE/LOAD ----------
def save_df(df): df.to_pickle(DATA_PATH)
@st.cache_data(show_spinner=False)
def load_df_cached(): return pd.read_pickle(DATA_PATH) if os.path.exists(DATA_PATH) else None
def clear_database():
    if os.path.exists(DATA_PATH): os.remove(DATA_PATH)
    st.session_state.df = None
    st.success("Database cleared.")
    st.rerun()

# ---------- APP ----------
st.set_page_config(page_title="Syariah Appeal Case Search", layout="wide")
if "df" not in st.session_state:
    st.session_state.df = load_df_cached()
df = st.session_state.df

st.title("Syariah Appeal Board Case Database")

# Management
with st.expander("Database Management"):
    if st.button("Clear Database"): clear_database()

# Upload
with st.expander("Upload PDFs", expanded=(df is None)):
    uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        records=[]
        progress_bar=st.progress(0)
        status_text=st.empty()
        for idx, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing {uploaded_file.name}...")
            with pdfplumber.open(uploaded_file) as pdf:
                text="\n".join([page.extract_text() or "" for page in pdf.pages])
            case_data={
                "Case Name": extract_case_name_first_block(text, uploaded_file.name),
                "Year": extract_year(text),
                "Issues (headnotes)": extract_headnotes(text),
                "Topic Groups": assign_topic_groups(extract_headnotes(text)),
                "Legislation referred": extract_legislation_block(text),
                "Cases referred to": extract_cases_referred_block(text),
                "Quranic verse(s) referred": extract_quranic_verses_block(text),
                "Main Body": extract_main_body(text)
            }
            records.append(case_data)
            progress_bar.progress(int(100*(idx+1)/len(uploaded_files)))
        status_text.text("Done.")
        save_df(pd.DataFrame(records))
        st.session_state.df = load_df_cached()
        df = st.session_state.df
        st.success(f"Processed and saved {len(df)} cases.")

# Show DB and search if DF exists (even empty)
if df is not None:
    if not df.empty:
        if st.checkbox("Show full database table"):
            st.dataframe(df)
        # Download
        excel_data = io.BytesIO()
        df.to_excel(excel_data,index=False)
        st.download_button("Download database (.xlsx)", data=excel_data.getvalue(),
                           file_name="ssar_cases.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        # Visuals (skip if no Year/Topics)
        if "Year" in df and "Topic Groups" in df:
            cntdata=df.explode("Topic Groups").groupby(["Year","Topic Groups"]).size().reset_index(name="count")
            if not cntdata.empty:
                st.subheader("📊 Yearly Topic Group Trends: Number of Cases")
                plt.figure(figsize=(10,6))
                sns.lineplot(data=cntdata,x="Year",y="count",hue="Topic Groups",marker="o")
                st.pyplot(plt.gcf()); plt.clf()
    # Search tools (always available if df exists)
    st.subheader("🔍 Search Cases")
    col1,col2=st.columns(2)
    with col1:
        keywords=st.text_input("Act name/short form","AMLA")
        section=st.text_input("Section (e.g. 52, 52(8))","")
        if section:
            if "(" in section:
                results=search_legislation_exact_subsection(df,keywords,section)
            else:
                results=search_legislation_section_strict(df,keywords,section)
            st.write(results if results else "No matches found.")
    with col2:
        verse=st.text_input("Quranic Verse (Surah:Verse)","")
        if verse:
            results=search_quranic(df,verse)
            st.write(results if results else "No matches found.")
else:
    st.info("No database found. Please upload PDFs.")
