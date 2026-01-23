import requests
import psycopg2
from config import Config

def send_slack(tekst):
    """Sender tekst til Slack"""
    try:
        payload = {"text": tekst}
        requests.post(Config.SLACK_URL, json=payload)
    except Exception as e:
        print(f"Feil mot Slack: {e}")

def sjekk_og_varsle():
    conn = psycopg2.connect(
        dbname=Config.DB_NAME, user=Config.DB_USER, 
        password=Config.DB_PASSWORD, host=Config.DB_HOST, port=Config.DB_PORT
    )
    cur = conn.cursor()

    # 1. Finn dokumenter som matcher søkeordene OG som ikke er varslet før
    nye_treff = []
    
    print("🕵️ Sjekker etter nye varsler...")
    
    for ordet in Config.SOKEORD:
        # Søk etter uvarslede saker
        cur.execute("""
            SELECT id, tittel, url_pdf, ekstern_id 
            FROM dokumenter 
            WHERE varslet = FALSE 
            AND ocr_tekst ILIKE %s
        """, (f"%{ordet}%",))
        
        treff = cur.fetchall()
        for rad in treff:
            nye_treff.append((rad, ordet))

    if not nye_treff:
        print("   Ingen nye treff å varsle om.")
        cur.close()
        conn.close()
        return

    # 2. Send varsel og marker som varslet
    antall_sendt = 0
    ids_to_update = []

    for (rad, ordet) in nye_treff:
        db_id, tittel, url, ekstern_id = rad
        
        # Unngå å varsle samme sak to ganger hvis den matcher flere ord
        if db_id in ids_to_update:
            continue
            
        tekst = (
            f"🔔 *Nytt treff på '{ordet.upper()}'*\n"
            f"📄 {tittel}\n"
            f"🔗 <{url}|Klikk for å lese saken>"
        )
        
        print(f"   -> Sender til Slack: {tittel[:30]}...")
        send_slack(tekst)
        ids_to_update.append(db_id)
        antall_sendt += 1

    # 3. Oppdater databasen slik at vi ikke varsler disse igjen
    if ids_to_update:
        # Konverter listen til en tuple for SQL (1, 2, 3)
        cur.execute("UPDATE dokumenter SET varslet = TRUE WHERE id = ANY(%s)", (ids_to_update,))
        conn.commit()
        print(f"✅ Sendte {antall_sendt} varsler til Slack!")

    cur.close()
    conn.close()

if __name__ == "__main__":
    sjekk_og_varsle()