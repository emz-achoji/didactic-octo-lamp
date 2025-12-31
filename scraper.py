import os
import requests
from pymongo import MongoClient
from datetime import datetime

# --- SETTINGS ---
MONGO_URI = os.getenv("MONGO_URI") 
DB_NAME = "bet9ja_virtuals"
COLLECTION_NAME = "weekly_snapshots"

API_URL = "https://stadium-tv-api.bet9ja.com/game/standings/3/1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://leagueplus-tv.bet9ja.com/"
}

def parse_league_snapshot(raw_string):
    if not raw_string: return {}
    teams_data = raw_string.split('|')
    snapshot = {}
    for index, team_entry in enumerate(teams_data):
        parts = team_entry.split('-')
        if len(parts) >= 3:
            team_code = parts[0]
            snapshot[team_code] = {
                "position": index + 1,
                "points": int(parts[1]),
                "result": parts[2][0] if parts[2] else None
            }
    return snapshot

def main():
    if not MONGO_URI:
        print("Error: MONGO_URI environment variable not set.")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data_payload = response.json().get('data', {})
            season = data_payload.get('season')
            week = data_payload.get('week')
            unique_id = f"{season}_{week}"

            league_data = parse_league_snapshot(data_payload.get('value', ""))
            
            document = {
                "_id": unique_id,
                "season": season,
                "week": week,
                "scraped_at": datetime.now(),
                "teams": league_data
            }

            # This will save if new, or do nothing if it already exists
            collection.replace_one({"_id": unique_id}, document, upsert=True)
            print(f"Successfully processed Season {season} Week {week}")
        else:
            print(f"API Error: {response.status_code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
