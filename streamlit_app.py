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
                     "s 35","section 35","s 526","legal capacity","variation","procedural","intervener", "forum"],
    "Marriage": ["marriage","wali","nikah","consent","registration",
                 "polygamy","remarry","solemnisation","validation","dissolution"]
}
SHORTFORM_MAP = {
    "Administration of Muslim Law Act": "AMLA",
    "Women’s Charter": "WC",
    "Women's Charter": "WC"
}
DATA_PATH = "case_data.pkl"

# ---------- EXTRACTION HELPERS ----------

def extract_header_window(lines, start_pattern, stop_patterns):
    block, in_block = [], False
    for line in lines:
        if in_block:
            if any(re.match(p, line, re.IGNORECASE) for p in stop_patterns) or not line.strip():
                break
            block.append(line.strip())
        if re.match(start_pattern, line, re.IGNORECASE):
            in_block = True
    return block

def add_short_forms(name):
    out = [name]
    for long, short in SHORTFORM_MAP.items():
        if long in name and short not in name:
            out.append(name.replace(long, short))
    return out

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
    headnotes = []
    for line in lines:
        if re.search(r'[—–-]', line):
            for item in re.split(r'[—–-]', line):
                cleaned = item.strip()
                if cleaned and len(cleaned.split()) > 2 and not cleaned.lower().startswith("syariah appeal board"):
                    headnotes.append(cleaned)
    return sorted(set(headnotes))

def assign_topic_groups(headnotes):
    assigned = set()
    for h in headnotes:
        h_lc = h.lower()
        for group, keywords in ISSUE_TOPICS.items():
            if any(re.search(rf"\b{k}\b", h_lc) for k in keywords):
                assigned.add(group)
    return sorted(assigned) if assigned else ["Other"]

def extract_legislation_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Legislation referred to', [
            r'^Quranic verse', r'^Cases? referred to', r'^Issues?', r'^Background'
        ])
    acts = []
    for line in block_lines:
        m = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b.*?)(?:\([^)]+\))?", line)
        if m:
            stat = m.group(1).strip()
            section_tokens = re.findall(r'(s|ss|section|r|rule|cap)\s*([0-9]{1,4}(?:[A-Za-z]|(?:\([\w]+\))*)*)', line)
            for s_type, sect in section_tokens:
                for s in re.split(r"[,;/]", sect):
                    s = s.strip()
                    if not s: continue
                    for name in add_short_forms(stat):
                        acts.append(f"{name} {s_type} {s}")
        else:
            m2 = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b.*?)", line)
            if m2:
                stat = m2.group(1).strip()
                for name in add_short_forms(stat):
                    acts.append(name)
    return sorted(set(acts))

def extract_quranic_verses_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Quranic verse\(s\) referred to', [
            r'^Legislation referred to', r'^Cases? referred to', r'^Issues?', r'^Background'
        ])
    verses = []
    for l in block_lines:
        surah_matches = re.findall(r'Surah\s*(\d+)', l, re.IGNORECASE)
        for surah in surah_matches:
            for vpart in re.finditer(r'verse[s]?\s*([\d,\-\– ]+)', l, re.IGNORECASE):
                for frag in vpart.group(1).split(','):
                    frag = frag.strip()
                    if re.search(r'\d+[–-]\d+', frag):
                        a, b = re.split(r'[–-]', frag)
                        verses += [f"{surah}:{v}" for v in range(int(a), int(b)+1)]
                    elif frag.isdigit():
                        verses.append(f"{surah}:{frag}")
        sv_short = re.findall(r'Surah\s*(\d+)\s*[:]\s*(\d+)', l, re.IGNORECASE)
        for surah, verse in sv_short:
            verses.append(f"{surah}:{verse}")
    return sorted(set(verses))

def extract_cases_referred_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Cases? referred to', [
            r'^Legislation referred to', r'^Quranic verse', r'^Issues?', r'^Background'
        ])
    cases = []
    for line in block_lines:
        if re.match(r"^[A-Z]{2,} v [A-Z]{2,}", line) or line.startswith("Re "):
            cases.append(line.strip())
        elif re.search(r'SSAR|SGSAB', line):
            cases.append(line.strip())
    return sorted(set(cases))

def extract_main_body(text):
    return text

# ---------- SEARCH ----------
def normalize(s): return re.sub(r'[\s\(\)\[\]\.,:\-]', '', str(s).lower())

def search_legislation_section_strict(df, keywords, section):
    section_clean = str(section)
    keywords = [normalize(k) for k in ([keywords] if isinstance(keywords,str) else keywords)]
    pattern = re.compile(rf'(s|ss|section)\s*{re.escape(section_clean)}', re.IGNORECASE)
    mask = df["Legislation referred"].apply(lambda lst: any(any(k in normalize(leg) and pattern.search(leg) for k in keywords) for leg in lst))
    return sorted(df.loc[mask, "Case Name"])

def search_legislation_exact_subsection(df, keywords, exact_subsection):
    pattern = re.compile(rf'(s|ss|section)\s*{re.escape(exact_subsection)}', re.IGNORECASE)
    keywords = [normalize(k) for k in ([keywords] if isinstance(keywords,str) else keywords)]
    mask = df["Legislation referred"].apply(lambda lst: any(any(k in normalize(leg) and pattern.search(leg) for k in keywords) for leg in lst))
    return sorted(df.loc[mask, "Case Name"])

def search_quranic(df, verse_query):
    verse_norm = normalize(verse_query)
    mask = df["Quranic verse(s) referred"].apply(lambda lst: any(verse_norm == normalize(v) for v in lst))
    return sorted(df.loc[mask, "Case Name"])

# ---------- SAVE/LOAD/CLEAR ----------
def save_df(df): df.to_pickle(DATA_PATH)

@st.cache_data(show_spinner=False)
def load_df_cached(file_mtime=None):
    if os.path.exists(DATA_PATH):
        return pd.read_pickle(DATA_PATH)
    return None

def clear_database():
    if os.path.exists(DATA_PATH): os.remove(DATA_PATH)
    st.session_state.df = None
    st.cache_data.clear()
    st.cache_resource.clear()
    st.success("Database cleared.")
    st.rerun()

# ---------- APP ----------
st.set_page_config(page_title="SSAR Engine", layout="wide")
st.title("SSAR Engine: Visualisation and Search")

if "df" not in st.session_state:
    st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH) if os.path.exists(DATA_PATH) else None)
df = st.session_state.df

with st.expander("Database Management"):
    if st.button("Clear Database"):
        clear_database()

with st.expander("Upload PDFs", expanded=(df is None)):
    uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        records = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        for idx, upl in enumerate(uploaded_files):
            status_text.text(f"Processing {upl.name}...")
            with pdfplumber.open(upl) as pdf:
                text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            case_data = {
                "Case Name": extract_case_name_first_block(text, upl.name),
                "Year": extract_year(text),
                "Issues (headnotes)": extract_headnotes(text),
                "Topic Groups": assign_topic_groups(extract_headnotes(text)),
                "Legislation referred": extract_legislation_block(text),
                "Quranic verse(s) referred": extract_quranic_verses_block(text),
                "Main Body": extract_main_body(text),
                # "Cases referred to" is ONLY for table view, not used in search
                "Cases referred to": extract_cases_referred_block(text)
            }
            records.append(case_data)
            progress_bar.progress(int(100 * (idx+1)/len(uploaded_files)))
        status_text.text("Done.")
        save_df(pd.DataFrame(records))
        st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH))
        df = st.session_state.df
        if df is not None:
            st.success(f"Processed and saved {len(df)} cases.")
        else:
            st.error("No cases were processed.")

if df is not None:
    if not df.empty and st.checkbox("Show full database table"):
        st.dataframe(df)
    if not df.empty:
        output = io.BytesIO()
        df.to_excel(output, index=False)
        st.download_button("Download database (.xlsx)", data=output.getvalue(),
                           file_name="ssar_cases.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        # Visuals
        cntdata = df.explode("Topic Groups").groupby(["Year", "Topic Groups"]).size().reset_index(name="count")
        if not cntdata.empty:
            st.subheader("📊 Yearly Topic Group Trends: Number of Cases")
            plt.figure(figsize=(10,6))
            sns.lineplot(data=cntdata, x="Year", y="count", hue="Topic Groups", marker="o")
            st.pyplot(plt.gcf()); plt.clf()
            st.subheader("📊 Yearly Topic Group Trends: Proportion of Cases")
            prop_data = cntdata.copy()
            totals = prop_data.groupby("Year")["count"].transform("sum")
            prop_data["proportion"] = prop_data["count"] / totals
            plt.figure(figsize=(10,6))
            sns.lineplot(data=prop_data, x="Year", y="proportion", hue="Topic Groups", marker="o")
            st.pyplot(plt.gcf()); plt.clf()
        all_topics = [t for sublist in df["Topic Groups"] for t in sublist]
        if all_topics:
            topic_df = pd.DataFrame(all_topics, columns=["Topic"])
            fig, ax = plt.subplots()
            sns.countplot(data=topic_df, y="Topic", order=topic_df["Topic"].value_counts().index, ax=ax)
            st.subheader("📊 Topic Group Distribution")
            st.pyplot(fig); plt.clf()
        all_legs = [l for sublist in df["Legislation referred"] for l in sublist]
    # SEARCH BAR
    st.subheader("🔍 Search Cases")
    col1, col2 = st.columns(2)
    with col1:
        keywords = st.text_input("Act name/short form", "AMLA")
        section = st.text_input("Section (e.g. 52, 52(8))", "")
        if section:
            if "(" in section:
                st.write(search_legislation_exact_subsection(df, keywords, section) or "No matches found.")
            else:
                st.write(search_legislation_section_strict(df, keywords, section) or "No matches found.")
    with col2:
        verse = st.text_input("Quranic Verse (Surah:Verse)", "")
        if verse:
            st.write(search_quranic(df, verse) or "No matches found.")
else:
    st.info("No database loaded. Please upload PDFs.")
