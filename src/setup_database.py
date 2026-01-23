import psycopg2
from config import Config

def opprett_tabeller():
    # Koble til Postgres
    try:
        conn = psycopg2.connect(
            dbname=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            host=Config.DB_HOST,
            port=Config.DB_PORT
        )
        cur = conn.cursor()

        print("Koblet til databasen. Oppretter tabeller...")

        # SQL-kommandoer (Samme modell som vi diskuterte)
        sql_commands = [
            """
            CREATE TABLE IF NOT EXISTS kommuner (
                id SERIAL PRIMARY KEY,
                navn VARCHAR(100) NOT NULL UNIQUE,
                postliste_url VARCHAR(255)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS dokumenter (
                id SERIAL PRIMARY KEY,
                kommune_id INTEGER REFERENCES kommuner(id),
                ekstern_id VARCHAR(100),
                tittel TEXT NOT NULL,
                dato_publisert DATE,
                url_pdf TEXT NOT NULL,
                ocr_tekst TEXT,
                soke_vektor TSVECTOR, -- For raskt søk
                registrert_tid TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(kommune_id, ekstern_id)
            );
            """,
            # Automatisk oppdatering av søke-vektor når tekst legges inn
            """
            CREATE OR REPLACE FUNCTION dokumenter_trigger() RETURNS trigger AS $$
            begin
              new.soke_vektor :=
                setweight(to_tsvector('norwegian', coalesce(new.tittel,'')), 'A') ||
                setweight(to_tsvector('norwegian', coalesce(new.ocr_tekst,'')), 'B');
              return new;
            end
            $$ LANGUAGE plpgsql;
            """,
            """
            DROP TRIGGER IF EXISTS tsvectorupdate ON dokumenter;
            CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
            ON dokumenter FOR EACH ROW EXECUTE PROCEDURE dokumenter_trigger();
            """
        ]

        for command in sql_commands:
            cur.execute(command)

        # Legg inn Skien kommune hvis den ikke finnes
        cur.execute("INSERT INTO kommuner (navn) VALUES ('Skien') ON CONFLICT (navn) DO NOTHING;")

        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database ferdig oppsatt!")

    except Exception as e:
        print(f"❌ Feil under oppsett av database: {e}")
        print("Tips: Sjekk at du har laget databasen i Postgres først (CREATE DATABASE kommunevarsling_db;)")

if __name__ == "__main__":
    opprett_tabeller()