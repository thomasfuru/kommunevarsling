import psycopg2
from config import Config

def opprett_tabeller():
    print("☁️ Kobler til Supabase...")
    try:
        conn = psycopg2.connect(
            dbname=Config.DB_NAME, user=Config.DB_USER, 
            password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
        )
        cur = conn.cursor()
        
        print("🔨 Snekrer tabeller...")

        # 1. Tabell for Kommuner
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kommuner (
                id SERIAL PRIMARY KEY,
                navn VARCHAR(100) UNIQUE NOT NULL,
                aktiv BOOLEAN DEFAULT TRUE
            );
        """)

        # 2. Tabell for Dokumenter (Oppdatert med dato og varslet)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dokumenter (
                id SERIAL PRIMARY KEY,
                kommune_id INTEGER REFERENCES kommuner(id),
                tittel TEXT,
                url_pdf TEXT,
                ocr_tekst TEXT,
                ekstern_id VARCHAR(255),
                dato TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                varslet BOOLEAN DEFAULT FALSE,
                UNIQUE(ekstern_id)
            );
        """)

        # 3. NY: Tabell for Søkeord (Så vi kan endre dem uten kode!)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sokeord (
                id SERIAL PRIMARY KEY,
                ord VARCHAR(255) UNIQUE NOT NULL,
                aktiv BOOLEAN DEFAULT TRUE
            );
        """)
        
        # Legg inn dine eksisterende søkeord i den nye tabellen
        initial_ord = Config.SOKEORD
        for ordet in initial_ord:
            cur.execute("INSERT INTO sokeord (ord) VALUES (%s) ON CONFLICT (ord) DO NOTHING", (ordet,))

        conn.commit()
        print("✅ Ferdig! Tabellene er opprettet i skyen.")
        print(f"✅ La også inn {len(initial_ord)} søkeord i databasen.")
        
        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Feil: {e}")
        print("Tips: Sjekk at passordet og 'Host' i config.py er helt riktig.")

if __name__ == "__main__":
    opprett_tabeller()