"""
MLB HR Tracker Dashboard — Streamlit App
Displays player tracking data, today's schedule, and HR analysis.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import requests
import csv
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DATA_DIR = Path(__file__).parent / "data"
MLB_API = "https://statsapi.mlb.com/api/v1"
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Player roster with IDs
TRACKED_PLAYERS = {
    663728: {"name": "Cal Raleigh", "team": "SEA", "league": "AL", "bats": "S"},
    592450: {"name": "Aaron Judge", "team": "NYY", "league": "AL", "bats": "R"},
    691406: {"name": "Junior Caminero", "team": "TB", "league": "AL", "bats": "R"},
    666176: {"name": "Jo Adell", "team": "LAA", "league": "AL", "bats": "R"},
    682985: {"name": "Riley Greene", "team": "DET", "league": "AL", "bats": "L"},
    701762: {"name": "Nick Kurtz", "team": "ATH", "league": "AL", "bats": "L"},
    621493: {"name": "Taylor Ward", "team": "BAL", "league": "AL", "bats": "R"},
    621439: {"name": "Byron Buxton", "team": "MIN", "league": "AL", "bats": "R"},
    663757: {"name": "Trent Grisham", "team": "NYY", "league": "AL", "bats": "L"},
    686469: {"name": "Vinnie Pasquantino", "team": "KC", "league": "AL", "bats": "L"},
    656941: {"name": "Kyle Schwarber", "team": "PHI", "league": "NL", "bats": "L"},
    660271: {"name": "Shohei Ohtani", "team": "LAD", "league": "NL", "bats": "L"},
    665742: {"name": "Juan Soto", "team": "NYM", "league": "NL", "bats": "L"},
    624413: {"name": "Pete Alonso", "team": "BAL", "league": "AL", "bats": "R"},
    553993: {"name": "Eugenio Suarez", "team": "CIN", "league": "NL", "bats": "R"},
    683737: {"name": "Michael Busch", "team": "CHC", "league": "NL", "bats": "L"},
    673548: {"name": "Seiya Suzuki", "team": "CHC", "league": "NL", "bats": "R"},
    682998: {"name": "Corbin Carroll", "team": "AZ", "league": "NL", "bats": "L"},
    691718: {"name": "Pete Crow-Armstrong", "team": "CHC", "league": "NL", "bats": "L"},
    696100: {"name": "Hunter Goodman", "team": "COL", "league": "NL", "bats": "R"},
}

BATS_LABEL = {"L": "LHB", "R": "RHB", "S": "Switch"}
THROWS_LABEL = {"L": "LHP", "R": "RHP"}

# Team name to abbreviation mapping (built dynamically from API)
TEAM_ABBREVS = {}


# --- Data Loading ---

@st.cache_data(ttl=300)
def load_csv(filename):
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


@st.cache_data(ttl=300)
def load_daily_log():
    return load_csv("daily_game_log.csv")


@st.cache_data(ttl=300)
def load_hr_details():
    return load_csv("hr_details.csv")


@st.cache_data(ttl=300)
def load_splits():
    return load_csv("splits.csv")


@st.cache_data(ttl=120)
def fetch_todays_schedule(target_date=None):
    """Fetch today's MLB schedule with probable pitchers."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"{MLB_API}/schedule"
    params = {
        "date": date_str,
        "sportId": 1,
        "hydrate": "probablePitcher,team",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=3600)
def fetch_pitcher_hand(pitcher_id):
    """Get a pitcher's throw hand from the MLB API."""
    try:
        resp = requests.get(f"{MLB_API}/people/{pitcher_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        people = data.get("people", [])
        if people:
            return people[0].get("pitchHand", {}).get("code", "?")
    except Exception:
        pass
    return "?"


@st.cache_data(ttl=120)
def fetch_game_results(target_date=None):
    """Fetch completed game results for a specific date, including pitcher details for HRs."""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    date_str = target_date.strftime("%Y-%m-%d")

    results = []
    for pid, info in TRACKED_PLAYERS.items():
        try:
            url = f"{MLB_API}/people/{pid}"
            params = {"hydrate": f"stats(group=[hitting],type=[gameLog],season={target_date.year})"}
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            people = data.get("people", [])
            if not people:
                continue
            player = people[0]
            stats = player.get("stats", [])
            if not stats:
                continue
            for game in stats[0].get("splits", []):
                if game.get("date") == date_str:
                    stat = game.get("stat", {})
                    game_pk = game.get("game", {}).get("gamePk")
                    hr_details = []

                    # If player hit HR(s), fetch play-by-play for pitcher details
                    if stat.get("homeRuns", 0) > 0 and game_pk:
                        hr_details = fetch_hr_from_pbp(game_pk, pid)

                    results.append({
                        "player_name": info["name"],
                        "player_id": pid,
                        "bats": info["bats"],
                        "team": info["team"],
                        "opponent": game.get("opponent", {}).get("abbreviation", ""),
                        "home_away": "Home" if game.get("isHome") else "Away",
                        "ab": stat.get("atBats", 0),
                        "hits": stat.get("hits", 0),
                        "home_runs": stat.get("homeRuns", 0),
                        "rbi": stat.get("rbi", 0),
                        "hr_details": hr_details,
                    })
        except Exception:
            continue

    return results


@st.cache_data(ttl=300)
def fetch_hr_from_pbp(game_pk, batter_id):
    """Extract HR details from play-by-play for a specific batter in a specific game."""
    try:
        url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        feed = resp.json()
        all_plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        hrs = []
        for play in all_plays:
            matchup = play.get("matchup", {})
            if matchup.get("batter", {}).get("id") != batter_id:
                continue
            result = play.get("result", {})
            if "Home Run" not in result.get("event", ""):
                continue
            hit_data = {}
            for pe in play.get("playEvents", []):
                if pe.get("hitData"):
                    hit_data = pe["hitData"]
                    break
            hrs.append({
                "pitcher_name": matchup.get("pitcher", {}).get("fullName", ""),
                "pitcher_hand": matchup.get("pitchHand", {}).get("code", "?"),
                "batter_side": matchup.get("batSide", {}).get("code", "?"),
                "inning": f"{play.get('about', {}).get('halfInning', '')} {play.get('about', {}).get('inning', '')}",
                "launch_speed": hit_data.get("launchSpeed", ""),
                "total_distance": hit_data.get("totalDistance", ""),
                "description": result.get("description", ""),
            })
        return hrs
    except Exception:
        return []


def get_watchlist_games(schedule_data):
    """Extract games involving tracked players from schedule data."""
    if not schedule_data:
        return []

    # Build team-to-players mapping
    team_players = {}
    for pid, info in TRACKED_PLAYERS.items():
        team = info["team"]
        if team not in team_players:
            team_players[team] = []
        team_players[team].append(info)

    games = []
    for game_date in schedule_data.get("dates", []):
        for game in game_date.get("games", []):
            away_team = game.get("teams", {}).get("away", {}).get("team", {})
            home_team = game.get("teams", {}).get("home", {}).get("team", {})
            away_abbr = away_team.get("abbreviation", "")
            home_abbr = home_team.get("abbreviation", "")

            # Check if any tracked players are on these teams
            away_players = team_players.get(away_abbr, [])
            home_players = team_players.get(home_abbr, [])

            if not away_players and not home_players:
                continue

            # Get probable pitchers
            away_pitcher = game.get("teams", {}).get("away", {}).get("probablePitcher", {})
            home_pitcher = game.get("teams", {}).get("home", {}).get("probablePitcher", {})

            away_pitcher_hand = ""
            home_pitcher_hand = ""
            if away_pitcher.get("id"):
                away_pitcher_hand = fetch_pitcher_hand(away_pitcher["id"])
            if home_pitcher.get("id"):
                home_pitcher_hand = fetch_pitcher_hand(home_pitcher["id"])

            game_status = game.get("status", {}).get("abstractGameState", "Preview")
            game_time = game.get("gameDate", "")

            game_info = {
                "away_team": away_abbr,
                "home_team": home_abbr,
                "away_pitcher": away_pitcher.get("fullName", "TBD"),
                "away_pitcher_hand": away_pitcher_hand,
                "home_pitcher": home_pitcher.get("fullName", "TBD"),
                "home_pitcher_hand": home_pitcher_hand,
                "status": game_status,
                "game_time": game_time,
                "game_pk": game.get("gamePk", ""),
            }

            # Add tracked players in this game with their matchup details
            for p in home_players:
                pitcher_facing = away_pitcher.get("fullName", "TBD")
                pitcher_hand = away_pitcher_hand
                games.append({
                    **game_info,
                    "player_name": p["name"],
                    "player_team": p["team"],
                    "player_bats": p["bats"],
                    "home_away": "Home",
                    "facing_pitcher": pitcher_facing,
                    "facing_hand": pitcher_hand,
                    "matchup": f"{BATS_LABEL.get(p['bats'], p['bats'])} vs {THROWS_LABEL.get(pitcher_hand, pitcher_hand)}",
                })
            for p in away_players:
                pitcher_facing = home_pitcher.get("fullName", "TBD")
                pitcher_hand = home_pitcher_hand
                games.append({
                    **game_info,
                    "player_name": p["name"],
                    "player_team": p["team"],
                    "player_bats": p["bats"],
                    "home_away": "Away",
                    "facing_pitcher": pitcher_facing,
                    "facing_hand": pitcher_hand,
                    "matchup": f"{BATS_LABEL.get(p['bats'], p['bats'])} vs {THROWS_LABEL.get(pitcher_hand, pitcher_hand)}",
                })

    return games


# --- Dashboard ---

@st.cache_data(ttl=600)
def fetch_hr_odds():
    """Fetch HR prop odds for tracked players from The Odds API."""
    if not ODDS_API_KEY:
        return [], "No API key configured"

    tracked_names = {info["name"] for info in TRACKED_PLAYERS.values()}
    tracked_teams = {info["team"] for info in TRACKED_PLAYERS.values()}

    # Full team name to abbreviation mapping
    TEAM_NAME_MAP = {
        "Seattle Mariners": "SEA", "New York Yankees": "NYY", "Tampa Bay Rays": "TB",
        "Los Angeles Angels": "LAA", "Detroit Tigers": "DET", "Oakland Athletics": "ATH",
        "Minnesota Twins": "MIN", "Kansas City Royals": "KC", "Philadelphia Phillies": "PHI",
        "Los Angeles Dodgers": "LAD", "New York Mets": "NYM", "Arizona Diamondbacks": "AZ",
        "Chicago Cubs": "CHC", "Colorado Rockies": "COL", "Baltimore Orioles": "BAL",
        "Boston Red Sox": "BOS", "Chicago White Sox": "CWS", "Cleveland Guardians": "CLE",
        "Houston Astros": "HOU", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
        "Atlanta Braves": "ATL", "Cincinnati Reds": "CIN", "Miami Marlins": "MIA",
        "Milwaukee Brewers": "MIL", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD",
        "San Francisco Giants": "SF", "St. Louis Cardinals": "STL", "Washington Nationals": "WSH",
    }

    try:
        # Get events (free, no credits)
        events_resp = requests.get(
            f"{ODDS_API_BASE}/sports/baseball_mlb/events",
            params={"apiKey": ODDS_API_KEY}, timeout=15
        )
        events_resp.raise_for_status()
        events = events_resp.json()

        # Filter to games with tracked teams
        priority_events = []
        for e in events:
            home_abbr = TEAM_NAME_MAP.get(e.get("home_team", ""), "")
            away_abbr = TEAM_NAME_MAP.get(e.get("away_team", ""), "")
            if home_abbr in tracked_teams or away_abbr in tracked_teams:
                priority_events.append(e)

        all_odds = []
        credits_remaining = "?"

        for e in priority_events:
            try:
                odds_resp = requests.get(
                    f"{ODDS_API_BASE}/sports/baseball_mlb/events/{e['id']}/odds",
                    params={
                        "apiKey": ODDS_API_KEY,
                        "regions": "us",
                        "markets": "batter_home_runs",
                        "oddsFormat": "american",
                    },
                    timeout=15,
                )
                odds_resp.raise_for_status()
                credits_remaining = odds_resp.headers.get("x-requests-remaining", "?")
                odds_data = odds_resp.json()

                game_label = f"{TEAM_NAME_MAP.get(e['away_team'], e['away_team'])} @ {TEAM_NAME_MAP.get(e['home_team'], e['home_team'])}"

                for bk in odds_data.get("bookmakers", []):
                    for mkt in bk.get("markets", []):
                        for o in mkt.get("outcomes", []):
                            if o["description"] in tracked_names and o["point"] == 0.5:
                                price = o["price"]
                                implied = (
                                    100 / (price + 100) if price > 0
                                    else abs(price) / (abs(price) + 100)
                                )
                                all_odds.append({
                                    "player": o["description"],
                                    "game": game_label,
                                    "book": bk["title"],
                                    "odds": price,
                                    "implied_prob": round(implied * 100, 1),
                                })
            except Exception:
                continue

        return all_odds, f"Credits remaining: {credits_remaining}"
    except Exception as ex:
        return [], f"Error: {ex}"


st.set_page_config(page_title="MLB HR Tracker", layout="wide", page_icon="\u26be")

st.title("\u26be MLB Home Run Tracker")
st.caption("Tracking top HR hitters | Situational analysis for HR prop betting")

# Sidebar
st.sidebar.header("Navigation")
page = st.sidebar.radio("View", [
    "Today's Games",
    "Yesterday's Results",
    "Matchup Drill-Down",
    "Odds & Edge",
    "Player Profiles",
    "HR Detail Log",
    "Situational Analysis",
])

# --- Page: Today's Games ---
if page == "Today's Games":
    st.header("Today's Watchlist Games")

    col1, col2 = st.columns([3, 1])
    with col2:
        selected_date = st.date_input("Date", value=date.today())

    schedule = fetch_todays_schedule(selected_date)
    watchlist_games = get_watchlist_games(schedule)

    if not watchlist_games:
        st.info(f"No tracked players have games scheduled for {selected_date.strftime('%B %d, %Y')}.")
    else:
        st.subheader(f"{len(watchlist_games)} tracked players in action")

        # Group by game
        game_groups = {}
        for g in watchlist_games:
            key = f"{g['away_team']} @ {g['home_team']}"
            if key not in game_groups:
                game_groups[key] = {
                    "matchup": key,
                    "away_pitcher": g["away_pitcher"],
                    "away_pitcher_hand": g["away_pitcher_hand"],
                    "home_pitcher": g["home_pitcher"],
                    "home_pitcher_hand": g["home_pitcher_hand"],
                    "status": g["status"],
                    "players": [],
                }
            game_groups[key]["players"].append(g)

        for game_key, game_info in game_groups.items():
            with st.expander(
                f"{'**' + game_key + '**'} | "
                f"{game_info['away_pitcher']} ({THROWS_LABEL.get(game_info['away_pitcher_hand'], '?')}) vs "
                f"{game_info['home_pitcher']} ({THROWS_LABEL.get(game_info['home_pitcher_hand'], '?')}) | "
                f"Status: {game_info['status']}",
                expanded=True,
            ):
                for p in game_info["players"]:
                    status_icon = ""
                    if game_info["status"] == "Final":
                        status_icon = " | FINAL"
                    elif game_info["status"] == "Live":
                        status_icon = " | LIVE"

                    st.markdown(
                        f"- **{p['player_name']}** ({p['player_team']}) | "
                        f"{BATS_LABEL.get(p['player_bats'], p['player_bats'])} | "
                        f"{p['home_away']} | "
                        f"Facing: {p['facing_pitcher']} ({THROWS_LABEL.get(p['facing_hand'], '?')}) | "
                        f"**{p['matchup']}**{status_icon}"
                    )

# --- Page: Yesterday's Results ---
elif page == "Yesterday's Results":
    st.header("Yesterday's HR Results")

    col1, col2 = st.columns([3, 1])
    with col2:
        results_date = st.date_input("Date", value=date.today() - timedelta(days=1))

    with st.spinner("Fetching results from MLB API..."):
        results = fetch_game_results(results_date)

    if not results:
        st.info(f"No game data found for tracked players on {results_date.strftime('%B %d, %Y')}.")
    else:
        hr_results = [r for r in results if r["home_runs"] > 0]
        no_hr = [r for r in results if r["home_runs"] == 0]
        dnp = len(TRACKED_PLAYERS) - len(results)

        col1, col2, col3 = st.columns(3)
        col1.metric("Players with HRs", len(hr_results))
        col2.metric("Players without HRs", len(no_hr))
        col3.metric("Did Not Play", dnp)

        if hr_results:
            st.subheader("Home Runs Hit")
            for r in hr_results:
                bats_label = BATS_LABEL.get(r["bats"], r["bats"])
                st.success(
                    f"**{r['player_name']}** ({r['team']}) | "
                    f"{r['home_runs']} HR | {r['home_away']} vs {r['opponent']} | "
                    f"{bats_label} | {r['ab']} AB, {r['hits']} H, {r['rbi']} RBI"
                )
                # Show individual HR details with pitcher info
                if r.get("hr_details"):
                    for idx, hr in enumerate(r["hr_details"], 1):
                        pitcher_hand_label = THROWS_LABEL.get(hr["pitcher_hand"], hr["pitcher_hand"])
                        batter_side_label = BATS_LABEL.get(hr["batter_side"], hr["batter_side"])
                        distance_str = f" | {hr['total_distance']} ft" if hr.get("total_distance") else ""
                        speed_str = f" | {hr['launch_speed']} mph" if hr.get("launch_speed") else ""
                        st.markdown(
                            f"&nbsp;&nbsp;&nbsp;&nbsp;HR #{idx}: "
                            f"**{hr['pitcher_name']}** ({pitcher_hand_label}) | "
                            f"Batting {batter_side_label} | "
                            f"{hr['inning']}{speed_str}{distance_str}"
                        )

        if no_hr:
            st.subheader("No Home Runs")
            for r in no_hr:
                bats_label = BATS_LABEL.get(r["bats"], r["bats"])
                st.markdown(
                    f"- {r['player_name']} ({r['team']}) | "
                    f"{r['home_away']} vs {r['opponent']} | "
                    f"{bats_label} | {r['ab']} AB, {r['hits']} H"
                )

# --- Page: Matchup Drill-Down ---
elif page == "Matchup Drill-Down":
    st.header("Matchup Drill-Down")
    st.caption("Cross-factor analysis: filter by Home/Away and Pitcher Hand to find HR edges")

    hr_details = load_hr_details()

    if not hr_details:
        st.info("No HR detail data available yet.")
    else:
        # Filter controls
        col_f1, col_f2, col_f3 = st.columns(3)

        with col_f1:
            player_filter = st.multiselect(
                "Player(s)",
                sorted(set(h.get("player_name", "") for h in hr_details)),
                default=[],
                help="Leave empty for all players",
            )

        with col_f2:
            ha_filter = st.radio("Home / Away", ["All", "Home", "Away"], horizontal=True)

        with col_f3:
            pitcher_hand_filter = st.radio("Pitcher Hand", ["All", "LHP", "RHP"], horizontal=True)

        # Apply filters
        filtered = hr_details
        if player_filter:
            filtered = [h for h in filtered if h.get("player_name") in player_filter]
        if ha_filter != "All":
            filtered = [h for h in filtered if h.get("home_away") == ha_filter]
        if pitcher_hand_filter != "All":
            hand_code = "L" if pitcher_hand_filter == "LHP" else "R"
            filtered = [h for h in filtered if h.get("pitcher_hand") == hand_code]

        st.markdown(f"**{len(filtered)}** home runs match current filters")

        if filtered:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            home_ct = sum(1 for h in filtered if h.get("home_away") == "Home")
            away_ct = sum(1 for h in filtered if h.get("home_away") == "Away")
            vs_lhp = sum(1 for h in filtered if h.get("pitcher_hand") == "L")
            vs_rhp = sum(1 for h in filtered if h.get("pitcher_hand") == "R")
            col1.metric("Home HRs", home_ct)
            col2.metric("Away HRs", away_ct)
            col3.metric("vs LHP", vs_lhp)
            col4.metric("vs RHP", vs_rhp)

            # Breakdown by player
            st.subheader("HR Count by Player & Situation")
            player_data = {}
            for h in filtered:
                name = h.get("player_name", "Unknown")
                if name not in player_data:
                    player_data[name] = {"Home": 0, "Away": 0, "vs LHP": 0, "vs RHP": 0, "Total": 0}
                player_data[name]["Total"] += 1
                if h.get("home_away") == "Home":
                    player_data[name]["Home"] += 1
                else:
                    player_data[name]["Away"] += 1
                if h.get("pitcher_hand") == "L":
                    player_data[name]["vs LHP"] += 1
                elif h.get("pitcher_hand") == "R":
                    player_data[name]["vs RHP"] += 1

            # Build table rows
            table_rows = []
            for name, counts in sorted(player_data.items(), key=lambda x: x[1]["Total"], reverse=True):
                bats = ""
                for pid, info in TRACKED_PLAYERS.items():
                    if info["name"] == name:
                        bats = BATS_LABEL.get(info["bats"], info["bats"])
                        break
                table_rows.append({
                    "Player": name,
                    "Bats": bats,
                    "Total": counts["Total"],
                    "Home": counts["Home"],
                    "Away": counts["Away"],
                    "vs LHP": counts["vs LHP"],
                    "vs RHP": counts["vs RHP"],
                })
            st.dataframe(table_rows, use_container_width=True, hide_index=True)

            # Grouped bar chart: Home vs Away by player
            st.subheader("Home vs Away HR Distribution")
            chart_names = [r["Player"] for r in table_rows]
            fig_ha = go.Figure(data=[
                go.Bar(name="Home", x=chart_names, y=[r["Home"] for r in table_rows], marker_color="#2E75B6"),
                go.Bar(name="Away", x=chart_names, y=[r["Away"] for r in table_rows], marker_color="#BF8F00"),
            ])
            fig_ha.update_layout(barmode="group", height=400, xaxis_tickangle=-45, yaxis_title="HR Count")
            st.plotly_chart(fig_ha, use_container_width=True)

            # Grouped bar chart: vs LHP vs RHP by player
            st.subheader("vs LHP vs RHP HR Distribution")
            fig_ph = go.Figure(data=[
                go.Bar(name="vs LHP", x=chart_names, y=[r["vs LHP"] for r in table_rows], marker_color="#375623"),
                go.Bar(name="vs RHP", x=chart_names, y=[r["vs RHP"] for r in table_rows], marker_color="#7030A0"),
            ])
            fig_ph.update_layout(barmode="group", height=400, xaxis_tickangle=-45, yaxis_title="HR Count")
            st.plotly_chart(fig_ph, use_container_width=True)

            # Cross-factor heatmap: Home/Away x Pitcher Hand
            st.subheader("Cross-Factor: Home/Away x Pitcher Hand")
            cross_data = {}
            for h in filtered:
                name = h.get("player_name", "Unknown")
                ha = h.get("home_away", "?")
                ph = "LHP" if h.get("pitcher_hand") == "L" else "RHP" if h.get("pitcher_hand") == "R" else "?"
                combo = f"{ha} vs {ph}"
                if name not in cross_data:
                    cross_data[name] = {}
                cross_data[name][combo] = cross_data[name].get(combo, 0) + 1

            combos = ["Home vs LHP", "Home vs RHP", "Away vs LHP", "Away vs RHP"]
            cross_names = sorted(cross_data.keys())
            z_values = []
            for name in cross_names:
                z_values.append([cross_data[name].get(c, 0) for c in combos])

            if cross_names:
                fig_heat = go.Figure(data=go.Heatmap(
                    z=z_values,
                    x=combos,
                    y=cross_names,
                    colorscale="YlOrRd",
                    text=z_values,
                    texttemplate="%{text}",
                    textfont={"size": 14},
                ))
                fig_heat.update_layout(height=max(300, len(cross_names) * 35 + 100), yaxis_autorange="reversed")
                st.plotly_chart(fig_heat, use_container_width=True)

            # Detailed HR log for current filter
            with st.expander("Filtered HR Detail Log", expanded=False):
                detail_rows = []
                for h in filtered:
                    detail_rows.append({
                        "Date": h.get("date", ""),
                        "Player": h.get("player_name", ""),
                        "H/A": h.get("home_away", ""),
                        "Opponent": h.get("opponent", ""),
                        "Pitcher": h.get("pitcher_name", ""),
                        "P Hand": THROWS_LABEL.get(h.get("pitcher_hand", ""), h.get("pitcher_hand", "")),
                        "Bat Side": BATS_LABEL.get(h.get("batter_side", ""), h.get("batter_side", "")),
                        "Inning": h.get("inning", ""),
                        "Exit Velo": h.get("launch_speed", ""),
                        "Distance": h.get("total_distance", ""),
                    })
                st.dataframe(detail_rows, use_container_width=True, hide_index=True)

# --- Page: Odds & Edge ---
elif page == "Odds & Edge":
    st.header("HR Prop Odds & Edge Finder")
    st.caption("Live odds vs situational HR rates — the edge is in the specific matchup, not the averages")

    if not ODDS_API_KEY:
        st.error("No Odds API key found. Add ODDS_API_KEY to your .env file.")
    else:
        with st.spinner("Fetching live HR prop odds and today's matchups..."):
            odds_data, status_msg = fetch_hr_odds()
            schedule_data = fetch_todays_schedule()

        st.caption(status_msg)

        if not odds_data:
            st.info("No HR prop odds available for tracked players right now. Odds typically appear a few hours before game time.")
        else:
            # Load all data sources for edge calculation
            splits_data = load_splits()
            splits_by_name = {s.get("player_name", ""): s for s in splits_data}
            hr_details = load_hr_details()

            # Build cross-factor HR counts from hr_details (actual HR events)
            # Key: (player_name, home_away, pitcher_hand) -> HR count
            cross_hr_counts = defaultdict(int)
            for h in hr_details:
                name = h.get("player_name", "")
                ha = h.get("home_away", "")
                ph = h.get("pitcher_hand", "")
                if name and ha and ph:
                    cross_hr_counts[(name, ha, ph)] += 1

            # Get today's pitcher matchups from schedule
            # Build pitcher hand lookup for today's games
            today_pitcher_info = {}  # team_abbr -> {"pitcher_name": ..., "pitcher_hand": ...}
            watchlist_games = get_watchlist_games(schedule_data) if schedule_data else []
            # Collect unique facing pitcher info per player
            player_today_matchup = {}  # player_name -> {"facing_pitcher", "facing_hand", "home_away"}
            for g in watchlist_games:
                player_today_matchup[g["player_name"]] = {
                    "facing_pitcher": g.get("facing_pitcher", "TBD"),
                    "facing_hand": g.get("facing_hand", ""),
                    "home_away": g.get("home_away", ""),
                }

            def safe_int_odds(val, default=0):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return default

            # Group odds by player, find best odds per player
            by_player = defaultdict(list)
            for o in odds_data:
                by_player[o["player"]].append(o)

            edge_rows = []
            for player_name in sorted(by_player.keys()):
                player_odds = by_player[player_name]
                best = max(player_odds, key=lambda x: x["odds"])
                game = best["game"]

                # Get player info
                player_info = None
                for pid, info in TRACKED_PLAYERS.items():
                    if info["name"] == player_name:
                        player_info = info
                        break

                bats_code = player_info["bats"] if player_info else "?"
                bats = BATS_LABEL.get(bats_code, "?")

                split = splits_by_name.get(player_name, {})

                # Determine Home/Away and pitcher hand from today's schedule
                today = player_today_matchup.get(player_name, {})
                ha_label = today.get("home_away", "")
                facing_pitcher = today.get("facing_pitcher", "TBD")
                facing_hand_code = today.get("facing_hand", "")
                facing_hand = THROWS_LABEL.get(facing_hand_code, "TBD")

                # If we didn't get it from schedule, infer H/A from odds game label
                if not ha_label and player_info:
                    parts = game.split(" @ ")
                    if len(parts) == 2:
                        ha_label = "Home" if parts[1].strip() == player_info["team"] else "Away"

                # === EDGE CALCULATION: Three layers ===

                # Layer 1: Overall HR rate (baseline)
                total_games = safe_int_odds(split.get("home_games")) + safe_int_odds(split.get("away_games"))
                total_hr = safe_int_odds(split.get("home_hr")) + safe_int_odds(split.get("away_hr"))
                overall_rate = (total_hr / total_games * 100) if total_games > 0 else 0

                # Layer 2: Home/Away HR rate
                if ha_label == "Home":
                    ha_games = safe_int_odds(split.get("home_games"))
                    ha_hr = safe_int_odds(split.get("home_hr"))
                else:
                    ha_games = safe_int_odds(split.get("away_games"))
                    ha_hr = safe_int_odds(split.get("away_hr"))
                ha_rate = (ha_hr / ha_games * 100) if ha_games > 0 else 0

                # Layer 3: vs Pitcher Hand HR rate (from splits)
                if facing_hand_code == "L":
                    ph_ab = safe_int_odds(split.get("vs_lhp_ab"))
                    ph_hr = safe_int_odds(split.get("vs_lhp_hr"))
                elif facing_hand_code == "R":
                    ph_ab = safe_int_odds(split.get("vs_rhp_ab"))
                    ph_hr = safe_int_odds(split.get("vs_rhp_hr"))
                else:
                    ph_ab, ph_hr = 0, 0
                platoon_rate = (ph_hr / ph_ab * 100) if ph_ab > 0 else 0

                # Layer 4: Cross-factor (H/A + pitcher hand) from actual HR events
                cross_hr = cross_hr_counts.get((player_name, ha_label, facing_hand_code), 0)
                # Denominator: use H/A games as best available proxy
                cross_rate = (cross_hr / ha_games * 100) if ha_games > 0 else 0

                # Determine best situational rate to use for edge
                # Priority: cross-factor > platoon > H/A > overall
                if cross_hr > 0 and ha_games > 0:
                    sit_rate = cross_rate
                    sit_label = f"{ha_label} vs {facing_hand}"
                elif facing_hand_code and ph_ab > 0:
                    sit_rate = platoon_rate
                    sit_label = f"vs {facing_hand}"
                elif ha_games > 0:
                    sit_rate = ha_rate
                    sit_label = ha_label
                else:
                    sit_rate = overall_rate
                    sit_label = "Overall"

                implied = best["implied_prob"]
                edge = round(sit_rate - implied, 1) if sit_rate > 0 else None

                # Matchup description for today
                if facing_hand_code:
                    matchup_desc = f"{bats} vs {facing_hand}"
                else:
                    matchup_desc = bats

                # Determine batter side for switch hitters
                if bats_code == "S" and facing_hand_code:
                    actual_side = "RHB" if facing_hand_code == "L" else "LHB"
                    matchup_desc = f"{actual_side} (S) vs {facing_hand}"

                all_books = ", ".join(
                    f"{o['book']}: {o['odds']:+d}" for o in sorted(player_odds, key=lambda x: -x["odds"])
                )

                edge_rows.append({
                    "Player": player_name,
                    "Matchup": matchup_desc,
                    "Game": game,
                    "H/A": ha_label,
                    "Pitcher": f"{facing_pitcher} ({facing_hand})" if facing_hand != "TBD" else facing_pitcher,
                    "Best Odds": f"{best['odds']:+d}",
                    "Implied %": f"{implied}%",
                    "Situation": sit_label,
                    "Sit. HR%": f"{sit_rate:.1f}%" if sit_rate > 0 else "N/A",
                    "Edge": f"{edge:+.1f}%" if edge is not None else "N/A",
                    "All Books": all_books,
                    "_edge_val": edge if edge is not None else -999,
                    "_implied": implied,
                    "_sit_rate": sit_rate,
                    "_overall": overall_rate,
                    "_ha_rate": ha_rate,
                    "_platoon_rate": platoon_rate,
                    "_cross_rate": cross_rate,
                    "_cross_hr": cross_hr,
                    "_ha_games": ha_games,
                })

            # Summary metrics
            has_edge = [r for r in edge_rows if r["_edge_val"] > 0]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Players with Odds", len(edge_rows))
            col2.metric("Potential Edges", len(has_edge))
            col3.metric("Best Edge", f"{max(r['_edge_val'] for r in edge_rows):+.1f}%" if edge_rows else "N/A")
            col4.metric("Avg Edge (positive)", f"{sum(r['_edge_val'] for r in has_edge) / len(has_edge):+.1f}%" if has_edge else "N/A")

            # Sort by edge descending
            edge_rows_sorted = sorted(edge_rows, key=lambda x: x["_edge_val"], reverse=True)

            # Highlight edge opportunities
            if has_edge:
                st.subheader("Edge Opportunities")
                st.caption("Players where situational HR rate exceeds sportsbook implied probability")
                for r in edge_rows_sorted:
                    if r["_edge_val"] <= 0:
                        break
                    st.success(
                        f"**{r['Player']}** | {r['Matchup']} | {r['H/A']} | "
                        f"vs {r['Pitcher']} | "
                        f"Odds: {r['Best Odds']} (Implied {r['Implied %']}) | "
                        f"**{r['Situation']} HR rate: {r['Sit. HR%']}** | "
                        f"**Edge: {r['Edge']}**"
                    )
                    # Show the rate breakdown
                    with st.expander(f"{r['Player']} — Rate Breakdown", expanded=False):
                        bcol1, bcol2, bcol3, bcol4 = st.columns(4)
                        bcol1.metric("Overall HR/G", f"{r['_overall']:.1f}%")
                        bcol2.metric(f"{r['H/A']} HR/G", f"{r['_ha_rate']:.1f}%")
                        bcol3.metric(f"vs {r['Pitcher'].split('(')[-1].rstrip(')')}" if "(" in r["Pitcher"] else "Platoon", f"{r['_platoon_rate']:.1f}%")
                        bcol4.metric(f"Cross-Factor", f"{r['_cross_rate']:.1f}% ({r['_cross_hr']} HR / {r['_ha_games']} G)")
                        st.caption(f"Books: {r['All Books']}")

            # Full table
            st.subheader("All Players")
            display_cols = ["Player", "Matchup", "Game", "H/A", "Pitcher", "Best Odds", "Implied %", "Situation", "Sit. HR%", "Edge"]
            display_rows = [{k: r[k] for k in display_cols} for r in edge_rows_sorted]
            st.dataframe(display_rows, use_container_width=True, hide_index=True)

            # Edge visualization
            st.subheader("Implied Probability vs Situational HR Rate")
            chart_data = [r for r in edge_rows_sorted if r["_sit_rate"] > 0]

            if chart_data:
                fig_edge = go.Figure()
                fig_edge.add_trace(go.Bar(
                    name="Sportsbook Implied %",
                    x=[r["Player"] for r in chart_data],
                    y=[r["_implied"] for r in chart_data],
                    marker_color="#BF8F00",
                ))
                fig_edge.add_trace(go.Bar(
                    name="Situational HR %",
                    x=[r["Player"] for r in chart_data],
                    y=[r["_sit_rate"] for r in chart_data],
                    marker_color="#375623",
                    text=[r["Situation"] for r in chart_data],
                    textposition="outside",
                    textfont_size=9,
                ))
                fig_edge.update_layout(
                    barmode="group", height=500,
                    xaxis_tickangle=-45,
                    yaxis_title="Probability %",
                    title="Green bar > Gold bar = Edge (labels show which situation)",
                )
                st.plotly_chart(fig_edge, use_container_width=True)

            st.markdown("---")
            st.caption(
                "**How the edge is calculated:** The sportsbook sets one HR price across all situations. "
                "We look at today's specific matchup (Home/Away + pitcher hand) and compare the player's "
                "actual HR rate in that situation against the book's implied probability. "
                "Cross-factor rates (e.g., 'Home vs RHP') use HR events from hr_details.csv divided by "
                "H/A games from splits. Sample sizes are small early in the season — look for 50+ games "
                "before treating edges as reliable."
            )

# --- Page: Player Profiles ---
elif page == "Player Profiles":
    st.header("Player Profiles & Splits")

    daily_log = load_daily_log()
    splits_data = load_splits()

    player_names = sorted([p["name"] for p in TRACKED_PLAYERS.values()])
    selected_player = st.selectbox("Select Player", player_names)

    # Find player info
    player_info = None
    player_id = None
    for pid, info in TRACKED_PLAYERS.items():
        if info["name"] == selected_player:
            player_info = info
            player_id = pid
            break

    if player_info:
        bats_label = BATS_LABEL.get(player_info["bats"], player_info["bats"])
        st.subheader(f"{selected_player} | {player_info['team']} | {player_info['league']} | {bats_label}")

        # Player's game log
        player_games = [g for g in daily_log if g.get("player_name") == selected_player]

        if player_games:
            total_games = len(player_games)
            total_hrs = sum(int(g.get("home_runs", 0)) for g in player_games)
            total_ab = sum(int(g.get("ab", 0)) for g in player_games)
            total_hits = sum(int(g.get("hits", 0)) for g in player_games)
            hr_rate = total_hrs / total_games if total_games > 0 else 0
            avg = total_hits / total_ab if total_ab > 0 else 0

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Games", total_games)
            col2.metric("Home Runs", total_hrs)
            col3.metric("HR Rate", f"{hr_rate:.3f}")
            col4.metric("AVG", f"{avg:.3f}")
            col5.metric("AB/HR", f"{total_ab / total_hrs:.1f}" if total_hrs > 0 else "N/A")

            # Splits from CSV
            player_split = None
            for s in splits_data:
                if s.get("player_name") == selected_player:
                    player_split = s
                    break

            if player_split:
                st.subheader("Situational Splits (2026)")

                col1, col2 = st.columns(2)

                def safe_int(val, default=0):
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return default

                with col1:
                    st.markdown("**Home vs Away**")
                    home_hr = safe_int(player_split.get("home_hr"))
                    home_games = safe_int(player_split.get("home_games"))
                    away_hr = safe_int(player_split.get("away_hr"))
                    away_games = safe_int(player_split.get("away_games"))

                    fig_ha = go.Figure(data=[
                        go.Bar(
                            x=["Home", "Away"],
                            y=[
                                home_hr / home_games if home_games > 0 else 0,
                                away_hr / away_games if away_games > 0 else 0,
                            ],
                            text=[
                                f"{home_hr} HR / {home_games} G",
                                f"{away_hr} HR / {away_games} G",
                            ],
                            textposition="auto",
                            marker_color=["#1f4e79", "#7f7f7f"],
                        )
                    ])
                    fig_ha.update_layout(
                        title="HR Rate: Home vs Away",
                        yaxis_title="HR per Game",
                        height=350,
                        showlegend=False,
                    )
                    st.plotly_chart(fig_ha, use_container_width=True)

                with col2:
                    st.markdown("**vs LHP vs RHP**")
                    vlhp_hr = safe_int(player_split.get("vs_lhp_hr"))
                    vlhp_ab = safe_int(player_split.get("vs_lhp_ab"))
                    vrhp_hr = safe_int(player_split.get("vs_rhp_hr"))
                    vrhp_ab = safe_int(player_split.get("vs_rhp_ab"))

                    fig_lr = go.Figure(data=[
                        go.Bar(
                            x=["vs LHP", "vs RHP"],
                            y=[
                                vlhp_hr / vlhp_ab if vlhp_ab > 0 else 0,
                                vrhp_hr / vrhp_ab if vrhp_ab > 0 else 0,
                            ],
                            text=[
                                f"{vlhp_hr} HR / {vlhp_ab} AB",
                                f"{vrhp_hr} HR / {vrhp_ab} AB",
                            ],
                            textposition="auto",
                            marker_color=["#e07b39", "#2e75b6"],
                        )
                    ])
                    fig_lr.update_layout(
                        title="HR Rate: vs Pitcher Hand",
                        yaxis_title="HR per AB",
                        height=350,
                        showlegend=False,
                    )
                    st.plotly_chart(fig_lr, use_container_width=True)

            # Game-by-game HR timeline
            st.subheader("Game-by-Game HR Timeline")
            dates = [g.get("date", "") for g in player_games]
            hrs = [int(g.get("home_runs", 0)) for g in player_games]
            cumulative_hrs = []
            running = 0
            for h in hrs:
                running += h
                cumulative_hrs.append(running)

            fig_timeline = go.Figure()
            fig_timeline.add_trace(go.Bar(
                x=dates, y=hrs, name="HRs per Game",
                marker_color=["#c0392b" if h > 0 else "#d5d8dc" for h in hrs],
            ))
            fig_timeline.add_trace(go.Scatter(
                x=dates, y=cumulative_hrs, name="Cumulative HRs",
                mode="lines+markers", yaxis="y2",
                line=dict(color="#1f4e79", width=2),
            ))
            fig_timeline.update_layout(
                height=350,
                yaxis=dict(title="HRs", side="left"),
                yaxis2=dict(title="Cumulative", side="right", overlaying="y"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_timeline, use_container_width=True)

        else:
            st.info("No game log data found. Run the backfill script first.")

# --- Page: HR Detail Log ---
elif page == "HR Detail Log":
    st.header("Home Run Detail Log")

    hr_details = load_hr_details()

    if not hr_details:
        st.info("No HR detail data found. Run the backfill script first.")
    else:
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            players = sorted(set(h.get("player_name", "") for h in hr_details))
            selected = st.multiselect("Player", players, default=players)
        with col2:
            pitcher_hand_filter = st.multiselect("Pitcher Hand", ["L", "R"], default=["L", "R"])
        with col3:
            ha_filter = st.multiselect("Home/Away", ["Home", "Away"], default=["Home", "Away"])

        filtered = [
            h for h in hr_details
            if h.get("player_name", "") in selected
            and h.get("pitcher_hand", "") in pitcher_hand_filter
            and h.get("home_away", "") in ha_filter
        ]

        st.metric("Total HRs (filtered)", len(filtered))

        # Summary by pitcher hand
        col1, col2 = st.columns(2)
        with col1:
            vs_lhp = len([h for h in filtered if h.get("pitcher_hand") == "L"])
            vs_rhp = len([h for h in filtered if h.get("pitcher_hand") == "R"])
            fig_ph = px.pie(
                values=[vs_lhp, vs_rhp],
                names=["vs LHP", "vs RHP"],
                title="HRs by Pitcher Hand",
                color_discrete_sequence=["#e07b39", "#2e75b6"],
            )
            fig_ph.update_layout(height=300)
            st.plotly_chart(fig_ph, use_container_width=True)

        with col2:
            home_hrs = len([h for h in filtered if h.get("home_away") == "Home"])
            away_hrs = len([h for h in filtered if h.get("home_away") == "Away"])
            fig_ha = px.pie(
                values=[home_hrs, away_hrs],
                names=["Home", "Away"],
                title="HRs by Home/Away",
                color_discrete_sequence=["#1f4e79", "#7f7f7f"],
            )
            fig_ha.update_layout(height=300)
            st.plotly_chart(fig_ha, use_container_width=True)

        # Detail table
        st.subheader("HR Events")
        display_cols = [
            "date", "player_name", "bats", "home_away", "opponent",
            "pitcher_name", "pitcher_hand", "batter_side",
            "launch_speed", "launch_angle", "total_distance",
        ]
        table_data = []
        for h in filtered:
            row = {}
            for c in display_cols:
                val = h.get(c, "")
                if c == "bats":
                    val = BATS_LABEL.get(val, val)
                elif c == "pitcher_hand":
                    val = THROWS_LABEL.get(val, val)
                elif c == "batter_side":
                    val = BATS_LABEL.get(val, val)
                row[c] = val
            table_data.append(row)

        st.dataframe(table_data, use_container_width=True, height=400)

# --- Page: Situational Analysis ---
elif page == "Situational Analysis":
    st.header("Situational HR Analysis")

    splits_data = load_splits()
    hr_details = load_hr_details()

    if not splits_data:
        st.info("No splits data found. Run the backfill script first.")
    else:
        st.subheader("All Players: HR Rates by Situation")

        # Build comparison data
        def safe_int(val, default=0):
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        rows = []
        for s in splits_data:
            name = s.get("player_name", "")
            bats = s.get("bats", "")
            home_hr = safe_int(s.get("home_hr"))
            home_games = safe_int(s.get("home_games"))
            away_hr = safe_int(s.get("away_hr"))
            away_games = safe_int(s.get("away_games"))
            vlhp_hr = safe_int(s.get("vs_lhp_hr"))
            vlhp_ab = safe_int(s.get("vs_lhp_ab"))
            vrhp_hr = safe_int(s.get("vs_rhp_hr"))
            vrhp_ab = safe_int(s.get("vs_rhp_ab"))
            total_hr = home_hr + away_hr
            total_games = home_games + away_games

            rows.append({
                "Player": name,
                "Bats": BATS_LABEL.get(bats, bats),
                "HRs": total_hr,
                "Games": total_games,
                "HR Rate": round(total_hr / total_games, 3) if total_games > 0 else 0,
                "Home HR Rate": round(home_hr / home_games, 3) if home_games > 0 else 0,
                "Away HR Rate": round(away_hr / away_games, 3) if away_games > 0 else 0,
                "vs LHP HR/AB": round(vlhp_hr / vlhp_ab, 3) if vlhp_ab > 0 else 0,
                "vs RHP HR/AB": round(vrhp_hr / vrhp_ab, 3) if vrhp_ab > 0 else 0,
                "Home HRs": home_hr,
                "Away HRs": away_hr,
                "vs LHP HRs": vlhp_hr,
                "vs RHP HRs": vrhp_hr,
            })

        # Sort by HR Rate descending
        rows.sort(key=lambda x: x["HR Rate"], reverse=True)

        st.dataframe(rows, use_container_width=True, height=500)

        # Comparison chart
        st.subheader("HR Rate Comparison: Home vs Away")
        fig_compare = go.Figure()
        player_names = [r["Player"] for r in rows]
        fig_compare.add_trace(go.Bar(
            x=player_names,
            y=[r["Home HR Rate"] for r in rows],
            name="Home",
            marker_color="#1f4e79",
        ))
        fig_compare.add_trace(go.Bar(
            x=player_names,
            y=[r["Away HR Rate"] for r in rows],
            name="Away",
            marker_color="#7f7f7f",
        ))
        fig_compare.update_layout(
            barmode="group",
            height=450,
            xaxis_tickangle=-45,
            yaxis_title="HR per Game",
        )
        st.plotly_chart(fig_compare, use_container_width=True)

        # vs Pitcher Hand chart
        st.subheader("HR Rate: vs LHP vs RHP")
        fig_hand = go.Figure()
        fig_hand.add_trace(go.Bar(
            x=player_names,
            y=[r["vs LHP HR/AB"] for r in rows],
            name="vs LHP",
            marker_color="#e07b39",
        ))
        fig_hand.add_trace(go.Bar(
            x=player_names,
            y=[r["vs RHP HR/AB"] for r in rows],
            name="vs RHP",
            marker_color="#2e75b6",
        ))
        fig_hand.update_layout(
            barmode="group",
            height=450,
            xaxis_tickangle=-45,
            yaxis_title="HR per AB",
        )
        st.plotly_chart(fig_hand, use_container_width=True)

        # Platoon advantage analysis
        st.subheader("Platoon Advantage Breakdown")
        st.caption("Positive = player hits more HRs in the platoon-advantage matchup (LHB vs RHP, RHB vs LHP)")

        platoon_data = []
        for r in rows:
            bats = r["Bats"]
            if bats == "LHB":
                advantage_rate = r["vs RHP HR/AB"]
                disadvantage_rate = r["vs LHP HR/AB"]
            elif bats == "RHB":
                advantage_rate = r["vs LHP HR/AB"]
                disadvantage_rate = r["vs RHP HR/AB"]
            else:  # Switch
                advantage_rate = max(r["vs LHP HR/AB"], r["vs RHP HR/AB"])
                disadvantage_rate = min(r["vs LHP HR/AB"], r["vs RHP HR/AB"])

            platoon_data.append({
                "Player": r["Player"],
                "Bats": bats,
                "Platoon Adv Rate": advantage_rate,
                "Platoon Dis Rate": disadvantage_rate,
                "Platoon Edge": round(advantage_rate - disadvantage_rate, 4),
            })

        platoon_data.sort(key=lambda x: x["Platoon Edge"], reverse=True)

        fig_platoon = go.Figure(data=[
            go.Bar(
                x=[p["Player"] for p in platoon_data],
                y=[p["Platoon Edge"] for p in platoon_data],
                marker_color=[
                    "#27ae60" if p["Platoon Edge"] > 0 else "#c0392b"
                    for p in platoon_data
                ],
                text=[f"{p['Platoon Edge']:.4f}" for p in platoon_data],
                textposition="auto",
            )
        ])
        fig_platoon.update_layout(
            height=400,
            xaxis_tickangle=-45,
            yaxis_title="Platoon Edge (HR/AB)",
            title="Platoon Advantage Edge by Player",
        )
        st.plotly_chart(fig_platoon, use_container_width=True)

# --- Footer ---
st.sidebar.markdown("---")
st.sidebar.caption("Data: MLB Stats API | Odds: The Odds API")
st.sidebar.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()
