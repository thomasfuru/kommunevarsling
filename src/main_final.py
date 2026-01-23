import os
import sys
import time
import requests
import psycopg2
import pytesseract
from pdf2image import convert_from_bytes
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- IMPORT FIX ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from config import Config
except ImportError:
    print("⚠️ Kunne ikke importere Config direkte. Bruker miljøvariabler.")
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
    print("🏆 Starter 'Skien Spesial-roboten'...")
    
    # --- OPPSETT AV CHROME ---
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        print(f"❌ Kunne ikke starte Chrome: {e}")
        return

    conn = get_db_connection()
    if not conn:
        print("❌ Ingen database. Avslutter.")
        driver.quit()
        return

    cur = conn.cursor()

    try:
        # VI GÅR RETT TIL ACOS INNSYN FOR SKIEN
        base_url = "https://innsynpluss.onacos.no/skien/sok/#/"
        print(f"🌍 Går til: {base_url}")
        driver.get(base_url)
        
        # Vent på at siden skal laste (ACOS er tregt og bruker mye Javascript)
        wait = WebDriverWait(driver, 20)
        
        # Vi venter til vi ser lenker som inneholder "details" (Dette er sakene)
        print("⏳ Venter på at listen skal lastes...")
        saker = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, 'details')]")))
        
        print(f"Fant {len(saker)} saker/dokumenter. Sjekker de 10 nyeste...")

        # Vi må samle URL-ene først, fordi hvis vi klikker oss bort mister vi listen
        sak_urler = []
        for sak in saker[:10]:
            href = sak.get_attribute("href")
            tittel = sak.text.strip()
            # Fiks URL hvis den er relativ
            if href and not href.startswith("http"):
                href = "https://innsynpluss.onacos.no" + href
            
            if href and "details" in href:
                sak_urler.append((href, tittel))

        # Nå går vi inn på hver enkelt sak
        for perm_url, tittel in sak_urler:
            try:
                # 1. SJEKK OM DEN ER LAGRET FRA FØR
                # Vi bruker perm_url som ID, for den er unik og trygg
                cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (perm_url,))
                if cur.fetchone():
                    print(f"⏭️  Har allerede: {tittel[:30]}...")
                    continue

                print(f"🔎 Behandler ny sak: {tittel[:30]}...")
                
                # 2. GÅ INN PÅ DETALJ-SIDEN FOR Å FINNE PDF
                driver.get(perm_url)
                time.sleep(3) # Gi detaljsiden tid til å laste
                
                # Prøv å finne nedlastings-knapp eller PDF-ikon
                pdf_download_url = None
                ocr_text = ""

                try:
                    # Let etter lenker som ser ut som nedlastinger/filer
                    # ACOS varierer litt, men ofte er det en lenke inni dokument-visningen
                    fil_lenker = driver.find_elements(By.XPATH, "//a[contains(@href, 'api/file') or contains(@href, 'download')]")
                    
                    if fil_lenker:
                        pdf_download_url = fil_lenker[0].get_attribute("href")
                        if pdf_download_url and not pdf_download_url.startswith("http"):
                             pdf_download_url = "https://innsynpluss.onacos.no" + pdf_download_url
                        
                        print("   📄 Fant PDF-fil, laster ned for lesing...")
                        
                        # Last ned og gjør OCR
                        pdf_response = requests.get(pdf_download_url, timeout=15)
                        if pdf_response.status_code == 200:
                            try:
                                images = convert_from_bytes(pdf_response.content)
                                for image in images:
                                    ocr_text += pytesseract.image_to_string(image, lang='nor') + "\n"
                            except Exception as ocr_e:
                                print(f"   ⚠️ OCR feilet: {ocr_e}")
                                ocr_text = "OCR_FAILED"
                except Exception as e:
                    print(f"   ⚠️ Fant ingen PDF å lese: {e}")

                # Hvis vi ikke fant PDF-tekst, lagre tittelen som tekst så vi har noe
                if not ocr_text:
                    ocr_text = tittel

                # 3. LAGRE TIL DATABASE
                # Viktig: Vi lagrer perm_url (details) som 'url_pdf', slik at brukeren kommer til den trygge siden
                cur.execute("""
                    INSERT INTO dokumenter (tittel, url_pdf, ekstern_id, ocr_tekst, dato)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (tittel, perm_url, perm_url, ocr_text))
                
                conn.commit()
                print("   ✅ Lagret!")

            except Exception as e:
                print(f"⚠️ Feil med en sak: {e}")
                continue

    except Exception as main_error:
        print(f"❌ En hovedfeil oppstod: {main_error}")
    
    finally:
        print("💾 Ferdig. Rydder opp.")
        cur.close()
        conn.close()
        driver.quit()

if __name__ == "__main__":
    hent_fasit_data()