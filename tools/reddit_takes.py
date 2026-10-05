"""find_hot_takes and prep_for_pushback: real NBA takes and arguments from Reddit.

Reddit data comes from Arctic Shift, a free, keyless Reddit archive. If it is down or
rate-limits us, the tools return an error message telling the model to try again shortly.
"""

import json
import math
import re
import time
from datetime import date, timedelta

import requests

from tools.fetch import get_json

ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com"

# Spice = (1 - upvote_ratio) * log10(1 + num_comments): lots of argument, few upvotes.
# A raw score below each cutoff gets that level; anything above the last cutoff is 5.
SPICE_LEVELS = [
    (0.15, 1, "Mild"),
    (0.35, 2, "Warm"),
    (0.60, 3, "Hot"),
    (0.85, 4, "Scorching"),
]
MAX_SPICE = (5, "Nuclear")

MIN_AGE_HOURS = 48  # newer posts haven't collected votes/comments yet
NBATALK_DAYS_AGO = [3, 20, 40]  # r/NBATalk is too busy to page through; sample these days
BODY_PREVIEW_CHARS = 200
COMMENT_CHARS = 300
REDDIT_ID = re.compile(r"[a-z0-9]{5,10}")

# Lowercase name -> other ways fans refer to them. Matched as whole words.
ALIASES = {
    "stephen curry": ["curry", "steph"],
    "lebron james": ["lebron", "bron", "lbj"],
    "victor wembanyama": ["wemby", "wembanyama"],
    "nikola jokic": ["jokic", "joker"],
    "luka doncic": ["luka", "doncic"],
    "giannis antetokounmpo": ["giannis", "antetokounmpo", "greek freak"],
    "shai gilgeous-alexander": ["shai", "sga", "gilgeous-alexander"],
    "kevin durant": ["durant", "kd"],
    "anthony edwards": ["edwards", "ant", "ant-man"],
    "jayson tatum": ["tatum"],
    "joel embiid": ["embiid"],
    "jalen brunson": ["brunson"],
    "cooper flagg": ["flagg"],
    "ja morant": ["morant", "ja"],
    "kyrie irving": ["kyrie", "irving"],
    "damian lillard": ["lillard", "dame"],
    "michael jordan": ["jordan", "mj"],
    "lakers": ["lakers", "lal"],
    "warriors": ["warriors", "dubs", "gsw"],
    "knicks": ["knicks", "nyk"],
    "celtics": ["celtics"],
}


# --- Pure helpers (unit-tested in tests/test_tools.py) ---


def spice_score(upvote_ratio: float, num_comments: int) -> float:
    """How controversial a post was: many comments but a low upvote ratio."""
    return (1 - upvote_ratio) * math.log10(1 + num_comments)


def spice_level(score: float) -> tuple[int, str]:
    """Map a raw spice score to a 1-5 level and its label."""
    for cutoff, level, label in SPICE_LEVELS:
        if score < cutoff:
            return level, label
    return MAX_SPICE


def search_terms(player: str) -> list[str]:
    """All the names to look for: the player's alias group if we know it, else just what was asked."""
    asked = player.strip().lower()
    for name, aliases in ALIASES.items():
        if asked == name or asked in aliases:
            return [name] + aliases
    return [asked]


def mentions(text: str, terms: list[str]) -> bool:
    """True if any term appears in the text as a whole word (case-insensitive)."""
    return any(re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) for term in terms)


def is_question(title: str) -> bool:
    """Titles ending in '?' are asking, not taking a position."""
    return title.strip().endswith("?")


def is_usable(post: dict, now: float) -> bool:
    """Keep posts that are an actual take, safe for work, and old enough to have votes."""
    title = (post.get("title") or "").strip()
    if not title or title in ("[removed]", "[deleted]"):
        return False
    if post.get("over_18") or is_question(title):
        return False
    return now - post.get("created_utc", now) >= MIN_AGE_HOURS * 3600


def to_take(post: dict) -> dict:
    """The fields of a Reddit post that the model and the UI need."""
    body = post.get("selftext") or ""
    if body in ("[removed]", "[deleted]"):
        body = ""
    level, label = spice_level(spice_score(post["upvote_ratio"], post["num_comments"]))
    return {
        "id": post["id"],
        "title": post["title"].strip(),
        "body_preview": body[:BODY_PREVIEW_CHARS],
        "subreddit": post["subreddit"],
        "author": post["author"],
        "spice": level,
        "spice_label": label,
        "upvote_ratio": post["upvote_ratio"],
        "num_comments": post["num_comments"],
        "url": "https://www.reddit.com" + post["permalink"],
    }


# --- Fetching posts ---


def fetch_live_posts() -> list[dict]:
    """Recent posts from both subreddits. Raises requests.RequestException if Arctic Shift fails.

    We never keyword-search: Arctic Shift's search often times out (HTTP 422 "Timeout"), and
    filtering locally lets aliases like "Wemby" match "Wembanyama". It also means every request
    shares the same few cached pages.
    """
    # r/NBAHotTakes is quiet: its latest 100 posts go back more than a year.
    params = {"subreddit": "NBAHotTakes", "limit": 100, "sort": "desc"}
    posts = get_json(ARCTIC_SHIFT + "/api/posts/search", params)["data"]

    # r/NBATalk is busy: 100 posts is only ~8 hours. So grab the 100 posts before a few
    # sample days. Dates (not timestamps) keep the cache key stable all day.
    for days_ago in NBATALK_DAYS_AGO:
        before = (date.today() - timedelta(days=days_ago)).isoformat()
        params = {"subreddit": "NBATalk", "before": before, "limit": 100, "sort": "desc"}
        posts += get_json(ARCTIC_SHIFT + "/api/posts/search", params)["data"]
    return posts


# --- Tools ---


def find_hot_takes(player: str | None = None, min_spice: int = 1, limit: int = 3,
                   state: dict | None = None) -> str:
    """Find real NBA hot takes on Reddit, most controversial first.

    `state` is this session's memory, injected by run_tool (the model never sees it).
    """
    state = state if state is not None else {"served_ids": set(), "takes": {}}
    min_spice = min(max(int(min_spice), 1), 5)
    limit = min(max(int(limit), 1), 5)

    try:
        posts = fetch_live_posts()
    except (requests.RequestException, KeyError, ValueError):
        return json.dumps({"error": "Couldn't load Reddit takes right now (the archive may be "
                           "down or rate-limiting). Try again in a minute; meanwhile you can still "
                           "offer stats or a player profile."})

    now = time.time()
    posts = [p for p in posts if is_usable(p, now)]
    if player:
        terms = search_terms(player)
        posts = [p for p in posts if mentions(p["title"] + " " + (p.get("selftext") or ""), terms)]
        if not posts:
            return json.dumps({"error": f"No takes mention '{player}' in the posts I can see. Try a "
                               "last name ('Curry'), a nickname ('Steph'), a team ('Warriors'), "
                               "or call with no player."})

    # Remove duplicates (the same post can come from two fetches), then rank.
    takes = list({p["id"]: to_take(p) for p in posts}.values())
    takes = [t for t in takes if t["spice"] >= min_spice and t["id"] not in state["served_ids"]]
    if not takes:
        return json.dumps({"error": f"No unseen takes at spice {min_spice}+"
                           + (f" about '{player}'" if player else "")
                           + ". Try a lower min_spice, a different player, or no player."})
    # Takes that name the player in the title beat ones that only mention them in the body.
    named = {t["id"] for t in takes if player and mentions(t["title"], search_terms(player))}
    takes.sort(key=lambda t: (t["id"] in named, t["spice"], t["num_comments"]), reverse=True)
    takes = takes[:limit]

    # Remember what we served, so we don't repeat it and prep_for_pushback can find it.
    for take in takes:
        state["served_ids"].add(take["id"])
        state["takes"][take["id"]] = {
            "title": take["title"], "author": take["author"], "num_comments": take["num_comments"],
        }

    return json.dumps({"takes": takes})


def is_bot(author: str) -> bool:
    return author.lower() == "automoderator" or author.lower().endswith("bot")


def walk_comments(nodes: list[dict]) -> list[dict]:
    """Flatten Reddit's nested comment tree into a list of comment dicts.

    Each node is {"kind": "t1", "data": {..., "replies": "" or {"data": {"children": [...]}}}}.
    """
    comments = []
    for node in nodes:
        if node.get("kind") != "t1":
            continue  # "more" placeholders
        comment = node["data"]
        comments += [comment]
        if comment.get("replies"):
            comments += walk_comments(comment["replies"]["data"]["children"])
    return comments


def is_real_comment(comment: dict) -> bool:
    body = comment.get("body", "")
    return body not in ("", "[removed]", "[deleted]") and not is_bot(comment.get("author", ""))


def short(comment: dict) -> dict:
    text = comment["body"].strip()
    if len(text) > COMMENT_CHARS:
        text = text[:COMMENT_CHARS].rsplit(" ", 1)[0] + "…"
    return {"score": comment.get("score", 0), "text": text}


def prep_for_pushback(take_id: str, state: dict | None = None) -> str:
    """Counterarguments Redditors made against a take, plus the original poster's defenses."""
    state = state if state is not None else {"served_ids": set(), "takes": {}}
    take_id = str(take_id).strip().lower().removeprefix("t3_")
    if not REDDIT_ID.fullmatch(take_id):
        return json.dumps({"error": f"'{take_id}' is not a Reddit post id. Pass the 'id' field of a "
                           "take returned by find_hot_takes, e.g. '1wr3ojt' (no t3_ prefix)."})

    try:
        take = state["takes"].get(take_id)
        if take is None:
            # Not served in this session (e.g. a server restart): look the post up.
            found = get_json(ARCTIC_SHIFT + "/api/posts/ids", {"ids": take_id})["data"]
            if not found:
                return json.dumps({"error": f"No Reddit post with id '{take_id}'. Use an id from "
                                   "find_hot_takes in this conversation."})
            take = {k: found[0][k] for k in ("title", "author", "num_comments")}
        tree = get_json(ARCTIC_SHIFT + "/api/comments/tree", {"link_id": "t3_" + take_id, "limit": 50})
    except (requests.RequestException, KeyError, ValueError):
        return json.dumps({"error": "Couldn't load the Reddit comments right now (the archive may be "
                           "rate-limiting). Try again in a minute, or lean on the stat receipt instead."})

    top_level = [node["data"] for node in tree.get("data", []) if node.get("kind") == "t1"]
    counters = [c for c in top_level if is_real_comment(c) and c.get("author") != take["author"]]
    counters.sort(key=lambda c: c.get("score", 0), reverse=True)

    defenses = []
    if take["author"] not in ("", "[deleted]"):
        defenses = [c for c in walk_comments(tree.get("data", []))
                    if c.get("author") == take["author"] and is_real_comment(c)]
        defenses.sort(key=lambda c: c.get("score", 0), reverse=True)

    if not counters and not defenses:
        return json.dumps({"error": "Nobody has argued with this take yet — lean on the stat "
                           "receipt instead."})

    return json.dumps({
        "take_title": take["title"],
        "counterarguments": [short(c) for c in counters[:5]],
        "op_defenses": [short(c) for c in defenses[:3]],
        "total_comments": take["num_comments"],
    })
