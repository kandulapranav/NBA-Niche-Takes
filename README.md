# 🏀 Ball Knowledge

**Sound like you watch every game.**

Ball Knowledge is a chat agent for people whose friends are into the NBA but who don't follow
it themselves. Ask it for a take and it gives you a niche, spicy NBA opinion pulled from real
Reddit posts (r/NBAHotTakes and r/NBATalk), backs it up with a real stat from ESPN, and tells
you what to say when a friend pushes back. It never makes up takes or numbers: everything
comes from one of its tools.

## Tools

- **Get Reddit takes and threads** (`find_hot_takes`, `prep_for_pushback`): finds the most
  controversial real takes on Reddit about any player or team, and pulls the arguments people
  made against a take (plus the original poster's defenses) from its comment thread.
- **Get current season stats** (`get_stat_receipts`): gets a player's latest-season averages
  from ESPN and the stats that differ most from their career norm, as ready-to-say lines.
- **Get career summary** (`get_player_profile`): who a player is: team, position, age,
  height, draft pick, years in the league, and top career awards (MVPs, Finals MVPs, All-NBA
  teams, and so on).

## How to use it

Open the app and type a message, or tap one of the quick prompts. You can also open the
player picker (☰) to get a take on a specific player in one tap. The agent remembers the
conversation, so you can follow up on a take it gave you.

Example queries:

1. **"Give me a niche take about Stephen Curry"**: a real Reddit take about Curry, a stat
   that backs it up, and a comeback for when someone disagrees.
2. **"My friend says that's a terrible take, what do I say?"** (in the same chat, right
   after #1): what your friend will probably say, pulled from real Reddit replies to that take,
   and how to answer.
3. **"Who is Wemby?"**: a quick profile of Victor Wembanyama (team, age, height, draft pick,
   awards) plus one line you can drop in the group chat.

## Setup

### Run locally

Requires [uv](https://docs.astral.sh/uv/) and a Google Cloud project with billing and the
Agent Platform (Vertex AI) API enabled. There are no API keys: the app calls Gemini
(`vertex_ai/gemini-3.5-flash-lite` through LiteLLM) using Application Default Credentials.

```bash
gcloud auth application-default login
uv run app.py
```

Then open http://localhost:8000. Tests: `uv run pytest` (unit tests),
`uv run scripts/smoke.py` (each tool against the live APIs), and, with the server running,
`uv run scripts/e2e_check.py` (a take → follow-up conversation end to end, plus a check that separate chats share no memory).

### Deploy to Cloud Run

1. Enable the APIs:
   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com --project PROJECT_ID
   ```
2. In the console: **Cloud Run → Deploy container → Service → Continuously deploy from a
   repository → Set up with Cloud Build**. Connect this GitHub repo, branch `^main$`, build
   type **Python via Google Cloud's buildpacks** (the `Procfile` sets the start command).
3. Settings: any region (e.g. `us-central1`), **Allow unauthenticated access**, and
   **Maximum instances = 1**. Chat sessions live in memory, so every request has to reach the
   same instance. No environment variables are needed.
4. Let the service account call Gemini:
   ```bash
   gcloud projects add-iam-policy-binding PROJECT_ID \
     --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```
5. Click **Create**, then put the service URL in `submission.json`.

### Known limitations

- Reddit data comes from Arctic Shift, a free, unofficial archive that sometimes rate-limits.
  When it fails, takes come from a saved backup of 300 real posts (`data/seed_takes.json`).
- It's preseason, so stats are from the most recent completed season (2025-26), labeled as such.
- ESPN's API is unofficial, and its awards list doesn't include championships.
- Sessions are in memory and reset when the server restarts.
