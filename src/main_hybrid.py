import time
import requests
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sys
import os

# Legg til path for config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config

# URL-er
BASE_URL = "https://innsynpluss.onacos.no/skien"
API_URL = "https://innsynpluss.onacos.no/skien/api/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_hybrid():
    print("🤖 Starter Hybrid-roboten...")
    
    # 1. Start nettleser for å hente 'nøkler'
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Vi kjører synlig for sikkerhets skyld
    chrome_options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        print("🔐 Går til forsiden for å hente Cookies og Tokens...")
        driver.get(f"{BASE_URL}/sok")
        
        # Vent litt så siden får satt alle cookies
        time.sleep(5)
        
        # 2. STJEL NØKLENE (Cookies og XSRF-token)
        selenium_cookies = driver.get_cookies()
        
        # Konverter til Requests-format
        session = requests.Session()
        xsrf_token = None
        
        for cookie in selenium_cookies:
            # Legg cookie inn i vår sesjon
            session.cookies.set(cookie['name'], cookie['value'])
            
            # Se etter XSRF-tokenet
            if cookie['name'].upper() == "XSRF-TOKEN":
                xsrf_token = cookie['value']
        
        print(f"🍪 Fant {len(selenium_cookies)} cookies.")
        
        if xsrf_token:
            print(f"🔑 Fant XSRF-TOKEN: {xsrf_token[:10]}...")
        else:
            print("⚠️ Fant ikke XSRF-token i cookies. Prøver uten (kan feile)...")

        # Vi trenger ikke nettleseren mer nå
        driver.quit()
        
        # 3. KOBLE TIL API-ET MED NØKLENE
        print("🚀 Kobler til API-et...")
        
        headers = {
            "Content-Type": "application/json",
            "X-Xsrf-Token": xsrf_token, # Dette er nøkkelen!
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Søkeparametere
        payload = {
            "fritekst": "", # Tomt = alt
            "side": 0,
            "antall": 20, # Hent de 20 siste
            "sortering": "publisert_dato_synkende",
            "dokumenttype": ["I", "U"] # Inngående og Utgående
        }
        
        resp = session.post(API_URL, json=payload, headers=headers)
        
        if resp.status_code != 200:
            print(f"❌ Feil fra API: {resp.status_code}")
            print(resp.text[:500])
            return

        data = resp.json()
        antall_treff = data.get('totaltAntallTreff', 0)
        resultater = data.get('resultater', [])
        
        print(f"✅ SUKSESS! Fant {antall_treff} dokumenter via API.")

        # 4. LAGRE I DATABASEN
        lagre_til_db(resultater)

    except Exception as e:
        print(f"❌ Noe gikk galt: {e}")
        try:
            driver.quit()
        except:
            pass

def lagre_til_db(saker):
    if not saker:
        print("   Ingen saker å lagre.")
        return

    conn = koble_til_db()
    cur = conn.cursor()
    
    # Sikre kommune
    cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
    cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
    kommune_id = cur.fetchone()[0]
    
    teller = 0
    for sak in saker:
        tittel = sak.get('tittel', 'Uten tittel')
        saksnr = sak.get('saksnummer', {}).get('saksnummer', 'Ukjent')
        saks_id = sak.get('saksnummer', {}).get('saksId', '')
        
        # Url til saken
        url = f"{BASE_URL}/sak/{saks_id}"
        
        # Unik ID
        unik_id = sak.get('id') or saksnr
        
        # Slå sammen tekst for søk
        ocr_tekst = f"{tittel} {saksnr}"
        
        # Sjekk duplikat
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
        if not cur.fetchone():
            print(f"📥 {saksnr}: {tittel[:40]}...")
            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (kommune_id, tittel, url, ocr_tekst, str(unik_id)))
            teller += 1
            
    conn.commit()
    print(f"🏁 Ferdig! Lagret {teller} nye saker i databasen.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    hent_hybrid()