from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import logging

from PIL import Image, ImageFont, ImageDraw

from boards.base_board import BoardBase
from . import __version__, __description__, __board_name__
from .scoreboard_service import get_scoreboard_snapshot

debug = logging.getLogger("scoreboard")


class NCAAHockeyTicker(BoardBase):
    BOARD_WIDTH = 128
    BOARD_HEIGHT = 64

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
        self._glyph_cache = {}

        font_dir = self._find_font_dir()
        self.font_top = ImageFont.truetype(str(font_dir / "04B_24__.TTF"), 16)
        self.font_small = ImageFont.truetype(str(font_dir / "04B_24__.TTF"), 8)
        self.font_score = ImageFont.truetype(str(font_dir / "score_large.otf"), 32)

        self.layout = self._load_layout()

    def render(self):
        for team_name in self.teams:
            self.matrix.clear()

            try:
                snapshot = get_scoreboard_snapshot(
                    team_name=team_name,
                    lookahead_days=self.lookahead_days,
                    logo_dir=self.logo_dir,
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

        self._draw_layout_text("scheduled_date", top1, self.font_top)
        self._draw_layout_text("scheduled_time", top2, self.font_top)
        self._draw_layout_text("vs", "VS", self.font_score)

    def _render_live(self, s):
        period_text, clock_text = self._live_header_lines(s)

        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_layout_text("period", period_text, self.font_top)
        self._draw_layout_text("clock", clock_text, self.font_top)

        self._draw_score_glyph_at("away_score", self._score_text(s.get("away_score")))
        self._draw_score_glyph_at("dash", "-")
        self._draw_score_glyph_at("home_score", self._score_text(s.get("home_score")))

    def _render_final(self, s):
        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_layout_text("final", "FINAL", self.font_top)

        self._draw_score_glyph_at("away_score", self._score_text(s.get("away_score")))
        self._draw_score_glyph_at("dash", "-")
        self._draw_score_glyph_at("home_score", self._score_text(s.get("home_score")))

    def _render_postponed(self, s):
        self._draw_matchup_logos(s)
        self._draw_center_gradient()

        self._draw_layout_text("postponed", "POSTPONED", self.font_top)

        detail = self._safe_text(s.get("detail_text")) or self._safe_text(s.get("matchup_text"))
        self._draw_layout_text("off_day_time", self._truncate(detail, 24), self.font_small)

    def _render_off_day(self, s):
        next_opp = s.get("next_opponent") or "No game in window"
        next_time = s.get("next_time") or ""

        self._draw_layout_text("off_day_title", "NO GAME", self.font_score)
        self._draw_layout_text("off_day_opponent", self._truncate(str(next_opp), 22), self.font_top)
        self._draw_layout_text("off_day_time", self._truncate(str(next_time), 24), self.font_small)

    def _render_error(self, message: str):
        self._draw_layout_text("error_title", "DATA ERROR", self.font_score)
        self._draw_layout_text("error_message", self._truncate(message, 24), self.font_small)

    def _draw_matchup_logos(self, s):
        away_logo = self._get_logo_image(s.get("away_logo_path"))
        home_logo = self._get_logo_image(s.get("home_logo_path"))

        away_pos = self._get_pos("away_logo")
        home_pos = self._get_pos("home_logo")

        if away_logo is not None:
            self._draw_image_centered(away_pos["x"], away_pos["y"], away_logo)
        else:
            self._draw_text_centered_xy(
                away_pos["x"],
                away_pos["y"],
                self._safe_text(s.get("away_abbr")),
                self.font_score,
            )

        if home_logo is not None:
            self._draw_image_centered(home_pos["x"], home_pos["y"], home_logo)
        else:
            self._draw_text_centered_xy(
                home_pos["x"],
                home_pos["y"],
                self._safe_text(s.get("home_abbr")),
                self.font_score,
            )

    def _draw_layout_text(self, key: str, text: str, font):
        if not text:
            return
        pos = self._get_pos(key)
        self._draw_text_centered_xy(pos["x"], pos["y"], text, font)

    def _draw_score_glyph_at(self, key: str, text: str):
        if not text:
            return

        pos = self._get_pos(key)
        center_x = pos["x"]
        center_y = pos["y"]

        if text == "-":
            width = int(pos.get("width", 14))
            height = int(pos.get("height", 3))
            dash = Image.new("RGBA", (width, height), (255, 255, 255, 255))
            self._draw_image_centered(center_x, center_y, dash)
            return

        glyph_img = self._get_score_glyph_image(text)
        if glyph_img is not None:
            self._draw_image_centered(center_x, center_y, glyph_img)

    def _draw_text_centered_xy(self, center_x: int, center_y: int, text: str, font):
        if not text:
            return

        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        draw_x = int(round(center_x - (text_width / 2) - bbox[0]))
        draw_y = int(round(center_y - (text_height / 2) - bbox[1]))

        self.matrix.draw_text((draw_x, draw_y), text, font=font, fill="white")

    def _get_score_glyph_image(self, text: str):
        if text in self._glyph_cache:
            return self._glyph_cache[text]

        canvas = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((32, 32), text, font=self.font_score, fill="white")

        bbox = canvas.getbbox()
        if bbox is None:
            return None

        glyph = canvas.crop(bbox)
        self._glyph_cache[text] = glyph
        return glyph

    def _draw_image_centered(self, center_x: int, center_y: int, image):
        width, height = image.size
        draw_x = int(round(center_x - (width / 2)))
        draw_y = int(round(center_y - (height / 2)))
        self.matrix.draw_image((draw_x, draw_y), image)

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

    def _live_header_lines(self, s):
        period_clock = self._safe_text(s.get("period_clock")).strip()

        if period_clock:
            parts = period_clock.rsplit(" ", 1)
            if len(parts) == 2 and ":" in parts[1]:
                return parts[0].upper(), parts[1]
            if ":" in period_clock:
                return "LIVE", period_clock
            return period_clock.upper(), ""

        status_text = self._safe_text(s.get("status_text")).strip()
        if status_text:
            parts = status_text.rsplit(" ", 1)
            if len(parts) == 2 and ":" in parts[1]:
                return parts[0].upper(), parts[1]
            if ":" in status_text:
                return "LIVE", status_text

        return "LIVE", ""

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
            size = self.layout.get("logo_size", {})
            target_w = int(size.get("width", 82))
            target_h = int(size.get("height", 82))

            if img.size != (target_w, target_h):
                resample = getattr(Image, "Resampling", Image).LANCZOS
                img = img.resize((target_w, target_h), resample)

            self._logo_cache[path_str] = img
            return img
        except Exception as exc:
            debug.warning("Failed to load logo %s: %s", path, exc)
            return None

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

        pos = self._get_pos("center_gradient")
        self._draw_image_centered(pos["x"], pos["y"], img)

    def _load_layout(self):
        layout_path = self.plugin_dir / "layout_128x64.json"
        if not layout_path.exists():
            raise FileNotFoundError(f"Missing layout file: {layout_path}")

        data = json.loads(layout_path.read_text())
        block = data.get("ncaa_scoreboard")
        if not isinstance(block, dict):
            raise ValueError("layout_128x64.json must contain an 'ncaa_scoreboard' object")

        return block

    def _get_pos(self, key: str):
        value = self.layout.get(key)
        if not isinstance(value, dict):
            raise KeyError(f"Missing layout key: {key}")
        return value

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
