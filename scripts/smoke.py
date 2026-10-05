"""Call each tool once against the live APIs, plus the failure cases. Run: uv run scripts/smoke.py"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # so "tools" imports when run as a script
from tools import new_session_state, run_tool  # noqa: E402


def show(label: str, name: str, args: dict, state: dict) -> dict:
    result = json.loads(run_tool(name, args, state))
    print(f"\n== {label}: {name}({args})")
    print(json.dumps(result, indent=1, ensure_ascii=False)[:900])
    return result


state = new_session_state()

takes = show("live", "find_hot_takes", {"player": "Curry", "limit": 2}, state)
show("live", "get_stat_receipts", {"player_name": "Stephen Curry"}, state)
show("live", "get_player_profile", {"player_name": "Victor Wembanyama"}, state)
if takes.get("takes"):
    time.sleep(2)  # be gentle with Arctic Shift
    show("live", "prep_for_pushback", {"take_id": takes["takes"][0]["id"]}, state)

show("misspelled player", "get_stat_receipts", {"player_name": "Stef Curry"}, state)
show("misspelled player", "get_player_profile", {"player_name": "Stef Curry"}, state)
show("bad take_id", "prep_for_pushback", {"take_id": "t3_not-a-real-id!"}, state)
print("\nSmoke test done.")
