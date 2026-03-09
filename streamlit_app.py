''' 
This is the work of a Law undergraduate, with elementary coding expertise.
Perplexity AI was used to generate code here, with refinements via further prompting.

This tool is NOT intended to replace reading of cases, and should not be taken as an authoritative source of legal research.
Feel free to use this app as an exploratory tool, without relying entirely on the output generated.
Furthermore, feel free to fork this code and make improvements!

- Kamal
'''

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
            if any(re.search(p, line, re.IGNORECASE) for p in stop_patterns) or not line.strip():
                break
            block.append(line.strip())
        if re.search(start_pattern, line, re.IGNORECASE):
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
    for line in lines[:15]:
        if re.search(r"\b v \b", line) or re.search(r"^Re \b", line, re.IGNORECASE):
            return line
            
    clean_name = os.path.basename(filename)
    clean_name = re.sub(r'^\d+\s*SSAR\/', '', clean_name)
    return clean_name.replace('.pdf', '')

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

# [UPGRADED] Legislation Extraction
def extract_legislation_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Legislation referred to', [
            r'^Quranic verse', r'^Cases? referred to', r'^Issues?', r'^Background'
        ])
    acts = []
    for line in block_lines:
        # Isolate the Act name from the list of comma-separated sections
        match = re.search(r'\b(?:s|ss|section|r|rule|cap)s?\b\s*(.*)', line, re.IGNORECASE)
        
        if match:
            act_part = line[:match.start()].strip()
            sections_part = match.group(1).strip()
            
            # Clean up trailing years / descriptors from the Act name
            act_name_match = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b)", act_part)
            stat = act_name_match.group(1).strip() if act_name_match else act_part
            
            # Split the comma-separated sections
            sections = [sect.strip() for sect in re.split(r',', sections_part) if sect.strip()]
            
            for name in add_short_forms(stat):
                for sect in sections:
                    # Strip all internal spaces so "35 (2) (e)" strictly becomes "35(2)(e)"
                    clean_sect = re.sub(r'\s+', '', sect)
                    acts.append(f"{name} s {clean_sect}")
        else:
            # Fallback if no specific section is mentioned
            act_name_match = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b)", line)
            stat = act_name_match.group(1).strip() if act_name_match else line.strip()
            for name in add_short_forms(stat):
                acts.append(name)
                
    return sorted(set(acts))

# [UPGRADED] Quranic Extraction
def extract_quranic_verses_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Quranic verse\(s\) referred to', [
            r'^Legislation referred to', r'^Cases? referred to', r'^Issues?', r'^Background', r'^At the'
        ])
    verses = []
    for l in block_lines:
        surah_match = re.search(r'Surah\s*(\d+)', l, re.IGNORECASE)
        if surah_match:
            surah_num = surah_match.group(1)
            verse_match = re.search(r'verse[s]?\s*(.*)', l, re.IGNORECASE)
            
            if verse_match:
                verse_part = verse_match.group(1)
                for frag in verse_part.split(','):
                    frag = frag.strip()
                    frag_clean = re.sub(r'[^\d\-\–]', '', frag)
                    if not frag_clean: continue
                    
                    if re.search(r'\d+[–-]\d+', frag_clean):
                        parts = re.split(r'[–-]', frag_clean)
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            verses += [f"{surah_num}:{v}" for v in range(int(parts[0]), int(parts[1])+1)]
                    elif frag_clean.isdigit():
                        verses.append(f"{surah_num}:{frag_clean}")
            else:
                # Fallback for "Surah X:Y" format
                sv_short = re.findall(r'Surah\s*(\d+)\s*[:]\s*(\d+)', l, re.IGNORECASE)
                for s, v in sv_short:
                    verses.append(f"{s}:{v}")
        else:
            sv_short = re.findall(r'(?:Surah\s*)?(\d+)\s*[:]\s*(\d+)', l, re.IGNORECASE)
            for s, v in sv_short:
                verses.append(f"{s}:{v}")
                
    return sorted(set(verses))

# ---------- SEARCH LOGIC ----------

def normalize(s): return re.sub(r'[\s\(\)\[\]\.,:\-]', '', str(s).lower())

# [UPGRADED] Search Legislation 
def search_legislation(df, act_keyword, section_query):
    if df.empty: return []
    
    act_kw_norm = normalize(act_keyword)
    section_clean = re.sub(r'\s+', '', str(section_query))
    
    if not section_clean:
        # Search by Act keyword only if section isn't specified
        def is_match_act(leg_list):
            if not isinstance(leg_list, list): return False
            for leg in leg_list:
                if act_kw_norm in normalize(leg): return True
            return False
        mask = df["Legislation referred"].apply(is_match_act)
        return sorted(df.loc[mask, "Case Name"].unique())
        
    escaped_sec = re.escape(section_clean)
    
    # Matches the exact section and its sub-sections (e.g. 52 matches 52(8)), 
    # but strictly prevents 52 from matching 520 or 52A.
    pattern = re.compile(rf'\bs\s*{escaped_sec}(?!\d|[a-zA-Z])', re.IGNORECASE)

    def is_match(leg_list):
        if not isinstance(leg_list, list): return False
        for leg in leg_list:
            if act_kw_norm in normalize(leg) and pattern.search(leg):
                return True
        return False

    mask = df["Legislation referred"].apply(is_match)
    return sorted(df.loc[mask, "Case Name"].unique())

# [UPGRADED] Search Quran
def search_quranic(df, verse_query):
    if df.empty: return []
    
    nums = re.findall(r'\d+', str(verse_query))
    
    def is_match(q_list):
        if not isinstance(q_list, list): return False
        for v in q_list:
            v_nums = v.split(':')
            
            if len(nums) == 1:
                # User only searched for Surah (e.g., "2")
                if v_nums[0] == nums[0]: return True
            elif len(nums) >= 2:
                # User searched for Surah and Verse (e.g., "2:236")
                if v_nums[0] == nums[0] and v_nums[1] == nums[1]: return True
            else:
                # Text match fallback
                if normalize(verse_query) in normalize(v): return True
                
        return False

    mask = df["Quranic verse(s) referred"].apply(is_match)
    return sorted(df.loc[mask, "Case Name"].unique())

# ---------- SAVE/LOAD/CLEAR ----------

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
    st.rerun()

# ---------- APP MAIN ----------

st.set_page_config(page_title="SSAR Engine", layout="wide")
st.title("SSAR Engine: Visualisation and Search")

# Initialize Session State
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
            try:
                with pdfplumber.open(upl) as pdf:
                    text = "\n".join([page.extract_text() or "" for page in pdf.pages])
                
                headnotes = extract_headnotes(text)
                case_data = {
                    "Case Name": extract_case_name_first_block(text, upl.name),
                    "Year": extract_year(text),
                    "Issues (headnotes)": headnotes,
                    "Topic Groups": assign_topic_groups(headnotes),
                    "Legislation referred": extract_legislation_block(text),
                    "Quranic verse(s) referred": extract_quranic_verses_block(text),
                }
                records.append(case_data)
            except Exception as e:
                st.warning(f"Failed to process {upl.name}: {e}")
                
            progress_bar.progress(int(100 * (idx+1)/len(uploaded_files)))
            
        status_text.text("Done processing.")
        
        if records:
            save_df(pd.DataFrame(records))
            st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH))
            df = st.session_state.df
            st.success(f"Processed and saved {len(df)} cases.")
            st.rerun()
        else:
            st.error("No valid cases were processed.")

if df is not None and not df.empty:
    if st.checkbox("Show full database table"):
        st.dataframe(df)
        
    output = io.BytesIO()
    df.to_excel(output, index=False)
    st.download_button(
        "Download database (.xlsx)", 
        data=output.getvalue(),
        file_name="ssar_cases.xlsx", 
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # ---------- VISUALS ----------
    cntdata = df.explode("Topic Groups").groupby(["Year", "Topic Groups"]).size().reset_index(name="count")
    cntdata["Year"] = pd.to_numeric(cntdata["Year"], errors="coerce")
    cntdata = cntdata.dropna(subset=["Year"])
    cntdata["Year"] = cntdata["Year"].astype(int).astype(str)
    
    if not cntdata.empty:
        st.subheader("📊 Yearly Topic Group Trends: Number of Cases")
        fig1, ax1 = plt.subplots(figsize=(10, 6))
        sns.lineplot(data=cntdata, x="Year", y="count", hue="Topic Groups", marker="o", ax=ax1)
        st.pyplot(fig1)
    
        st.subheader("📊 Yearly Topic Group Trends: Proportion of Cases")
        prop_data = cntdata.copy()
        totals = prop_data.groupby("Year")["count"].transform("sum")
        prop_data["proportion"] = prop_data["count"] / totals
        
        fig2, ax2 = plt.subplots(figsize=(10, 6))
        sns.lineplot(data=prop_data, x="Year", y="proportion", hue="Topic Groups", marker="o", ax=ax2)
        st.pyplot(fig2)

    all_topics = [t for sublist in df["Topic Groups"] for t in sublist]
    if all_topics:
        topic_df = pd.DataFrame(all_topics, columns=["Topic"])
        st.subheader("📊 Topic Group Distribution")
        fig3, ax3 = plt.subplots(figsize=(10, 6))
        sns.countplot(data=topic_df, y="Topic", order=topic_df["Topic"].value_counts().index, ax=ax3)
        st.pyplot(fig3)

    # ---------- SEARCH BAR ----------
    st.subheader("🔍 Search Cases")
    col1, col2 = st.columns(2)
    with col1:
        keywords = st.text_input("Act name/short form", "AMLA")
        section = st.text_input("Section (e.g. 52, 52(8))", "")
        if keywords or section:
            results = search_legislation(df, keywords, section)
            st.write(results if results else "No matches found.")
            
    with col2:
        verse = st.text_input("Quranic Verse (Surah:Verse)", "")
        if verse:
            quranic_results = search_quranic(df, verse)
            st.write(quranic_results if quranic_results else "No matches found.")
else:
    st.info("No database loaded. Please upload PDFs.")

st.markdown("""
---
This application was developed by a Law undergraduate with basic coding skills.
Perplexity AI was used for code generation, further refined through additional prompting.

**Disclaimer:** This tool is provided for academic and exploratory purposes only.  
It does **not** replace reading primary legal sources, and should **not** be considered authoritative legal advice or relied upon for any official or professional matter.

Case Topic Groupings are based on arbitrarily-set catchwords, and may be prone to under/over-counting. See my GitHub page for the full code.

Legislation and Quranic verse searches are more objective, based on a fixed citation format, and are potentially more reliable.

Feel free to use, fork, or improve this tool!

— Kamal Ashraf
""")
