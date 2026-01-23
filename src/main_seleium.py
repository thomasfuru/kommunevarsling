import time
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from config import Config

# URL til Skiens søkeside
URL = "https://innsynpluss.onacos.no/skien/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_med_nettleser():
    print("🤖 Starter robot-nettleseren...")
    
    # Oppsett av Chrome
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Kommenter ut denne for å SE nettleseren jobbe
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    
    # Starter nettleseren
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # VENT! Nettsiden bruker litt tid på å bygge seg opp
        print("⏳ Venter på at siden skal laste (5 sekunder)...")
        time.sleep(5) 
        
        # Acos Innsyn+ viser ofte en liste med resultater.
        # Vi ser etter elementer som inneholder teksten "Sak" eller lenker.
        
        # Her henter vi alle lenker som ser ut som saker
        # (Vi ser etter <a> tagger som har 'sak' i lenken sin)
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/sak/']")
        
        print(f"✅ Fant {len(elements)} mulige saker på siden.")
        
        if len(elements) == 0:
            print("   ⚠️ Fant ingen lenker. Prøver å finne tekst-bokser i stedet...")
            # Fallback: Hent alt som ser ut som rader i listen
            elements = driver.find_elements(By.CLASS_NAME, "search-result-item")

        conn = koble_til_db()
        cur = conn.cursor()
        
        # Sikre kommune
        cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
        cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
        kommune_id = cur.fetchone()[0]

        antall_lagret = 0
        
        # Gå gjennom funnene
        for elem in elements:
            try:
                tekst = elem.text
                if not tekst: continue
                
                # Prøv å finne lenken
                url = elem.get_attribute("href")
                if not url: url = URL # Fallback hvis ingen lenke
                
                # Lag en grov tittel av teksten (første linje)
                tittel = tekst.split("\n")[0]
                if len(tittel) > 200: tittel = tittel[:200]
                
                # Unik ID kan være URL-en
                unik_id = url
                
                # Sjekk database
                cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (unik_id,))
                if not cur.fetchone():
                    print(f"📥 Lagrer: {tittel[:40]}...")
                    cur.execute("""
                        INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (kommune_id, tittel, url, tekst, unik_id))
                    antall_lagret += 1
                    
            except Exception as e:
                print(f"   Feil med et element: {e}")

        conn.commit()
        print(f"🏁 Ferdig! Lagret {antall_lagret} nye poster.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Kritisk feil: {e}")
    finally:
        # Lukk nettleseren til slutt
        driver.quit()

if __name__ == "__main__":
    hent_med_nettleser()