"""Build data/seed_takes.json: the offline fallback for find_hot_takes.

Run once locally (takes ~2 minutes, it pauses between calls to be gentle with Arctic Shift):
    uv run scripts/build_seed.py
"""

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))  # so "tools" imports when run as a script
from tools.reddit_takes import ARCTIC_SHIFT, SEED_PATH, is_usable, spice_level, spice_score  # noqa: E402

DAYS_BACK = 180
NBATALK_EVERY_DAYS = 7  # one page of 100 r/NBATalk posts per week
PER_SPICE_LEVEL = 60  # 5 levels x 60 = up to 300 takes, so the fallback isn't all one level
PAUSE_SECONDS = 3
KEEP_FIELDS = ["id", "title", "selftext", "subreddit", "author", "upvote_ratio", "num_comments",
               "created_utc", "permalink", "over_18"]


def fetch(params: dict) -> list[dict]:
    time.sleep(PAUSE_SECONDS)
    response = requests.get(ARCTIC_SHIFT + "/api/posts/search", params=params, timeout=30)
    response.raise_for_status()
    return response.json()["data"]


def main():
    oldest = date.today() - timedelta(days=DAYS_BACK)

    # r/NBAHotTakes: page backwards by date until we pass the oldest day.
    posts, before = [], date.today().isoformat()
    while True:
        page = fetch({"subreddit": "NBAHotTakes", "after": oldest.isoformat(), "before": before,
                      "limit": 100, "sort": "desc"})
        posts += page
        print(f"r/NBAHotTakes before {before}: {len(page)} posts")
        if len(page) < 100:
            break
        before = str(page[-1]["created_utc"])  # epoch seconds of the oldest post so far

    # r/NBATalk: one page per week.
    for days_ago in range(2, DAYS_BACK, NBATALK_EVERY_DAYS):
        day = (date.today() - timedelta(days=days_ago)).isoformat()
        page = fetch({"subreddit": "NBATalk", "before": day, "limit": 100, "sort": "desc"})
        posts += page
        print(f"r/NBATalk before {day}: {len(page)} posts")

    now = time.time()
    unique = {p["id"]: p for p in posts if is_usable(p, now)}
    # Most-discussed posts first, grouped by spice level.
    by_level = {level: [] for level in range(1, 6)}
    for post in sorted(unique.values(), key=lambda p: p["num_comments"], reverse=True):
        level, _ = spice_level(spice_score(post["upvote_ratio"], post["num_comments"]))
        by_level[level] += [post]
    kept = [post for posts_at_level in by_level.values() for post in posts_at_level[:PER_SPICE_LEVEL]]
    seed = [{field: post.get(field) for field in KEEP_FIELDS} for post in kept]
    for post in seed:
        post["selftext"] = (post["selftext"] or "")[:1000]  # enough for player matching

    SEED_PATH.parent.mkdir(exist_ok=True)
    SEED_PATH.write_text(json.dumps(seed, indent=1))
    print(f"{len(posts)} fetched, {len(unique)} usable, wrote {len(seed)} to {SEED_PATH}")


if __name__ == "__main__":
    main()
