import os
import requests
import time
import threading
import sys
from flask import Flask
from pymongo import MongoClient
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# --- SETTINGS ---
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "bet9ja_virtuals"
COLLECTION_NAME = "weekly_snapshots"

app = Flask(__name__)

@app.route('/')
def home():
    # Simple status page for Render & Cron-job.org pings
    return f"Scraper is Active. Last checked: {datetime.now().strftime('%H:%M:%S')}"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    # use_reloader=False is crucial to avoid starting the scraper thread twice
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def run_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempting to scrape with Results (W/D/L)...", flush=True)
    
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        response = session.get(
            "https://stadium-tv-api.bet9ja.com/game/standings/3/1", 
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=(10, 30) 
        )
        
        if response.status_code == 200:
            data = response.json().get('data', {})
            season, week = data.get('season'), data.get('week')
            unique_id = f"{season}_{week}"
            
            # The "value" string looks like: "LIV-45-WDLWW|CHE-42-LLWDW|..."
            raw_value = data.get('value', "")
            teams_data = raw_value.split('|')
            
            league_snapshot = {}
            for i, team_entry in enumerate(teams_data):
                parts = team_entry.split('-')
                if len(parts) >= 3:
                    team_code = parts[0]   # e.g., "LIV"
                    points = int(parts[1]) # e.g., 45
                    history = parts[2]    # e.g., "WDLWW"
                    
                    # The LAST character in the history string is the result of the CURRENT week
                    # current_result = history[-1] if history else None
                    
                    league_snapshot[team_code] = {
                        "pos": i + 1,
                        "pts": points,
                        "result": current_result, # W, D, or L
                        # "recent_form": history    # The full string (e.g., "WDLWW")
                    }

            document = {
                "_id": unique_id, 
                "season": season, 
                "week": week, 
                "scraped_at": datetime.now(), 
                "teams": league_snapshot
            }
            
            collection.replace_one({"_id": unique_id}, document, upsert=True)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SUCCESS: Saved S{season} W{week} with Results.", flush=True)
            
    except Exception as e:
        print(f"SCRAPER ERROR: {e}", flush=True)
    finally:
        session.close()
        client.close()
        
def scraper_loop():
    print("Background scraper thread started.", flush=True)
    while True:
        run_scraper()
        
        # Timing logic: target the next 5-minute mark exactly
        now = datetime.now()
        seconds_to_wait = 300 - (now.minute % 5 * 60 + now.second)
        if seconds_to_wait < 10: seconds_to_wait += 300 
        
        print(f"Next run in {seconds_to_wait} seconds.", flush=True)
        time.sleep(seconds_to_wait)

if __name__ == "__main__":
    # Start the scraper in a separate thread so Flask can handle pings
    t = threading.Thread(target=scraper_loop, daemon=True)
    t.start()
    
    # Start the web server
    run_flask()
