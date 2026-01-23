import time
import json
import psycopg2
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import Config

URL = "https://innsynpluss.onacos.no/skien/sok"

def koble_til_db():
    return psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )

def hent_med_js_injeksjon():
    print("🤖 Starter JS-Injection roboten...")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print(f"🌍 Går til: {URL}")
        driver.get(URL)
        
        # Vent til siden har satt cookies (Viktig!)
        print("⏳ Venter 5 sekunder på initiering...")
        time.sleep(5)
        
        print("💉 Injiserer JavaScript for å hente data...")
        
        # Dette er JavaScript-koden vi tvinger nettleseren til å kjøre.
        # Den finner XSRF-tokenet selv i cookiene, og sender en forespørsel.
        js_script = """
        var callback = arguments[arguments.length - 1];
        
        // 1. Prøv å finn Token i cookies
        var token = "";
        try {
            var match = document.cookie.match(new RegExp('(^| )XSRF-TOKEN=([^;]+)'));
            if (match) token = decodeURIComponent(match[2]);
        } catch (e) { console.log("Kunne ikke lese token cookie"); }

        console.log("Bruker token:", token);

        // 2. Gjør API-kallet fra innsiden
        fetch('/skien/api/sok', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Xsrf-Token': token  // Send med tokenet vi fant
            },
            body: JSON.stringify({
                "fritekst": "",
                "side": 0,
                "antall": 20,
                "sortering": "publisert_dato_synkende",
                "dokumenttype": ["I", "U"]
            })
        })
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => { throw new Error(response.status + " " + text) });
            }
            return response.json();
        })
        .then(data => callback({status: "success", data: data}))
        .catch(error => callback({status: "error", message: error.toString()}));
        """

        # execute_async_script lar Python vente til JavaScriptet er ferdig
        resultat = driver.execute_async_script(js_script)
        
        if resultat['status'] == 'error':
            print(f"❌ JavaScript feilet: {resultat['message']}")
            print("   Tips: Kanskje URL-en er feil, eller token mangler.")
        
        else:
            data = resultat['data']
            antall = data.get('totaltAntallTreff', 0)
            resultater = data.get('resultater', [])
            
            print(f"✅ SUKSESS! Hentet {len(resultater)} saker direkte fra nettleserens kjerne.")
            
            if resultater:
                lagre_til_db(resultater)

    except Exception as e:
        print(f"❌ Python-feil: {e}")
    finally:
        driver.quit()

def lagre_til_db(saker):
    conn = koble_til_db()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING")
    cur.execute("SELECT id FROM kommuner WHERE navn='Skien'")
    kommune_id = cur.fetchone()[0]
    
    teller = 0
    for sak in saker:
        tittel = sak.get('tittel', 'Uten tittel')
        saksnr = sak.get('saksnummer', {}).get('saksnummer', 'Ukjent')
        saks_id = sak.get('saksnummer', {}).get('saksId', '')
        unik_id = sak.get('id') or saksnr
        
        url = f"https://innsynpluss.onacos.no/skien/sak/{saks_id}"
        ocr_tekst = f"{tittel} {saksnr}"
        
        cur.execute("SELECT id FROM dokumenter WHERE ekstern_id=%s", (str(unik_id),))
        if not cur.fetchone():
            print(f"📥 Lagrer: {saksnr}")
            cur.execute("""
                INSERT INTO dokumenter (kommune_id, tittel, url_pdf, ocr_tekst, ekstern_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (kommune_id, tittel, url, ocr_tekst, str(unik_id)))
            teller += 1
            
    conn.commit()
    print(f"🏁 Ferdig! Lagret {teller} dokumenter.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    hent_med_js_injeksjon()