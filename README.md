# 🏀 Ball Knowledge

**Sound like you watch every game.**

Ball Knowledge is a chat agent for people whose friends are into the NBA but who don't follow
it themselves. Ask for a take and you get a niche, spicy NBA opinion pulled from **real Reddit
posts** (r/NBAHotTakes, r/NBATalk), backed by a **real stat** from ESPN, plus ammo for when a
friend pushes back. It never invents takes or numbers; everything comes from a tool call.
The UI turns the tool results into a take card (link to the original Reddit
post, stat line, and the real Reddit replies), and `/chat` returns every tool call
(`name`, `args`, `result`) in `tool_calls`.

Built on the course starter `gemini-web-tool-calling`: FastAPI + LiteLLM + Gemini
(`vertex_ai/gemini-3.5-flash-lite`) with the same hand-written tool-calling loop.

## How it works

The browser POSTs to `/chat`. `run_agent()` in `app.py` sends the conversation and the tool
schemas to Gemini, runs whatever tools Gemini asks for, sends the results back, and repeats
until Gemini answers in text (at most 5 rounds).

| Tool | What it does | Data source |
|---|---|---|
| `find_hot_takes(player?, min_spice?, limit?)` | Real takes from Reddit, ranked by a 1–5 "spice" (controversy) score: `(1 − upvote_ratio) × log10(1 + comments)` | [Arctic Shift](https://arctic-shift.photon-reddit.com) Reddit archive, with `data/seed_takes.json` as a fallback |
| `get_stat_receipts(player_name)` | Latest-season vs career averages, and the two stats that changed the most, phrased as ready-to-say lines | ESPN's public site API |
| `prep_for_pushback(take_id)` | The top counterarguments Redditors made against a take, plus the original poster's own defenses | Arctic Shift comment trees |
| `get_player_profile(player_name)` | A "starter pack" on who a player is: team, position, age, size, years in the league, draft pick, college, birthplace, top awards | ESPN's public site API |

**Memory:** each session keeps its full message history (as in the starter) plus a small
tool state: which takes were already shown (so they don't repeat) and their titles/authors
(so `prep_for_pushback` can use them). The server adds this state when it runs a tool;
the model never sees it as an argument. Different `session_id`s never share anything.

## Try it: sample queries

Run these in order in one chat:

1. **"Give me a niche take"** → `find_hot_takes` → a real take, picked for how controversial it was.
2. **"Give me a niche take about Stephen Curry"** → `find_hot_takes(player="Curry")` + `get_stat_receipts("Stephen Curry")`.
3. **"My friend says that's a terrible take, what do I say?"** → `prep_for_pushback(<id of the take from #2>)`. This shows memory: the agent knows which take "that" is.

Bonus: **"Who is Wemby?"** → `get_player_profile("Victor Wembanyama")` shows a profile card with headshot, quick facts, and awards.

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and a Google Cloud project with billing and the
Agent Platform API (Vertex AI) enabled. No API keys: the app uses Application Default
Credentials and your gcloud default project.

```bash
gcloud auth application-default login
uv run app.py
```

Open http://localhost:8000.

Tests and checks:

```bash
uv run pytest                 # unit tests for the pure functions (no network)
uv run scripts/smoke.py       # each tool once against the live APIs, plus failure cases
uv run scripts/e2e_check.py   # with the server running: the 3 sample queries + a 2nd session
uv run scripts/build_seed.py  # rebuild data/seed_takes.json (only needed occasionally)
```

Set `FORCE_TAKES_FALLBACK=1` to make `find_hot_takes` skip the live archive and use the seed file.

## Deploy to Cloud Run (continuous deployment from GitHub)

The app listens on `$PORT` (Cloud Run sets it; locally it defaults to 8000). `Procfile`
tells Cloud Run's Python buildpack to start it with `python app.py`, and the buildpack
installs dependencies from `pyproject.toml` + `uv.lock`. **No secrets or API keys are needed:**
on Cloud Run, the Gemini client authenticates as the service's service account through ADC
and reads the project ID from the metadata server.

1. **Enable APIs** (once): Cloud Run, Cloud Build, Artifact Registry, and the Agent Platform
   (Vertex AI) API:
   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com --project PROJECT_ID
   ```
2. **Console → Cloud Run → Deploy container → Service → "Continuously deploy from a repository (source or function)" → Set up with Cloud Build.**
   - Repository provider: GitHub. Authenticate and select this repo.
   - Branch: `^main$`.
   - Build type: **Python via Google Cloud's buildpacks** (build context directory `/`, no entrypoint needed: the `Procfile` provides it).
3. **Service settings:**
   - Region: `us-central1` (any region works; Gemini is called in the `global` location).
   - Authentication: **Allow unauthenticated access** (public URL).
   - Scaling: **Maximum instances = 1.** Sessions live in memory, so every request must reach the same instance. With more instances, a follow-up could land on an instance that never saw the conversation.
   - Environment variables: none required. Optional: `GOOGLE_CLOUD_PROJECT` to override the project ID.
4. **Let the service account call Gemini.** By default, Cloud Run runs as the Compute Engine
   default service account. Grant it the Vertex AI User role:
   ```bash
   gcloud projects add-iam-policy-binding PROJECT_ID \
     --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```
   (Find `PROJECT_NUMBER` with `gcloud projects describe PROJECT_ID --format='value(projectNumber)'`.
   If you picked a different service account in step 3, use that one.)
5. Click **Create**. Every push to `main` now rebuilds and redeploys. Put the service URL in `submission.json`.

## Data sources and known limitations

- **Arctic Shift is an unofficial, free archive.** It rate-limits quickly (HTTP 429) and its
  keyword search often times out (HTTP 422 "Timeout"), so the app doesn't use keyword search.
  It fetches recent posts and filters them locally by player name, using an alias map
  ("Wemby" → Wembanyama, "Steph" → Curry). Responses are cached for 30 minutes, calls time out after 8 seconds, and a
  429 is retried once. On any failure, takes come from `data/seed_takes.json` (300 real posts
  from the past ~6 months), and the result says `"source": "cached"`.
- **Coverage:** r/NBAHotTakes is quiet (its latest 100 posts go back over a year); r/NBATalk is
  busy (100 posts ≈ 8 hours), so the app samples 100 posts from 3, 20 and 40 days ago.
  Some players simply won't have a take.
- **Scores are snapshots.** Arctic Shift captures posts and comments soon after they're posted,
  so very new posts show ~1 point / 100% upvoted (we skip posts under 48 hours old), and many
  comment scores are low.
- **Preseason stats:** it's before the 2026-27 regular season, so `get_stat_receipts` uses the most
  recent season with at least 5 games played (currently 2025-26) and says which season it is.
- **ESPN's API is unofficial** and undocumented; if it fails, the agent gives the take without numbers.
  Its awards list (used by `get_player_profile`) doesn't include championships or All-Star selections.
- **The first request after a restart is slow** (~15 s) while the Reddit cache fills up.
- Sessions are in memory: they're lost when the instance restarts or scales to zero.

## Files

| Path | What it is |
|---|---|
| `app.py` | FastAPI app: system prompt, tool-calling loop, session store, `/chat`, `/clear` |
| `tools/__init__.py` | Tool schemas the model sees, the name → function map, and `run_tool` (never raises) |
| `tools/reddit_takes.py` | `find_hot_takes`, `prep_for_pushback`, spice scoring, alias matching, seed fallback |
| `tools/espn.py` | `get_stat_receipts`, `get_player_profile`, the stat-swing calculation, and award ranking |
| `tools/fetch.py` | Shared `get_json`: 8 s timeout, one retry on 429, 30-minute cache |
| `index.html` | The whole frontend (plain HTML/CSS/JS) |
| `data/seed_takes.json` | Offline fallback takes, built by `scripts/build_seed.py` |
| `scripts/` | Seed builder, live smoke test, end-to-end check |
| `tests/` | pytest unit tests |
| `Procfile`, `.python-version` | How Cloud Run's buildpack starts the app, and which Python to use |
