import schedule
import time
from datetime import datetime
from main_final import hent_fasit_data  # Henter data
from varsling import sjekk_og_varsle   # Sender Slack

def jobb():
    print(f"\n⏰ Starter planlagt jobb: {datetime.now()}")
    
    # 1. Hent nye data
    try:
        hent_fasit_data()
    except Exception as e:
        print(f"❌ Feil under henting: {e}")
        
    # 2. Sjekk om vi skal varsle
    try:
        sjekk_og_varsle()
    except Exception as e:
        print(f"❌ Feil under varsling: {e}")
        
    print("💤 Jobb ferdig. Venter på neste runde...")

# Definer at den skal kjøre hver time
schedule.every(1).hours.do(jobb)

# ... eller hvert minutt mens du tester:
# schedule.every(1).minutes.do(jobb) 

print("🚀 Systemet er i gang! Trykk Ctrl+C for å avslutte.")

# Kjør en gang med en gang programmet starter
jobb()

while True:
    schedule.run_pending()
    time.sleep(1)