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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempting to scrape...", flush=True)
    
    if not MONGO_URI:
        print("CRITICAL: MONGO_URI is missing from environment variables!", flush=True)
        return

    # 1. Setup a Persistent Session with Retries
    session = requests.Session()
    retry_strategy = Retry(
        total=3,                # Try 3 times before giving up
        backoff_factor=2,       # Wait 2s, 4s, 8s between retries
        status_forcelist=[429, 500, 502, 503, 504], # Retry on these server errors
    )
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        # 2. Increased Timeout (Connect: 10s, Read: 30s)
        response = session.get(
            "https://stadium-tv-api.bet9ja.com/game/standings/3/1", 
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=(10, 30) 
        )
        
        if response.status_code == 200:
            data = response.json().get('data', {})
            season, week = data.get('season'), data.get('week')
            unique_id = f"{season}_{week}"
            
            teams_data = data.get('value', "").split('|')
            league_snapshot = {t.split('-')[0]: {"pos": i+1, "pts": int(t.split('-')[1])} 
                               for i, t in enumerate(teams_data) if len(t.split('-')) >= 3}

            document = {
                "_id": unique_id, 
                "season": season, 
                "week": week, 
                "scraped_at": datetime.now(), 
                "teams": league_snapshot
            }
            
            collection.replace_one({"_id": unique_id}, document, upsert=True)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SUCCESS: Saved S{season} W{week}", flush=True)
        else:
            print(f"API ERROR: HTTP {response.status_code}", flush=True)
            
    except requests.exceptions.Timeout:
        print("SCRAPER ERROR: Request timed out after retries. Server might be down.", flush=True)
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
