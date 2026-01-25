import streamlit as st
import pandas as pd
import glob
import os
import json
import plotly.express as px

# --- POSTAVKE I KONFIGURACIJA ---
st.set_page_config(page_title="Baza Troškovnika", page_icon="🏗️", layout="wide")
CONFIG_FILE = "mapping_config.json"

# --- FUNKCIJE ZA UPRAVLJANJE KONFIGURACIJOM (PAMĆENJE POSTAVKI) ---
def load_mapping_config():
    """Učitava spremljene postavke stupaca za specifične datoteke."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_mapping_config(config):
    """Sprema vaše ručne popravke u JSON datoteku."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# --- GLAVNA FUNKCIJA ZA UČITAVANJE ---
@st.cache_data(show_spinner=False)
def load_data_with_status(refresh_trigger=0):
    # refresh_trigger služi samo da resetira cache kad spremimo novu konfiguraciju
    mapping_config = load_mapping_config()
    
    path_csv = os.path.join("podaci", "*.csv")
    path_xlsx = os.path.join("podaci", "*.xlsx")
    all_files = glob.glob(path_csv) + glob.glob(path_xlsx)
    
    successful_data = []
    failed_files = [] # Ovdje ćemo spremati datoteke koje nismo uspjeli pročitati

    # Ključne riječi za automatsku detekciju (ako nema ručne postavke)
    desc_keywords = ['opis', 'vrsta rada', 'naziv stavke', 'tekst', 'specifikacija']
    unit_keywords = ['j.m.', 'jed. mj.', 'jedinica', 'mjera']
    price_keywords = ['jed. cijena', 'jedinična cijena', 'cijena', 'iznos', 'vrijednost']

    for file_path in all_files:
        filename = os.path.basename(file_path)
        
        try:
            # 1. PRIPREMA SIROVIH PODATAKA (za provjeru)
            if file_path.endswith('.csv'):
                # Probaj detektirati encoding (utf-8 ili windows-1250)
                try:
                    df_raw = pd.read_csv(file_path, header=None, nrows=50, encoding='utf-8', sep=None, engine='python')
                except:
                    df_raw = pd.read_csv(file_path, header=None, nrows=50, encoding='cp1250', sep=None, engine='python')
            else:
                df_raw = pd.read_excel(file_path, header=None, nrows=50)

            selected_data = pd.DataFrame()

            # 2. SLUČAJ A: IMAMO SPREMLJENO RUČNO MAPIRANJE
            if filename in mapping_config:
                cfg = mapping_config[filename]
                header_row = cfg['header_row']
                
                # Učitaj cijeli file s poznatim zaglavljem
                if file_path.endswith('.csv'):
                    try:
                        df = pd.read_csv(file_path, header=header_row, encoding='utf-8', sep=None, engine='python')
                    except:
                        df = pd.read_csv(file_path, header=header_row, encoding='cp1250', sep=None, engine='python')
                else:
                    df = pd.read_excel(file_path, header=header_row)
                
                # Izvuci stupce po indeksima koje je korisnik spremio
                # (Koristimo iloc jer se imena stupaca mogu malo razlikovati)
                if cfg['col_opis'] < len(df.columns):
                    selected_data['Opis'] = df.iloc[:, cfg['col_opis']]
                
                if cfg['col_cijena'] < len(df.columns):
                    selected_data['Cijena'] = df.iloc[:, cfg['col_cijena']]
                
                if cfg['col_jm'] is not None and cfg['col_jm'] < len(df.columns):
                    selected_data['JM'] = df.iloc[:, cfg['col_jm']]
                else:
                    selected_data['JM'] = "kom" # Default ako nije odabrano

            # 3. SLUČAJ B: NEMA MAPIRANJA -> AUTOMATSKA DETEKCIJA
            else:
                header_idx = -1
                # Tražimo redak koji sadrži i "cijena" i "opis"
                for i, row in df_raw.iterrows():
                    row_str = row.astype(str).str.lower().tolist()
                    row_joined = ' '.join(row_str)
                    if any(k in row_joined for k in price_keywords) and any(k in row_joined for k in desc_keywords):
                        header_idx = i
                        break
                
                if header_idx == -1:
                    failed_files.append((filename, "Nije pronađeno zaglavlje tablice (ključne riječi: cijena, opis)"))
                    continue

                # Učitaj s pronađenim headerom
                if file_path.endswith('.csv'):
                    try:
                        df = pd.read_csv(file_path, header=header_idx, encoding='utf-8', sep=None, engine='python')
                    except:
                        df = pd.read_csv(file_path, header=header_idx, encoding='cp1250', sep=None, engine='python')
                else:
                    df = pd.read_excel(file_path, header=header_idx)

                # Normalizacija imena stupaca za lakše traženje
                df.columns = [str(c).lower().strip() for c in df.columns]
                
                col_map = {'opis': None, 'jm': None, 'cijena': None}
                for col in df.columns:
                    if any(k in col for k in desc_keywords) and not col_map['opis']: col_map['opis'] = col
                    if any(k in col for k in unit_keywords) and not col_map['jm']: col_map['jm'] = col
                    if any(k in col for k in price_keywords) and not col_map['cijena']: col_map['cijena'] = col

                if not col_map['opis'] or not col_map['cijena']:
                    failed_files.append((filename, f"Zaglavlje nađeno, ali fale stupci. Nađeno: {list(col_map.values())}"))
                    continue

                selected_data = df[[col_map['opis'], col_map['jm'], col_map['cijena']]].copy()
                selected_data.columns = ['Opis', 'JM', 'Cijena']

            # 4. ZAVRŠNO ČIŠĆENJE I DODAVANJE PROJEKTA
            # Metapodaci iz imena datoteke
            project_name = filename.split('.')[0]
            
            cat = "Ostalo"
            lname = filename.lower()
            if "građ" in lname: cat = "Građevinski radovi"
            elif "elek" in lname: cat = "Elektroinstalacije"
            elif "stroj" in lname or "grijanje" in lname: cat = "Strojarski radovi"
            elif "vod" in lname or "kanal" in lname: cat = "Vodovod i Odvodnja"
            
            selected_data['Projekt'] = project_name
            selected_data['Kategorija'] = cat

            # Čišćenje cijena od valuta i pretvaranje u broj
            selected_data['Cijena'] = selected_data['Cijena'].astype(str).str.replace('€','').str.replace('kn','').str.replace('EUR','').str.replace('.','').str.replace(',','.').str.strip()
            selected_data['Cijena'] = pd.to_numeric(selected_data['Cijena'], errors='coerce')
            
            # Izbaci prazne redove
            selected_data = selected_data.dropna(subset=['Cijena', 'Opis'])
            selected_data = selected_data[selected_data['Cijena'] > 0]
            
            successful_data.append(selected_data)

        except Exception as e:
            failed_files.append((filename, str(e)))

    final_df = pd.concat(successful_data, ignore_index=True) if successful_data else pd.DataFrame()
    return final_df, failed_files

# --- USER INTERFACE ---

st.title("🏗️ Pametni Sustav Troškovnika")

# Session state za osvježavanje nakon spremanja konfiguracije
if 'refresh_counter' not in st.session_state:
    st.session_state.refresh_counter = 0

# Učitavanje podataka
with st.spinner('Učitavam datoteke...'):
    df, failed_files = load_data_with_status(st.session_state.refresh_counter)

# KREIRANJE KARTICA (TABS)
tab1, tab2 = st.tabs(["🔍 Tražilica i Analiza", "⚙️ Ručno Mapiranje (Popravak grešaka)"])

# --- TAB 1: GLAVNA TRAŽILICA ---
with tab1:
    if df.empty:
        st.warning("Baza je trenutno prazna. Provjerite 'Ručno Mapiranje' ako su datoteke učitane ali nevidljive.")
    else:
        # Filteri
        c_filter1, c_filter2 = st.columns(2)
        with c_filter1:
            cats = st.multiselect("Filtriraj po kategoriji:", df['Kategorija'].unique(), default=df['Kategorija'].unique())
        with c_filter2:
            projs = st.multiselect("Filtriraj po projektu:", df['Projekt'].unique(), default=df['Projekt'].unique())
        
        df_view = df[(df['Kategorija'].isin(cats)) & (df['Projekt'].isin(projs))]

        search = st.text_input("Upišite pojam (npr. beton, kabel, gletanje):", placeholder="Pretraži bazu...", key="search_main")

        if search:
            results = df_view[df_view['Opis'].str.contains(search, case=False, na=False)]
            
            if not results.empty:
                st.markdown(f"### Rezultati: {len(results)} stavki")
                
                # Metrika
                m1, m2, m3 = st.columns(3)
                m1.metric("Min. Cijena", f"{results['Cijena'].min():.2f} €")
                m2.metric("Prosječna Cijena", f"{results['Cijena'].mean():.2f} €")
                m3.metric("Max. Cijena", f"{results['Cijena'].max():.2f} €")
                
                # Graf
                fig = px.box(results, x="Cijena", y="Kategorija", points="all", hover_data=["Opis", "Projekt"], color="Kategorija")
                st.plotly_chart(fig, use_container_width=True)
                
                # Tablica
                st.dataframe(
                    results[['Opis', 'JM', 'Cijena', 'Projekt', 'Kategorija']].sort_values('Cijena'),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nema rezultata za traženi pojam.")
        else:
            st.info("Upišite pojam iznad za pretragu.")
            st.divider()
            st.caption(f"Ukupno učitano: {len(df)} stavki iz {len(df['Projekt'].unique())} projekata.")

# --- TAB 2: RUČNO MAPIRANJE (ADMIN) ---
with tab2:
    st.markdown("### 🛠️ Popravak neprepoznatih datoteka")
    
    if not failed_files:
        st.success("🎉 Odlično! Sve datoteke su uspješno automatski učitane.")
    else:
        st.warning(f"Sustav nije uspio automatski pročitati **{len(failed_files)}** datoteka.")
        st.markdown("Odaberite datoteku ispod i ručno recite sustavu koji stupac je koji.")
        
        # Izbornik problematičnih datoteka
        file_map = {f[0]: f[1] for f in failed_files}
        selected_file = st.selectbox("Odaberite datoteku za popravak:", list(file_map.keys()))
        
        if selected_file:
            st.error(f"Razlog greške: {file_map[selected_file]}")
            
            file_path = os.path.join("podaci", selected_file)
            
            # Učitaj preview (prvih 20 redova) da korisnik vidi
            try:
                if selected_file.endswith('.csv'):
                    try:
                        df_preview = pd.read_csv(file_path, header=None, nrows=20, encoding='utf-8', sep=None, engine='python')
                    except:
                        df_preview = pd.read_csv(file_path, header=None, nrows=20, encoding='cp1250', sep=None, engine='python')
                else:
                    df_preview = pd.read_excel(file_path, header=None, nrows=20)
                
                st.markdown("#### 1. Pregled sirovog sadržaja (kako bi odredili redak zaglavlja)")
                st.dataframe(df_preview)
                
                st.markdown("#### 2. Definirajte strukturu")
                
                with st.form("manual_mapping_form"):
                    # 1. Odabir reda zaglavlja
                    header_row_idx = st.number_input(
                        "U kojem redu se nalaze naslovi stupaca (Opis, Cijena...)? (Gledajte indeks lijevo 0,1,2...)", 
                        min_value=0, max_value=20, value=0
                    )
                    
                    # Osvježi stupce na temelju odabranog reda (simulacija)
                    # Ovdje uzimamo redak koji je korisnik odabrao da bi mu ponudili imena stupaca u padajućem izborniku
                    if header_row_idx < len(df_preview):
                        cols = df_preview.iloc[header_row_idx].astype(str).tolist()
                        # Dodajemo indeks stupca u naziv radi lakšeg snalaženja ako su imena ista
                        col_options = {f"{i}: {col}": i for i, col in enumerate(cols)}
                    else:
                        col_options = {}
                        st.warning("Odabrani redak je izvan dosega pregleda.")

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        sel_opis = st.selectbox("Koji stupac je OPIS?", options=col_options.keys())
                    with c2:
                        sel_cijena = st.selectbox("Koji stupac je CIJENA?", options=col_options.keys())
                    with c3:
                        sel_jm = st.selectbox("Koji stupac je J.M.? (Opcionalno)", options=["Nema"] + list(col_options.keys()))

                    submit_btn = st.form_submit_button("💾 Spremi Postavke")
                    
                    if submit_btn:
                        # Pripremi podatke za spremanje
                        new_config = {
                            "header_row": int(header_row_idx),
                            "col_opis": col_options[sel_opis],
                            "col_cijena": col_options[sel_cijena],
                            "col_jm": col_options[sel_jm] if sel_jm != "Nema" else None
                        }
                        
                        # Učitaj postojeće, dodaj novo i spremi
                        current_config = load_mapping_config()
                        current_config[selected_file] = new_config
                        save_mapping_config(current_config)
                        
                        st.success(f"Postavke za '{selected_file}' su spremljene! Osvježavam bazu...")
                        
                        # Ovo će triggerirati ponovno učitavanje
                        st.session_state.refresh_counter += 1
                        st.rerun()

            except Exception as e:
                st.error(f"Ne mogu otvoriti pregled datoteke: {str(e)}")
