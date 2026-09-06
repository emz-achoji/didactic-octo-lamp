import os
import time
import threading
from flask import Flask
from pymongo import MongoClient, ASCENDING
from datetime import datetime, timezone
from curl_cffi import requests as crequests

# --- CONFIGURATION ---
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "BJ_ml_factory"

# Distinct collection names for Competition 2 (Spanish League)
COL_RAW = "raw_payloads_c2"      
COL_MATCH = "match_records_c2"   

TARGET_COMPETITION_ID = 2
ROUND_ENDPOINT = "https://stadium-tv-api.bet9ja.com/game/4/round"
STANDINGS_ENDPOINT = "https://stadium-tv-api.bet9ja.com/game/standings/4/2"

SELECTION_NAMES = [
    "1", "X", "2", "1X", "X2", "12", "GG", "NG", "O2.5", "U2.5", 
    "CS_1-0", "CS_2-0", "CS_2-1", "CS_3-0", "CS_3-1", "CS_3-2", "CS_4-0", "CS_4-1", "CS_4-2", "CS_5-0", "CS_5-1", "CS_6-0", 
    "CS_0-1", "CS_0-2", "CS_1-2", "CS_0-3", "CS_1-3", "CS_2-3", "CS_0-4", "CS_1-4", "CS_2-4", "CS_0-5", "CS_1-5", "CS_0-6", 
    "CS_0-0", "CS_1-1", "CS_2-2", "CS_3-3", 
    "HO1.5", "HU1.5", "AO1.5", "AU1.5", "O1.5", "U1.5", "O3.5", "U3.5", "O4.5", "U4.5", 
    "HO2.5", "HU2.5", "AO2.5", "AU2.5", "HO3.5", "HU3.5", "AO3.5", "AU3.5", 
    "1+O1.5", "1+U1.5", "X+O1.5", "X+U1.5", "2+O1.5", "2+U1.5", 
    "1+O2.5", "1+U2.5", "X+O2.5", "X+U2.5", "2+O2.5", "2+U2.5", 
    "1+O3.5", "1+U3.5", "X+O3.5", "X+U3.5", "2+O3.5", "2+U3.5", 
    "1+O4.5", "1+U4.5", "X+O4.5", "X+U4.5", "2+O4.5", "2+U4.5", 
    "1X+O1.5", "1X+U1.5", "12+O1.5", "12+U1.5", "X2+O1.5", "X2+U1.5", 
    "1X+O2.5", "1X+U2.5", "12+O2.5", "12+U2.5", "X2+O2.5", "X2+U2.5", 
    "1X+O3.5", "1X+U3.5", "12+O3.5", "12+U3.5", "X2+O3.5", "X2+U3.5", 
    "1X+O4.5", "1X+U4.5", "12+O4.5", "12+U4.5", "X2+O4.5", "X2+U4.5", 
    "MG1-2", "MG1-3", "MG1-4", "MG1-5", "MG2-3", "MG2-4", "MG2-5", "MG2-6", 
    "MG3-4", "MG3-5", "MG3-6", "MG4-5", "MG4-6", "MG5-6", 
    "HO0.5", "HU0.5", "AO0.5", "AU0.5", 
    "1 - 1UP", "X - 1UP", "2 - 1UP"
]

app = Flask(__name__)

@app.route('/')
def health_check():
    return {
        "status": "active", 
        "competition_id": TARGET_COMPETITION_ID,
        "collections": [COL_RAW, COL_MATCH],
        "time": datetime.now(timezone.utc).isoformat()
    }

def fetch_current_standings(session, headers):
    try:
        resp = session.get(STANDINGS_ENDPOINT, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            raw_value = data.get('value', "")
            teams_data = raw_value.split('|')
            standings_map = {}
            for i, team_entry in enumerate(teams_data):
                parts = team_entry.split('-')
                if len(parts) >= 2:
                    team_code = parts[0]
                    points = int(parts[1])
                    standings_map[team_code] = {"position": i + 1, "points": points}
            return standings_map
        else:
            print(f"Standings Fetch Failed: HTTP {resp.status_code}", flush=True)
    except Exception as e:
        print(f"Standings Fetch Error: {e}", flush=True)
    return {}

def run_pipeline():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Running Pipeline for Competition {TARGET_COMPETITION_ID}...", flush=True)
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    db[COL_MATCH].create_index([("home", ASCENDING), ("away", ASCENDING)])
    db[COL_MATCH].create_index([("home", 1), ("away", 1), ("odds.1", 1), ("odds.X", 1), ("odds.2", 1)])

    session = crequests.Session(impersonate="chrome120")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://leagueplus-tv.bet9ja.com",
        "Referer": "https://leagueplus-tv.bet9ja.com/",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}

    try:
        standings = fetch_current_standings(session, headers)
        resp = session.get(ROUND_ENDPOINT, headers=headers, timeout=30)
        
        if resp.status_code != 200:
            print(f"Round Fetch Failed: HTTP Status {resp.status_code}", flush=True)
            return

        data = resp.json().get('data', {})
        
        # 1. Process UPCOMING Matches
        if 'round' in data:
            r_info = data['round']
            comps = [int(c) for c in r_info.get('competitions', [])]
            
            if TARGET_COMPETITION_ID in comps:
                c_idx = comps.index(TARGET_COMPETITION_ID)
                season = int(r_info['seasons'][c_idx])
                week = int(r_info['weeks'][c_idx])
                round_id = f"S{season}_W{week}"

                db[COL_RAW].update_one(
                    {"_id": round_id},
                    {"$set": {
                        "captured_at": datetime.now(timezone.utc),
                        "payload": data
                    }},
                    upsert=True
                )

                matches_list = r_info.get('matches', [])
                odds_list_all = r_info.get('odds', [])

                if len(matches_list) > c_idx and len(odds_list_all) > c_idx:
                    match_names = matches_list[c_idx].split('|')
                    odds_groups = odds_list_all[c_idx].split('|')

                    for i, name in enumerate(match_names):
                        if not name or '-' not in name:
                            continue
                        match_uid = f"{round_id}_{name.replace('-', '_')}"
                        h_team, a_team = name.split('-')[0], name.split('-')[1]
                        
                        h_context = standings.get(h_team, {"position": None, "points": None})
                        a_context = standings.get(a_team, {"position": None, "points": None})
                        
                        if i < len(odds_groups):
                            odds_list = odds_groups[i].split('-')
                            market_odds = {
                                SELECTION_NAMES[idx]: float(val) 
                                for idx, val in enumerate(odds_list) 
                                if idx < len(SELECTION_NAMES)
                            }
                        else:
                            market_odds = {}

                        data_doc = {
                            "round_id": round_id,
                            "season": season,
                            "week": week,
                            "home": h_team, "away": a_team,
                            "home_pos": h_context['position'], "home_pts": h_context['points'],
                            "away_pos": a_context['position'], "away_pts": a_context['points'],
                            "odds": market_odds, "status": "PENDING",
                            "created_at": datetime.now(timezone.utc)
                        }
                        db[COL_MATCH].update_one({"_id": match_uid}, {"$setOnInsert": data_doc}, upsert=True)

        # 2. Process COMPLETED Matches
        if 'roundResults' in data:
            res_info = data['roundResults']
            res_comps = [int(c) for c in res_info.get('competitions', [])]
            
            if TARGET_COMPETITION_ID in res_comps:
                res_idx = res_comps.index(TARGET_COMPETITION_ID)
                res_season = int(res_info['seasons'][res_idx])
                res_week = int(res_info['weeks'][res_idx])
                res_rid = f"S{res_season}_W{res_week}"

                res_matches_list = res_info.get('matches', [])
                res_results_list = res_info.get('results', [])

                if len(res_matches_list) > res_idx and len(res_results_list) > res_idx:
                    res_matches = res_matches_list[res_idx].split('|')
                    scores = res_results_list[res_idx].split('|')

                    if scores and scores[0] != "":
                        for i, score_val in enumerate(scores):
                            if i < len(res_matches) and ':' in score_val:
                                res_uid = f"{res_rid}_{res_matches[i].replace('-', '_')}"
                                
                                update_data = {
                                    "score": score_val, 
                                    "status": "COMPLETED", 
                                    "finalized_at": datetime.now(timezone.utc)
                                }
                                db[COL_MATCH].update_one({"_id": res_uid}, {"$set": update_data})

        print("Sync Completed Successfully.", flush=True)
    except Exception as e:
        print(f"Pipeline Execution Error: {e}", flush=True)
    finally:
        client.close()

def scraper_loop():
    print("Streamlined Scraper Thread Running.", flush=True)
    while True:
        run_pipeline()
        now = datetime.now()
        seconds_to_wait = 300 - (now.minute % 5 * 60 + now.second)
        if seconds_to_wait < 10: seconds_to_wait += 300 
        print(f"Next RUN in {seconds_to_wait} seconds.", flush=True)
        time.sleep(seconds_to_wait)

if __name__ == "__main__":
    threading.Thread(target=scraper_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
