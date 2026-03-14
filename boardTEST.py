from pathlib import Path
import logging

from boards.base_board import BoardBase
from . import __version__, __description__, __board_name__

debug = logging.getLogger("scoreboard")


class NCAAHockeyTicker(BoardBase):
    def __init__(self, data, matrix, sleepEvent):
        debug.warning("NCAA board __init__ called")
        super().__init__(data, matrix, sleepEvent)

        self.board_name = __board_name__
        self.board_version = __version__
        self.board_description = __description__

        self.display_seconds = int(self.get_config_value("display_seconds", 8))

        self.font_small = getattr(data.config.layout, "font_small", data.config.layout.font)
        self.font_medium = data.config.layout.font
        self.font_large = data.config.layout.font_large

    def render(self):
        debug.warning("NCAA board render() called")
        self.matrix.clear()
        self.matrix.draw_text_centered(18, "NCAA TEST", self.font_large, "white")
        self.matrix.draw_text_centered(40, "PLUGIN OK", self.font_medium, "cyan")
        self.matrix.render()
        self.sleepEvent.wait(self.display_seconds)