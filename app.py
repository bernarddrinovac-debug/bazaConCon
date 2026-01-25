import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os

# --- POSTAVKE STRANICE ---
st.set_page_config(page_title="Baza Troškovnika v2", page_icon="🏗️", layout="wide")

st.title("🏗️ Robusna Tražilica Troškovnika")
st.markdown("Ubacite Excel/CSV datoteke. Sustav će pokušati automatski detektirati strukturu čak i ako je nestandardna.")

# --- SIDEBAR: UPLOAD ---
st.sidebar.header("1. Ubacite datoteke")
uploaded_files = st.sidebar.file_uploader(
    "Povucite i ispustite datoteke (Excel/CSV)", 
    accept_multiple_files=True,
    type=['xlsx', 'xls', 'csv']
)

# --- NAPREDNA LOGIKA ZA ČITANJE ---
@st.cache_data(show_spinner=False)
def process_files_robust(files):
    all_data = []
    report_log = [] # Ovdje ćemo spremati što se dogodilo sa svakom datotekom

    # Proširene ključne riječi
    price_keywords = ['cijena', 'jed.cij', 'j.cij', 'iznos', 'vrijednost', 'jedinična', 'price', 'amount']
    desc_keywords = ['opis', 'vrsta', 'naziv', 'tekst', 'specifikacija', 'predmet', 'description', 'item']
    
    for up_file in files:
        filename = up_file.name
        try:
            # 1. Učitavanje sirovih podataka ovisno o ekstenziji
            if filename.lower().endswith('.csv'):
                try:
                    df_raw = pd.read_csv(up_file, header=None, on_bad_lines='skip', encoding='utf-8')
                except:
                    up_file.seek(0)
                    df_raw = pd.read_csv(up_file, header=None, on_bad_lines='skip', encoding='cp1250') # Hrvatski encoding
            else:
                try:
                    df_raw = pd.read_excel(up_file, header=None)
                except Exception as e:
                    report_log.append(f"❌ {filename}: Greška kod otvaranja Excela ({str(e)})")
                    continue

            # 2. Detekcija zaglavlja (Tražimo redak koji ima i OPIS i CIJENU)
            header_idx = -1
            found_cols = {}
            
            # Skeniraj prvih 80 redova
            for i, row in df_raw.head(80).iterrows():
                row_str = row.astype(str).str.lower().tolist()
                
                # Provjeri ima li ključnih riječi u ovom redu
                has_price = any(k in cell for cell in row_str for k in price_keywords)
                has_desc = any(k in cell for cell in row_str for k in desc_keywords)
                
                if has_price and has_desc:
                    header_idx = i
                    break
            
            if header_idx == -1:
                report_log.append(f"⚠️ {filename}: Nisam pronašao redak zaglavlja (tražio sam riječi: 'opis', 'cijena'...)")
                continue

            # 3. Postavljanje zaglavlja
            df = df_raw.iloc[header_idx+1:].copy()
            df.columns = df_raw.iloc[header_idx].astype(str).str.lower().str.strip()
            
            # 4. Pronalazak ključnih stupaca
            col_map = {'opis': None, 'cijena': None, 'jm': None}
            
            for col in df.columns:
                if not col_map['opis'] and any(k in col for k in desc_keywords): col_map['opis'] = col
                if not col_map['cijena'] and any(k in col for k in price_keywords): col_map['cijena'] = col
                if not col_map['jm'] and any(k in col for k in ['jm', 'j.m', 'mjera', 'jed', 'unit']): col_map['jm'] = col

            if not col_map['opis'] or not col_map['cijena']:
                report_log.append(f"⚠️ {filename}: Našao zaglavlje, ali fale stupci. (Opis: {col_map['opis']}, Cijena: {col_map['cijena']})")
                continue

            # 5. Čišćenje podataka
            clean_df = df[[col_map['opis'], col_map['cijena']]].copy()
            clean_df.columns = ['Opis', 'Cijena']
            
            # Ako postoji JM, dodaj ga, inače stavi prazno
            if col_map['jm']:
                clean_df['JM'] = df[col_map['jm']]
            else:
                clean_df['JM'] = '-'

            clean_df['Projekt'] = filename.split('.')[0]
            
            # Kategorizacija
            cat = "Ostalo"
            ln = filename.lower()
            if "građ" in ln: cat = "Građevinski"
            elif "elek" in ln: cat = "Elektro"
            elif "stroj" in ln: cat = "Strojarski"
            elif "vod" in ln: cat = "Vodovod"
            clean_df['Kategorija'] = cat

            # Konverzija cijene (miče €, kn, točke)
            clean_df['Cijena'] = clean_df['Cijena'].astype(str).str.replace('€','').str.replace('kn','').str.replace(' ','')
            # Zamjena zareza točkom samo ako je to decimalni zarez (heuristic)
            clean_df['Cijena'] = clean_df['Cijena'].str.replace('.','', regex=False).str.replace(',','.', regex=False)
            
            clean_df['Cijena'] = pd.to_numeric(clean_df['Cijena'], errors='coerce')
            
            # Izbaci redove gdje nema cijene ili opisa
            clean_df = clean_df.dropna(subset=['Cijena', 'Opis'])
            clean_df = clean_df[clean_df['Cijena'] > 0] # Samo pozitivne cijene

            if not clean_df.empty:
                all_data.append(clean_df)
                report_log.append(f"✅ {filename}: Učitano {len(clean_df)} stavki.")
            else:
                report_log.append(f"⚠️ {filename}: Tablica je prazna nakon čišćenja.")

        except Exception as e:
            report_log.append(f"❌ {filename}: Kritična greška ({str(e)})")

    final_df = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
    return final_df, report_log

# --- GLAVNI DIO ---

if uploaded_files:
    with st.spinner('Analiziram datoteke...'):
        df, log = process_files_robust(uploaded_files)

    # Ispis statusa (Diagnostika)
    with st.expander("📋 Status učitavanja datoteka (Klikni za detalje)", expanded=False):
        for msg in log:
            if "✅" in msg: st.success(msg)
            elif "⚠️" in msg: st.warning(msg)
            else: st.error(msg)

    if df.empty:
        st.error("Niti jedna datoteka nije uspješno učitana. Pogledajte status iznad za razloge.")
    else:
        st.success(f"Uspješno kreirana baza od **{len(df)}** stavki!")
        
        # --- TRAŽILICA ---
        st.divider()
        col_search, col_cat = st.columns([3, 1])
        with col_search:
            search_term = st.text_input("🔍 Pretraži stavku:", placeholder="npr. beton, kabel, gletanje...")
        with col_cat:
            cat_filter = st.multiselect("Kategorija", df['Kategorija'].unique(), default=df['Kategorija'].unique())

        # Filtriranje
        results = df[
            (df['Opis'].str.contains(search_term, case=False, na=False)) & 
            (df['Kategorija'].isin(cat_filter))
        ]

        if search_term:
            st.subheader(f"Rezultati ({len(results)})")
            if not results.empty:
                # Metrika
                c1, c2, c3 = st.columns(3)
                c1.metric("Min", f"{results['Cijena'].min():.2f}")
                c2.metric("Prosjek", f"{results['Cijena'].mean():.2f}")
                c3.metric("Max", f"{results['Cijena'].max():.2f}")
                
                # Graf
                fig = px.box(results, x="Cijena", y="Kategorija", color="Kategorija", points="all", hover_data=["Opis", "Projekt"])
                st.plotly_chart(fig, use_container_width=True)
                
                # Tablica
                st.dataframe(results[['Opis', 'JM', 'Cijena', 'Projekt', 'Kategorija']].sort_values('Cijena'), use_container_width=True)
            else:
                st.info("Nema rezultata.")
        else:
            st.info("Upišite pojam za pretragu.")
            st.dataframe(df.head(50), use_container_width=True)

else:
    st.info("⬅️ Molim učitajte datoteke u izborniku lijevo.")
