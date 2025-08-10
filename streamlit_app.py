pip install streamlit pdfplumber pandas openpyxl

import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# ==== 1. Topic Groupings ====
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
# ==== Helper functions ====
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
    start = next((i for i, line in enumerate(lines[:30])
        if "SYARIAH APPEALS REPORTS" in line or ("SSAR" in line and "REPORTS" in line)), None)
    if start is None:
        for line in lines[:7]:
            if re.match(r"^[A-Z]{2,} v [A-Z]{2,}$", line):
                return line
            if line.startswith("Re ") and re.match(r"^Re [A-Z]{2,}$", line):
                return line
        return filename
    block = lines[start+1:start+12]
    for j in range(len(block) - 2):
        if re.match(r"^[A-Z]{2,}$", block[j]) and block[j+1].lower() == "v" and re.match(r"^[A-Z]{2,}$", block[j+2]):
            return f"{block[j]} v {block[j+2]}"
    for line in block:
        if re.match(r"^[A-Z]{2,} v [A-Z]{2,}$", line): return line
        if line.startswith("Re ") and re.match(r"^Re [A-Z]{2,}$", line): return line
    return filename

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
            r'^Quranic verse', r'^Cases? referred to', r'^Issues? for determination', r'^Background'
        ])
    acts = []
    for line in block_lines:
        m = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b.*?)(?:\([^)]+\))?", line)
        if m:
            stat = m.group(1).strip()
            section_tokens = re.findall(r'(s|ss|section|r|rule|cap)\s*([0-9]{1,4}(?:[A-Za-z]|(?:\([\dA-Za-z]+\))*)*)', line)
            for s_type, sect in section_tokens:
                for s in re.split(r"[,;/]", sect):
                    s = s.strip()
                    if not s: continue
                    for name in add_short_forms(stat):
                        acts.append(f"{name} {s_type} {s}")
        else:
            m2 = re.match(r"^(.*?\b(?:Act|Charter|Rules|Ordinance)\b.*?)(?:[\s\.,;:]|$)", line)
            if m2:
                stat = m2.group(1).strip()
                for name in add_short_forms(stat):
                    acts.append(name)
    return sorted(set(acts))

def extract_cases_referred_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Cases? referred to', [
            r'^Legislation referred to', r'^Quranic verse', r'^Issues? for determination', r'^Background'
        ])
    cases = []
    for line in block_lines:
        if re.match(r"^[A-Z]{2,} v [A-Z]{2,}", line) or line.startswith("Re "):
            cases.append(line.strip())
        elif re.search(r'SSAR|SGSAB', line):
            cases.append(line.strip())
    return sorted(set(cases))

def extract_quranic_verses_block(text):
    lines = text.split('\n')
    block_lines = extract_header_window(
        lines, r'^Quranic verse\(s\) referred to', [
            r'^Legislation referred to', r'^Cases? referred to', r'^Issues? for determination', r'^Background'
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

def extract_main_body(text): return text

# ==== Search functions ====
def normalize(s):
    return re.sub(r'[\s\(\)\[\]\.,:\-]', '', str(s).lower())

def search_legislation_section_strict(df, keywords, section):
    results = []
    section_clean = str(section)
    keywords = [normalize(k) for k in (keywords if isinstance(keywords, list) else [keywords])]
    pattern = re.compile(rf'(s|ss|section)\s*{re.escape(section_clean)}(\b|\()', re.IGNORECASE)
    for _, row in df.iterrows():
        for leg in row.get("Legislation referred", []):
            if not any(k in normalize(leg) for k in keywords): continue
            if pattern.search(leg):
                results.append(row["Case Name"])
                break
    return sorted(set(results))

def search_legislation_exact_subsection(df, keywords, exact_subsection):
    results = []
    keywords = [normalize(k) for k in (keywords if isinstance(keywords, list) else [keywords])]
    pattern = re.compile(rf'(s|ss|section)\s*{re.escape(exact_subsection)}(\b|\([a-zA-Z0-9]+\))?', re.IGNORECASE)
    for _, row in df.iterrows():
        for leg in row.get("Legislation referred", []):
            if not any(k in normalize(leg) for k in keywords): continue
            if pattern.search(leg):
                results.append(row["Case Name"])
                break
    return sorted(set(results))

def search_quranic(df, verse_query):
    results = []
    verse_norm = normalize(verse_query)
    for _, row in df.iterrows():
        if any(verse_norm == normalize(v) for v in row.get("Quranic verse(s) referred", [])):
            results.append(row['Case Name'])
    return sorted(set(results))

# ==== Streamlit UI ====
st.set_page_config(page_title="Syariah Appeal Case Search", layout="wide")
st.title("Syariah Appeal Board Case Database")
st.markdown("""
Upload PDF case judgements, extract searchable database, and filter by legislation or Quranic verse.  
**All processing is local and private.**
""")

uploaded_files = st.file_uploader("Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)
records = []

if uploaded_files:
    progress_bar = st.progress(0)
    status_text = st.empty()
    for idx, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"Processing {uploaded_file.name}...")
        try:
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
        except Exception as ex:
            st.warning(f"Failed on {uploaded_file.name}: {ex}")
        progress_bar.progress(int(100*(idx+1)/len(uploaded_files)))
    status_text.text("Done.")
    df = pd.DataFrame(records)
    st.success(f"Processed {len(df)} cases.")
    st.dataframe(df[["Case Name", "Year", "Topic Groups", "Legislation referred", "Quranic verse(s) referred"]])

    # Download functionality
    excel_data = io.BytesIO()
    df.to_excel(excel_data, index=False)
    st.download_button("Download full case database (.xlsx)", data=excel_data.getvalue(),
                      file_name="ssar_cases.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("### Search Cases By Legislation or Quranic Verse")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Legislation Section Search")
        keywords = st.text_input("Act short-form or name (e.g. 'AMLA', 'Women's Charter')", "AMLA")
        section = st.text_input("Section number or subsection (e.g. '52', '52(8)')", "")
        if section:
            if "(" in section:  # subsection: s 52(8) logic
                results = search_legislation_exact_subsection(df, keywords, section)
            else:
                results = search_legislation_section_strict(df, keywords, section)
            st.write(f"Cases referring to: **{keywords} s {section}**")
            st.write(results if results else "No matches found.")

    with col2:
        st.markdown("#### Quranic Verse Search")
        verse = st.text_input("Quranic Verse (format Surah:Verse, e.g. '2:282', '4:3')", "")
        if verse:
            results = search_quranic(df, verse)
            st.write(f"Cases referring to: **Surah {verse}**")
            st.write(results if results else "No matches found.")

else:
    st.info("Please upload PDF files to begin.")

# Optional: show a usage guide
with st.expander("How to use this app"):
    st.markdown("""
**1. Upload Syariah Appeal Board judgement PDFs** (e.g. those with Singapore Syariah Appeals Reports, SSAR).
**2. Wait for processing.**
**3. Search by legislation sections (AMLA, Women's Charter), or by Quranic verse.**
**4. Download the extracted database for offline analysis.**
*Note: the app does not store your files or data—everything runs locally in your browser or Python session.*
    """)
