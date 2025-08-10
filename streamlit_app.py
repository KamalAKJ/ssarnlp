import streamlit as st
import pandas as pd
import pdfplumber
import re, io, os, matplotlib.pyplot as plt, seaborn as sns
from datetime import datetime

# ---------------- Constants ----------------
ISSUE_TOPICS = {
    "Divorce Grounds": ["talak","fasakh","khuluk","nusyuz","irretrievable breakdown","judicial separation","taklik",
                        "pronouncement","divorce","fault","reconciliation","nullity","consent order","bain","rajii"],
    "Matrimonial Asset Division": ["division","apportion","matrimonial asset","matrimonial property","property","assets",
                                   "cpf","hdb","sale of flat","valuation","uplift","refund","ownership","net sale proceeds",
                                   "structured approach","direct financial","indirect contribution","asset pool"],
    "Child Matters": ["custody","care and control","access","maintenance (child)","parenting","joint custody",
                      "variation of custody","hadhanah","wilayah","school","accommodation","child maintenance",
                      "welfare","guardianship","minor child","children"],
    "Jurisdiction": ["jurisdiction","forum","appeal board powers","court jurisdiction","s 35","section 35","s 526",
                     "legal capacity","variation","procedural","intervener"],
    "Marriage": ["marriage","wali","nikah","consent","registration","polygamy","remarry","solemnisation",
                 "validation","dissolution"]
}
SHORTFORM_MAP = {"Administration of Muslim Law Act": "AMLA", "Women’s Charter": "WC", "Women's Charter": "WC"}
DATA_PATH = "case_data.pkl"

# ---------------- Extraction helpers ----------------
def extract_case_name_first_block(text, filename):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:10]:
        if re.match(r"^[A-Z]{2,} v [A-Z]{2,}$", line):
            return line
        if line.startswith("Re ") and re.match(r"^Re [A-Z]{2,}$", line):
            return line
    return os.path.splitext(filename)[0]

def extract_year(text):
    years = re.findall(r"(20\d{2}|19\d{2})", text)
    return int(years[0]) if years else None

def extract_headnotes(text):
    lines = text.split('\n')[:160]
    out = []
    for line in lines:
        if re.search(r'[—–-]', line):
            for item in re.split(r'[—–-]', line):
                cleaned = item.strip()
                if cleaned and len(cleaned.split()) > 2 and not cleaned.lower().startswith("syariah appeal board"):
                    out.append(cleaned)
    return sorted(set(out))

def assign_topic_groups(headnotes):
    assigned = set()
    for h in headnotes:
        for group, keywords in ISSUE_TOPICS.items():
            if any(k.lower() in h.lower() for k in keywords):
                assigned.add(group)
    return sorted(assigned) if assigned else ["Other"]

def extract_legislation_block(text): return []
def extract_cases_referred_block(text): return []
def extract_quranic_verses_block(text): return []
def extract_main_body(text): return text

# ---------------- Search helpers ----------------
def normalize(s): return re.sub(r'[\s\(\)\[\]\.,:\-]', '', str(s).lower())

def search_legislation_section_strict(df,k,sec):
    section_clean = str(sec)
    keywords = [normalize(k) for k in ([k] if isinstance(k,str) else k)]
    pat = re.compile(rf'(s|ss|section)\s*{re.escape(section_clean)}', re.I)
    mask = df["Legislation referred"].apply(lambda lst: any(any(k in normalize(leg) and pat.search(leg) for k in keywords) for leg in lst))
    return sorted(df.loc[mask,"Case Name"])

def search_legislation_exact_subsection(df,k,subsec):
    pat = re.compile(rf'(s|ss|section)\s*{re.escape(subsec)}', re.I)
    keywords = [normalize(k) for k in ([k] if isinstance(k,str) else k)]
    mask = df["Legislation referred"].apply(lambda lst: any(any(k in normalize(leg) and pat.search(leg) for k in keywords) for leg in lst))
    return sorted(df.loc[mask,"Case Name"])

def search_quranic(df,verse_query):
    verse_norm = normalize(verse_query)
    mask = df["Quranic verse(s) referred"].apply(lambda lst: any(verse_norm == normalize(v) for v in lst))
    return sorted(df.loc[mask,"Case Name"])

# ---------------- Save/Load/Clear ----------------
def save_df(df):
    df.to_pickle(DATA_PATH)

@st.cache_data(show_spinner=False)
def load_df_cached(file_mtime=None):
    if os.path.exists(DATA_PATH):
        return pd.read_pickle(DATA_PATH)
    return None

def clear_database():
    if os.path.exists(DATA_PATH):
        os.remove(DATA_PATH)
    st.session_state.df = None
    st.cache_data.clear()
    st.cache_resource.clear()
    st.success("Database cleared.")
    st.rerun()

# ---------------- APP ----------------
st.set_page_config(page_title="Syariah Appeal Case Search", layout="wide")
st.title("Syariah Appeal Board Case Database")

if "df" not in st.session_state:
    st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH) if os.path.exists(DATA_PATH) else None)
df = st.session_state.df

with st.expander("Database Management"):
    if st.button("Clear Database"):
        clear_database()

# --- Upload ---
with st.expander("Upload PDFs", expanded=(df is None)):
    uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        records = []
        progress = st.progress(0)
        status = st.empty()
        for idx, upl in enumerate(uploaded_files):
            status.text(f"Processing {upl.name}...")
            with pdfplumber.open(upl) as pdf:
                text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            case_data = {
                "Case Name": extract_case_name_first_block(text, upl.name),
                "Year": extract_year(text),
                "Issues (headnotes)": extract_headnotes(text),
                "Topic Groups": assign_topic_groups(extract_headnotes(text)),
                "Legislation referred": extract_legislation_block(text),
                "Cases referred to": extract_cases_referred_block(text),
                "Quranic verse(s) referred": extract_quranic_verses_block(text),
                "Main Body": extract_main_body(text)
            }
            records.append(case_data)
            progress.progress(int(100*(idx+1)/len(uploaded_files)))
        status.text("Done.")
        save_df(pd.DataFrame(records))
        st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH))
        df = st.session_state.df
        if df is not None:
            st.success(f"Processed and saved {len(df)} cases.")
        else:
            st.error("No cases were processed.")

# --- Display & Search ---
if df is not None:
    if not df.empty and st.checkbox("Show full database table"):
        st.dataframe(df)
    if not df.empty:
        # download
        out = io.BytesIO()
        df.to_excel(out, index=False)
        st.download_button("Download database (.xlsx)", data=out.getvalue(),
                           file_name="ssar_cases.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        # visuals
        cntdata = df.explode("Topic Groups").groupby(["Year","Topic Groups"]).size().reset_index(name="count")
        if not cntdata.empty:
            st.subheader("📊 Yearly Topic Group Trends")
            plt.figure(figsize=(10,6))
            sns.lineplot(data=cntdata, x="Year", y="count", hue="Topic Groups", marker="o")
            st.pyplot(plt.gcf()); plt.clf()
        # search
    st.subheader("🔍 Search Cases")
    c1, c2 = st.columns(2)
    with c1:
        keywords = st.text_input("Act name/short form", "AMLA")
        section = st.text_input("Section")
        if section:
            if "(" in section:
                st.write(search_legislation_exact_subsection(df, keywords, section) or "No matches found.")
            else:
                st.write(search_legislation_section_strict(df, keywords, section) or "No matches found.")
    with c2:
        verse = st.text_input("Quranic Verse (e.g. 2:282)")
        if verse:
            st.write(search_quranic(df, verse) or "No matches found.")
else:
    st.info("No database loaded. Please upload PDFs.")
