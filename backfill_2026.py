"""
MLB Home Run Backfill Script — Early 2026 Season
Pulls game logs and HR play-by-play details for tracked players from MLB Stats API.
Outputs CSV files for import into Google Sheets.
"""

import requests
import csv
import time
import json
from datetime import datetime, date
from pathlib import Path

BASE_URL = "https://statsapi.mlb.com/api/v1"
GAME_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
SEASON = 2026
OUTPUT_DIR = Path(__file__).parent / "data"

# Cache of team ID -> abbreviation, populated from the API at startup
TEAM_ABBREVS = {}


def load_team_abbrevs():
    """Fetch all MLB team abbreviations from the API and populate the lookup dict."""
    url = f"{BASE_URL}/teams"
    resp = requests.get(url, params={"sportId": 1}, timeout=15)
    resp.raise_for_status()
    for team in resp.json().get("teams", []):
        TEAM_ABBREVS[team["id"]] = team.get("abbreviation", "")

# Top 10 AL + Top 10 NL HR hitters from 2025
TRACKED_PLAYERS = {
    # AL Top 10
    663728: {"name": "Cal Raleigh", "team": "SEA", "league": "AL", "bats": "S", "hr_2025": 60},
    592450: {"name": "Aaron Judge", "team": "NYY", "league": "AL", "bats": "R", "hr_2025": 53},
    691406: {"name": "Junior Caminero", "team": "TB", "league": "AL", "bats": "R", "hr_2025": 45},
    666176: {"name": "Jo Adell", "team": "LAA", "league": "AL", "bats": "R", "hr_2025": 37},
    682985: {"name": "Riley Greene", "team": "DET", "league": "AL", "bats": "L", "hr_2025": 36},
    701762: {"name": "Nick Kurtz", "team": "ATH", "league": "AL", "bats": "L", "hr_2025": 36},
    621493: {"name": "Taylor Ward", "team": "BAL", "league": "AL", "bats": "R", "hr_2025": 36},
    621439: {"name": "Byron Buxton", "team": "MIN", "league": "AL", "bats": "R", "hr_2025": 35},
    663757: {"name": "Trent Grisham", "team": "NYY", "league": "AL", "bats": "L", "hr_2025": 34},
    686469: {"name": "Vinnie Pasquantino", "team": "KC", "league": "AL", "bats": "L", "hr_2025": 32},
    # NL Top 10
    656941: {"name": "Kyle Schwarber", "team": "PHI", "league": "NL", "bats": "L", "hr_2025": 56},
    660271: {"name": "Shohei Ohtani", "team": "LAD", "league": "NL", "bats": "L", "hr_2025": 55},
    665742: {"name": "Juan Soto", "team": "NYM", "league": "NL", "bats": "L", "hr_2025": 43},
    624413: {"name": "Pete Alonso", "team": "BAL", "league": "AL", "bats": "R", "hr_2025": 38},
    553993: {"name": "Eugenio Suarez", "team": "CIN", "league": "NL", "bats": "R", "hr_2025": 36},
    683737: {"name": "Michael Busch", "team": "CHC", "league": "NL", "bats": "L", "hr_2025": 34},
    673548: {"name": "Seiya Suzuki", "team": "CHC", "league": "NL", "bats": "R", "hr_2025": 32},
    682998: {"name": "Corbin Carroll", "team": "AZ", "league": "NL", "bats": "L", "hr_2025": 31},
    691718: {"name": "Pete Crow-Armstrong", "team": "CHC", "league": "NL", "bats": "L", "hr_2025": 31},
    696100: {"name": "Hunter Goodman", "team": "COL", "league": "NL", "bats": "R", "hr_2025": 31},
}


def get_player_game_log(player_id: int, season: int) -> list[dict]:
    """Pull a player's game log for the season from the MLB Stats API."""
    url = f"{BASE_URL}/people/{player_id}"
    params = {"hydrate": f"stats(group=[hitting],type=[gameLog],season={season})"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    people = data.get("people", [])
    if not people:
        return []

    stats_list = people[0].get("stats", [])
    if not stats_list:
        return []

    splits = stats_list[0].get("splits", [])
    return splits


def get_game_feed(game_pk: int) -> dict:
    """Pull the live game feed (play-by-play) for a specific game."""
    url = GAME_FEED_URL.format(game_pk=game_pk)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def extract_hr_details(game_feed: dict, batter_id: int) -> list[dict]:
    """Extract home run details for a specific batter from play-by-play data."""
    hrs = []
    all_plays = game_feed.get("liveData", {}).get("plays", {}).get("allPlays", [])

    for play in all_plays:
        matchup = play.get("matchup", {})
        batter = matchup.get("batter", {})
        if batter.get("id") != batter_id:
            continue

        result = play.get("result", {})
        event = result.get("event", "")
        if "Home Run" not in event:
            continue

        pitcher = matchup.get("pitcher", {})
        pitch_hand = matchup.get("pitchHand", {}).get("code", "")
        bat_side = matchup.get("batSide", {}).get("code", "")

        # Get hit data from playEvents
        hit_data = {}
        play_events = play.get("playEvents", [])
        for pe in play_events:
            if pe.get("hitData"):
                hit_data = pe["hitData"]
                break

        about = play.get("about", {})

        hrs.append({
            "inning": about.get("halfInning", "") + " " + str(about.get("inning", "")),
            "pitcher_name": pitcher.get("fullName", ""),
            "pitcher_id": pitcher.get("id", ""),
            "pitcher_hand": pitch_hand,
            "batter_side": bat_side,
            "description": result.get("description", ""),
            "rbi": result.get("rbi", 0),
            "launch_speed": hit_data.get("launchSpeed", ""),
            "launch_angle": hit_data.get("launchAngle", ""),
            "total_distance": hit_data.get("totalDistance", ""),
        })

    return hrs


def process_player(player_id: int, player_info: dict) -> tuple[list[dict], list[dict]]:
    """Process a single player: get game log, then HR details from play-by-play."""
    print(f"  Pulling game log for {player_info['name']}...")
    game_log = get_player_game_log(player_id, SEASON)

    daily_rows = []
    hr_detail_rows = []

    for game in game_log:
        stat = game.get("stat", {})
        team_info = game.get("team", {})
        opponent = game.get("opponent", {})
        game_date = game.get("date", "")
        is_home = game.get("isHome", False)
        game_pk = game.get("game", {}).get("gamePk", "")

        team_abbr = TEAM_ABBREVS.get(team_info.get("id"), player_info["team"])
        opp_abbr = TEAM_ABBREVS.get(opponent.get("id"), "")

        daily_rows.append({
            "date": game_date,
            "player_name": player_info["name"],
            "player_id": player_id,
            "team": team_abbr,
            "league": player_info["league"],
            "opponent": opp_abbr,
            "home_away": "Home" if is_home else "Away",
            "ab": stat.get("atBats", 0),
            "hits": stat.get("hits", 0),
            "home_runs": stat.get("homeRuns", 0),
            "rbi": stat.get("rbi", 0),
            "bb": stat.get("baseOnBalls", 0),
            "so": stat.get("strikeOuts", 0),
            "game_pk": game_pk,
        })

        # If player hit a HR, pull play-by-play for details
        if stat.get("homeRuns", 0) > 0:
            print(f"    HR found on {game_date} vs {opponent.get('abbreviation', '?')} — pulling play-by-play...")
            try:
                feed = get_game_feed(game_pk)
                hr_details = extract_hr_details(feed, player_id)
                for hr in hr_details:
                    hr_detail_rows.append({
                        "date": game_date,
                        "player_name": player_info["name"],
                        "player_id": player_id,
                        "bats": player_info["bats"],
                        "team": team_abbr,
                        "opponent": opp_abbr,
                        "home_away": "Home" if is_home else "Away",
                        "pitcher_name": hr["pitcher_name"],
                        "pitcher_id": hr["pitcher_id"],
                        "pitcher_hand": hr["pitcher_hand"],
                        "batter_side": hr["batter_side"],
                        "inning": hr["inning"],
                        "rbi": hr["rbi"],
                        "launch_speed": hr["launch_speed"],
                        "launch_angle": hr["launch_angle"],
                        "total_distance": hr["total_distance"],
                        "description": hr["description"],
                    })
                # Be polite to the API
                time.sleep(0.5)
            except Exception as e:
                print(f"    Warning: Could not get play-by-play for game {game_pk}: {e}")

    return daily_rows, hr_detail_rows


def get_player_splits(player_id: int, player_info: dict, season: int) -> dict:
    """Pull aggregate splits (home/away, vs LHP/RHP) for a player."""
    url = f"{BASE_URL}/people/{player_id}"
    params = {"hydrate": f"stats(group=[hitting],type=[statSplits],sitCodes=[h,a,vl,vr],season={season})"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    people = data.get("people", [])
    if not people:
        return {}

    stats_list = people[0].get("stats", [])
    if not stats_list:
        return {}

    splits = stats_list[0].get("splits", [])
    result = {
        "player_name": player_info["name"],
        "player_id": player_id,
        "team": player_info["team"],
        "league": player_info["league"],
        "bats": player_info["bats"],
    }

    for split in splits:
        split_info = split.get("split", {})
        code = split_info.get("code", "")
        stat = split.get("stat", {})

        prefix = {
            "h": "home",
            "a": "away",
            "vl": "vs_lhp",
            "vr": "vs_rhp",
        }.get(code, code)

        result[f"{prefix}_games"] = stat.get("gamesPlayed", 0)
        result[f"{prefix}_ab"] = stat.get("atBats", 0)
        result[f"{prefix}_hr"] = stat.get("homeRuns", 0)
        result[f"{prefix}_avg"] = stat.get("avg", "")
        result[f"{prefix}_ops"] = stat.get("ops", "")

    return result


def write_csv(filepath: Path, rows: list[dict], fieldnames: list[str] | None = None):
    """Write rows to a CSV file."""
    if not rows:
        print(f"  No data to write for {filepath.name}")
        return

    if fieldnames is None:
        fieldnames = list(rows[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Wrote {len(rows)} rows to {filepath.name}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading team abbreviations from MLB API...")
    load_team_abbrevs()
    print(f"  Loaded {len(TEAM_ABBREVS)} teams")
    print(f"=" * 60)
    print(f"MLB Home Run Backfill — {SEASON} Season")
    print(f"Tracking {len(TRACKED_PLAYERS)} players")
    print(f"Output: {OUTPUT_DIR}")
    print(f"=" * 60)

    all_daily = []
    all_hr_details = []
    all_splits = []

    for player_id, player_info in TRACKED_PLAYERS.items():
        print(f"\n[{player_info['name']}] ({player_info['team']})")

        # Game log + HR details
        daily, hr_details = process_player(player_id, player_info)
        all_daily.extend(daily)
        all_hr_details.extend(hr_details)

        # Aggregate splits
        print(f"  Pulling splits...")
        try:
            splits = get_player_splits(player_id, player_info, SEASON)
            if splits:
                all_splits.append(splits)
        except Exception as e:
            print(f"  Warning: Could not get splits: {e}")

        # Rate limiting
        time.sleep(0.3)

    # Write CSV files
    print(f"\n{'=' * 60}")
    print("Writing output files...")

    # Roster CSV
    roster_rows = []
    for pid, info in TRACKED_PLAYERS.items():
        roster_rows.append({
            "player_name": info["name"],
            "player_id": pid,
            "team": info["team"],
            "league": info["league"],
            "bats": info["bats"],
            "hr_2025": info["hr_2025"],
            "status": "Active",
        })
    write_csv(OUTPUT_DIR / "roster.csv", roster_rows)

    # Daily game log CSV
    daily_fields = [
        "date", "player_name", "player_id", "team", "league",
        "opponent", "home_away", "ab", "hits", "home_runs",
        "rbi", "bb", "so", "game_pk",
    ]
    all_daily.sort(key=lambda x: (x["date"], x["player_name"]))
    write_csv(OUTPUT_DIR / "daily_game_log.csv", all_daily, daily_fields)

    # HR detail CSV
    hr_fields = [
        "date", "player_name", "player_id", "bats", "team",
        "opponent", "home_away", "pitcher_name", "pitcher_id",
        "pitcher_hand", "batter_side", "inning", "rbi",
        "launch_speed", "launch_angle", "total_distance", "description",
    ]
    all_hr_details.sort(key=lambda x: (x["date"], x["player_name"]))
    write_csv(OUTPUT_DIR / "hr_details.csv", all_hr_details, hr_fields)

    # Splits CSV
    if all_splits:
        split_fields = [
            "player_name", "player_id", "team", "league", "bats",
            "home_games", "home_ab", "home_hr", "home_avg", "home_ops",
            "away_games", "away_ab", "away_hr", "away_avg", "away_ops",
            "vs_lhp_games", "vs_lhp_ab", "vs_lhp_hr", "vs_lhp_avg", "vs_lhp_ops",
            "vs_rhp_games", "vs_rhp_ab", "vs_rhp_hr", "vs_rhp_avg", "vs_rhp_ops",
        ]
        write_csv(OUTPUT_DIR / "splits.csv", all_splits, split_fields)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"  Players tracked: {len(TRACKED_PLAYERS)}")
    print(f"  Total game entries: {len(all_daily)}")
    print(f"  Total HR events: {len(all_hr_details)}")
    print(f"  Files saved to: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
