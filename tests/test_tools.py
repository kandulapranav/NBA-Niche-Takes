"""Unit tests for the pure helper functions (no network). Run: uv run pytest"""

import json
import time

from tools import new_session_state, run_tool
from tools.espn import biggest_swings, to_numbers
from tools.reddit_takes import (
    is_question,
    is_usable,
    mentions,
    search_terms,
    spice_level,
    spice_score,
    walk_comments,
)

# --- Spice scoring ---


def test_spice_score_is_zero_without_comments_or_downvotes():
    assert spice_score(0.5, 0) == 0
    assert spice_score(1.0, 500) == 0


def test_spice_score_grows_with_comments_and_downvotes():
    assert spice_score(0.4, 100) > spice_score(0.4, 10)
    assert spice_score(0.2, 100) > spice_score(0.8, 100)


def test_spice_levels_at_each_cutoff():
    assert spice_level(0.0) == (1, "Mild")
    assert spice_level(0.149) == (1, "Mild")
    assert spice_level(0.15) == (2, "Warm")
    assert spice_level(0.35) == (3, "Hot")
    assert spice_level(0.6) == (4, "Scorching")
    assert spice_level(0.85) == (5, "Nuclear")
    assert spice_level(3.0) == (5, "Nuclear")


# --- Alias matching ---


def test_search_terms_expands_known_aliases():
    assert "steph" in search_terms("Curry")
    assert "curry" in search_terms("Stephen Curry")
    assert "wembanyama" in search_terms("wemby")


def test_search_terms_passes_through_unknown_names():
    assert search_terms("Brunson ") == ["jalen brunson", "brunson"]
    assert search_terms("Sengun") == ["sengun"]


def test_mentions_matches_whole_words_case_insensitive():
    assert mentions("STEPH is washed", ["steph"])
    assert mentions("Is Curry > Magic?", ["curry"])
    assert not mentions("Stephen A said it", ["steph"])  # 'steph' inside 'Stephen'
    assert not mentions("I love currywurst", ["curry"])


# --- Question / usability filter ---


def test_is_question():
    assert is_question("Is LeBron the GOAT?")
    assert is_question("Who wins?  ")
    assert not is_question("LeBron is the GOAT")


def test_is_usable_drops_questions_nsfw_removed_and_new_posts():
    now = time.time()
    old = now - 72 * 3600
    good = {"title": "Jokic is overrated", "over_18": False, "created_utc": old}
    assert is_usable(good, now)
    assert not is_usable({**good, "title": "Is Jokic overrated?"}, now)
    assert not is_usable({**good, "over_18": True}, now)
    assert not is_usable({**good, "title": "[deleted]"}, now)
    assert not is_usable({**good, "created_utc": now - 3600}, now)


# --- Stat swings ---


def test_biggest_swings_ranks_by_relative_change():
    season = {"PTS": 26.6, "REB": 3.6, "AST": 4.7, "FG%": 46.8, "3P%": 39.3, "FT%": 92.3}
    career = {"PTS": 24.8, "REB": 4.7, "AST": 6.3, "FG%": 47.1, "3P%": 42.2, "FT%": 91.2}
    swings = biggest_swings(season, career)
    assert [s["stat"] for s in swings] == ["AST", "REB"]
    assert swings[0]["change_pct"] == -25.4
    assert swings[0]["line"] == "dishing 4.7 assists vs 6.3 for his career"


def test_biggest_swings_skips_missing_or_zero_career_stats():
    swings = biggest_swings({"PTS": 10.0, "3P%": 30.0}, {"PTS": 8.0, "3P%": 0.0})
    assert [s["stat"] for s in swings] == ["PTS"]


def test_to_numbers_ignores_dashes():
    assert to_numbers(["GP", "PTS", "3P%"], ["5", "12.0", "-"]) == {"GP": 5.0, "PTS": 12.0}


# --- Comment tree + dispatcher ---


def test_walk_comments_flattens_nested_replies():
    tree = [
        {"kind": "t1", "data": {"id": "a", "replies": {"data": {"children": [
            {"kind": "t1", "data": {"id": "b", "replies": ""}},
            {"kind": "more", "data": {}},
        ]}}}},
        {"kind": "t1", "data": {"id": "c", "replies": ""}},
    ]
    assert [c["id"] for c in walk_comments(tree)] == ["a", "b", "c"]


def test_run_tool_returns_errors_instead_of_raising():
    state = new_session_state()
    assert "Unknown tool" in json.loads(run_tool("nope", {}, state))["error"]
    assert "Bad arguments" in json.loads(run_tool("get_stat_receipts", {"name": "x"}, state))["error"]
    assert "not a Reddit post id" in json.loads(run_tool("prep_for_pushback", {"take_id": "?!"}, state))["error"]
