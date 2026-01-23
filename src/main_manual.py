import requests
import json
import psycopg2
from config import Config

# --- HER SKAL DU LIME INN ---
# 1. Lim inn HELE cookie-teksten mellom hermetegnene:
MIN_COOKIE = ".ASPXANONYMOUS=5ZoX9iDC3AEkAAAAMTc2YWZiYzMtMmJmOS00NjcxLWFlZDEtYmY1MTAxMDZmY2Zm_LkDR89s483W0pPSfODyfd2lQC6Mev1fbhoFHZNUTpQ1; ASP.NET_SessionId=2qkpwyxx5y4tevmm2dbhzyj4; lang=1; __AntiXsrfToken=f5a9306521194d6f8f66d48c0a57d4cb; ApplicationOptions=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJQb3J0YWxJRCI6MiwiU3ByYWtJRCI6MSwiTWVueXB1bmt0SUQiOjIxMCwiV2ViT2JqZWt0SUQiOjQwMDAsIk9iamVrdElEIjotMSwiX19BbnRpWHNyZlRva2VuIjoiZjVhOTMwNjUyMTE5NGQ2ZjhmNjZkNDhjMGE1N2Q0Y2IifQ.IHQ8mCYrthpDG6gmm8S3ha4KSOsXJVCVEsPsH204o78"

# 2. Lim inn tokenet her:
MITT_TOKEN = "LIM_INN_TOKEN_HER"

# -----------------------------

URL = "https://innsynpluss.onacos.no/skien/api/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_manuelt():
    print("🕵️‍♂️ Prøver å hente data med stjålne nøkler...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Cookie": MIN_COOKIE,       # Her bruker vi cookien din
        "X-Xsrf-Token": MITT_TOKEN  # Her bruker vi tokenet ditt
    }

    payload = {
        "fritekst": "bygg",  # Vi søker etter "bygg" for å få treff
        "side": 0,
        "antall": 10,
        "sortering": "publisert_dato_synkende",
        "dokumenttype": ["I", "U"] 
    }

    try:
        resp = requests.post(URL, json=payload, headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            antall = data.get('totaltAntallTreff', 0)
            resultater = data.get('resultater', [])
            print(f"✅ SUKSESS! Fant {antall} dokumenter.")
            
            # Lagre til DB (forenklet)
            conn = koble_til_db()
            cur = conn.cursor()
            
            # Sørg for at Skien finnes
            cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
            cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
            kommune_id = cur.fetchone()[0]

            lagret_teller = 0
            for sak in resultater:
                tittel = sak.get('tittel', 'Ukjent')
                saksnr = sak.get('saksnummer', {}).get('saksnummer', 'Ukjent')
                saks_id = sak.get('saksnummer', {}).get('saksId', '')
                url_sak = f"https://innsynpluss.onacos.no/skien/sak/{saks_id}"
                
                # Unik ID
                unik_id = sak.get('id') or saksnr
                
                print(f"   📄 Fant: {saksnr} - {tittel[:30]}...")

                cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
                if not cur.fetchone():
                    tekst = f"{tittel} {saksnr}"
                    cur.execute("""
                        INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (kommune_id, tittel, url_sak, tekst, str(unik_id)))
                    lagret_teller += 1
            
            conn.commit()
            print(f"🏁 Ferdig! Lagret {lagret_teller} nye saker i databasen.")
            cur.close()
            conn.close()

        else:
            print(f"❌ Feilkode: {resp.status_code}")
            print("Tokenet eller Cookien er sannsynligvis feil/utløpt, eller URL er feil.")
            print(resp.text[:500])

    except Exception as e:
        print(f"❌ Noe gikk galt: {e}")

if __name__ == "__main__":
    hent_manuelt()