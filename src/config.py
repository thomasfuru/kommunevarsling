import streamlit as st
import os

class Config:
    # Vi prøver å hente fra Streamlit sine hemmeligheter først
    try:
        # Database
        DB_NAME = st.secrets["database"]["DB_NAME"]
        DB_USER = st.secrets["database"]["DB_USER"]
        DB_PASSWORD = st.secrets["database"]["DB_PASSWORD"]
        DB_HOST = st.secrets["database"]["DB_HOST"]
        DB_PORT = st.secrets["database"]["DB_PORT"]
        
        # Varsling
        SLACK_URL = st.secrets["varsling"]["SLACK_URL"]
        
    except FileNotFoundError:
        # Hvis vi ikke finner secrets (f.eks. kjører i GitHub Actions senere),
        # kan vi hente fra miljøvariabler (Environment Variables)
        DB_NAME = os.getenv("DB_NAME", "postgres")
        DB_USER = os.getenv("DB_USER")
        DB_PASSWORD = os.getenv("DB_PASSWORD")
        DB_HOST = os.getenv("DB_HOST")
        DB_PORT = os.getenv("DB_PORT", "5432")
        SLACK_URL = os.getenv("SLACK_URL")

    # Søkeordene beholder vi her inntil vi flytter dem til databasen helt
    SOKEORD = ["Luksefjellvegen", "Gbnr", "Skole", "Barnehage", "Reguleringsplan"]