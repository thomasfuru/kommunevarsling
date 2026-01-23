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

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        print(f"❌ Kunne ikke starte Chrome: {e}")
        return None

# --- ROBOT: SKIEN (Innsyn+) ---
def scrape_skien(driver, cur, conn):
    print("\n🔵 Starter SKIEN-roboten...")
    try:
        base_url = "https://innsynpluss.onacos.no/skien/sok/#/"
        driver.get(base_url)
        wait = WebDriverWait(driver, 20)
        
        try:
            # Skien bruker 'details' i lenkene
            saker = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, 'details')]")))
        except:
            print("   ⚠️ Skien: Fant ingen saker (Timeout).")
            return

        sak_urler = []
        for sak in saker[:15]: # Økt til 15 saker
            href = sak.get_attribute("href")
            tittel = sak.text.strip()
            if href and not href.startswith("http"):
                href = "https://innsynpluss.onacos.no" + href
            if href and "details" in href:
                sak_urler.append((href, tittel))

        print(f"   Fant {len(sak_urler)} saker i Skien.")
        for perm_url, tittel in sak_urler:
            process_single_case(driver, cur, conn, perm_url, tittel, "Skien")

    except Exception as e:
        print(f"⚠️ Feil i Skien-roboten: {e}")

# --- FELLES FUNKSJON ---
def process_single_case(driver, cur, conn, url, tittel, kommune_navn):
    try:
        # Sjekk om finnes
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (url,))
        if cur.fetchone():
            return # Finnes allerede

        print(f"🔎 [{kommune_navn}] Behandler: {tittel[:40]}...")
        lagrings_tittel = f"[{kommune_navn}] {tittel}"

        driver.get(url)
        time.sleep(1)
        
        ocr_text = ""
        pdf_download_url = None

        try:
            # Let etter PDF-lenker
            fil_lenker = driver.find_elements(By.XPATH, "//a[contains(@href, 'file') or contains(@href, 'download') or contains(@href, 'variant=P')]")
            
            if fil_lenker:
                raw_href = fil_lenker[0].get_attribute("href")
                
                # Skien fiks
                if raw_href and not raw_href.startswith("http"):
                    pdf_download_url = "https://innsynpluss.onacos.no" + raw_href
                else:
                    pdf_download_url = raw_href

                if pdf_download_url:
                    # Last ned PDF
                    pdf_response = requests.get(pdf_download_url, timeout=15)
                    if pdf_response.status_code == 200:
                        try:
                            images = convert_from_bytes(pdf_response.content)
                            for image in images:
                                ocr_text += pytesseract.image_to_string(image, lang='nor') + "\n"
                        except Exception:
                            ocr_text = "OCR_FAILED"
        except Exception as e:
            print(f"   ⚠️ PDF-feil: {e}")

        if not ocr_text: ocr_text = tittel # Fallback

        # Lagre
        cur.execute("""
            INSERT INTO dokumenter (tittel, url_pdf, ekstern_id, ocr_tekst, dato)
            VALUES (%s, %s, %s, %s, NOW())
        """, (lagrings_tittel, url, url, ocr_text))
        conn.commit()
        print("   ✅ Lagret!")

    except Exception as e:
        print(f"⚠️ Feil under lagring av sak: {e}")

def main():
    driver = setup_driver()
    if not driver: return
    
    conn = get_db_connection()
    if not conn: 
        driver.quit()
        return
    cur = conn.cursor()

    try:
        # Porsgrunn er midlertidig deaktivert pga Geo-blocking i GitHub
        scrape_skien(driver, cur, conn)
        
    finally:
        print("💾 Ferdig. Rydder opp.")
        cur.close()
        conn.close()
        driver.quit()

if __name__ == "__main__":
    main()