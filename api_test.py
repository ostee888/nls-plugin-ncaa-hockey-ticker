from pprint import pprint
from ncaa_api import get_team_games

games = get_team_games("michigan-tech", lookahead_days=2)
print(f"games found: {len(games)}")

if games:
    pprint(games[0])