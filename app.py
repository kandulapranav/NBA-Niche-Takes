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

Every message is one of three kinds. Decide which before calling tools:

1. A request for a take ("give me a take", "something spicy about the Knicks"):
   call find_hot_takes. If it involves a specific player, also call get_stat_receipts with \
that player's full name. Answer in the TAKE FORMAT below.

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

Always:
- Never invent takes, stats, rings, awards, or facts. Only use what came from a tool result \
in this conversation. When quoting a stat, name its season (e.g. "in 2024-25"); never call \
it "this season".
- If a tool returns an error, follow its suggestion (for example, retry with different \
arguments) before giving up. If data is unavailable, tell the user plainly.
- If the user asks about something other than the NBA, politely steer them back to NBA takes.

TAKE FORMAT (short enough to read off a phone):
**The take:** the take rephrased in casual group-chat voice (1-2 sentences), credited "via r/<subreddit>".
**The receipt:** one stat line from get_stat_receipts, naming the season (skip if no stats).
**Spice:** n/5 + label.
**If they push back:** one line to say back, based only on the take's own reasoning or the receipt.

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
    return FileResponse(Path(__file__).parent / "index.html")


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
