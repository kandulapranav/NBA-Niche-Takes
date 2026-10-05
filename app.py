import json
import os
import uuid
from pathlib import Path

import litellm
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tools import TOOLS, new_session_state, run_tool

# --- Config ---

SYSTEM_PROMPT = """You are Ball Knowledge: a hype friend who helps people who don't follow \
the NBA sound like they do when their friends talk basketball.

Every message is one of these kinds. Decide which before calling tools:

1. A request for a take ("give me a take", "something spicy about the Knicks"):
   call find_hot_takes. It can return posts that are news, gossip, memes, or questions \
rather than opinions; skip those and present the most controversial post that states an \
opinion about basketball. When the user names a player or team, the take must be ABOUT \
them (they are the subject of the claim), not a take about someone else that only uses \
them as the comparison: for a LeBron request, "LeBron is washed" fits but "Giannis is better \
than LeBron" does not. If no returned post fits, call find_hot_takes again (for example \
with a lower min_spice) before settling. If the take involves a specific player, also call get_stat_receipts with that \
player's full name. Answer in the TAKE FORMAT below.

2. Pushback on a take YOU already gave ("my friend says that's a terrible take", "how do I \
defend that?"): the user is talking about your take, not raising a new topic. Call \
prep_for_pushback with that take's id. Build the answer only from its counterarguments (what \
the friend will probably say) and op_defenses (how to answer), plus stats already returned. \
Answer in the ARGUMENT FORMAT.

3. A new argument or comparison the user brings ("my friend says Kyrie is better than Dame, \
how do I argue Dame is better?"): this is NOT pushback on your earlier take, even if it \
mentions the same player, so do not call prep_for_pushback. Call get_stat_receipts for every \
player involved, and find_hot_takes with the player the user wants to argue for, to find \
real fan arguments. Answer in the ARGUMENT FORMAT, siding with the user.

4. "Who is this player?" or a request for the basics about a player ("who is Wemby?", "tell \
me about Jokic"): call get_player_profile with the player's full name. Answer in the PROFILE \
FORMAT. If they also want a take, do that too (TAKE FORMAT after the profile).

Always:
- Never invent takes, stats, rings, awards, or facts. Only use what came from a tool result \
in this conversation. When quoting a stat, name its season (e.g. "in 2024-25"); never call \
it "this season".
- If a tool returns an error, follow its suggestion (for example, retry with different \
arguments) before giving up. If data is unavailable, tell the user plainly.
- If the user asks about something other than the NBA, politely steer them back to NBA takes.

TAKE FORMAT (short enough to read off a phone):
**The take:** the take rephrased in casual group-chat voice (1-2 sentences), credited "via r/<subreddit>".
**The receipt:** one stat line from get_stat_receipts that backs up the take, naming the \
season (skip if no stats). If no stat supports the take, give the most relevant one plainly.
**If they push back:** They'll say "<the friend's objection, i.e. the opposite of the take>" \
→ you say "<a comeback that keeps the take's position>". The user is the one making the take, \
so the comeback DEFENDS the take; it never agrees with the objection. Base it on the post's \
own reasoning (title/body_preview) or the receipt. Example for a take "X is overrated": \
They'll say "he averages 30 a night" → you say "Nobody said he can't score, I said he's \
overrated. Big numbers aren't the same as winning."
**Take id:** the id of the take you presented, exactly as find_hot_takes returned it (the \
app uses it to show the matching Reddit post).

PROFILE FORMAT:
One or two casual sentences on who the player is, using only fields from get_player_profile \
(team, position, age, size, draft, top awards). Then:
**Drop this:** one line the user can say in the group chat to sound like they know the player.

ARGUMENT FORMAT:
One short intro line, then 2-4 bullets. Each bullet is "**They'll say:** ..." followed by \
"**You say:** ...", or a single "**Say this:** ..." line backed by a stat. No take format, \
and don't repeat an earlier take.
"""
MAX_TOOL_ROUNDS = 5

# --- The Harness ---


def run_agent(messages: list[dict], state: dict) -> tuple[str, list[dict]]:
    """Complete until the model answers without asking for a tool.

    `state` is this session's tool memory; it goes to the tools, never to the model.
    Returns the final text and a record of every tool call made along the way.
    """
    tool_calls = []

    for _ in range(MAX_TOOL_ROUNDS):
        reply = litellm.completion(
            model="vertex_ai/gemini-3.5-flash-lite",
            vertex_location="global",
            messages=messages,
            tools=TOOLS,
        ).choices[0].message

        # Append assistant's reply (text, tool calls, or both) to the context.
        # model_dump() keeps it a plain dict: the raw object carries provider-specific
        # fields that trip Pydantic when LiteLLM re-serializes it next round.
        messages += [reply.model_dump()]

        if not reply.tool_calls:
            return reply.content, tool_calls

        # The harness, not the model, runs each tool and appends the result
        for call in reply.tool_calls:
            args = json.loads(call.function.arguments)
            result = run_tool(call.function.name, args, state)
            tool_calls += [{"name": call.function.name, "args": args, "result": result}]

            messages += [{"role": "tool", "tool_call_id": call.id, "content": result}]

    return "Sorry, I hit my tool-call limit before finishing.", tool_calls


# --- Session Store ---

# session_id -> list of messages. In-memory, single process.
sessions: dict[str, list] = {}
# session_id -> tool memory (takes already shown, and their details). See tools.new_session_state.
session_state: dict[str, dict] = {}

# --- FastAPI App ---

app = FastAPI()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[dict]


@app.get("/")
def index():
    # no-cache: the browser must check for a newer index.html instead of reusing an old copy.
    return FileResponse(Path(__file__).parent / "index.html", headers={"Cache-Control": "no-cache"})


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    # Get or create the session
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        session_state[session_id] = new_session_state()

    # Append user's message to the context
    sessions[session_id] += [{"role": "user", "content": request.message}]

    try:
        response, tool_calls = run_agent(sessions[session_id], session_state[session_id])
    except Exception as e:
        # Auth, billing, a model that is not running: show it in the chat, not as a 500.
        response, tool_calls = f"Model call failed: {type(e).__name__}: {str(e)[:300]}", []

    return ChatResponse(response=response, session_id=session_id, tool_calls=tool_calls)


@app.post("/clear")
def clear(session_id: str | None = None):
    sessions.pop(session_id, None)
    session_state.pop(session_id, None)
    return {"status": "ok"}


if __name__ == "__main__":
    # Cloud Run tells us which port to listen on via $PORT; locally we default to 8000.
    # 0.0.0.0 so requests from outside the container can reach us.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
