import requests
import json
import psycopg2
from config import Config

# --- LIM INN COOKIEN DIN HER ---
# Pass på at den står mellom hermetegnene " "
MIN_COOKIE = ".ASPXANONYMOUS=5ZoX9iDC3AEkAAAAMTc2YWZiYzMtMmJmOS00NjcxLWFlZDEtYmY1MTAxMDZmY2Zm_LkDR89s483W0pPSfODyfd2lQC6Mev1fbhoFHZNUTpQ1; ASP.NET_SessionId=2qkpwyxx5y4tevmm2dbhzyj4; lang=1; __AntiXsrfToken=f5a9306521194d6f8f66d48c0a57d4cb; ApplicationOptions=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJQb3J0YWxJRCI6MiwiU3ByYWtJRCI6MSwiTWVueXB1bmt0SUQiOjIxMCwiV2ViT2JqZWt0SUQiOjQwMDAsIk9iamVrdElEIjotMSwiX19BbnRpWHNyZlRva2VuIjoiZjVhOTMwNjUyMTE5NGQ2ZjhmNjZkNDhjMGE1N2Q0Y2IifQ.IHQ8mCYrthpDG6gmm8S3ha4KSOsXJVCVEsPsH204o78"
# -------------------------------

# Vi prøver standard søke-URL for Skien igjen
URL = "https://innsynpluss.onacos.no/skien/api/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def test_med_cookie():
    print("🍪 Tester med kun Cookie...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Cookie": MIN_COOKIE
    }

    # Standard søk etter alt ("")
    payload = {
        "fritekst": "",
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
            print(f"✅ SUKSESS! Vi er inne! Fant {antall} dokumenter.")
            
            # Lagrer til DB hvis vi fikk treff
            resultater = data.get('resultater', [])
            if resultater:
                lagre_til_db(resultater)
                
        elif resp.status_code == 401:
            print("❌ 401 Unauthorized - Cookien var ikke nok, eller den er utløpt.")
            print("Tips: Last nettsiden på nytt i Chrome, kopier ny cookie raskt.")
        else:
            print(f"❌ Feilkode: {resp.status_code}")
            print(resp.text[:300])

    except Exception as e:
        print(f"❌ Noe gikk galt: {e}")

def lagre_til_db(resultater):
    print("💾 Lagrer data til databasen...")
    conn = koble_til_db()
    cur = conn.cursor()
    
    # Sikre at Skien finnes
    cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
    cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
    kommune_id = cur.fetchone()[0]

    count = 0
    for sak in resultater:
        tittel = sak.get('tittel', 'Ukjent')
        saksnr = sak.get('saksnummer', {}).get('saksnummer', 'Ukjent')
        # ID-håndtering
        id_sak = sak.get('saksnummer', {}).get('saksId', '')
        url = f"https://innsynpluss.onacos.no/skien/sak/{id_sak}"
        unik_id = sak.get('id') or saksnr

        tekst = f"{tittel} {saksnr}"
        
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (kommune_id, tittel, url, tekst, str(unik_id)))
            count += 1
    
    conn.commit()
    print(f"🏁 Lagret {count} nye saker!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    test_med_cookie()