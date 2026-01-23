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

# --- ROBOT 1: SKIEN (Innsyn+) ---
def scrape_skien(driver, cur, conn):
    print("\n🔵 Starter SKIEN-roboten...")
    try:
        base_url = "https://innsynpluss.onacos.no/skien/sok/#/"
        driver.get(base_url)
        wait = WebDriverWait(driver, 20)
        
        print("   ⏳ Venter på listen...")
        # Skien bruker 'details' i lenkene
        saker = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, 'details')]")))
        
        sak_urler = []
        for sak in saker[:10]: # Sjekker de 10 nyeste
            href = sak.get_attribute("href")
            tittel = sak.text.strip()
            if href and not href.startswith("http"):
                href = "https://innsynpluss.onacos.no" + href
            if href and "details" in href:
                sak_urler.append((href, tittel))

        for perm_url, tittel in sak_urler:
            process_single_case(driver, cur, conn, perm_url, tittel, "Skien")

    except Exception as e:
        print(f"⚠️ Feil i Skien-roboten: {e}")

# --- ROBOT 2: PORSGRUNN (Klassisk WebSak) ---
def scrape_porsgrunn(driver, cur, conn):
    print("\n🟢 Starter PORSGRUNN-roboten...")
    try:
        # Går til forsiden for innsyn
        start_url = "https://innsyn.porsgrunn.kommune.no/innsyn"
        driver.get(start_url)
        wait = WebDriverWait(driver, 20)

        # 1. Klikk på "Siste 50 publiserte" (eller lignende lenke)
        print("   ⏳ Leter etter 'Siste 50'...")
        try:
            # Porsgrunn har ofte en lenke som heter "Siste 50 publiserte i postlisten" eller bare "Siste 50..."
            knapp = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Siste 50")))
            knapp.click()
        except:
            print("   ⚠️ Fant ikke 'Siste 50'-knappen direkte. Prøver URL-triks...")
            driver.get("https://innsyn.porsgrunn.kommune.no/innsyn?response=journalpost_siste50")
        
        # 2. Vent på tabellen
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
        
        # 3. Hent rader
        rader = driver.find_elements(By.TAG_NAME, "tr")
        print(f"   Fant {len(rader)} rader. Sjekker de første...")

        porsgrunn_saker = []
        for rad in rader[1:15]: # Hopper over overskrift, tar de 15 første
            try:
                # I klassisk ACOS er tittelen ofte i kolonne nr 3 eller 4, og lenken er på et ikon
                tekst = rad.text
                if not tekst: continue
                
                # Finn lenke til detaljene (ofte på saksnummer eller ikon)
                lenker = rad.find_elements(By.TAG_NAME, "a")
                detalj_url = None
                
                for lenke in lenker:
                    href = lenke.get_attribute("href")
                    # Vi ser etter lenker som går til "registryEntry" (journalpost)
                    if href and ("registryEntry" in href or "journalpost" in href):
                        detalj_url = href
                        if not detalj_url.startswith("http"):
                            detalj_url = "https://innsyn.porsgrunn.kommune.no/innsyn/" + detalj_url
                        break
                
                if detalj_url:
                    # Tittelen er ofte vanskelig å isolere i tabellen, så vi bruker hele radteksten foreløpig
                    # eller henter den pent inne på detaljsiden.
                    # Vi bruker rad-teksten kortet ned som foreløpig tittel.
                    tittel = tekst.split("\n")[0][:100] 
                    porsgrunn_saker.append((detalj_url, tittel))
            except:
                continue

        for perm_url, tittel in porsgrunn_saker:
            process_single_case(driver, cur, conn, perm_url, tittel, "Porsgrunn")

    except Exception as e:
        print(f"⚠️ Feil i Porsgrunn-roboten: {e}")

# --- FELLES HJELPEFUNKSJON FOR Å LAGRE OG LESE PDF ---
def process_single_case(driver, cur, conn, url, tittel, kommune_navn):
    try:
        # Sjekk om finnes
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (url,))
        if cur.fetchone():
            return # Finnes allerede

        print(f"🔎 [{kommune_navn}] Ny sak: {tittel[:30]}...")
        
        # Legg til kommunenavn i tittelen for oversiktens skyld
        lagrings_tittel = f"[{kommune_navn}] {tittel}"

        # Gå inn på saken for å finne PDF
        driver.get(url)
        time.sleep(2)
        
        ocr_text = ""
        pdf_download_url = None

        try:
            # Let etter PDF-lenker.
            # Skien: 'api/file'
            # Porsgrunn: 'variant=P' eller 'type=I' eller 'Download'
            fil_lenker = driver.find_elements(By.XPATH, "//a[contains(@href, 'file') or contains(@href, 'download') or contains(@href, 'variant=P')]")
            
            if fil_lenker:
                # Ta den første som ser ut som en hovedfil
                raw_href = fil_lenker[0].get_attribute("href")
                
                # Fiks relative lenker for Porsgrunn/Skien
                if raw_href and not raw_href.startswith("http"):
                    if kommune_navn == "Skien":
                        pdf_download_url = "https://innsynpluss.onacos.no" + raw_href
                    else:
                        pdf_download_url = "https://innsyn.porsgrunn.kommune.no" + raw_href.lstrip("/")
                else:
                    pdf_download_url = raw_href

                if pdf_download_url:
                    print("   📄 Laster ned PDF...")
                    pdf_response = requests.get(pdf_download_url, timeout=15)
                    if pdf_response.status_code == 200:
                        try:
                            images = convert_from_bytes(pdf_response.content)
                            for image in images:
                                ocr_text += pytesseract.image_to_string(image, lang='nor') + "\n"
                        except Exception:
                            ocr_text = "OCR_FAILED"
        except Exception as e:
            print(f"   ⚠️ Fant ingen lesbar PDF: {e}")

        if not ocr_text:
            ocr_text = tittel # Fallback

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
        # KJØR BEGGE ROBOTENE
        scrape_skien(driver, cur, conn)
        scrape_porsgrunn(driver, cur, conn)
        
    finally:
        print("💾 Ferdig. Rydder opp.")
        cur.close()
        conn.close()
        driver.quit()

if __name__ == "__main__":
    main()