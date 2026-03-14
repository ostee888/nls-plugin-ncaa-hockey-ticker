import json
from pathlib import Path

_plugin_dir = Path(__file__).parent
with open(_plugin_dir / "plugin.json") as f:
    _metadata = json.load(f)

__plugin_id__ = _metadata["name"]
__version__ = _metadata["version"]
__description__ = _metadata["description"]
__board_name__ = "NCAA Hockey Ticker"
__author__ = _metadata.get("author", "")