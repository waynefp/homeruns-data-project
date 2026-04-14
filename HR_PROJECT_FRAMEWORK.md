# Home Run Hitters Data Project — Framework

## Project Goal
Track top MLB home run hitters daily, capturing key situational factors (batting side, home/away, pitcher handedness) to identify potentially profitable HR prop betting opportunities.

---

## Data Availability Assessment

### What We Can Get — FREE, No Key Required

**MLB Stats API** (`statsapi.mlb.com`) — the primary data engine for this project:

| Data Point | Endpoint | Available? |
|-----------|----------|------------|
| Player game logs (daily stats) | `/people/{id}?hydrate=stats(type=gameLog)` | YES |
| Home runs per game | Game log | YES |
| Home vs Away | Game log (isHome flag) | YES |
| Batter bat side (L/R/S) | `/people/{id}` → batSide | YES |
| Aggregate splits (vs LHP/RHP, H/A) | `statSplits` with sitCodes `vl,vr,h,a` | YES |
| Play-by-play per game | `/game/{gamePk}/feed/live` | YES |
| Pitcher handedness per HR | Play-by-play matchup data | YES |
| Pitcher name for each at-bat | Play-by-play matchup data | YES |
| HR launch data (speed, angle, distance) | Play-by-play hitData | YES |
| Season leaders | `/stats/leaders?leaderCategories=homeRuns` | YES |

### What We Can Get — With Odds API Key (Already Have)

**The Odds API** — HR prop betting lines:

| Data Point | Market Key | Available? |
|-----------|-----------|------------|
| HR prop odds (Yes/No per player) | `batter_home_runs` | YES |
| Odds from multiple sportsbooks | DraftKings, FanDuel, BetMGM, etc. | YES |
| Historical odds | Available but costs 10x credits | YES (paid) |

**Note:** Free tier = 500 credits/month. Each live odds call = 1 credit. Player props may cost more per call. Budget accordingly.

---

## Data We Need to Collect Daily

### Core Daily Collection (from previous day's games)

For each tracked player, each game day:

1. **Did they play?** (game log check)
2. **Did they hit a HR?** (game log: homeRuns field)
3. **Home or Away?** (game log: isHome)
4. **Who was the pitcher when HR was hit?** (play-by-play: matchup.pitcher)
5. **Pitcher handedness?** (play-by-play: matchup.pitchHand)
6. **Batter side used?** (play-by-play: matchup.batSide — matters for switch hitters)
7. **HR details** (play-by-play: hitData — launch speed, angle, distance)

### Betting Data Collection (from Odds API, pre-game)

For each tracked player, each game day:

1. **HR prop odds** — Yes/No lines from 2-3 books
2. **Best available odds** across books
3. **Implied probability** (calculated from odds)

### Derived/Calculated Fields

| Field | Formula |
|-------|---------|
| HR Rate (season) | Total HRs / Games Played |
| HR Rate vs LHP | HRs vs LHP / Games vs LHP |
| HR Rate vs RHP | HRs vs RHP / Games vs RHP |
| HR Rate Home | Home HRs / Home Games |
| HR Rate Away | Away HRs / Away Games |
| Implied Prob | 1 / (American odds conversion) |
| Edge | Actual HR Rate - Implied Probability |

---

## Tracked Players — Starting Roster

### 2025 AL Top 10 HR Hitters

| Player | Team | 2025 HRs | Bats | Player ID |
|--------|------|----------|------|-----------|
| Cal Raleigh | SEA | 60 | S | 663728 |
| Aaron Judge | NYY | 53 | R | 592450 |
| Junior Caminero | TB | 45 | R | 691406 |
| Jo Adell | LAA | 37 | R | 666176 |
| Riley Greene | DET | 36 | L | 682985 |
| Nick Kurtz | OAK | 36 | L | 701762 |
| Taylor Ward | LAA | 36 | R | 621493 |
| Byron Buxton | MIN | 35 | R | 621439 |
| Trent Grisham | NYY | 34 | L | 663757 |
| Vinnie Pasquantino | KC | 32 | L | 686469 |

### 2025 NL Top 10 HR Hitters

| Player | Team | 2025 HRs | Bats | Player ID |
|--------|------|----------|------|-----------|
| Kyle Schwarber | PHI | 56 | L | 656941 |
| Shohei Ohtani | LAD | 55 | L | 660271 |
| Juan Soto | NYM | 43 | L | 665742 |
| Pete Alonso | NYM | 38 | R | 624413 |
| Eugenio Suarez | ARI | 36 | R | 553993 |
| Michael Busch | CHC | 34 | L | 683737 |
| Seiya Suzuki | CHC | 32 | R | 673548 |
| Corbin Carroll | ARI | 31 | L | 682998 |
| Pete Crow-Armstrong | CHC | 31 | L | 691718 |
| Hunter Goodman | COL | 31 | R | 696100 |

---

## Early 2026 Season — Cross-Reference

Current 2026 HR leaders (through ~April 12):

| Player | Team | 2026 HRs | On Our List? |
|--------|------|----------|-------------|
| Jordan Walker | STL | 7 | No |
| Yordan Alvarez | HOU | 6 | No |
| Gunnar Henderson | BAL | 6 | No |
| Shohei Ohtani | LAD | 5 | YES |
| Elly De La Cruz | CIN | 5 | No |
| James Wood | WSH | 5 | No |
| Aaron Judge | NYY | 4 | YES |
| Kyle Schwarber | PHI | 4 | YES |
| Corey Seager | TEX | 4 | No |

**Observation:** Only 3 of the early 2026 HR leaders overlap with our 2025 top-20 list. This suggests we should also track "hot starters" and potentially expand the roster dynamically.

---

## Storage Options

### Option A: Google Sheets (Recommended to Start)
- **Pros:** Quick setup, visual, easy formulas, The Odds API has a Google Sheets extension, shareable
- **Cons:** Gets unwieldy with lots of data, limited automation
- **Structure:** One sheet per data type (Player Roster, Daily Game Logs, HR Events, Odds Tracking, Analysis Dashboard)

### Option B: Notion Database
- **Pros:** Relational data, views/filters, good for tracking and notes
- **Cons:** Harder to do calculations, no native API integration with MLB/Odds data
- **Best for:** High-level tracking, notes, and decision logging

### Option C: Hybrid (Recommended Long-Term)
- **Google Sheets** for raw data collection and calculations (API-friendly)
- **Notion** for decision tracking, betting log, and notes
- **Python script** to automate daily pulls from MLB Stats API

---

## Proposed Sheet Structure (Google Sheets)

### Sheet 1: Player Roster
Columns: Player Name | Team | League | Bats | Player ID | 2025 HRs | Status (Active/Watch)

### Sheet 2: Daily Game Log
Columns: Date | Player | Opponent | Home/Away | AB | Hits | HRs | RBIs | Result

### Sheet 3: HR Detail Log
Columns: Date | Player | Opponent | Home/Away | Pitcher Name | Pitcher Hand (L/R) | Batter Side Used | Inning | HR Distance | Launch Speed | Launch Angle

### Sheet 4: Odds Tracking
Columns: Date | Player | Opponent | DraftKings HR Odds | FanDuel HR Odds | BetMGM HR Odds | Best Odds | Implied Prob | Did Hit HR?

### Sheet 5: Analysis Dashboard
Pivot tables and charts:
- HR Rate by situation (Home/Away, vs LHP/RHP)
- Edge calculation (Actual Rate vs Implied Probability)
- Rolling HR rates (last 7/14/30 games)
- Profitable situations highlighted

---

## Automation Options

### Manual (Phase 1 — Now)
- Check MLB Stats API endpoints daily via browser or simple script
- Log data into Google Sheets manually
- Pull odds from Odds API Google Sheets extension

### Semi-Automated (Phase 2)
- Python script to pull game logs + play-by-play for all tracked players
- Script outputs CSV or writes directly to Google Sheets via API
- Run script each morning for previous day's games

### Fully Automated (Phase 3)
- Scheduled script (n8n workflow or cron job) runs daily
- Pulls MLB data + Odds API data
- Writes to Google Sheets automatically
- Sends summary notification (email/Telegram)

---

## Next Steps

1. **Set up Google Sheets** with the 5-sheet structure above
2. **Backfill early 2026 data** — pull game logs for first ~10 days of season for all 20 tracked players
3. **Pull HR detail data** from play-by-play for any HRs hit so far
4. **Start daily tracking** — establish the morning routine
5. **After 2-3 weeks of data** — begin analyzing patterns and comparing to odds
