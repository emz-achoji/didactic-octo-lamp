import requests
import time
from pymongo import MongoClient
from datetime import datetime

# --- SETTINGS ---
MONGO_URI = os.getenv("MONGO_URI") 
CHECK_INTERVAL = 300  # 5 Minutes (Standard cycle)
POLL_INTERVAL = 30    # 30 Seconds (If we are waiting for a late update)
DB_NAME = "bet9ja_virtuals"
COLLECTION_NAME = "weekly_snapshots"

API_URL = "https://stadium-tv-api.bet9ja.com/game/standings/3/1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://leagueplus-tv.bet9ja.com/"
}

def parse_league_snapshot(raw_string):
    """
    Parses the pipe-string into a dictionary where each team is a key.
    The order in the string determines the standing position.
    """
    teams_data = raw_string.split('|')
    snapshot = {}
    
    for index, team_entry in enumerate(teams_data):
        parts = team_entry.split('-')
        if len(parts) == 3:
            team_code = parts[0]
            snapshot[team_code] = {
                "position": index + 1,  # 1st, 2nd, 3rd...
                "points": int(parts[1]),
                "result": parts[2][0] if parts[2] else None # Most recent 'W/D/L'
            }
    return snapshot

def main():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    last_processed_id = ""

    print("Snapshot Scraper Started. Saving one row per week.")

    while True:
        try:
            response = requests.get(API_URL, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                data_payload = response.json().get('data', {})
                
                season = data_payload.get('season')
                week = data_payload.get('week')
                unique_id = f"{season}_{week}" # This acts as our unique key

                if unique_id != last_processed_id:
                    # Parse all teams into one single dictionary
                    league_data = parse_league_snapshot(data_payload.get('value', ""))
                    
                    # Create the Single Document (The "One Row")
                    document = {
                        "_id": unique_id, # MongoDB uses _id to prevent duplicates automatically
                        "season": season,
                        "week": week,
                        "scraped_at": datetime.now(),
                        "teams": league_data
                    }

                    # Use replace_one with upsert=True to either insert or update
                    collection.replace_one({"_id": unique_id}, document, upsert=True)
                    
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved Snapshot: Season {season} Week {week}")
                    last_processed_id = unique_id
                    
                    time.sleep(300) # Wait 5 mins for next update
                else:
                    print(".", end="", flush=True)
                    time.sleep(30) # Check again in 30s
            else:
                time.sleep(60)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
