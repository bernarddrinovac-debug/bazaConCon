import streamlit as st
import pandas as pd
import plotly.express as px
import io

# --- POSTAVKE STRANICE ---
st.set_page_config(page_title="Baza Troškovnika", page_icon="📂", layout="wide")

# Naslov i opis
st.title("📂 Brza Tražilica Troškovnika")
st.markdown("Ubacite svoje Excel ili CSV troškovnike ispod i odmah pretražite cijene.")

# --- 1. DIO: UBACIVANJE DATOTEKA (UPLOAD) ---
st.sidebar.header("1. Ubacite datoteke")
uploaded_files = st.sidebar.file_uploader(
    "Povucite i ispustite datoteke ovdje (Excel/CSV)", 
    accept_multiple_files=True,
    type=['xlsx', 'xls', 'csv']
)

# --- FUNKCIJA ZA OBRADU ---
@st.cache_data(show_spinner=False)
def process_uploaded_files(files):
    all_data = []
    
    # Ključne riječi za prepoznavanje
    desc_keywords = ['opis', 'vrsta rada', 'naziv stavke', 'tekst']
    unit_keywords = ['j.m.', 'jed. mj.', 'jedinica', 'mjera']
    price_keywords = ['jed. cijena', 'jedinična cijena', 'cijena', 'iznos']

    for uploaded_file in files:
        try:
            filename = uploaded_file.name
            # Učitavanje ovisno o tipu
            if filename.endswith('.csv'):
                try:
                    df = pd.read_csv(uploaded_file, header=None, on_bad_lines='skip', encoding='utf-8')
                except:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, header=None, on_bad_lines='skip', encoding='cp1250')
            else:
                df = pd.read_excel(uploaded_file, header=None)

            # Traženje zaglavlja (Header detection)
            header_idx = -1
            # Gledamo prvih 20 redova da nađemo gdje počinje tablica
            for i, row in df.head(30).iterrows():
                row_str = row.astype(str).str.lower().tolist()
                row_joined = ' '.join(row_str)
                if any(k in row_joined for k in price_keywords) and any(k in row_joined for k in desc_keywords):
                    header_idx = i
                    break
            
            if header_idx == -1:
                continue # Preskoči ako ne nađe tablicu

            # Postavljanje pravog zaglavlja
            df.columns = df.iloc[header_idx]
            df = df.iloc[header_idx+1:]
            
            # Normalizacija imena stupaca
            df.columns = [str(c).lower().strip() for c in df.columns]

            # Mapiranje stupaca
            col_map = {'opis': None, 'jm': None, 'cijena': None}
            for col in df.columns:
                if any(k in col for k in desc_keywords) and not col_map['opis']: col_map['opis'] = col
                if any(k in col for k in unit_keywords) and not col_map['jm']: col_map['jm'] = col
                if any(k in col for k in price_keywords) and not col_map['cijena']: col_map['cijena'] = col

            if not col_map['opis'] or not col_map['cijena']:
                continue

            # Odabir podataka
            clean_df = df[[col_map['opis'], col_map['jm'], col_map['cijena']]].copy()
            clean_df.columns = ['Opis', 'JM', 'Cijena']
            
            # Dodavanje imena projekta (iz imena datoteke)
            clean_df['Projekt'] = filename.split('.')[0]
            
            # Kategorizacija
            cat = "Ostalo"
            lname = filename.lower()
            if "građ" in lname: cat = "Građevinski"
            elif "elek" in lname: cat = "Elektro"
            elif "stroj" in lname: cat = "Strojarski"
            elif "vod" in lname: cat = "Vodovod"
            clean_df['Kategorija'] = cat

            # Čišćenje cijena
            clean_df['Cijena'] = clean_df['Cijena'].astype(str).str.replace('€','').str.replace('kn','').str.replace('.','').str.replace(',','.').str.strip()
            clean_df['Cijena'] = pd.to_numeric(clean_df['Cijena'], errors='coerce')
            
            clean_df = clean_df.dropna(subset=['Cijena', 'Opis'])
            all_data.append(clean_df)

        except Exception:
            continue

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()

# --- 2. DIO: LOGIKA APLIKACIJE ---

if not uploaded_files:
    st.info("⬅️ Molim vas, učitajte troškovnike u lijevom izborniku da biste počeli.")
else:
    with st.spinner('Obrađujem datoteke...'):
        df = process_uploaded_files(uploaded_files)

    if df.empty:
        st.warning("Nisam uspio pročitati podatke. Provjerite jesu li datoteke standardni troškovnici.")
    else:
        # Prikaz statistike
        st.sidebar.success(f"Učitano {len(df)} stavki iz {len(uploaded_files)} datoteka.")
        
        # --- 3. DIO: TRAŽILICA ---
        st.divider()
        search_term = st.text_input("🔍 Pretraži bazu (npr. 'Beton', 'Kabel', 'Gletanje')", "")

        if search_term:
            results = df[df['Opis'].str.contains(search_term, case=False, na=False)]
            
            if not results.empty:
                # Metrika
                col1, col2, col3 = st.columns(3)
                col1.metric("Min. Cijena", f"{results['Cijena'].min():.2f} €")
                col2.metric("Prosječna Cijena", f"{results['Cijena'].mean():.2f} €")
                col3.metric("Max. Cijena", f"{results['Cijena'].max():.2f} €")
                
                # Grafikon
                st.subheader("Analiza cijena")
                fig = px.box(results, x="Cijena", y="Kategorija", 
                             points="all", 
                             hover_data=["Opis", "Projekt"],
                             color="Kategorija")
                st.plotly_chart(fig, use_container_width=True)
                
                # Tablica
                st.subheader("Rezultati pretrage")
                st.dataframe(
                    results[['Opis', 'JM', 'Cijena', 'Projekt', 'Kategorija']].sort_values('Cijena'),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Nema rezultata za taj pojam.")
        else:
            st.info("Upišite pojam iznad za prikaz cijena.")
            
            # Pregled baze kad nema pretrage
            st.subheader("Pregled učitane baze")
            st.dataframe(df.head(100), use_container_width=True)
