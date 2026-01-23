import os
import sys
import time
import requests
import psycopg2
import pytesseract
from pdf2image import convert_from_bytes
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- IMPORT FIX (For at skyen skal finne config.py) ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from config import Config
except ImportError:
    # Fallback hvis config feiler (skjer sjeldent med fixen over)
    print("⚠️ Kunne ikke importere Config direkte. Sjekk at config.py ligger i src-mappen.")
    class Config:
        DB_HOST = os.getenv("DB_HOST")
        DB_USER = os.getenv("DB_USER")
        DB_PASSWORD = os.getenv("DB_PASSWORD")
        DB_NAME = os.getenv("DB_NAME", "postgres")
        DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            host=Config.DB_HOST,
            port=Config.DB_PORT
        )
        return conn
    except Exception as e:
        print(f"❌ Feil ved databasetilkobling: {e}")
        return None

def hent_fasit_data():
    print("🏆 Starter 'Fasit-roboten'...")
    
    # --- OPPSETT AV CHROME (ROBUST FOR SKYEN) ---
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")       # Kjører uten vindu (MÅ være med)
    options.add_argument("--no-sandbox")         # Sikkerhetsinnstilling for Linux
    options.add_argument("--disable-dev-shm-usage") # <--- DENNE HINDRER KRÆSJ PÅ SERVER
    options.add_argument("--disable-gpu")        # Sparer ressurser
    options.add_argument("--window-size=1920,1080")
    
    # Prøv å starte Chrome
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        print(f"❌ Kunne ikke starte Chrome: {e}")
        return

    conn = get_db_connection()
    if not conn:
        print("❌ Stopper fordi vi mangler databasekobling.")
        driver.quit()
        return

    cur = conn.cursor()

    try:
        url = "https://www.skien.kommune.no/skien-kommune/politikk-og-innsyn/innsyn-postliste-og-arkivplan/"
        driver.get(url)
        
        # Vent til tabellen lastes (max 15 sekunder)
        wait = WebDriverWait(driver, 15)
        
        # Finn lenken til "Siste 50 publiserte saker" (eller tilsvarende tabell)
        # NB: Hvis Skien endrer nettsiden, må denne justeres. 
        # Vi ser etter rader i en tabell. Juster selectoren etter behov.
        # Her antar vi at scriptet ditt virket lokalt, så jeg bruker generell logikk:
        
        # (Legg inn din spesifikke navigasjon her hvis du må klikke deg inn noen steder først)
        # For dette eksempelet antar vi at vi finner dokumenter på siden eller en sub-side.
        # Hvis du må klikke på en knapp først, legg det inn her.
        
        # Eksempel: Hent alle rader som ser ut som dokumenter
        rader = driver.find_elements(By.TAG_NAME, "tr") # Dette henter alle tabellrader
        
        print(f"Fant {len(rader)} rader. Sjekker de 20 første...")

        for index, rad in enumerate(rader[:20]): # Begrenser til 20 for testing/fart
            try:
                tekst = rad.text
                if not tekst:
                    continue

                # Prøv å finne en PDF-lenke i raden
                lenker = rad.find_elements(By.TAG_NAME, "a")
                pdf_url = None
                tittel = tekst[:100] # Bruker starten av teksten som tittel hvis vi ikke finner noe bedre
                
                for lenke in lenker:
                    href = lenke.get_attribute("href")
                    if href and ".pdf" in href.lower():
                        pdf_url = href
                        tittel = lenke.text or tittel
                        break # Fant PDF, går videre
                
                if pdf_url:
                    print(f"📄 Behandler: {tittel}")
                    
                    # Sjekk om den finnes fra før
                    cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (pdf_url,))
                    if cur.fetchone():
                        print("   -> Finnes allerede, hopper over.")
                        continue

                    # Last ned PDF og kjør OCR (Tekst-tolkning)
                    ocr_text = ""
                    try:
                        pdf_response = requests.get(pdf_url, timeout=10)
                        if pdf_response.status_code == 200:
                            # Her konverterer vi PDF til tekst (OCR)
                            try:
                                images = convert_from_bytes(pdf_response.content)
                                for image in images:
                                    ocr_text += pytesseract.image_to_string(image, lang='nor') + "\n"
                            except Exception as ocr_error:
                                print(f"   ⚠️ OCR feilet (Tesseract mangler kanskje i skyen?): {ocr_error}")
                                ocr_text = "OCR_FAILED" # Markerer at vi ikke fikk tekst
                    except Exception as e:
                        print(f"   ⚠️ Kunne ikke laste ned PDF: {e}")

                    # Lagre til databasen
                    cur.execute("""
                        INSERT INTO dokumenter (tittel, url_pdf, ekstern_id, ocr_tekst, dato)
                        VALUES (%s, %s, %s, %s, NOW())
                    """, (tittel, pdf_url, pdf_url, ocr_text))
                    
                    conn.commit()
                    print("   ✅ Lagret i database!")

            except Exception as e:
                print(f"⚠️ Feil med en rad: {e}")
                continue

    except Exception as main_error:
        print(f"❌ En hovedfeil oppstod: {main_error}")
    
    finally:
        print("💾 Lukker og rydder opp...")
        cur.close()
        conn.close()
        driver.quit()
        print("✅ Ferdig!")

if __name__ == "__main__":
    hent_fasit_data()