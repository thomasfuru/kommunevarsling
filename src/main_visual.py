import time
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

def hent_visuelt():
    print("🤖 Starter VISUELL robot...")
    
    chrome_options = Options()
    # VIKTIG: Vi setter en stor skjermstørrelse så vi ikke får mobil-menyer
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20) # Gir den god tid (20 sek)

    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # 1. TVING ET KLIKK PÅ SØKEKNAPPEN
        print("🔎 Leter etter 'Søk'-knappen...")
        try:
            # Vi ser etter knappen med tekst "Søk"
            knapp = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Søk')]")))
            
            # Marker knappen med gult så du ser den
            driver.execute_script("arguments[0].style.backgroundColor = 'yellow';", knapp)
            time.sleep(1)
            
            print("   👉 Klikker!")
            knapp.click()
        except Exception as e:
            print(f"   ⚠️ Fant ikke knappen vanlig vei. Prøver JavaScript-klikk... ({e})")
            # Plan B: Tvangs-klikk med JavaSript
            driver.execute_script("document.querySelector('button[type=submit]').click();")

        # 2. VENT PÅ AT LISTEN SKAL LASTE
        print("⏳ Venter 10 sekunder på at resultatene skal dukke opp...")
        time.sleep(10)

        # 3. TA BEVIS-BILDE
        print("📸 Tar skjermbilde (screenshot.png)...")
        driver.save_screenshot("screenshot.png")
        print("   ✅ Bilde lagret! Sjekk mappen din etterpå.")

        # 4. PRØV Å HENTE DATA (Generelt søk etter tekstblokker)
        # Vi ser etter elementer som ser ut som rader. Acos bruker ofte 'div' med spesielle klasser.
        # Vi henter ALT tekstinnhold for å se om vi finner noe som ligner en sak.
        
        body_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Tell antall ganger ordet "Sak" eller årstallet "2025"/"2026" dukker opp
        antall_saker = body_text.lower().count("sak") + body_text.count("2025") + body_text.count("2026")
        
        print(f"📊 Analyse av siden: Fant ordet 'sak' eller årstall {antall_saker} ganger.")

        if antall_saker < 5:
            print("⚠️ Det virker som listen er tom. Sjekk screenshot.png!")
        else:
            print("✅ Det ser ut som vi har innhold! Prøver å lagre...")
            
            # Her gjør vi et grovt forsøk på å finne lenker igjen
            elements = driver.find_elements(By.CSS_SELECTOR, "a")
            conn = koble_til_db()
            cur = conn.cursor()
            
            # Sikre kommune
            cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
            cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
            kommune_id = cur.fetchone()[0]
            
            teller = 0
            for elem in elements:
                try:
                    tekst = elem.text.strip()
                    url = elem.get_attribute("href")
                    
                    # Filtrer: Vi vil ha lenker som har '/sak/' eller '/dokument/' i seg, og som har tekst
                    if url and ("/sak/" in url or "/dokument/" in url) and len(tekst) > 5:
                        
                        unik_id = url.split("/")[-1]
                        
                        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
                        if not cur.fetchone():
                            print(f"📥 {tekst[:30]}...")
                            cur.execute("""
                                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (kommune_id, tekst, url, tekst, str(unik_id)))
                            teller += 1
                except:
                    pass
            
            conn.commit()
            print(f"🏁 Ferdig! Lagret {teller} nye saker.")
            cur.close()
            conn.close()

    except Exception as e:
        print(f"❌ Feil: {e}")
        driver.save_screenshot("error_screenshot.png")
    finally:
        driver.quit()

if __name__ == "__main__":
    hent_visuelt()