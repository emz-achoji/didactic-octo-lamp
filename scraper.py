import os
import requests
import time
import threading
from flask import Flask
from pymongo import MongoClient
from datetime import datetime

# --- SETTINGS ---
MONGO_URI = "os.getenv("MONGO_URI")"
DB_NAME = "bet9ja_virtuals"
COLLECTION_NAME = "weekly_snapshots"

# --- THE HEARTBEAT SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Scraper is Alive and Punctual!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# --- THE SCRAPER LOGIC ---
def run_scraper():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    try:
        response = requests.get("https://stadium-tv-api.bet9ja.com/game/standings/3/1", timeout=15)
        if response.status_code == 200:
            data = response.json().get('data', {})
            season, week = data.get('season'), data.get('week')
            unique_id = f"{season}_{week}"
            
            teams_data = data.get('value', "").split('|')
            league_snapshot = {t.split('-')[0]: {"pos": i+1, "pts": int(t.split('-')[1])} 
                               for i, t in enumerate(teams_data) if len(t.split('-')) >= 3}

            document = {"_id": unique_id, "season": season, "week": week, 
                        "scraped_at": datetime.now(), "teams": league_snapshot}
            
            collection.replace_one({"_id": unique_id}, document, upsert=True)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: S{season} W{week}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

def scraper_loop():
    while True:
        run_scraper()
        now = datetime.now()
        seconds_to_wait = 300 - (now.minute % 5 * 60 + now.second)
        if seconds_to_wait < 10: seconds_to_wait += 300 
        time.sleep(seconds_to_wait)

if __name__ == "__main__":
    # Start the scraper in a separate thread
    threading.Thread(target=scraper_loop, daemon=True).start()
    # Start the web server
    run_flask()
