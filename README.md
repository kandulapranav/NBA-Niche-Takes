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

Type a message in the chat box, or tap one of the quick prompts. You can also open the player
picker (☰) to get a take on a specific player in one tap. The agent remembers the conversation,
so you can follow up on a take it just gave you ("my friend says that's a terrible take, what
do I say?").

### Example 1: a take about a player

> **You:** Give me a niche take about Stephen Curry

**The take:** Steph Curry isn't even a top 20 player of all time.
*Source card: "Yes. Steph Curry is not a top 20 player of all time." (r/NBATalk · 24 comments)*

**The receipt:** 4.7 AST in 2025-26, ▼25.4% vs his career average of 6.3. In the 2025-26
regular season, Curry is putting up 26.6 points per game while shooting 39.3% from deep.

**If they push back**
- *Your friend:* "He literally changed the game and has four rings!"
- *You say:* "Rings and shooting gravity are great, but all-time lists are about a complete body
  of work and two-way dominance over a long career."

*Tools used: Reddit takes, current season stats.*

### Example 2: settling an argument

> **You:** is damian lillard better than kyrie

Without a doubt, Dame is the better player to build around. Kyrie gets all the flash, but
Lillard is the ultimate floor-raiser and closer.

**How to argue it**
- *Your friend:* "Kyrie has the handles, the rings, and the ultimate shot-making bag."
- *You say:* "Kyrie has always needed a LeBron or a Luka to draw the heavy fire. Dame carried
  Portland as the undisputed focal point for a decade."
- *You say:* "In the 2024-25 regular season, Dame put up 24.9 points and 7.1 assists a night
  for Portland, proving he's way more of an offensive engine than just a scorer."

**Head to head (2024-25)**

| | Damian Lillard | Kyrie Irving |
|---|---|---|
| PTS | **24.9** | 24.7 |
| REB | 4.7 | **4.8** |
| AST | **7.1** | 4.6 |
| FG% | 44.8 | **47.3** |
| 3P% | 37.6 | **40.1** |
| FT% | **92.1** | 91.6 |

*Tools used: current season stats, once for each player.*

### Example 3: any take

> **You:** give me a niche take

**The take:** Kobe Bryant is actually a bigger threat to LeBron James's all-time legacy than
anyone else wants to admit.
*Source card: "Kobe Bryant is the biggest threat to LeBron's legacy" (r/NBATalk · 140 comments)*

There are no personal player stats for this one, but it's all about how Kobe's shadow and
mamba mentality still cast doubt on how people view the very top tier of all-time greats.

**If they push back**
- *Your friend:* "LeBron has longevity, stats, and finals appearances that completely blow Kobe
  out of the water!"
- *You say:* "Longevity is great, but legacy isn't just a spreadsheet. Kobe's peak cultural
  impact and killer instinct in the clutch still put psychological pressure on where people
  rank LeBron."

*Tools used: Reddit takes.*

Takes come from live Reddit data, so you'll get different takes each time you ask.

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
  If it's unavailable, the agent says so and asks you to try again in a minute.
- It's preseason, so stats are from the most recent completed season (2025-26), labeled as such.
- ESPN's API is unofficial, and its awards list doesn't include championships.
- Sessions are in memory and reset when the server restarts.
