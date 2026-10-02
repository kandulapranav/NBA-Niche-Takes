"""The tools the harness can run, and the JSON that describes them to the model."""

import json

from tools.espn import get_stat_receipts
from tools.reddit_takes import find_hot_takes, prep_for_pushback

# What the model sees: the "set notes" in the screenplay.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_hot_takes",
            "description": (
                "Find real NBA hot takes posted by fans on Reddit (r/NBAHotTakes and r/NBATalk), "
                "ranked by how controversial they were. Use whenever the user asks for a take, "
                "opinion, or something to say about the NBA, a player, or a team. Never invent takes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "player": {
                        "type": "string",
                        "description": (
                            "Player or team to filter on — a last name, nickname, or team name "
                            "(e.g. 'Curry', 'Wemby', 'Knicks'). Omit for any take."
                        ),
                    },
                    "min_spice": {
                        "type": "integer",
                        "description": (
                            "Minimum controversy level 1–5. Use 4+ when the user wants something "
                            "really spicy."
                        ),
                    },
                    "limit": {"type": "integer", "description": "How many takes to return, 1–5."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stat_receipts",
            "description": (
                "Get an NBA player's real stats plus 'receipts': the stats where his current "
                "numbers differ most from his career norm. Use to back up any take about a "
                "specific player. Never quote stats that didn't come from this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "player_name": {
                        "type": "string",
                        "description": "Player's full name, e.g. 'Stephen Curry'. Nicknames may not resolve.",
                    },
                },
                "required": ["player_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prep_for_pushback",
            "description": (
                "Get the strongest arguments real Redditors made against a specific take, plus the "
                "original poster's defenses, so the user can respond when a friend disagrees. Use "
                "when the user says someone pushed back or disagreed, or asks how to defend a take."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "take_id": {
                        "type": "string",
                        "description": (
                            "The id of a take returned earlier by find_hot_takes in this "
                            "conversation, e.g. '1wr3ojt' (no t3_ prefix)."
                        ),
                    },
                },
                "required": ["take_id"],
            },
        },
    },
]

# What the harness runs: tool name -> Python function.
TOOL_MAP = {
    "find_hot_takes": find_hot_takes,
    "get_stat_receipts": get_stat_receipts,
    "prep_for_pushback": prep_for_pushback,
}

# Tools that need this session's memory. run_tool passes it in as `state`;
# it is not in the schemas above, so the model can't see or set it.
STATEFUL_TOOLS = {"find_hot_takes", "prep_for_pushback"}


def new_session_state() -> dict:
    """Per-session memory the tools share: which takes we've shown, and their details."""
    return {"served_ids": set(), "takes": {}}


def run_tool(name: str, args: dict, state: dict) -> str:
    """Run one tool call. Models invent tool names and arguments; never let that crash the loop."""
    if name not in TOOL_MAP:
        return json.dumps({"error": f"Unknown tool '{name}'. Available: {list(TOOL_MAP)}"})
    if name in STATEFUL_TOOLS:
        args = {**args, "state": state}
    try:
        return TOOL_MAP[name](**args)
    except (TypeError, ValueError) as e:
        return json.dumps({"error": f"Bad arguments for {name}: {e}. Check the parameter names "
                           "and types in the tool description and call it again."})
    except Exception as e:
        # A bug or surprise API response: tell the model, don't 500 the whole chat.
        return json.dumps({"error": f"{name} failed unexpectedly ({type(e).__name__}). Try again "
                           "once; if it fails again, tell the user this data is unavailable."})
