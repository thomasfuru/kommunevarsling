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

# --- ROBOT 1: SKIEN ---
def scrape_skien(driver, cur, conn):
    print("\n🔵 Starter SKIEN-roboten...")
    try:
        base_url = "https://innsynpluss.onacos.no/skien/sok/#/"
        driver.get(base_url)
        wait = WebDriverWait(driver, 20)
        
        # Skien bruker 'details' i lenkene
        try:
            saker = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, 'details')]")))
        except:
            print("   ⚠️ Skien: Fant ingen saker på forsiden (Timeout).")
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

# --- ROBOT 2: PORSGRUNN (NY OG FORBEDRET) ---
def scrape_porsgrunn(driver, cur, conn):
    print("\n🟢 Starter PORSGRUNN-roboten...")
    base_domain = "https://innsyn.porsgrunn.kommune.no"
    
    try:
        # 1. Prøv direkte lenke til "Siste 50" først (Ofte sikrest)
        # Dette er URL-en ACOS ofte bruker for snarveien
        direct_url = "https://innsyn.porsgrunn.kommune.no/innsyn?response=journalpost_siste50"
        print(f"   🌍 Går til: {direct_url}")
        driver.get(direct_url)
        
        wait = WebDriverWait(driver, 15)

        # Sjekk om vi faktisk kom til en tabell, eller om vi må klikke oss frem
        try:
            # Se etter rader i en tabell
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
            print("   ✅ Fant tabell direkte!")
        except:
            print("   ⚠️ Fant ingen tabell direkte. Prøver å klikke på menyen...")
            # Gå til forsiden
            driver.get("https://innsyn.porsgrunn.kommune.no/innsyn")
            time.sleep(2)
            
            # Prøv å finne en lenke som inneholder "50" eller "Postliste"
            try:
                knapper = driver.find_elements(By.XPATH, "//a[contains(text(), '50') or contains(text(), 'Postliste')]")
                if knapper:
                    print(f"   Fant knapp: {knapper[0].text}. Klikker...")
                    knapper[0].click()
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
                else:
                    print("   ❌ Fant ingen knapper for postliste. Porsgrunn-strukturen kan være endret.")
                    return
            except Exception as e:
                print(f"   ❌ Klikking feilet: {e}")
                return

        # 3. Hent rader
        rader = driver.find_elements(By.TAG_NAME, "tr")
        print(f"   📊 Fant totalt {len(rader)} rader i tabellen.")

        porsgrunn_saker = []
        
        # Start loopen fra rad 1 (hopp over overskrift)
        for i, rad in enumerate(rader[1:15]): 
            try:
                radtekst = rad.text
                # Finn lenker
                lenker = rad.find_elements(By.TAG_NAME, "a")
                
                detalj_url = None
                
                for lenke in lenker:
                    href = lenke.get_attribute("href")
                    # Vi ser etter lenker som går til en sak/journalpost
                    if href and ("registryEntry" in href or "case" in href or "journalpost" in href):
                        detalj_url = href
                        if not detalj_url.startswith("http"):
                            # Håndter relative lenker robust
                            detalj_url = base_domain + "/innsyn/" + href.split("/")[-1] if "/innsyn/" not in href else base_domain + href
                        break
                
                if detalj_url:
                    # Vi bruker radteksten som foreløpig tittel, rensket for nyllinjer
                    tittel = " ".join(radtekst.split())[:100]
                    porsgrunn_saker.append((detalj_url, tittel))
                    print(f"      Rad {i}: Fant lenke -> {detalj_url}")
                else:
                    # Debug: Hvorfor fant vi ingen lenke her?
                    pass 

            except Exception as e:
                print(f"      Feil på rad {i}: {e}")
                continue

        print(f"   🎯 Fant {len(porsgrunn_saker)} gyldige saker å behandle.")

        for perm_url, tittel in porsgrunn_saker:
            process_single_case(driver, cur, conn, perm_url, tittel, "Porsgrunn")

    except Exception as e:
        print(f"⚠️ Hovedfeil i Porsgrunn-roboten: {e}")

# --- FELLES ---
def process_single_case(driver, cur, conn, url, tittel, kommune_navn):
    try:
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (url,))
        if cur.fetchone():
            return 

        print(f"🔎 [{kommune_navn}] Behandler: {tittel[:30]}...")
        lagrings_tittel = f"[{kommune_navn}] {tittel}"

        driver.get(url)
        time.sleep(1) # Rask pause
        
        ocr_text = ""
        pdf_download_url = None

        try:
            # Let etter PDF
            fil_lenker = driver.find_elements(By.XPATH, "//a[contains(@href, 'file') or contains(@href, 'download') or contains(@href, 'variant=P')]")
            
            if fil_lenker:
                raw_href = fil_lenker[0].get_attribute("href")
                
                if raw_href and not raw_href.startswith("http"):
                    if kommune_navn == "Skien":
                        pdf_download_url = "https://innsynpluss.onacos.no" + raw_href
                    else:
                        # Porsgrunn fiks
                        base = "https://innsyn.porsgrunn.kommune.no/innsyn"
                        if raw_href.startswith("/"):
                            pdf_download_url = "https://innsyn.porsgrunn.kommune.no" + raw_href
                        else:
                            pdf_download_url = base + "/" + raw_href
                else:
                    pdf_download_url = raw_href

                if pdf_download_url:
                    print(f"   📄 Fant PDF URL: {pdf_download_url[:40]}...")
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