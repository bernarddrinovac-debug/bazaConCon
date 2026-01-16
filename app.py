import io
import re
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Centralna baza troškovnika", layout="wide")

# --- Elegant Financial Report styling (emerald/gold) ---
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Serif+Pro:wght@400;600&display=swap');
:root{
  --emerald:#065f46;
  --gold:#b45309;
  --ink:#0f172a;
  --bg:#f8fafc;
  --border:#cbd5e1;
  --card:#ffffff;
}
html, body, [class*="css"]{
  font-family:"Source Serif Pro",serif;
  color:var(--ink);
  background:var(--bg);
}
h1,h2,h3{
  font-family:"Playfair Display",serif !important;
}
.card{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:16px;
  padding:16px;
  box-shadow:0 8px 24px rgba(15,23,42,0.06);
}
.badge{
  display:inline-block;
  padding:4px 10px;
  border-radius:999px;
  border:1px solid var(--border);
  font-size:0.9rem;
}
.badge.em{
  color:var(--emerald);
  border-color:rgba(6,95,70,0.3);
  background:rgba(6,95,70,0.06);
}
.badge.go{
  color:var(--gold);
  border-color:rgba(180,83,9,0.3);
  background:rgba(180,83,9,0.06);
}
.small-note{opacity:0.85;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="card">
  <span class="badge em">Centralna baza</span>
  <span class="badge go" style="margin-left:8px;">Povijesne cijene</span>
  <h1 style="margin:10px 0 0 0;">Troškovnici → aktivno znanje</h1>
  <div class="small-note" style="margin-top:8px;">
    Učitaj jedan ili više XLSX troškovnika. Aplikacija spoji stavke u jedinstvenu bazu i omogući pretragu te analitiku cijena.
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------
# Helpers
# --------------------------
def guess_date_from_filename(name: str):
    """
    Pokušaj prepoznati datum iz naziva datoteke.
    Primjeri: 2025-01-19, 19.01.2025, 20250119
    """
    s = name
    m = re.search(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d).date()

    m = re.search(r"(\d{1,2})[.](\d{1,2})[.](20\d{2})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return datetime(y, mo, d).date()

    m = re.search(r"(20\d{2})(\d{2})(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d).date()

    return None


def normalize_table(df: pd.DataFrame, source_file: str, sheet: str) -> pd.DataFrame:
    """
    MVP heuristika:
    pokušavamo prepoznati Opis / JM / Količina / Jed.cijena / Iznos
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(options):
        # exact
        for o in options:
            for c in df.columns:
                if str(c).strip().lower() == o.lower():
                    return c
        # contains
        for o in options:
            for c in df.columns:
                if o.lower() in str(c).lower():
                    return c
        return None

    c_desc = find_col(["Opis", "Naziv", "Stavka", "Opis stavke"])
    c_unit = find_col(["JM", "J.M.", "Jed mj", "Jed. mjere", "Mjerna jedinica"])
    c_qty = find_col(["Količina", "Kol", "Qty"])
    c_up = find_col(["Jedinična cijena", "Jed. cijena", "Cijena", "Unit price"])
    c_tot = find_col(["Iznos", "Ukupno", "Vrijednost", "Total"])

    if c_desc is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["opis"] = df[c_desc].astype(str)
    out["jm"] = df[c_unit].astype(str) if c_unit else ""
    out["kolicina"] = pd.to_numeric(df[c_qty], errors="coerce") if c_qty else np.nan
    out["jed_cijena"] = pd.to_numeric(df[c_up], errors="coerce") if c_up else np.nan
    out["iznos"] = pd.to_numeric(df[c_tot], errors="coerce") if c_tot else np.nan

    out["source_file"] = source_file
    out["sheet"] = sheet
    out["datum"] = guess_date_from_filename(source_file)

    # čišćenje
    out = out[out["opis"].str.strip().ne("")].copy()
    out = out[~out["opis"].str.lower().isin(["opis", "stavka", "naziv"])].copy()

    return out


def read_xlsx_bytes(xlsx_bytes: bytes, filename: str) -> pd.DataFrame:
    xls = pd.ExcelFile(io.BytesIO(xlsx_bytes))
    frames = []
    for sh in xls.sheet_names:
        try:
            raw = xls.parse(sh)
            if raw.shape[0] < 3:
                continue
            norm = normalize_table(raw, filename, sh)
            if not norm.empty:
                frames.append(norm)
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def ingest_xlsx_files(files) -> pd.DataFrame:
    frames = []
    for f in files:
        if f.name.lower().endswith(".xlsx") and not f.name.startswith("~$"):
            frames.append(read_xlsx_bytes(f.getvalue(), f.name))

    frames = [x for x in frames if not x.empty]
    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out["opis_norm"] = (
        out["opis"]
        .astype(str)
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
        .str.replace(r"[^\w\sčćđšž]", "", regex=True)
    )
    return out


# --------------------------
# Upload
# --------------------------
st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
xlsx_files = st.file_uploader(
    "Učitaj XLSX troškovnike (može više odjednom):",
    type=["xlsx"],
    accept_multiple_files=True,
)
st.markdown("</div>", unsafe_allow_html=True)

if not xlsx_files:
    st.info("Učitaj jedan ili više XLSX troškovnika i aplikacija će izgraditi centralnu bazu.")
    st.stop()

with st.spinner("Učitavam XLSX datoteke i gradim bazu..."):
    base = ingest_xlsx_files(xlsx_files)

if base.empty:
    st.error("Nisam uspio prepoznati tablice u Excelima. Ako su kolone nestandardne, u FAZI 2 dodajemo ručno mapiranje stupaca.")
    st.stop()

# --------------------------
# KPIs
# --------------------------
st.write("")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Redova (stavki)", f"{len(base):,}")
c2.metric("Datoteka", base["source_file"].nunique())
c3.metric("Sheetova", base["sheet"].nunique())
c4.metric("Datuma prepoznato", int(base["datum"].notna().sum()))

# --------------------------
# Search / Filters
# --------------------------
st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("Pretraga stavki")
q = st.text_input("Opis (npr. 'PVC prozor', 'armatura', 'estrih')", value="")
jm = st.text_input("JM filter (opcionalno)", value="")
st.markdown("</div>", unsafe_allow_html=True)

f = base.copy()
if q.strip():
    qq = re.sub(r"\s+", " ", q.strip().lower())
    qq = re.sub(r"[^\w\sčćđšž]", "", qq)
    f = f[f["opis_norm"].str.contains(qq, na=False)]

if jm.strip():
    f = f[f["jm"].str.contains(jm.strip(), case=False, na=False)]

# --------------------------
# Results
# --------------------------
st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("Rezultati")
st.dataframe(
    f.sort_values(["datum", "jed_cijena"], ascending=[True, True]),
    use_container_width=True,
    height=420,
)
st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Chart
# --------------------------
st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("Povijest jedinične cijene (ako postoji datum)")
g = f.dropna(subset=["datum", "jed_cijena"]).copy()
if len(g) >= 3:
    fig = px.scatter(
        g,
        x="datum",
        y="jed_cijena",
        color="source_file",
        hover_data=["opis", "jm", "kolicina", "iznos", "sheet"],
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Nema dovoljno redova s datumom i jediničnom cijenom za graf. (Datum se pokušava pogoditi iz naziva datoteke.)")
st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Download master dataset
# --------------------------
st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("Preuzmi centralnu bazu")
st.caption("Preuzmi master dataset kao CSV. Preporuka: spremi ga kao master.csv u repo u folder data/ (ako želiš trajnu bazu).")
csv_bytes = base.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download master.csv",
    data=csv_bytes,
    file_name="master.csv",
    mime="text/csv",
)
st.markdown("</div>", unsafe_allow_html=True)
