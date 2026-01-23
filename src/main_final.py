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
import urllib3

# Slå av advarsler om usikre HTTPS-forespørsler (pga IP-trikset)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    
    # --- VIKTIG: TILLAT UGYLDIGE SERTIFIKATER ---
    # Dette må til fordi vi bruker IP-adresse direkte
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--allow-running-insecure-content")

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

# --- ROBOT 2: PORSGRUNN (IP-BAKDØR) ---
def scrape_porsgrunn(driver, cur, conn):
    print("\n🟢 Starter PORSGRUNN-roboten (via IP-bakdør)...")
    
    # PORSGRUNN IP: 193.161.200.228
    # Vi bruker IP direkte for å unngå DNS-blokkering i utlandet
    ip_base = "https://193.161.200.228"
    public_domain = "https://innsyn.porsgrunn.kommune.no" # Det vi viser til brukeren
    
    try:
        # Direkte lenke til "Siste 50" via IP
        direct_url = f"{ip_base}/innsyn?response=journalpost_siste50"
        print(f"   🌍 Går til IP: {direct_url}")
        
        driver.get(direct_url)
        wait = WebDriverWait(driver, 15)

        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
            print("   ✅ Fant tabell hos Porsgrunn!")
        except:
            print("   ❌ Fant ingen tabell. Blokkeringen er for streng.")
            return

        rader = driver.find_elements(By.TAG_NAME, "tr")
        print(f"   📊 Fant {len(rader)} rader.")

        porsgrunn_saker = []
        
        for i, rad in enumerate(rader[1:15]): 
            try:
                radtekst = rad.text
                lenker = rad.find_elements(By.TAG_NAME, "a")
                detalj_url_ip = None
                
                for lenke in lenker:
                    href = lenke.get_attribute("href")
                    if href and ("registryEntry" in href or "case" in href or "journalpost" in href):
                        # Sikre at vi bruker IP-adressen for skraping
                        if "innsyn.porsgrunn.kommune.no" in href:
                            detalj_url_ip = href.replace("innsyn.porsgrunn.kommune.no", "193.161.200.228")
                        elif not href.startswith("http"):
                            detalj_url_ip = ip_base + "/innsyn/" + href.split("/")[-1] if "/innsyn/" not in href else ip_base + href
                        else:
                            detalj_url_ip = href
                        break
                
                if detalj_url_ip:
                    # Rens tittelen
                    tittel = " ".join(radtekst.split())[:100]
                    # Lag en "pen" URL for brukeren (bytt tilbake IP til domene)
                    user_url = detalj_url_ip.replace("193.161.200.228", "innsyn.porsgrunn.kommune.no")
                    
                    porsgrunn_saker.append((detalj_url_ip, user_url, tittel))
            except Exception as e:
                print(f"      Feil rad {i}: {e}")
                continue

        print(f"   🎯 Fant {len(porsgrunn_saker)} saker. Behandler...")

        for ip_url, user_url, tittel in porsgrunn_saker:
            # Vi sjekker mot user_url i databasen så vi ikke får duplikater hvis IP endres
            process_single_case(driver, cur, conn, ip_url, tittel, "Porsgrunn", display_url=user_url)

    except Exception as e:
        print(f"⚠️ Hovedfeil Porsgrunn: {e}")

# --- FELLES ---
def process_single_case(driver, cur, conn, scrape_url, tittel, kommune_navn, display_url=None):
    # Hvis display_url ikke er satt, bruk scrape_url (gjelder Skien)
    final_url = display_url if display_url else scrape_url
    
    try:
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id = %s", (final_url,))
        if cur.fetchone():
            return 

        print(f"🔎 [{kommune_navn}] Behandler: {tittel[:30]}...")
        lagrings_tittel = f"[{kommune_navn}] {tittel}"

        driver.get(scrape_url) # Vi går til "bakdøra" (IP) hvis Porsgrunn
        time.sleep(1)
        
        ocr_text = ""
        pdf_download_url = None

        try:
            fil_lenker = driver.find_elements(By.XPATH, "//a[contains(@href, 'file') or contains(@href, 'download') or contains(@href, 'variant=P')]")
            
            if fil_lenker:
                raw_href = fil_lenker[0].get_attribute("href")
                
                if kommune_navn == "Skien":
                    if raw_href and not raw_href.startswith("http"):
                        pdf_download_url = "https://innsynpluss.onacos.no" + raw_href
                    else:
                        pdf_download_url = raw_href
                else: 
                    # Porsgrunn logic (IP fix)
                    if raw_href:
                        # Erstatt domene med IP hvis det dukker opp
                        pdf_download_url = raw_href.replace("innsyn.porsgrunn.kommune.no", "193.161.200.228")
                        if not pdf_download_url.startswith("http"):
                            base = "https://193.161.200.228/innsyn"
                            if pdf_download_url.startswith("/"):
                                pdf_download_url = "https://193.161.200.228" + pdf_download_url
                            else:
                                pdf_download_url = base + "/" + pdf_download_url

                if pdf_download_url:
                    # verify=False er viktig for Porsgrunn IP-nedlasting
                    print(f"   📄 Laster ned...")
                    pdf_response = requests.get(pdf_download_url, timeout=15, verify=False)
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
        """, (lagrings_tittel, final_url, final_url, ocr_text))
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