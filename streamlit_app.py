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

# ---------- CONSTANTS ----------
SHORTFORM_MAP = {
    "Administration of Muslim Law Act": "AMLA",
    "Women’s Charter": "WC",
    "Women's Charter": "WC"
}

# Changed the database name slightly to avoid loading your older, heavier database file by mistake
DATA_PATH = "ssar_lite_data.pkl" 

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
        # KILL SWITCH: Stop scanning if we reach the citations section
        if re.match(r"^case\(s\)\s+referred\s+to", line, re.IGNORECASE):
            break
            
        # STRICT REGEX: Only match standard initialed case names (e.g., "FS v FT")
        if re.match(r"^[A-Z]{2,}\s+v\s+[A-Z]{2,}$", line):
            return line
        if re.match(r"^Re\s+[A-Z]{2,}$", line, re.IGNORECASE):
            return line

    # FALLBACK: Sanitize the highly-accurate uploaded filename
    clean_name = os.path.basename(filename)
    clean_name = os.path.splitext(clean_name)[0]
    # Remove any leading directory paths (e.g., "9 SSAR/")
    clean_name = re.sub(r'^\d+\s*SSAR[\\/]', '', clean_name)
    return clean_name.strip()

def extract_year(text):
    years = re.findall(r"(20\d{2}|19\d{2})", text)
    return int(years[0]) if years else None

# [ENHANCED] Advanced Legislation Extraction
def extract_legislation_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Legislation referred to', [
            r'^Quranic verse', r'^Cases? referred to', r'^Issues?', r'^Background'
        ])
    acts = []
    for line in block_lines:
        match = re.search(r'\b(?:s|ss|section|r|rule|cap)s?\b\s*(.*)', line, re.IGNORECASE)
        
        if match:
            act_part = line[:match.start()].strip()
            sections_part = match.group(1).strip()
            
            act_name_match = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b)", act_part)
            stat = act_name_match.group(1).strip() if act_name_match else act_part
            
            sections = [sect.strip() for sect in re.split(r',|and', sections_part) if sect.strip()]
            
            for name in add_short_forms(stat):
                for sect in sections:
                    clean_sect = re.sub(r'\s+', '', sect)
                    if clean_sect:
                        acts.append(f"{name} s {clean_sect}")
        else:
            act_name_match = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b)", line)
            stat = act_name_match.group(1).strip() if act_name_match else line.strip()
            for name in add_short_forms(stat):
                acts.append(name)
                
    return sorted(set(acts))

# [ENHANCED] Advanced Quranic Extraction
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
                for frag in re.split(r',|and', verse_part):
                    frag_clean = re.sub(r'[^\d\-\–]', '', frag.strip())
                    if not frag_clean: continue
                    
                    if re.search(r'\d+[–-]\d+', frag_clean):
                        parts = re.split(r'[–-]', frag_clean)
                        if len(parts) == 2:
                            verses += [f"{surah_num}:{v}" for v in range(int(parts[0]), int(parts[1])+1)]
                    elif frag_clean.isdigit():
                        verses.append(f"{surah_num}:{frag_clean}")
            else:
                sv_short = re.findall(r'Surah\s*(\d+)\s*[:]\s*(\d+)', l, re.IGNORECASE)
                for s, v in sv_short:
                    verses.append(f"{s}:{v}")
        else:
            sv_short = re.findall(r'(\d+)\s*[:]\s*(\d+)', l, re.IGNORECASE)
            for s, v in sv_short:
                verses.append(f"{s}:{v}")
                
    return sorted(set(verses))

# ---------- SEARCH LOGIC ----------

def normalize(s): return re.sub(r'[\s\(\)\[\]\.,:\-]', '', str(s).lower())

def search_legislation(df, act_keyword, section_query):
    if df.empty: return []
    
    act_kw_norm = normalize(act_keyword)
    section_clean = re.sub(r'\s+', '', str(section_query))
    
    if not section_clean:
        def is_match_act(leg_list):
            return any(act_kw_norm in normalize(leg) for leg in leg_list) if isinstance(leg_list, list) else False
        mask = df["Legislation referred"].apply(is_match_act)
        return sorted(df.loc[mask, "Case Name"].unique())
        
    escaped_sec = re.escape(section_clean)
    pattern = re.compile(rf'\bs\s*{escaped_sec}(?!\d|[a-zA-Z])', re.IGNORECASE)

    def is_match(leg_list):
        if not isinstance(leg_list, list): return False
        return any(act_kw_norm in normalize(leg) and pattern.search(leg) for leg in leg_list)

    mask = df["Legislation referred"].apply(is_match)
    return sorted(df.loc[mask, "Case Name"].unique())

def search_quranic(df, verse_query):
    if df.empty: return []
    nums = re.findall(r'\d+', str(verse_query))
    
    def is_match(q_list):
        if not isinstance(q_list, list): return False
        for v in q_list:
            v_parts = v.split(':')
            if len(nums) == 1 and v_parts[0] == nums[0]: 
                return True
            if len(nums) >= 2 and v_parts[0] == nums[0] and v_parts[1] == nums[1]: 
                return True
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

st.set_page_config(page_title="SSAR Reference Engine", layout="wide")
st.title("SSAR Legislation & Quranic Reference Engine")
st.markdown("A focused tool to extract and search statutory and religious citations from Syariah Court cases.")

if "df" not in st.session_state:
    st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH) if os.path.exists(DATA_PATH) else None)

df = st.session_state.df

with st.expander("Database Management"):
    if st.button("Clear Database"):
        clear_database()

with st.expander("Upload PDFs", expanded=(df is None)):
    uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        if st.button("Process Uploaded Files"): 
            records = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, upl in enumerate(uploaded_files):
                status_text.text(f"Processing {upl.name}...")
                try:
                    with pdfplumber.open(upl) as pdf:
                        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
                    
                    records.append({
                        "Case Name": extract_case_name_first_block(text, upl.name),
                        "Year": extract_year(text),
                        "Legislation referred": extract_legislation_block(text),
                        "Quranic verse(s) referred": extract_quranic_verses_block(text),
                    })
                except Exception as e:
                    st.warning(f"Error in {upl.name}: {e}")
                progress_bar.progress(int(100 * (idx+1)/len(uploaded_files)))
                
            status_text.text("Done processing.")
            
            if records:
                save_df(pd.DataFrame(records))
                st.session_state.df = load_df_cached(os.path.getmtime(DATA_PATH))
                df = st.session_state.df
                st.success(f"Processed and saved {len(df)} cases. You can now use the search engine below!")

if df is not None and not df.empty:
    
    # --- SEARCH ENGINE UI ---
    st.subheader("🔍 Search Engine")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Legislation Search")
        kw = st.text_input("Act/Statute (e.g., AMLA, WC)", "AMLA")
        sec = st.text_input("Section (e.g., 52, 52(8))", "")
        if kw or sec:
            results = search_legislation(df, kw, sec)
            if results:
                st.success(f"Found {len(results)} matching cases:")
                for r in results:
                    st.markdown(f"- **{r}**")
            else:
                st.warning("No matches found.")
            
    with col2:
        st.markdown("### Quranic Search")
        v = st.text_input("Surah or Surah:Verse (e.g., 2 or 2:236)", "")
        if v:
            q_results = search_quranic(df, v)
            if q_results:
                st.success(f"Found {len(q_results)} matching cases:")
                for r in q_results:
                    st.markdown(f"- **{r}**")
            else:
                st.warning("No matches found.")
                
    st.divider()
    
    # --- DATABASE VIEW ---
    st.subheader("📚 Current Database")
    if st.checkbox("Show full database table"):
        st.dataframe(df)
        
    output = io.BytesIO()
    df.to_excel(output, index=False)
    st.download_button(
        "Download database (.xlsx)", 
        data=output.getvalue(),
        file_name="ssar_reference_cases.xlsx", 
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("No database loaded. Please upload PDFs to begin.")

st.markdown("""
---
This application was developed by a Law undergraduate with basic coding skills.
Perplexity AI was used for code generation, further refined through additional prompting.

**Disclaimer:** This tool is provided for academic and exploratory purposes only.  
It does **not** replace reading primary legal sources, and should **not** be considered authoritative legal advice or relied upon for any official or professional matter.

Legislation and Quranic verse searches are objective, based on a fixed citation format, and are intended to assist in rapid cross-referencing.

Feel free to use, fork, or improve this tool!

— Kamal Ashraf
""")
