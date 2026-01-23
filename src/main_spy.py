import time
import json
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config

URL = "https://innsynpluss.onacos.no/skien/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def spioner_pa_trafikk():
    print("🕵️ Starter SPION-roboten...")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    # Aktiver logging av nettverk
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        time.sleep(5)

        # 1. UTFØR EN HANDLING FOR Å SKAPE TRAFIKK
        print("⌨️  Skriver '2024' i søkefeltet og trykker ENTER...")
        try:
            # Finn input-feltet (det er som regel bare ett synlig input-felt)
            input_felt = driver.find_element(By.TAG_NAME, "input")
            input_felt.click()
            input_felt.send_keys("2024")
            input_felt.send_keys(Keys.ENTER)
        except Exception as e:
            print(f"⚠️ Klarte ikke søke: {e}")

        print("⏳ Venter 8 sekunder på at data skal lastes...")
        time.sleep(8) 

        # 2. ANALYSER LOGGENE
        print("\n--- 📂 ANALYSERER NETTVERKSTRAFIKK ---")
        logs = driver.get_log("performance")
        
        fant_noe = False
        
        for entry in logs:
            try:
                message = json.loads(entry["message"])["message"]
                
                # Vi ser etter svar (Response)
                if message["method"] == "Network.responseReceived":
                    params = message["params"]
                    response = params["response"]
                    url = response["url"]
                    mime_type = response.get("mimeType", "")
                    
                    # Vi bryr oss kun om JSON-data fra onacos-domenet
                    if "json" in mime_type and "onacos" in url:
                        print(f"\n✅ FANT JSON-DATA!")
                        print(f"   URL: {url}")
                        
                        # Prøv å hente innholdet
                        request_id = params["requestId"]
                        try:
                            res_body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                            body_text = res_body['body']
                            
                            # Sjekk om dette ser ut som saker
                            if "tittel" in body_text or "saksnummer" in body_text or "resultater" in body_text:
                                print("   🎯 BINGO! Dette ser ut som dokumentlisten!")
                                print(f"   Innhold (starten): {body_text[:200]}...")
                                
                                # Prøv å lagre
                                data = json.loads(body_text)
                                # Ulike strukturer
                                items = data.get('resultater', []) or data.get('hits', []) or data.get('data', [])
                                if items:
                                    lagre_til_db(items)
                                    fant_noe = True
                        except:
                            print("   (Kunne ikke lese innholdet, kanskje det var tomt)")

            except:
                pass

        if not fant_noe:
            print("\n❌ Fant ingen JSON-trafikk med dokumenter. Sjekk skjermen mens den kjører!")

    except Exception as e:
        print(f"❌ Kritisk feil: {e}")
    finally:
        print("\n👋 Lukker om 5 sekunder...")
        time.sleep(5)
        driver.quit()

def lagre_til_db(saker):
    print(f"💾 Prøver å lagre {len(saker)} elementer...")
    conn = koble_til_db()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
    cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
    kommune_id = cur.fetchone()[0]
    
    teller = 0
    for sak in saker:
        # Tilpass denne til hva vi faktisk finner
        tittel = sak.get('tittel', 'Ukjent')
        saksnr = sak.get('saksnummer', {}).get('saksnummer', 'Ukjent')
        unik_id = sak.get('id') or saksnr
        
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
        if not cur.fetchone():
            print(f"   + Lagrer: {tittel[:30]}")
            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, 'mangler_url', %s, %s)
            """, (kommune_id, tittel, tittel, str(unik_id)))
            teller += 1
            
    conn.commit()
    print(f"🏁 Lagret {teller} dokumenter!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    spioner_pa_trafikk()