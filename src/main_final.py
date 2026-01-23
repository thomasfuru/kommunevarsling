import time
import json
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config

URL = "https://innsynpluss.onacos.no/skien/sok"
BASE_URL = "https://innsynpluss.onacos.no"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_fasit_data():
    print("🏆 Starter 'Fasit-roboten'...")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # Vi trenger ikke søke! Dataene lastes automatisk via 'overviewInit'
        print("⏳ Venter 10 sekunder på at start-dataene skal laste inn...")
        time.sleep(10) 

        print("\n--- 📂 ANALYSERER NETTVERKSTRAFIKK ---")
        logs = driver.get_log("performance")
        
        antall_totalt = 0
        
        for entry in logs:
            try:
                message = json.loads(entry["message"])["message"]
                
                if message["method"] == "Network.responseReceived":
                    params = message["params"]
                    url = params["response"]["url"]
                    
                    # Vi ser spesifikt etter den URL-en DU fant
                    if "overviewInit" in url or "overview" in url:
                        print(f"✅ Fant data-pakke: {url}")
                        
                        request_id = params["requestId"]
                        try:
                            res_body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                            body_text = res_body['body']
                            data = json.loads(body_text)
                            
                            # HER ER MAGIEN: Vi navigerer inn i strukturen du fant
                            items = []
                            
                            # Prøv struktur A (overviewInit)
                            try:
                                items = data['content']['searchItems']['items']
                            except:
                                pass
                                
                            # Prøv struktur B (vanlig overview)
                            if not items:
                                try:
                                    items = data['resultater']
                                except:
                                    pass

                            if items:
                                print(f"   🎯 Fant {len(items)} dokumenter i denne pakken!")
                                lagre_til_db(items)
                                antall_totalt += len(items)
                                
                        except Exception as e:
                            # print(f"   (Ignorerte en pakke: {e})")
                            pass

            except:
                pass

        if antall_totalt == 0:
            print("❌ Fant ingen dokumenter. Sjekk at nettsiden lastet ordentlig.")
        else:
            print(f"🎉 FERDIG! Totalt {antall_totalt} dokumenter behandlet.")

    except Exception as e:
        print(f"❌ Kritisk feil: {e}")
    finally:
        driver.quit()

def lagre_til_db(items):
    conn = koble_til_db()
    cur = conn.cursor()
    
    # Sikre kommune
    cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
    cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
    kommune_id = cur.fetchone()[0]
    
    lagret_teller = 0
    for item in items:
        # Hent data basert på JSON-strukturen du fant
        tittel = item.get('title', 'Uten tittel')
        doc_type = item.get('type', '')
        
        # ID og URL
        ekstern_id = item.get('identifier', '')
        # URLen i JSON er ofte relativ (starter med /), så vi legger til base_url
        raw_url = item.get('navigateUrl', '')
        if raw_url.startswith("http"):
            url = raw_url
        else:
            url = f"{BASE_URL}{raw_url}"
            
        # Lag en fin tekst for databasen
        full_tekst = f"{tittel} ({doc_type})"
        
        # Sjekk om den finnes fra før
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(ekstern_id),))
        if not cur.fetchone():
            print(f"   💾 Lagrer: {tittel[:40]}...")
            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (kommune_id, tittel, url, full_tekst, str(ekstern_id)))
            lagret_teller += 1
            
    conn.commit()
    if lagret_teller > 0:
        print(f"      -> La til {lagret_teller} nye i databasen.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    hent_fasit_data()