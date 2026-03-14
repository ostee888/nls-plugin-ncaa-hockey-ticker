from __future__ import annotations

from datetime import datetime
from pathlib import Path
import logging

from PIL import Image, ImageFont

from boards.base_board import BoardBase
from . import __version__, __description__, __board_name__
from .scoreboard_service import get_scoreboard_snapshot

debug = logging.getLogger("scoreboard")


class NCAAHockeyTicker(BoardBase):
    LOGO_SIZE = (82, 82)
    AWAY_LOGO_CENTER_X = 12
    HOME_LOGO_CENTER_X = 116
    LOGO_CENTER_Y = 32

    TOP_LINE_Y = 0
    SECOND_LINE_Y = 12
    MID_ROW_Y = 27
    SCORE_ROW_Y = 44
    BOTTOM_ROW_Y = 56

    def __init__(self, data, matrix, sleepEvent):
        super().__init__(data, matrix, sleepEvent)

        self._center_gradient = None
        self.board_name = __board_name__
        self.board_version = __version__
        self.board_description = __description__

        raw_teams = self.get_config_value("teams", None)
        if isinstance(raw_teams, list) and raw_teams:
            self.teams = [str(team).strip() for team in raw_teams if str(team).strip()]
        else:
            fallback_team = self.get_config_value("team_name", "michigan-tech")
            self.teams = [str(fallback_team).strip()]

        self.lookahead_days = int(self.get_config_value("lookahead_days", 2))
        self.display_seconds = int(self.get_config_value("display_seconds", 8))

        self.plugin_dir = Path(__file__).parent
        self.logo_dir = self.plugin_dir / "data" / "logos"
        self.logo_dir.mkdir(parents=True, exist_ok=True)

        self._logo_cache = {}

        font_dir = self._find_font_dir()
        self.font_top = ImageFont.truetype(str(font_dir / "04B_24__.TTF"), 16)
        self.font_small = ImageFont.truetype(str(font_dir / "04B_24__.TTF"), 8)
        self.font_score = ImageFont.truetype(str(font_dir / "score_large.otf"), 32)

    def render(self):
        for team_name in self.teams:
            self.matrix.clear()

            try:
                snapshot = get_scoreboard_snapshot(
                    team_name=team_name,
                    lookahead_days=self.lookahead_days,
                    logo_dir=self.logo_dir,
                )

                debug.warning(
                    "NCAA render team=%s state=%s matchup=%s",
                    team_name,
                    snapshot.get("state"),
                    snapshot.get("matchup_text"),
                )

            except Exception as exc:
                debug.exception(
                    "ncaa_hockey_ticker render fetch failed for %s: %s",
                    team_name,
                    exc,
                )
                self._render_error(str(exc))
                self.matrix.render()
                if self.sleepEvent.wait(self.display_seconds):
                    return
                continue

            state = snapshot.get("state", "off_day")

            if state == "scheduled":
                self._render_scheduled(snapshot)
            elif state == "live":
                self._render_live(snapshot)
            elif state == "final":
                self._render_final(snapshot)
            elif state == "postponed":
                self._render_postponed(snapshot)
            else:
                self._render_off_day(snapshot)

            self.matrix.render()

            if self.sleepEvent.wait(self.display_seconds):
                return

    def _render_scheduled(self, s):
        top1, top2 = self._scheduled_header_lines(s)

        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_center_text(self.TOP_LINE_Y, top1, self.font_top)
        self._draw_center_text(self.SECOND_LINE_Y, top2, self.font_top)
        self._draw_center_text(self.MID_ROW_Y, "VS", self.font_score)

    def _render_live(self, s):
        status = self._safe_text(s.get("period_clock")) or self._safe_text(s.get("status_text")) or "LIVE"

        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_center_text(self.TOP_LINE_Y, self._truncate(status, 18), self.font_top)
        self._draw_text_at_center_x(32, self.SCORE_ROW_Y, self._score_text(s.get("away_score")), self.font_score)
        self._draw_text_at_center_x(96, self.SCORE_ROW_Y, self._score_text(s.get("home_score")), self.font_score)

    def _render_final(self, s):
        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_center_text(self.TOP_LINE_Y, "FINAL", self.font_top)
        self._draw_text_at_center_x(32, self.SCORE_ROW_Y, self._score_text(s.get("away_score")), self.font_score)
        self._draw_text_at_center_x(96, self.SCORE_ROW_Y, self._score_text(s.get("home_score")), self.font_score)

    def _render_postponed(self, s):
        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_center_text(self.TOP_LINE_Y, "POSTPONED", self.font_top)

        detail = self._safe_text(s.get("detail_text")) or self._safe_text(s.get("matchup_text"))
        self._draw_center_text(self.BOTTOM_ROW_Y, self._truncate(detail, 24), self.font_small)

    def _render_off_day(self, s):
        self._draw_center_text(8, "NO GAME", self.font_score)

        next_opp = s.get("next_opponent") or "No game in window"
        next_time = s.get("next_time") or ""

        self._draw_center_text(34, self._truncate(str(next_opp), 22), self.font_top)
        self._draw_center_text(54, self._truncate(str(next_time), 24), self.font_small)

    def _render_error(self, message: str):
        self._draw_center_text(8, "DATA ERROR", self.font_score)
        self._draw_center_text(42, self._truncate(message, 24), self.font_small)

    def _draw_matchup_logos(self, s):
        away_logo = self._get_logo_image(s.get("away_logo_path"))
        home_logo = self._get_logo_image(s.get("home_logo_path"))

        if away_logo is not None:
            self._draw_image_centered(self.AWAY_LOGO_CENTER_X, self.LOGO_CENTER_Y, away_logo)
        else:
            self._draw_text_at_center_x(27, 22, self._safe_text(s.get("away_abbr")), self.font_score)

        if home_logo is not None:
            self._draw_image_centered(self.HOME_LOGO_CENTER_X, self.LOGO_CENTER_Y, home_logo)
        else:
            self._draw_text_at_center_x(101, 22, self._safe_text(s.get("home_abbr")), self.font_score)

    def _draw_center_text(self, y: int, text: str, font):
        if text:
            self.matrix.draw_text_centered(y, text, font, "white")

    def _draw_text_at_center_x(self, x: int, y: int, text: str, font):
        if text:
            self.matrix.draw_text((x, y), text, font=font, fill="white", align="center-top")

    def _scheduled_header_lines(self, s):
        start_dt = s.get("start_dt")
        start_time = self._safe_text(s.get("start_time"))

        if isinstance(start_dt, datetime):
            now = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
            if start_dt.date() == now.date():
                top1 = "TODAY"
            elif (start_dt.date() - now.date()).days == 1:
                top1 = "TOMORROW"
            else:
                top1 = start_dt.strftime("%a").upper()
        else:
            top1 = "UPCOMING"

        return top1, start_time or "TBD"

    def _get_logo_image(self, path_str):
        if not path_str:
            return None

        if path_str in self._logo_cache:
            return self._logo_cache[path_str]

        path = Path(path_str)
        if not path.exists():
            return None

        try:
            img = Image.open(path).convert("RGBA")
            if img.size != self.LOGO_SIZE:
                resample = getattr(Image, "Resampling", Image).LANCZOS
                img = img.resize(self.LOGO_SIZE, resample)
            self._logo_cache[path_str] = img
            return img
        except Exception as exc:
            debug.warning("Failed to load logo %s: %s", path, exc)
            return None

    def _find_font_dir(self) -> Path:
        repo_root = Path(__file__).resolve().parents[4]
        candidates = [
            Path("/nhl-led/scoreboard/assets/fonts"),
            Path("/home/pi/nhl-led-scoreboard/assets/fonts"),
            repo_root / "assets" / "fonts",
        ]

        for candidate in candidates:
            if (candidate / "04B_24__.TTF").exists() and (candidate / "score_large.otf").exists():
                return candidate

        raise FileNotFoundError("Could not locate scoreboard font directory")

    def _draw_image_centered(self, center_x: int, center_y: int, image):
        width, height = image.size
        draw_x = center_x - (width // 2)
        draw_y = center_y - (height // 2)
        self.matrix.draw_image((draw_x, draw_y), image)

    def _get_center_gradient(self):
        if self._center_gradient is not None:
            return self._center_gradient

        path = Path("/home/pi/nhl-led-scoreboard/assets/images/128x64_scoreboard_center_gradient.png")
        if not path.exists():
            debug.warning("Center gradient not found: %s", path)
            return None

        try:
            img = Image.open(path).convert("RGBA")
            self._center_gradient = img
            return img
        except Exception as exc:
            debug.warning("Failed to load center gradient %s: %s", path, exc)
            return None

    def _draw_center_gradient(self):
        img = self._get_center_gradient()
        if img is None:
            return

        w, h = img.size
        x = (128 - w) // 2
        y = (64 - h) // 2
        self.matrix.draw_image((x, y), img)

    @staticmethod
    def _score_text(value):
        return "-" if value is None else str(value)

    @staticmethod
    def _safe_text(value):
        return "" if value is None else str(value)

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"
