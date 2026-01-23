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
from selenium.common.exceptions import TimeoutException

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
    
    # --- NYTT: FAKE ID OG UTÅLMODIG ---
    # Vi later som vi er en vanlig Windows PC
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # 'eager' betyr: Ikke vent på bilder og scripts. Kjør så fort teksten er der.
    options.page_load_strategy = 'eager' 

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as e:
        print(f"❌ Kunne ikke starte Chrome: {e}")
        return None

# --- ROBOT 1: SKIEN ---
def scrape_skien(driver, cur, conn):
    print("\n🔵 Starter SKIEN-roboten...")
    try:
        base_url = "https://innsynpluss.onacos.no/skien/sok/#/"
        driver.get(base_url)
        wait = WebDriverWait(driver, 20)
        
        try:
            saker = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, 'details')]")))
        except:
            print("   ⚠️ Skien: Fant ingen saker (Timeout).")
            return

        sak_urler = []
        for sak in saker[:10]: 
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

# --- ROBOT 2: PORSGRUNN (NY STRATEGI) ---
def scrape_porsgrunn(driver, cur, conn):
    print("\n🟢 Starter PORSGRUNN-roboten (Fake User + Eager Mode)...")
    
    # Vi går tilbake til domenenavnet, men med ny "forkledning"
    url = "https://innsyn.porsgrunn.kommune.no/innsyn?response=journalpost_siste50"
    
    try:
        print(f"   🌍 Går til: {url}")
        
        # Sett en timeout så den ikke henger i 120 sekunder
        driver.set_page_load_timeout(30) 

        try:
            driver.get(url)
        except TimeoutException:
            print("   ⚠️ Siden lastet tregt, men vi prøver å lese likevel...")
        
        wait = WebDriverWait(driver, 10)

        # Sjekk om vi ser tabellen selv om den lastet tregt
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
            print("   ✅ Fant tabell!")
        except:
            print("   ❌ Fant ingen tabell. Sannsynligvis blokkert IP.")
            return

        rader = driver.find_elements(By.TAG_NAME, "tr")
        print(f"   📊 Fant {len(rader)} rader.")

        porsgrunn_saker = []
        
        for i, rad in enumerate(rader[1:15]): 
            try:
                radtekst = rad.text
                lenker = rad.find_elements(By.TAG_NAME, "a")
                detalj_url = None
                
                for lenke in lenker:
                    href = lenke.get_attribute("href")
                    if href and ("registryEntry" in href or "case" in href or "journalpost" in href):
                         # Sjekk URL format
                        if not href.startswith("http"):
                            if href.startswith("/"):
                                detalj_url = "https://innsyn.porsgrunn.kommune.no" + href
                            else:
                                detalj_url = "https://innsyn.porsgrunn.kommune.no/innsyn/" + href
                        else:
                            detalj_url = href
                        break
                
                if detalj_url:
                    tittel = " ".join(radtekst.split())[:100]
                    porsgrunn_saker.append((detalj_url, tittel))
            except Exception:
                continue

        print(f"   🎯 Fant {len(porsgrunn_saker)} saker. Behandler...")

        for perm_url, tittel in porsgrunn_saker:
            process_single_case(driver, cur, conn, perm_url, tittel, "Porsgrunn")

    except Exception as e:
        print(f"⚠️ Hovedfeil Porsgrunn: {e}")

# --- FELLES ---
def process_single_case(driver, cur, conn, url, tittel, kommune_navn):
    try:
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (url,))
        if cur.fetchone():
            return 

        print(f"🔎 [{kommune_navn}] Behandler: {tittel[:30]}...")
        lagrings_tittel = f"[{kommune_navn}] {tittel}"

        try:
            # Sett kort timeout på lasting av detaljside også
            driver.set_page_load_timeout(20)
            driver.get(url)
        except TimeoutException:
            print("   ⚠️ Detaljside treg, fortsetter...")

        time.sleep(1)
        ocr_text = ""
        pdf_download_url = None

        try:
            fil_lenker = driver.find_elements(By.XPATH, "//a[contains(@href, 'file') or contains(@href, 'download') or contains(@href, 'variant=P')]")
            if fil_lenker:
                raw_href = fil_lenker[0].get_attribute("href")
                if raw_href:
                    if not raw_href.startswith("http"):
                         # Håndter relative lenker korrekt per kommune
                        if kommune_navn == "Skien":
                            pdf_download_url = "https://innsynpluss.onacos.no" + raw_href
                        else:
                            if raw_href.startswith("/"):
                                pdf_download_url = "https://innsyn.porsgrunn.kommune.no" + raw_href
                            else:
                                pdf_download_url = "https://innsyn.porsgrunn.kommune.no/innsyn/" + raw_href
                    else:
                        pdf_download_url = raw_href

                if pdf_download_url:
                    # Bruk User-Agent i requesten også
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                    pdf_response = requests.get(pdf_download_url, headers=headers, timeout=15)
                    
                    if pdf_response.status_code == 200:
                        try:
                            images = convert_from_bytes(pdf_response.content)
                            for image in images:
                                ocr_text += pytesseract.image_to_string(image, lang='nor') + "\n"
                        except Exception:
                            ocr_text = "OCR_FAILED"
        except Exception as e:
            print(f"   ⚠️ PDF-feil: {e}")

        if not ocr_text: ocr_text = tittel

        cur.execute("""
            INSERT INTO dokumenter (tittel, url_pdf, ekstern_id, ocr_tekst, dato)
            VALUES (%s, %s, %s, %s, NOW())
        """, (lagrings_tittel, url, url, ocr_text))
        conn.commit()
        print("   ✅ Lagret!")

    except Exception as e:
        print(f"⚠️ Lagringsfeil: {e}")

def main():
    driver = setup_driver()
    if not driver: return
    
    conn = get_db_connection()
    if not conn: 
        driver.quit()
        return
    cur = conn.cursor()

    try:
        scrape_skien(driver, cur, conn)
        scrape_porsgrunn(driver, cur, conn)
    finally:
        print("💾 Ferdig. Rydder opp.")
        cur.close()
        conn.close()
        driver.quit()

if __name__ == "__main__":
    main()