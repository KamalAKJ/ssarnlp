import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import re
import ast

# Load DataFrame, making sure list columns are parsed
@st.cache_data
def load_data(path="ssar_cases.xlsx"):
    df = pd.read_excel(path)
    for col in ["Topic Groups", "Legislation referred", "Quranic verse(s) referred"]:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith("[") else x)
    return df

def normalize(s):
    return re.sub(r'[\\s\\(\\)\\[\\]\\.,:\\-]', '', str(s).lower())

def search_legislation_section_strict(df, keywords, section):
    results = []
    section_clean = str(section)
    keywords = [normalize(k) for k in (keywords if isinstance(keywords, list) else [keywords])]
    pattern = re.compile(rf'(s|ss|section)\\s*{re.escape(section_clean)}(\\b|\\()', re.IGNORECASE)
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
    pattern = re.compile(rf'(s|ss|section)\\s*{re.escape(exact_subsection)}(\\b|\\([a-zA-Z0-9]+\\))?', re.IGNORECASE)
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

def get_case_splits(df):
    group_table = (
        df.explode("Topic Groups")
          .groupby(["Year", "Topic Groups"])
          .size()
          .unstack(fill_value=0)
          .sort_index()
    )
    # True proportion: total unique cases per year
    proportion_table = group_table.divide(df.groupby("Year")["Case Name"].nunique(), axis=0).round(3)
    return group_table, proportion_table

def plot_cases(group_table, df):
    totals = df.groupby("Year")["Case Name"].nunique()
    fig, ax = plt.subplots(figsize=(10, 5))
    for col in group_table.columns:
        ax.plot(group_table.index, group_table[col], marker='o', label=col)
    ax.plot(totals.index, totals.values, marker='o', color='black', linestyle='--', linewidth=2, label='Total Cases')
    ax.set_title("Number of Cases per Topic Group per Year (True Total in Black)")
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of Cases")
    ax.set_yticks(range(0, int(totals.max()) + 2, 1))
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)

def plot_proportions(proportion_table):
    fig, ax = plt.subplots(figsize=(10, 5))
    for col in proportion_table.columns:
        ax.plot(proportion_table.index, proportion_table[col], marker='o', label=col)
    ax.set_title("Proportion of Cases per Topic Group per Year")
    ax.set_xlabel("Year")
    ax.set_ylabel("Proportion (0–1)")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)

def main():
    st.title("Syariah SSAR Interactive Statistical Browser")
    df = load_data()
    group_table, proportion_table = get_case_splits(df)
    st.header("Yearly Topic Group Trends — Number of Cases (with True Total)")
    st.dataframe(group_table)
    plot_cases(group_table, df)

    st.header("Yearly Topic Group Trends — Proportion of Cases")
    st.dataframe(proportion_table)
    plot_proportions(proportion_table)

    st.header("Legislation Search")
    leg = st.text_input("Legislation (eg. AMLA, Women's Charter)")
    section = st.text_input("Section (eg. 52, 52(8))")
    if st.button("Search Legislation"):
        if leg and section:
            broad_results = search_legislation_section_strict(df, [leg], section)
            exact_results = search_legislation_exact_subsection(df, [leg], section)
            st.subheader("Broad match (all cases citing section or any subsection):")
            st.write(broad_results if broad_results else "No broad matches found.")
            st.subheader("Exact subsection match (e.g. '52(8)' finds s 52(8), s 52(8)(d)):")
            st.write(exact_results if exact_results else "No exact matches found.")
        else:
            st.warning("Please enter both legislation and section.")

    st.header("Quranic Verse Search")
    verse = st.text_input("Verse (eg. 2:282, 4:3, 8:28)")
    if st.button("Search Quranic Verse"):
        if verse:
            results = search_quranic(df, verse)
            st.write(results if results else "No matching cases found.")
        else:
            st.warning("Please enter a Quranic verse.")

if __name__ == \"__main__\":
    main()
