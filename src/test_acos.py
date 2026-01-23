import requests
import json

# Base-URLen du fant
BASE_URL = "https://innsynpluss.onacos.no/skien"

def test_api():
    print("🕵️‍♂️ Starter søk etter Acos API-et for Skien...")

    # Liste over vanlige "bakdører" Acos bruker
    mulige_endepunkter = [
        "/api/sok",
        "/api/search",
        "/api/utvalg/sok",
        "/api/innsyn/sok",
        "/api/dokument/sok"
    ]

    # Dette er "passordet" vi prøver å sende (et tomt søk eller søk etter "bygg")
    payload = {
        "fritekst": "bygg",
        "side": 0,
        "antall": 5,
        "sortering": "dato_synkende"
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    fant_noe = False

    for sti in mulige_endepunkter:
        url = BASE_URL + sti
        print(f"👉 Tester: {url} ...")
        
        try:
            # Acos bruker nesten alltid POST for søk
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ BINGO! Fant API-et på: {url}")
                print("   Svar fra serveren (starten):")
                print(f"   {response.text[:300]}")
                fant_noe = True
                break # Vi fant det, trenger ikke lete mer
            else:
                print(f"   ❌ (Status: {response.status_code})")
                
        except Exception as e:
            print(f"   ❌ Feil: {e}")

    if not fant_noe:
        print("\n🤔 Fant ingen åpne dører med standard gjetting.")
        print("Vi må kanskje bruke nettleserens utviklerverktøy (F12) for å finne den.")

if __name__ == "__main__":
    test_api()