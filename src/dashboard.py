import streamlit as st
import sys
import os

# --- FEILSØKINGS-MODUS ---
st.set_page_config(page_title="Feilsøking", layout="wide")

st.title("🛠️ Feilsøkings-modus")
st.write("Hvis du ser denne teksten, så virker Streamlit!")

# Sjekk 1: Kan vi lese Secrets?
st.subheader("1. Sjekker Secrets...")
try:
    if "database" in st.secrets:
        st.success("✅ Fant seksjonen [database] i Secrets!")
        # Prøver å lese en verdi for å se om nøklene stemmer
        try:
            test_host = st.secrets["database"]["DB_HOST"]
            st.write(f"Fant DB_HOST: `{test_host}`")
        except KeyError:
            st.error("❌ Fant [database], men mangler 'DB_HOST' (Store bokstaver?). Sjekk stavemåten!")
            st.write("Dette er nøklene jeg fant:", st.secrets["database"].keys())
    else:
        st.error("❌ Fant IKKE seksjonen [database]. Har du husket klammeparentesene i Secrets?")
        st.write("Dette er topp-nivå nøklene jeg fant:", st.secrets.keys())
except Exception as e:
    st.error(f"Noe er veldig galt med Secrets: {e}")

# Sjekk 2: Prøver å laste Config
st.subheader("2. Prøver å laste Config.py...")
try:
    # Vi må jukse litt med path for at den skal finne filen
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from config import Config
    st.success("✅ Config lastet uten problemer!")
except Exception as e:
    st.error(f"❌ Config kræsjet: {e}")
    st.stop() # Stopper her hvis config feiler

# Sjekk 3: Prøver databasekobling
st.subheader("3. Tester databasekobling...")
try:
    import psycopg2
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        database=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        port=Config.DB_PORT
    )
    st.success("✅ Suksess! Koblet til databasen.")
    conn.close()
except Exception as e:
    st.error(f"❌ Klarte ikke koble til databasen: {e}")