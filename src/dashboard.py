import streamlit as st
import psycopg2
import pandas as pd
import os
import sys

# --- OPPSETT ---
st.set_page_config(page_title="Kommunevarsling", layout="wide")

# Tittel
st.title("🔎 Kommunevarsling: Skien & Porsgrunn")

# --- 1. HENT PASSORD (SECRETS) ---
# Vi gjør dette manuelt her for å unngå Config-feil
try:
    # Sjekk om vi kjører lokalt eller på Streamlit Cloud
    if "database" in st.secrets:
        db_config = st.secrets["database"]
    else:
        st.error("❌ Fant ingen hemmeligheter (Secrets). Har du lagt dem inn i Streamlit?")
        st.stop()
except Exception as e:
    st.error(f"❌ Noe gikk galt med lesing av Secrets: {e}")
    st.stop()

# --- 2. KOBLE TIL DATABASE ---
@st.cache_data(ttl=600)  # Cacher data i 10 minutter
def hent_data():
    try:
        conn = psycopg2.connect(
            host=db_config["DB_HOST"],
            database=db_config["DB_NAME"],
            user=db_config["DB_USER"],
            password=db_config["DB_PASSWORD"],
            port=db_config["DB_PORT"]
        )
        query = "SELECT id, tittel, url_pdf, dato FROM dokumenter ORDER BY dato DESC LIMIT 50;"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return str(e)

# --- 3. VIS DATA ---
data = hent_data()

if isinstance(data, str):
    # Hvis data er en tekststreng, betyr det at vi fikk en feilmelding
    st.error(f"❌ Klarte ikke koble til databasen: {data}")
    st.info("Tips: Sjekk at passordet i Streamlit Secrets er helt riktig.")
else:
    # Hvis data er en tabell
    if data.empty:
        st.warning("⚠️ Databasen er koblet til, men den er tom! Roboten har ikke funnet noe ennå.")
    else:
        st.success(f"✅ Viser de siste {len(data)} sakene.")
        
        # Gjør tabellen penere
        for index, row in data.iterrows():
            with st.expander(f"{row['dato']} - {row['tittel']}"):
                st.write(f"**Tittel:** {row['tittel']}")
                st.markdown(f"[📄 Åpne dokument]({row['url_pdf']})")