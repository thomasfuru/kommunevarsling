import streamlit as st
import pandas as pd
import psycopg2
import warnings  # <--- NY
from config import Config

# --- LYDDEMPER ---
# Vi ber Pandas slutte å klage på database-koblingen vår, for den virker fint.
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Oppsett av siden
st.set_page_config(page_title="Kommunevarsling", layout="wide")

st.title("🏛️ Kommunevarsling - Skien")

# Koble til database
@st.cache_data(ttl=60) # Cacher data i 60 sekunder
def hent_data():
    conn = psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )
    # Vi henter data med Pandas for enkel visning
    query = "SELECT dato, tittel, url_pdf as lenke, varslet, ocr_tekst FROM dokumenter ORDER BY id DESC LIMIT 500"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

try:
    df = hent_data()

    # --- SIDEBAR (SØK) ---
    st.sidebar.header("Filter")
    soketekst = st.sidebar.text_input("Søk i dokumenter")
    vis_kun_varslet = st.sidebar.checkbox("Vis kun varslede saker")

    # --- FILTRERING ---
    if soketekst:
        # Vi søker i både tittel og OCR-tekst for bedre treff
        df = df[
            df['ocr_tekst'].str.contains(soketekst, case=False, na=False) | 
            df['tittel'].str.contains(soketekst, case=False, na=False)
        ]
    
    if vis_kun_varslet:
        df = df[df['varslet'] == True]

    # Vis antall
    st.metric("Antall dokumenter funnet", len(df))

    # --- TABELL ---
    # Gjør lenken klikkbar
    st.dataframe(
        df[['dato', 'tittel', 'lenke', 'varslet']],
        column_config={
            "lenke": st.column_config.LinkColumn("Dokument"),
            "varslet": st.column_config.CheckboxColumn("Varslet?", disabled=True),
            "dato": st.column_config.DateColumn("Dato", format="DD.MM.YYYY")
        },
        use_container_width=True,
        hide_index=True
    )

except Exception as e:
    st.error(f"Kunne ikke koble til databasen: {e}")