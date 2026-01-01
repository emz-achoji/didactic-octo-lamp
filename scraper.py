import os
import requests
import time
import threading
import sys  # Added for flushing
from flask import Flask
from pymongo import MongoClient
from datetime import datetime

# --- SETTINGS ---
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "bet9ja_virtuals"
COLLECTION_NAME = "weekly_snapshots"

app = Flask(__name__)

@app.route('/')
def home():
    return "Scraper is Alive and Punctual!"

def run_flask():
    # Render's default port is 10000, but we use environ.get for safety
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def run_scraper():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempting to scrape...", flush=True)
    
    if not MONGO_URI:
        print("CRITICAL ERROR: MONGO_URI is missing from environment variables!", flush=True)
        return

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        response = requests.get("https://stadium-tv-api.bet9ja.com/game/standings/3/1", timeout=15)
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
            print(f"API ERROR: Status {response.status_code}", flush=True)
            
    except Exception as e:
        print(f"SCRAPER THREAD ERROR: {e}", flush=True)
    finally:
        client.close()

def scraper_loop():
    print("Background thread started successfully.", flush=True)
    while True:
        run_scraper()
        
        # Timing logic
        now = datetime.now()
        seconds_to_wait = 300 - (now.minute % 5 * 60 + now.second)
        if seconds_to_wait < 10: seconds_to_wait += 300 
        
        print(f"Next run in {seconds_to_wait} seconds.", flush=True)
        time.sleep(seconds_to_wait)

if __name__ == "__main__":
    # 1. Start scraper thread
    scraper_thread = threading.Thread(target=scraper_loop, daemon=True)
    scraper_thread.start()
    
    # 2. Start web server
    run_flask()
