from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
import re

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None
try:
    from . import ncaa_api
    from . import logo_service
except ImportError:
    import ncaa_api
    import logo_service

debug = logging.getLogger("scoreboard")


def get_scoreboard_snapshot(
    team_name: str,
    lookahead_days: int = 2,
    logo_dir=None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Return one normalized snapshot dict for the board renderer.

    Expected raw input:
    - Your ncaa_api.py should expose one of these helpers:
      get_team_games, fetch_team_games, get_games_for_team,
      fetch_games_for_team, get_schedule_for_team, fetch_schedule_for_team,
      get_schedule, fetch_schedule
    - That helper should return either:
      * a list of raw game dicts, or
      * a dict containing a game list under one of:
        games, events, data, scoreboard, contests
    """
    if not team_name:
        raise ValueError("team_name is required")

    local_now = now or datetime.now(_local_tz())
    raw_games = _fetch_raw_games(team_name=team_name, lookahead_days=lookahead_days)
    games = [_normalize_game(raw, tracked_team_slug=team_name) for raw in raw_games]
    games = [g for g in games if g is not None]
    games.sort(key=lambda g: g["sort_ts"])

    if not games:
        return _off_day_snapshot(team_name, None)

    live_games = [g for g in games if g["state"] == "live"]
    if live_games:
        chosen = live_games[0]
        _attach_logo_paths(chosen, logo_dir)
        return chosen

    scheduled_games = [
        g
        for g in games
        if g["state"] == "scheduled"
        and g["start_dt"] is not None
        and g["start_dt"] >= local_now - timedelta(hours=4)
    ]
    if scheduled_games:
        chosen = scheduled_games[0]
        _attach_logo_paths(chosen, logo_dir)
        return chosen

    final_games_today = [
        g
        for g in games
        if g["state"] == "final"
        and g["start_dt"] is not None
        and g["start_dt"].astimezone(_local_tz()).date() == local_now.date()
    ]
    if final_games_today:
        chosen = final_games_today[-1]
        _attach_logo_paths(chosen, logo_dir)
        return chosen

    future_games = [g for g in games if g["start_dt"] is not None and g["start_dt"] > local_now]
    if future_games:
        return _off_day_snapshot(team_name, future_games[0])

    return games[-1]


def _fetch_raw_games(team_name: str, lookahead_days: int) -> List[Dict[str, Any]]:
    function_names = (
        "get_team_games",
        "fetch_team_games",
        "get_games_for_team",
        "fetch_games_for_team",
        "get_schedule_for_team",
        "fetch_schedule_for_team",
        "get_schedule",
        "fetch_schedule",
    )

    call_patterns = (
        lambda fn: fn(team_name=team_name, lookahead_days=lookahead_days),
        lambda fn: fn(team_slug=team_name, lookahead_days=lookahead_days),
        lambda fn: fn(team_name, lookahead_days),
        lambda fn: fn(team_name=team_name),
        lambda fn: fn(team_slug=team_name),
        lambda fn: fn(team_name),
    )

    last_error = None
    for name in function_names:
        fn = getattr(ncaa_api, name, None)
        if not callable(fn):
            continue

        for call in call_patterns:
            try:
                payload = call(fn)
                return _coerce_game_list(payload)
            except TypeError:
                continue
            except Exception as exc:
                last_error = exc
                debug.exception("ncaa_hockey_ticker: %s failed", name)
                break

    if last_error is not None:
        raise RuntimeError(f"Unable to fetch NCAA games: {last_error}") from last_error

    raise RuntimeError(
        "ncaa_api.py does not expose a supported fetch helper. "
        "Add one of: get_team_games, fetch_team_games, get_games_for_team, "
        "fetch_games_for_team, get_schedule_for_team, fetch_schedule_for_team, "
        "get_schedule, fetch_schedule."
    )


def _coerce_game_list(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise TypeError("Game payload must be a list or dict")

    for key in ("games", "events", "data", "scoreboard", "contests"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    if "game" in payload and isinstance(payload["game"], dict):
        return [payload["game"]]

    if any(k in payload for k in ("home", "away", "homeTeam", "awayTeam", "opponent")):
        return [payload]

    return []


def _normalize_game(raw: Dict[str, Any], tracked_team_slug: str) -> Optional[Dict[str, Any]]:
    home = _extract_team(raw, "home")
    away = _extract_team(raw, "away")

    if not home and not away:
        opponent = _pick(raw, "opponent", "opponentTeam", "opponent_team")
        home_away = str(_pick(raw, "homeAway", "location", "site", default="")).lower()

        tracked_display = _title_from_slug(tracked_team_slug)
        tracked_team = {
            "name": tracked_display,
            "abbr": _abbr_from_name(tracked_display),
            "slug": tracked_team_slug,
            "score": _safe_int(_pick(raw, "teamScore", "score")),
        }
        opponent_team = _extract_team(opponent, None) if isinstance(opponent, dict) else {
            "name": str(opponent or "Opponent"),
            "abbr": _abbr_from_name(str(opponent or "Opponent")),
            "slug": _slugify(str(opponent or "Opponent")),
            "score": _safe_int(_pick(raw, "opponentScore")),
        }

        if home_away in ("away", "a"):
            away, home = tracked_team, opponent_team
        else:
            home, away = tracked_team, opponent_team

    if not home or not away:
        return None

    tracked_slug_norm = _slugify(tracked_team_slug)
    home_slug = _slugify(home.get("slug") or home.get("name") or home.get("abbr"))
    away_slug = _slugify(away.get("slug") or away.get("name") or away.get("abbr"))

    is_home = home_slug == tracked_slug_norm
    if not is_home and away_slug != tracked_slug_norm:
        tracked_name = _title_from_slug(tracked_team_slug)
        if _slugify(home.get("name")) == _slugify(tracked_name):
            is_home = True
        elif _slugify(away.get("name")) == _slugify(tracked_name):
            is_home = False

    opponent = away if is_home else home

    epoch = _pick(raw, "startTimeEpoch", "gameTimeEpoch", "epoch")
    start_dt = _parse_datetime(epoch)

    if start_dt is None:
        start_dt = _parse_datetime(
            _pick(
                raw,
                "startDateTime",
                "startDate",
                "startTime",
                "gameDate",
                "date",
                "datetime",
                "scheduled",
                "startTimeUTC",
                "contestDate",
            )
        )

    state = _normalize_state(_pick(raw, "gameState", "gameStatus", "status", "contestStatus", default=""))
    period_clock = _extract_period_clock(raw)
    status_text = _build_status_text(state, raw, start_dt, period_clock)

    snapshot = {
        "state": state,
        "status_text": status_text,
        "period_clock": period_clock,
        "sort_ts": start_dt.timestamp() if start_dt else float("inf"),
        "start_dt": start_dt,
        "start_date": _format_date(start_dt),
        "start_time": _format_time(start_dt),
        "detail_text": _format_detail_text(start_dt),
        "title_text": _title_from_slug(tracked_team_slug),
        "home_name": home["name"],
        "home_abbr": home["abbr"],
        "home_score": home["score"],
        "home_slug": home["slug"],
        "away_name": away["name"],
        "away_abbr": away["abbr"],
        "away_score": away["score"],
        "away_slug": away["slug"],
        "is_home": is_home,
        "opponent_name": opponent["name"],
        "opponent_abbr": opponent["abbr"],
        "opponent_slug": opponent["slug"],
        "matchup_text": f'{away["abbr"]} @ {home["abbr"]}',
        "home_logo_path": None,
        "away_logo_path": None,
        "next_opponent": None,
        "next_time": None,
    }

    if state == "off_day":
        snapshot["next_opponent"] = opponent["name"]
        snapshot["next_time"] = _format_detail_text(start_dt)

    return snapshot


def _extract_team(container: Any, side: Optional[str]) -> Optional[Dict[str, Any]]:
    if container is None:
        return None

    if side is not None and isinstance(container, dict):
        container = _pick(
            container,
            side,
            f"{side}Team",
            f"{side}_team",
            f"{side}Side",
        )

    if container is None:
        return None

    if isinstance(container, str):
        name = container.strip()
        return {
            "name": name,
            "abbr": _abbr_from_name(name),
            "slug": _slugify(name),
            "score": None,
        }

    if not isinstance(container, dict):
        return None

    names = container.get("names", {}) if isinstance(container.get("names"), dict) else {}

    name = str(
        _pick(
            names,
            "full",
            "short",
            "char6",
            "seo",
            default=_pick(
                container,
                "shortName",
                "displayName",
                "name",
                "team",
                "school",
                "market",
                default="",
            ),
        )
    ).strip()

    if not name:
        return None

    abbr = str(
        _pick(
            container,
            "abbreviation",
            "abbr",
            default=_pick(
                names,
                "short",
                "char6",
                "char4",
                default=_abbr_from_name(name),
            ),
        )
    ).strip()

    slug = str(
        _pick(
            container,
            "slug",
            "seoName",
            "teamSlug",
            default=_pick(names, "seo", default=_slugify(name)),
        )
    ).strip()

    score = _safe_int(_pick(container, "score", "currentScore", "goals", "runs"))

    return {
        "name": name,
        "abbr": abbr.upper() if abbr else _abbr_from_name(name),
        "slug": slug,
        "score": score,
    }


def _extract_period_clock(raw: Dict[str, Any]) -> str:
    direct = _pick(raw, "periodClock", "clock", "displayClock", "gameClock")
    if direct:
        period = _pick(raw, "period", "currentPeriod", "ordinal")
        if period:
            return f"{period} {direct}".strip()
        return str(direct)

    status = raw.get("status")
    if isinstance(status, dict):
        period = _pick(status, "period", "ordinal", "displayPeriod")
        clock = _pick(status, "clock", "displayClock")
        if period and clock:
            return f"{period} {clock}".strip()
        if clock:
            return str(clock)

    return ""


def _normalize_state(value: Any) -> str:
    s = str(value or "").strip().lower()

    if any(token in s for token in ("live", "in progress", "in_progress", "intermission", "period", "ot", "so")):
        return "live"
    if any(token in s for token in ("final", "complete", "completed")):
        return "final"
    if any(token in s for token in ("postponed", "cancelled", "canceled", "ppd")):
        return "postponed"
    if any(token in s for token in ("scheduled", "pre", "preview", "upcoming")):
        return "scheduled"

    return "scheduled"


def _build_status_text(state: str, raw: Dict[str, Any], start_dt: Optional[datetime], period_clock: str) -> str:
    if state == "live":
        return period_clock or str(_pick(raw, "status", "gameStatus", default="LIVE"))
    if state == "final":
        final_label = _pick(raw, "finalLabel", "result", default="FINAL")
        return str(final_label or "FINAL").upper()
    if state == "postponed":
        return "POSTPONED"
    if start_dt is not None:
        return _format_time(start_dt)
    return "SCHEDULED"


def _off_day_snapshot(team_name: str, next_game: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    snapshot = {
        "state": "off_day",
        "status_text": "NO GAME",
        "period_clock": "",
        "sort_ts": float("inf"),
        "start_dt": None,
        "start_date": "",
        "start_time": "",
        "detail_text": "",
        "title_text": _title_from_slug(team_name),
        "home_name": "",
        "home_abbr": "",
        "home_score": None,
        "home_slug": "",
        "away_name": "",
        "away_abbr": "",
        "away_score": None,
        "away_slug": "",
        "is_home": None,
        "opponent_name": "",
        "opponent_abbr": "",
        "opponent_slug": "",
        "matchup_text": "",
        "home_logo_path": None,
        "away_logo_path": None,
        "next_opponent": None,
        "next_time": None,
    }

    if next_game:
        snapshot["next_opponent"] = next_game["opponent_name"]
        snapshot["next_time"] = next_game["detail_text"]

    return snapshot


def _attach_logo_paths(snapshot: Dict[str, Any], logo_dir) -> None:
    if logo_dir is None:
        return

    for side in ("home", "away"):
        slug = snapshot.get(f"{side}_slug")
        if not slug:
            continue
        path = _cache_logo(slug)
        if path:
            snapshot[f"{side}_logo_path"] = str(path)


def _cache_logo(team_identifier: str):
    function_names = ("cache_logo", "get_logo", "ensure_logo")
    for name in function_names:
        fn = getattr(logo_service, name, None)
        if not callable(fn):
            continue
        try:
            return fn(team_identifier)
        except TypeError:
            try:
                return fn(team_name=team_identifier)
            except Exception:
                continue
        except Exception:
            continue
    return None


def _pick(container: Any, *keys: str, default=None):
    if not isinstance(container, dict):
        return default
    for key in keys:
        if key in container and container[key] not in (None, ""):
            return container[key]
    return default


def _safe_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None

    tz = _local_tz()

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz)

    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=tz)

    text = str(value).strip()

    if text.isdigit():
        return _parse_datetime(int(text))

    text = text.replace("Z", "+00:00")
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        try:
            dt = datetime.fromisoformat(text)
            return dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
        except ValueError:
            pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=tz)
        except ValueError:
            continue

    return None


def _format_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone(_local_tz()).strftime("%I:%M %p").lstrip("0")


def _format_date(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone(_local_tz()).strftime("%a %b %d")


def _format_detail_text(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    local = dt.astimezone(_local_tz())
    return f'{local.strftime("%a %b %d")} • {local.strftime("%I:%M %p").lstrip("0")}'


def _title_from_slug(value: str) -> str:
    return str(value).replace("-", " ").replace("_", " ").title()


def _abbr_from_name(name: str) -> str:
    parts = [part for part in re.split(r"[\s\-_\/]+", name.strip()) if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:3].upper()
    return "".join(part[0].upper() for part in parts[:4])


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _local_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/Detroit")
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo