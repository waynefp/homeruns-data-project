# MLB Home Run Tracker — Project Handoff

## Overview

This project tracks the top 20 HR hitters from the 2025 MLB season (10 AL, 10 NL) through the 2026 season. The goal is to identify which HR prop betting situations offer an edge by analyzing batter handedness, home/away splits, and pitcher handedness for every HR hit.

**Repo:** https://github.com/waynefp/homeruns-data-project

---

## What's Built

### 1. Backfill Script (`backfill_2026.py`)
- Pulls game logs and HR play-by-play from the MLB Stats API (free, no key needed)
- Tracks 20 players defined in `TRACKED_PLAYERS` dict (player IDs, names, teams, leagues, bat side, 2025 HR totals)
- Uses `/api/v1/teams` endpoint to build team ID → abbreviation lookup (fixes missing opponent data in game logs)
- Outputs 4 CSV files to `data/`:
  - `roster.csv` — 20 tracked players with metadata
  - `daily_game_log.csv` — every game played (date, AB, hits, HRs, etc.) — 320 rows backfilled
  - `hr_details.csv` — every HR with pitcher name, pitcher hand, batter side, launch speed, distance, inning — 42 rows backfilled
  - `splits.csv` — aggregate splits: home/away, vs LHP/RHP (games, AB, HR, AVG, OPS)
- Run with: `python backfill_2026.py`

### 2. Google Sheets Workbook (`create_sheets.py` / `HR_Tracker_2026.xlsx`)
- Generates a 5-tab Excel workbook pre-populated with backfill data
- Tabs: Roster, Daily Game Log, HR Details, Odds Tracking (template), Analysis (splits summary + formulas)
- Upload `HR_Tracker_2026.xlsx` to Google Drive — it auto-converts to a native Google Sheet
- The Odds Tracking tab has formula templates for implied probability and edge calculation
- Run with: `python create_sheets.py`

### 3. n8n Daily Collection Workflow
- **Workflow ID:** `YoSSrjIvj8ifakDj`
- **URL:** `https://n8n.srv1063345.hstgr.cloud/workflow/YoSSrjIvj8ifakDj`
- **Schedule:** Daily at 8 AM Eastern
- **What it does:**
  1. Builds player roster (same 20 players)
  2. Fetches game logs from MLB Stats API for previous day
  3. Splits into two parallel branches:
     - **Branch A:** Formats daily game log rows → appends to "Daily Game Log" sheet
     - **Branch B:** Filters HR games → fetches play-by-play → extracts HR details → appends to "HR Details" sheet
- **Column mapping:** Output fields use exact sheet header names (`'Player Name'`, `'Home/Away'`, `'HRs'`, `'Pitcher Hand'`, etc.)
- **Credential:** Uses `newCredential('Google Sheets')` — Google OAuth2
- **Action needed:** Both Google Sheets append nodes have `REPLACE_WITH_GOOGLE_SHEET_URL` placeholder — replace with actual sheet URL

### 4. Streamlit Dashboard (`dashboard.py`)
- **Launch:** `python -m streamlit run dashboard.py` (use `python -m` to ensure correct Python version)
- **7 pages** accessible via sidebar:

| Page | Description |
|------|-------------|
| **Today's Games** | Live schedule from MLB API — shows which tracked players are playing, matchup details (H/A, pitcher hand, batter hand), game status |
| **Yesterday's Results** | Game results for tracked players — HR hitters shown with pitcher name/hand, batter side, exit velo, distance for each HR |
| **Matchup Drill-Down** | Cross-factor analysis — filter by player(s), Home/Away, LHP/RHP; grouped bar charts, heatmap of all 4 combinations, filterable detail log |
| **Odds & Edge** | Live HR prop odds from The Odds API, implied probability calculations, edge analysis vs historical rates |
| **Player Profiles** | Individual player view with season totals, situational splits (home/away, vs LHP/RHP), HR timeline chart |
| **HR Detail Log** | Searchable/filterable table of all HR events from CSV data |
| **Situational Analysis** | League-wide analysis — HR rates by situation, platoon advantage chart |

- **Data sources:** CSV files in `data/` for historical views; live MLB Stats API calls for Today's Games and Yesterday's Results
- **Caching:** `@st.cache_data` with TTL on API calls (120s for schedule, 300s for play-by-play)
- **Dependencies:** `streamlit`, `plotly`, `requests`, `pandas` (via streamlit)

---

### 5. Telegram Notifications (n8n workflows)

**Pre-Game Alert — HR Watchlist**
- **Schedule:** Daily at 10 AM Eastern
- **Flow:** Cron Trigger → Fetch MLB Schedule (HTTP) → Build Pre-Game Message (Code) → Fetch Pitcher Hands (HTTP) → Format Pre-Game Alert (Code) → Telegram
- **What it does:** Lists all tracked players with games that day, including Home/Away, opponent, probable starting pitcher with throw hand (RHP/LHP), and batter handedness
- **Message format:** HTML with bold player/opponent names, pitcher hand labels
- **Key detail:** Pitcher IDs are collected in Build Pre-Game Message as a comma-separated string, then fetched in a single bulk API call to `/api/v1/people?personIds=...` (comma must be in URL, not Query Parameters — see Known Quirks)

**Post-Game HR Update**
- **Schedule:** Daily at midnight Eastern
- **Flow:** Cron Trigger → Fetch Yesterday's Schedule (HTTP) → Extract Tracked Games (Code) → Fetch Game Feed (HTTP) → Format Post-Game Message (Code) → Telegram
- **What it does:** Fetches full game feeds for all games involving tracked teams, extracts box score stats and HR play-by-play details for tracked players
- **Message format:** HTML with HR details (pitcher name/hand, batter side, inning, exit velo, distance), no-HR list, DNP count, and summary line

---

## What's NOT Built Yet

### Dashboard Deployment
Dashboard currently runs locally only. Options discussed:
- **Streamlit Community Cloud** — free, connects to GitHub, easiest path
- **Hostinger VPS** — same server as n8n, no cold starts, more setup
- **Railway/Render** — free tier available, some cold-start delays

### Odds Integration
- The Odds API key is available (free tier, 500 credits/month)
- `batter_home_runs` market endpoint exists
- Odds Tracking tab in Google Sheet has formula templates
- Odds & Edge dashboard page is built but not yet wired into n8n notifications

---

## Key Technical Details

### MLB Stats API Endpoints Used
| Endpoint | Purpose |
|----------|---------|
| `/api/v1/people/{id}?hydrate=stats(group=[hitting],type=[gameLog],season=YYYY)` | Player game log |
| `/api/v1/people/{id}?hydrate=stats(group=[hitting],type=[statSplits],sitCodes=[h,a,vl,vr],season=YYYY)` | Aggregate splits |
| `/api/v1.1/game/{gamePk}/feed/live` | Play-by-play (HR details, pitcher info) |
| `/api/v1/schedule?date=YYYY-MM-DD&sportId=1&hydrate=probablePitcher,team` | Daily schedule with probable pitchers and team abbreviations |
| `/api/v1/people?personIds=ID1,ID2,...` | Bulk pitcher lookup (throw hand, details) — needed because schedule doesn't include pitch hand |
| `/api/v1/teams?sportId=1` | All MLB teams with abbreviations — used for team ID → abbreviation mapping |

### Tracked Players (2025 HR leaders, 2026 teams)
**AL:** Cal Raleigh (SEA/S/60), Aaron Judge (NYY/R/53), Junior Caminero (TB/R/45), Jo Adell (LAA/R/37), Riley Greene (DET/L/36), Nick Kurtz (ATH/L/36), Taylor Ward (BAL/R/36), Byron Buxton (MIN/R/35), Trent Grisham (NYY/L/34), Vinnie Pasquantino (KC/L/32)

**NL:** Kyle Schwarber (PHI/L/56), Shohei Ohtani (LAD/L/55), Juan Soto (NYM/L/43), Pete Alonso (BAL/R/38), Eugenio Suarez (CIN/R/36), Michael Busch (CHC/L/34), Seiya Suzuki (CHC/R/32), Corbin Carroll (AZ/L/31), Pete Crow-Armstrong (CHC/L/31), Hunter Goodman (COL/R/31)

**2026 trades/moves:** Eugenio Suarez → CIN, Pete Alonso → BAL (now AL), Taylor Ward → BAL

### Python Environment
- **Use Python 3.13** — Python 3.11 is also installed but has numpy/pandas binary incompatibility
- Always launch Streamlit with `python -m streamlit run dashboard.py`
- Required packages: `streamlit`, `plotly`, `requests`, `openpyxl` (for sheet generation only)

### Known Quirks
- Splits CSV can have empty strings for numeric fields — `safe_int()` helper handles this in dashboard.py
- Schedule API returns probable pitcher name/ID but NOT throw hand — requires separate bulk `/people?personIds=...` call
- n8n Google Sheets `autoMapInputData` requires output field names to exactly match column headers
- **n8n comma encoding:** n8n's Query Parameters section URL-encodes commas (`%2C`), breaking API params like `hydrate=probablePitcher,team` and `personIds=123,456`. Always embed comma-separated values directly in the URL string instead.
- **n8n fetch() restricted:** `fetch()` silently fails in n8n Code nodes. All API calls must use HTTP Request nodes. Structure as: Code (prepare) → HTTP Request (fetch) → Code (process).
- **Team abbreviations:** MLB API uses `AZ` (not `ARI`) for Arizona and `ATH` (not `OAK`) for Oakland. Game log opponent objects don't include `abbreviation` — use team ID lookup via `/api/v1/teams` or boxscore data.
- Early season sample sizes are small — framework doc recommends 50+ games per player before drawing wagering conclusions

---

## File Structure
```
Home Runs/
  backfill_2026.py          # One-time data pull from MLB API
  create_sheets.py          # Generate Excel workbook for Google Sheets
  dashboard.py              # Streamlit dashboard (7-page app)
  HR_Tracker_2026.xlsx      # Generated workbook (upload to Google Drive)
  HR_PROJECT_FRAMEWORK.md   # Project plan and data structure docs
  HANDOFF.md                # This file
  CLAUDE.md                 # n8n workflow gotchas and project notes for AI assistants
  .gitignore
  data/
    roster.csv              # 20 tracked players
    daily_game_log.csv      # Game-by-game batting lines (320 rows)
    hr_details.csv          # Individual HR events with pitcher info (42 rows)
    splits.csv              # Aggregate home/away + vs LHP/RHP splits
```

---

## Quick Start
```bash
# View the dashboard
python -m streamlit run dashboard.py

# Re-run backfill (pulls fresh data from MLB API)
python backfill_2026.py

# Regenerate the Excel workbook
python create_sheets.py
```

---

## Design Philosophy
- **Data first, betting second** — collect broadly, narrow based on what data shows
- **Wider net preferred** — user prefers inclusive filters that can be trimmed later over aggressive early filtering
- **Cross-factor analysis is the goal** — not just "HRs at home" but "HRs at home vs RHP when batting left-handed"
- **Automation via n8n** — daily collection to Google Sheets, notifications via Telegram
- **Streamlit for deep analysis** — Google Sheets for daily tracking, Streamlit for interactive drill-down and visualization
