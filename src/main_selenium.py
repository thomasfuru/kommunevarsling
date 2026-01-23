import time
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

def hent_med_nettleser():
    print("🤖 Starter robot-nettleseren...")
    
    chrome_options = Options()
    # Vi kjører med synlig nettleser
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1200,800") # Setter en god størrelse
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 10) # En "smart-venter" som venter opptil 10 sekunder

    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # 1. FINN SØKEKNAPPEN (Mer robust metode)
        print("🔎 Leter etter knappen som heter 'Søk'...")
        try:
            # XPath: Finn et element som inneholder teksten "Søk"
            knapp = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Søk')]")))
            
            # (Visuelt triks: Tegn en rød ramme rundt knappen så du ser at den fant den)
            driver.execute_script("arguments[0].style.border='3px solid red'", knapp)
            time.sleep(1) 
            
            print("   👉 Klikker på knappen!")
            knapp.click()
            
        except Exception as e:
            print(f"   ⚠️ Fant ikke søkeknappen: {e}")
            # Fallback: Prøv å finne input-feltet og trykk ENTER
            input_felt = driver.find_element(By.TAG_NAME, "input")
            input_felt.send_keys(" ") # Skriv et mellomrom
            input_felt.send_keys(Keys.ENTER)

        print("⏳ Venter på at resultatlisten skal laste...")
        time.sleep(5) # Gi den litt tid til å hente data

        # 2. SKRAP RESULTATENE
        # Vi ser etter lenker som inneholder 'sak' eller 'mote'
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/sak/'], a[href*='/mote/']")
        
        print(f"✅ Fant {len(elements)} lenker i listen.")
        
        conn = koble_til_db()
        cur = conn.cursor()
        
        # Sikre kommune
        cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
        cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
        kommune_id = cur.fetchone()[0]

        antall_lagret = 0
        
        for elem in elements:
            try:
                # Noen ganger er lenkene skjult eller tomme, sjekk at de er synlige
                if not elem.is_displayed():
                    continue

                tekst = elem.text.strip()
                url = elem.get_attribute("href")
                
                if not tekst or not url: continue
                
                # Acos legger ofte saksnummer og tittel på forskjellige linjer
                # Vi slår dem sammen for bedre søk
                linjer = tekst.split('\n')
                tittel = linjer[0]
                full_tekst = " ".join(linjer)

                unik_id = url.split('/')[-1]

                # Sjekk database
                cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
                if not cur.fetchone():
                    print(f"📥 Lagrer: {tittel[:40]}...")
                    cur.execute("""
                        INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (kommune_id, tittel, url, full_tekst, str(unik_id)))
                    antall_lagret += 1
                    
            except Exception as e:
                pass 

        conn.commit()
        print(f"🏁 Ferdig! Lagret {antall_lagret} nye poster.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Kritisk feil: {e}")
    finally:
        print("👋 Lukker nettleseren om 5 sekunder...")
        time.sleep(5)
        driver.quit()

if __name__ == "__main__":
    hent_med_nettleser()