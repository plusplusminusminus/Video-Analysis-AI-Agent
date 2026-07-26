# Video Scene Validator

Upload a video and a scene definition, validate the video against the scene shot
by shot, and get a rich analysis report.

This App is built using pdd (prompt-driven-development)
The app is a **hybrid** of a RocketRide webhook pipeline and a small FastAPI
backend:

- **FastAPI backend** detects shots (PySceneDetect), extracts a keyframe per shot,
  and runs per-shot vision comparison via **Token Router** (an OpenAI-compatible
  provider). This mirrors the behavior of the original `validate.py`.
- **RocketRide** (`video_validator.pipe`) is the **webhook-triggered aggregator**:
  the backend posts the per-shot findings + scene to the `webhook` source, and the
  pipeline synthesizes an overall analysis via `llm_openai_api` pointed at Token
  Router, returning it through `response_answers`.
- **React + Vite frontend** provides upload, an inline player with click-to-seek,
  per-shot result cards, and an overall analysis summary.

> Why hybrid? RocketRide's native vision node (`image_vision_openai`) cannot use a
> custom base URL, so it can't talk to Token Router. Only `llm_openai_api` supports
> a custom `base_url`. Vision therefore runs in the backend; RocketRide handles the
> webhook intake and LLM aggregation.

```
Frontend (upload)
   -> FastAPI /api/validate
        -> shot detection + per-shot vision (Token Router)     [backend]
        -> RocketRide webhook pipeline -> LLM aggregation       [video_validator.pipe]
   -> results (per-shot cards + overall analysis)
```

## Project layout

| Path | Purpose |
| --- | --- |
| `video_validator.pipe` | RocketRide pipeline (webhook -> question -> prompt -> llm_openai_api -> response_answers) |
| `backend/app.py` | FastAPI app: `POST /api/validate`, `GET /api/health` |
| `backend/vision.py` | Shot detection + per-shot Token Router vision engine |
| `backend/rocketride_client.py` | RocketRide aggregation client + local fallback |
| `frontend/` | React + Vite single-page app |
| `prompts/test.scene` | Example scene definition |

## Prerequisites

- Python 3.10+ (tested on 3.12)
- Node 18+ (tested on Node 22)
- A funded **Token Router** account (OpenAI-compatible) — vision + aggregation
  both call it. With `$0` credit the app still runs but returns errored shots and
  falls back to a locally-computed analysis.
- A **RocketRide** cloud API key.

## Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in the keys
uvicorn app:app --reload --port 8000
```

Environment variables (`backend/.env`):

| Variable | Meaning |
| --- | --- |
| `ROCKETRIDE_URI` | RocketRide endpoint (default `https://api.rocketride.ai`) |
| `ROCKETRIDE_APIKEY` | RocketRide API key |
| `TOKENROUTER_API_KEY` | Token Router key used by the backend vision engine |
| `TOKENROUTER_BASE_URL` | `https://api.tokenrouter.com/v1` |
| `TOKENROUTER_MODEL` | Vision/LLM model id, e.g. `openai/gpt-4o-mini` |
| `ROCKETRIDE_TOKENROUTER_KEY` | Same Token Router key, exposed for the pipeline (`${ROCKETRIDE_*}` substitution) |
| `ROCKETRIDE_TOKENROUTER_BASE_URL` | Token Router base URL for the pipeline |
| `ROCKETRIDE_TOKENROUTER_MODEL` | Token Router model id for the pipeline |
| `ROCKETRIDE_AGGREGATION_ENABLED` | `true` to use RocketRide; `false` to use local aggregation only |
| `FRONTEND_ORIGIN` | Allowed CORS origin(s), default `http://localhost:5173` |

> RocketRide only substitutes variables prefixed `ROCKETRIDE_` inside `.pipe`
> configs, which is why the Token Router creds are duplicated under that prefix.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> http://localhost:8000
```

## Usage

1. Start the backend and frontend.
2. Open the Vite URL.
3. Upload a video (`.mp4`) and a scene definition (`prompts/test.scene` works).
4. Click **Validate video against scene**.
5. Review the overall analysis and per-shot cards; click a shot's timestamp chip
   to seek the player.

## Scene definition format

JSON with an `overview` (characters/objects) and a `shots` array; each shot has a
`scene` description plus optional `style`, `camera`, `movements`, and `audio`.
See `prompts/test.scene`.

## API

`POST /api/validate` (multipart: `video`, `scene`) returns:

```json
{
  "shots": [
    { "shot_index": 0, "start_time": 0.0, "end_time": 1.0, "timestamp": 0.5,
      "Valid": true, "Issues": [], "Score": 88, "expectation": "..." }
  ],
  "analysis": {
    "overall_valid": true, "overall_score": 84, "pass_rate": 0.8,
    "summary": "...", "key_issues": [], "recommendations": [],
    "shots": [ ... ], "source": "rocketride"
  },
  "meta": { "shot_count": 5, "model": "openai/gpt-4o-mini", "aggregation_source": "rocketride" }
}
```

`analysis.source` / `meta.aggregation_source` indicate whether the analysis came
from RocketRide (`rocketride`) or the local fallback (`local ...`).

## Notes

- Secrets live only in `backend/.env` (gitignored). `backend/.env.example` is the
  template.
- `backend/make_test_video.py` generates a small synthetic multi-shot clip for
  local testing.
- The original `video.py` / `scene.py` / `validate.py` remain as the behavioral
  reference; the web app reproduces `validate.py`'s per-shot contract.
