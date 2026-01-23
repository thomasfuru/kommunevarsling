import time
import json
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager
import sys
import os

# Legg til path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config

URL = "https://innsynpluss.onacos.no/skien/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_med_cdp():
    print("🕵️ Starter avansert nettverks-overvåkning (CDP)...")
    
    # 1. Sett opp Chrome til å logge ALT som skjer på nettverket
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    # Dette er trikset: Vi ber Chrome lagre "Performance"-logger
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)

    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # 2. Trykk på Søk-knappen (samme logikk som før)
        print("🔎 Klikker på Søk-knappen...")
        try:
            knapp = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Søk')]")))
            knapp.click()
        except:
            driver.execute_script("document.querySelector('button[type=submit]').click();")

        print("⏳ Venter 5 sekunder på trafikk...")
        time.sleep(5) 

        # 3. Gå gjennom loggene Chrome har samlet
        print("📂 Analyserer logger...")
        logs = driver.get_log("performance")
        
        funnet = False
        
        for entry in logs:
            message = json.loads(entry["message"])["message"]
            
            # Vi ser etter svar fra nettverket (Network.responseReceived)
            if message["method"] == "Network.responseReceived":
                response_url = message["params"]["response"]["url"]
                
                # Sjekk om dette er API-kall til søk
                if "api/sok" in response_url or "api/search" in response_url:
                    print(f"✅ BINGO! Fant trafikk til: {response_url}")
                    
                    # Nå må vi bruke "request id" for å hente ut selve innholdet (body)
                    request_id = message["params"]["requestId"]
                    
                    try:
                        # Be Chrome om innholdet i pakken
                        response_body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                        body_content = response_body['body']
                        
                        data = json.loads(body_content)
                        
                        # Håndter ulike formater
                        resultater = data.get('resultater', [])
                        if not resultater: 
                            resultater = data.get('hits', [])
                            
                        print(f"📊 Fant {len(resultater)} saker i pakken.")
                        
                        if resultater:
                            lagre_til_db(resultater)
                            funnet = True
                            break # Stopp etter første gode treff
                            
                    except Exception as e:
                        # Noen ganger er dataene borte før vi rekker å hente dem, det er normalt
                        print(f"   Kunne ikke lese pakkeinnhold: {e}")

        if not funnet:
            print("❌ Fant ingen relevante API-pakker i loggen.")

    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        driver.quit()

def lagre_til_db(saker):
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
        unik_id = sak.get('id') or saksnr
        
        url = f"https://innsynpluss.onacos.no/skien/sak/{saks_id}"
        ocr_tekst = f"{tittel} {saksnr}"
        
        # Sjekk duplikat
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
        if not cur.fetchone():
            print(f"📥 Lagrer: {saksnr} - {tittel[:30]}...")
            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (kommune_id, tittel, url, ocr_tekst, str(unik_id)))
            teller += 1
            
    conn.commit()
    print(f"🏁 Ferdig! Lagret {teller} nye saker.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    hent_med_cdp()