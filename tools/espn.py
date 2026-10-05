"""get_stat_receipts and get_player_profile: real NBA data from ESPN's public (unofficial, keyless) API."""

import json

import requests

from tools.fetch import get_json

SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"
ATHLETE_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{athlete_id}"
STATS_URL = ATHLETE_URL + "/stats"
OVERVIEW_URL = ATHLETE_URL + "/overview"  # has the awards list

# A season with fewer games than this is too small a sample; use the season before it.
MIN_GAMES = 5

# The stats we report, and how to say each one out loud.
SHOWN_STATS = ["GP", "MIN", "PTS", "REB", "AST", "FG%", "3P%", "FT%"]
SWING_PHRASES = {
    "PTS": "averaging {season} points vs {career} for his career",
    "REB": "grabbing {season} rebounds vs {career} for his career",
    "AST": "dishing {season} assists vs {career} for his career",
    "FG%": "shooting {season}% from the field vs {career}% for his career",
    "3P%": "shooting {season}% from three vs {career}% for his career",
    "FT%": "shooting {season}% from the line vs {career}% for his career",
}

# ESPN lists awards in no particular order. These come first, biggest first; others follow.
AWARD_RANK = [
    "MVP", "Finals MVP", "Defensive Player of the Year", "Rookie of the Year", "All-NBA 1st Team",
    "Clutch Player of the Year", "Most Improved Player", "All-NBA 2nd Team", "All-NBA 3rd Team",
    "All-Defensive 1st Team", "NBA Cup MVP", "All-Star MVP", "All-Defensive 2nd Team",
]
TOP_AWARDS = 5


def find_nba_player(player_name: str) -> dict | None:
    """Search ESPN and return the first NBA player hit as {id, name, team}, or None."""
    data = get_json(SEARCH_URL, {"query": player_name, "limit": 5})
    for group in data.get("results", []):
        if group.get("type") != "player":
            continue
        for hit in group.get("contents", []):
            # uid looks like "s:40~l:46~a:3975"; the number after "a:" is the athlete id.
            if hit.get("defaultLeagueSlug") == "nba" and "~a:" in hit.get("uid", ""):
                return {
                    "id": hit["uid"].split("~a:")[1],
                    "name": hit["displayName"],
                    "team": hit.get("subtitle", ""),
                }
    return None


def to_numbers(labels: list[str], values: list[str]) -> dict:
    """Pair ESPN's labels with their values, keeping only the stats we show."""
    row = dict(zip(labels, values))
    numbers = {}
    for stat in SHOWN_STATS:
        try:
            numbers[stat] = float(row[stat])
        except (KeyError, ValueError):
            pass  # missing, or ESPN shows "-" for no data
    return numbers


def biggest_swings(season: dict, career: dict, top: int = 2) -> list[dict]:
    """The stats where this season differs most from the career norm, by relative change."""
    swings = []
    for stat, phrase in SWING_PHRASES.items():
        if stat not in season or not career.get(stat):
            continue
        change = (season[stat] - career[stat]) / career[stat]
        swings += [{
            "stat": stat,
            "season": season[stat],
            "career": career[stat],
            "change_pct": round(change * 100, 1),
            "line": phrase.format(season=season[stat], career=career[stat]),
        }]
    swings.sort(key=lambda s: abs(s["change_pct"]), reverse=True)
    return swings[:top]


def get_stat_receipts(player_name: str) -> str:
    """Get a player's latest-season and career averages, plus the biggest swings between them."""
    try:
        player = find_nba_player(player_name)
        if player is None:
            return json.dumps({"error": f"No NBA player matched '{player_name}'. "
                               "Use the full name, e.g. 'Stephen Curry'."})
        stats = get_json(STATS_URL.format(athlete_id=player["id"]))
    except requests.RequestException:
        return json.dumps({"error": "ESPN stats are unavailable right now. Give the take without "
                           "numbers and tell the user stats couldn't be loaded."})

    averages = next((c for c in stats.get("categories", []) if c.get("name") == "averages"), None)
    if not averages or not averages.get("statistics"):
        return json.dumps({"error": f"ESPN has no NBA stats for {player['name']} yet (maybe a "
                           "rookie). Give the take without numbers."})

    # One row per season. A player traded mid-season has a row per team and then a
    # "Totals" row; later rows overwrite earlier ones, so we keep the Totals row.
    by_season = {}
    for row in averages["statistics"]:
        by_season[row["season"]["year"]] = row
    rows = [by_season[year] for year in sorted(by_season)]

    # Newest season with enough games. Early in a season (or preseason) that's last season.
    labels = averages["labels"]
    latest = rows[-1]
    for row in reversed(rows):
        if to_numbers(labels, row["stats"]).get("GP", 0) >= MIN_GAMES:
            latest = row
            break

    season_averages = to_numbers(labels, latest["stats"])
    career_averages = to_numbers(labels, averages["totals"])

    return json.dumps({
        "player": player["name"],
        "team": player["team"],
        "season": latest["season"]["displayName"] + " regular season",
        "season_averages": season_averages,
        "career_averages": career_averages,
        "biggest_swings": biggest_swings(season_averages, career_averages),
    })


def top_awards(awards: list[dict], limit: int = TOP_AWARDS) -> list[str]:
    """The player's biggest awards as short labels like "2x MVP", most important first."""
    def rank(award: dict) -> int:
        name = award.get("name", "")
        return AWARD_RANK.index(name) if name in AWARD_RANK else len(AWARD_RANK)

    ranked = sorted(awards, key=rank)
    return [f"{a.get('displayCount', '1x')} {a['name']}" for a in ranked[:limit] if a.get("name")]


def get_player_profile(player_name: str) -> str:
    """Who a player is: team, position, age, size, experience, draft, college, and top awards."""
    try:
        player = find_nba_player(player_name)
        if player is None:
            return json.dumps({"error": f"No NBA player matched '{player_name}'. "
                               "Use the full name, e.g. 'Victor Wembanyama'."})
        athlete = get_json(ATHLETE_URL.format(athlete_id=player["id"]))["athlete"]
        awards = get_json(OVERVIEW_URL.format(athlete_id=player["id"])).get("awards", [])
    except (requests.RequestException, KeyError):
        return json.dumps({"error": "ESPN player profiles are unavailable right now. Tell the user "
                           "you couldn't load who this player is, and offer a take instead."})

    return json.dumps({
        "player": athlete.get("displayName", player["name"]),
        "team": (athlete.get("team") or {}).get("displayName", player["team"]),
        "position": (athlete.get("position") or {}).get("displayName"),
        "jersey": athlete.get("displayJersey"),
        "age": athlete.get("age"),
        "height": athlete.get("displayHeight"),
        "weight": athlete.get("displayWeight"),
        "experience": athlete.get("displayExperience"),
        "draft": athlete.get("displayDraft", "Undrafted"),
        "college": (athlete.get("college") or {}).get("name"),
        "birthplace": athlete.get("displayBirthPlace"),
        "top_awards": top_awards(awards),
        "headshot": (athlete.get("headshot") or {}).get("href"),
        "note": "ESPN's awards list does not include championships or All-Star selections.",
    })
