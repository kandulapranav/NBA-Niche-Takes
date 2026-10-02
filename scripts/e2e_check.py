"""End-to-end check against a running server: the 3 README queries in one session, then a fresh session.

Start the server first (uv run app.py), then:
    uv run scripts/e2e_check.py [base_url]
"""

import json
import sys

import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def chat(message: str, session_id: str | None = None) -> dict:
    response = requests.post(BASE_URL + "/chat", json={"message": message, "session_id": session_id},
                             timeout=120)
    response.raise_for_status()
    data = response.json()
    print(f"\n>>> {message}\n{data['response']}")
    for call in data["tool_calls"]:
        assert {"name", "args", "result"} <= call.keys(), call
        print(f"  tool: {call['name']}({json.dumps(call['args'])}) -> {call['result'][:150]}")
    return data


def take_ids(data: dict) -> list[str]:
    ids = []
    for call in data["tool_calls"]:
        if call["name"] == "find_hot_takes":
            ids += [take["id"] for take in json.loads(call["result"]).get("takes", [])]
    return ids


turn1 = chat("Give me a niche take")
session_id = turn1["session_id"]
assert "find_hot_takes" in [c["name"] for c in turn1["tool_calls"]], "turn 1 should call find_hot_takes"

turn2 = chat("Give me a niche take about Stephen Curry", session_id)
names = [c["name"] for c in turn2["tool_calls"]]
assert "find_hot_takes" in names and "get_stat_receipts" in names, names
assert not set(take_ids(turn1)) & set(take_ids(turn2)), "a take was served twice in one session"

turn3 = chat("My friend says that's a terrible take, what do I say?", session_id)
pushback = [c for c in turn3["tool_calls"] if c["name"] == "prep_for_pushback"]
assert pushback, "turn 3 should call prep_for_pushback"
used_id = pushback[0]["args"]["take_id"].removeprefix("t3_")
assert used_id in take_ids(turn2), f"turn 3 used {used_id}, not a take from turn 2 {take_ids(turn2)}"
print(f"\nOK: turn 3 used take_id {used_id} from turn 2")

fresh = chat("What take did you just give me, and what did my friend say about it?")
assert fresh["session_id"] != session_id
assert not fresh["tool_calls"] or "prep_for_pushback" not in [c["name"] for c in fresh["tool_calls"]]
print(f"\nOK: new session {fresh['session_id'][:8]} is separate from {session_id[:8]}")
