import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://innsynpluss.onacos.no/skien/sok"

def ta_rontgenbilde():
    print("📸 Starter fotografen...")
    
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1200,800")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)

    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # 1. Klikk SØK
        print("🔎 Klikker Søk...")
        knapp = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Søk')]")))
        knapp.click()
        
        # 2. Vent lenge nok til at alt laster
        print("⏳ Venter 8 sekunder på at listen skal dukke opp...")
        time.sleep(8)
        
        # 3. Lagre hele sidens kildekode til en fil
        print("💾 Lagrer 'skien_fasit.html'...")
        with open("skien_fasit.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
            
        # 4. Prøv å lese litt tekst fra siden for å se om det er tomt
        body_tekst = driver.find_element(By.TAG_NAME, "body").text
        print("\n--- Hva ser roboten av tekst? (Første 500 tegn) ---")
        print(body_tekst[:500])
        print("---------------------------------------------------\n")

    except Exception as e:
        print(f"❌ Feil: {e}")
    finally:
        driver.quit()
        print("✅ Ferdig. Sjekk mappen din for filen 'skien_fasit.html'")

if __name__ == "__main__":
    ta_rontgenbilde()