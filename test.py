from pprint import pprint
from scoreboard_service import get_scoreboard_snapshot

for team in ["michigan-tech"]:
    snapshot = get_scoreboard_snapshot(team_name=team, lookahead_days=3)
    print(f"\nTEAM: {team}")
    pprint(snapshot) 