import psycopg2
from config import Config

# --- DINE SØKEORD ---
SOKEORD = ["Luksefjellvegen", "Gbnr", "Skole", "Barnehage", "Reguleringsplan"]

def sjekk_nye_treff():
    conn = psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )
    cur = conn.cursor()

    print(f"🕵️ Sjekker databasen for disse ordene: {SOKEORD}")
    print("-" * 50)

    fant_noe = False

    for ordet in SOKEORD:
        # SQL-søk: ILIKE betyr at den driter i store/små bokstaver
        # %ordet% betyr at ordet kan stå hvor som helst i teksten
        cur.execute("SELECT tittel, url_pdf FROM dokumenter WHERE ocr_tekst ILIKE %s", (f"%{ordet}%",))
        treff = cur.fetchall()

        if treff:
            for tittel, url in treff:
                print(f"🔔 TREFF PÅ '{ordet.upper()}':")
                print(f"   📄 Tittel: {tittel}")
                print(f"   🔗 Lenke:  {url}")
                print("-" * 50)
                fant_noe = True

    if not fant_noe:
        print("Ingen nye treff på dine søkeord i dag.")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    sjekk_nye_treff()