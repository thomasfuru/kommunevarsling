import requests
import json
import psycopg2
from config import Config
from datetime import datetime

# --- KONFIGURASJON FOR SKIEN ---
BASE_URL = "https://innsynpluss.onacos.no/skien"
# Dette er API-et som gir oss selve dokumentlisten
API_SEARCH_URL = f"{BASE_URL}/api/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_skien_acos():
    print(f"🚀 Starter henting fra Skien (Acos Innsyn+): {datetime.now()}")

    # 1. Start en sesjon (som en nettleser)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    })

    try:
        # 2. Besøk forsiden først for å få Cookies og XSRF-token
        print("🔐 Henter sikkerhetstoken (Cookies)...")
        resp_init = session.get(BASE_URL, timeout=10)
        
        # Finn XSRF-TOKEN i cookiene vi fikk
        xsrf_token = session.cookies.get("XSRF-TOKEN")
        
        if not xsrf_token:
            print("❌ Fant ikke XSRF-TOKEN. Skien har kanskje endret sikkerhet.")
            # Prøv å se om token ligger i headeren istedenfor
            return

        print(f"✅ Fikk token: {xsrf_token[:15]}...")

        # 3. Forbered søket (Payload)
        # Vi legger til tokenet i headeren, det er dette som låser opp døren!
        headers = {
            "X-Xsrf-Token": xsrf_token,
            "Content-Type": "application/json"
        }

        # Søkeparametere: Henter de 20 nyeste dokumentene/sakene
        payload = {
            "fritekst": "", # Tomt søk = vis alt
            "side": 0,
            "antall": 20,
            "sortering": "publisert_dato_synkende", # Vi vil ha det nyeste først
            "dokumenttype": ["I", "U"] # I = Inngående, U = Utgående (Dropp N/X notater)
        }

        print("🔎 Søker i postlisten...")
        resp_api = session.post(API_SEARCH_URL, json=payload, headers=headers)

        if resp_api.status_code != 200:
            print(f"❌ Feil fra API: {resp_api.status_code}")
            print(f"Svar: {resp_api.text[:300]}")
            return

        data = resp_api.json()
        treff_liste = data.get("resultater", [])
        
        print(f"✅ Fant {len(treff_liste)} dokumenter.")

        # 4. Lagre i Database
        conn = koble_til_db()
        cur = conn.cursor()

        # Sjekk at Skien finnes
        cur.execute("SELECT id FROM kommuner WHERE navn = 'Skien'")
        if not cur.fetchone():
            cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien')")
            conn.commit()
        
        cur.execute("SELECT id FROM kommuner WHERE navn = 'Skien'")
        kommune_id = cur.fetchone()[0]
        
        antall_lagret = 0

        for sak in treff_liste:
            # Acos-strukturen varierer, men ofte ser den slik ut:
            tittel = sak.get("tittel", "Uten tittel")
            saksnr = sak.get("saksnummer", {}).get("saksnummer", "")
            
            # Lag en lenke til saken
            saks_id = sak.get("saksnummer", {}).get("saksId", "") # Kan være en ID eller år/sekvens
            if not saks_id and saksnr:
                # Fallback hvis ID mangler, bruk saksnummer i URL
                url_sak = f"{BASE_URL}/sak/{saksnr}"
            else:
                url_sak = f"{BASE_URL}/sak/{saks_id}"

            # Bruk unik ID fra Acos for å unngå duplikater
            ekstern_id = sak.get("id") or saksnr

            # Sjekk om lagret
            cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (str(ekstern_id),))
            if cur.fetchone():
                continue

            print(f"📥 Lagrer: {saksnr} - {tittel[:40]}...")

            # Vi kombinerer tittel og saksnummer for søk
            sokbar_tekst = f"{tittel} {saksnr}"

            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (kommune_id, tittel, url_sak, sokbar_tekst, str(ekstern_id)))
            
            antall_lagret += 1

        conn.commit()
        print(f"🏁 Ferdig! Lagret {antall_lagret} nye poster.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Kritisk feil: {e}")

if __name__ == "__main__":
    hent_skien_acos()