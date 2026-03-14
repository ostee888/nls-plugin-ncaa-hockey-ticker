from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List
from urllib.request import Request, urlopen
from urllib.parse import quote
import json
import logging
import os

debug = logging.getLogger("scoreboard")

API_BASE_URL = os.getenv("NCAA_API_BASE_URL", "https://ncaa-api.henrygd.me").rstrip("/")
SPORT = "icehockey-men"
DIVISION = "d1"
CONFERENCE = "all-conf"
TIMEOUT_SECONDS = 10


def get_team_games(team_name: str, lookahead_days: int = 2) -> List[Dict[str, Any]]:
    """
    Fetch NCAA hockey games for today through lookahead_days and return only
    games involving the requested team slug/name.

    Returns a list of raw game dicts shaped like:
    {
        "away": {...},
        "home": {...},
        "gameID": "...",
        "gameState": "...",
        "startTimeEpoch": "...",
        ...
    }

    This is intentionally raw-ish. scoreboard_service.py normalizes it.
    """
    if not team_name:
        raise ValueError("team_name is required")

    slug = _slugify(team_name)
    seen_ids = set()
    matching_games: List[Dict[str, Any]] = []

    start_date = datetime.now()
    for offset in range(max(0, int(lookahead_days)) + 1):
        day = start_date + timedelta(days=offset)
        payload = _fetch_scoreboard_for_date(day)

        for item in payload.get("games", []):
            raw_game = item.get("game", item)
            if not isinstance(raw_game, dict):
                continue

            if not _game_matches_team(raw_game, slug):
                continue

            game_id = str(raw_game.get("gameID") or raw_game.get("id") or "")
            dedupe_key = game_id or _fallback_dedupe_key(raw_game)

            if dedupe_key in seen_ids:
                continue

            seen_ids.add(dedupe_key)
            matching_games.append(raw_game)

    return matching_games


# Aliases so scoreboard_service.py can find the fetcher even if it probes
# several possible helper names.
fetch_team_games = get_team_games
get_games_for_team = get_team_games
fetch_games_for_team = get_team_games
get_schedule_for_team = get_team_games
fetch_schedule_for_team = get_team_games
get_schedule = get_team_games
fetch_schedule = get_team_games


def _fetch_scoreboard_for_date(day: datetime) -> Dict[str, Any]:
    path = f"/scoreboard/{SPORT}/{DIVISION}/{day:%Y/%m/%d}/{CONFERENCE}"
    url = f"{API_BASE_URL}{quote(path, safe='/:')}"
    debug.debug("ncaa_hockey_ticker requesting %s", url)

    req = Request(
        url,
        headers={
            "User-Agent": "NCAA-Hockey-Ticker/1.0",
            "Accept": "application/json",
        },
    )

    with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8")
        payload = json.loads(body)

    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected NCAA API payload shape")

    return payload


def _game_matches_team(game: Dict[str, Any], team_slug: str) -> bool:
    for side in ("home", "away"):
        team = game.get(side, {})
        if not isinstance(team, dict):
            continue

        names = team.get("names", {})
        candidates = [
            names.get("seo"),
            names.get("short"),
            names.get("full"),
            team.get("name"),
            team.get("shortName"),
            team.get("displayName"),
        ]

        for candidate in candidates:
            if candidate and _slugify(candidate) == team_slug:
                return True

    return False


def _fallback_dedupe_key(game: Dict[str, Any]) -> str:
    home = _slugify(_extract_team_name(game.get("home", {})))
    away = _slugify(_extract_team_name(game.get("away", {})))
    epoch = str(game.get("startTimeEpoch") or game.get("startDate") or "")
    return f"{away}@{home}:{epoch}"


def _extract_team_name(team: Dict[str, Any]) -> str:
    if not isinstance(team, dict):
        return ""
    names = team.get("names", {})
    return (
        names.get("seo")
        or names.get("short")
        or names.get("full")
        or team.get("name")
        or ""
    )


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = []
    last_dash = False

    for ch in text:
        if ch.isalnum():
            chars.append(ch)
            last_dash = False
        else:
            if not last_dash:
                chars.append("-")
                last_dash = True

    return "".join(chars).strip("-")