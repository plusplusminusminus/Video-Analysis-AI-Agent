"""FastAPI backend for the Video Validator.

Flow:
  1. Frontend uploads a video (.mp4) + a scene definition (.scene/.json).
  2. Backend runs per-shot vision validation via Token Router (vision.py).
  3. Backend sends the findings to the RocketRide webhook pipeline, which
     synthesizes an overall analysis (rocketride_client.py).
  4. Combined result is returned to the frontend.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv(Path(__file__).resolve().parent / ".env")

# Ensure the RocketRide websocket (and other TLS clients) can verify certs on
# macOS Python builds that lack a system CA bundle.
import certifi  # noqa: E402

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("SSL_CERT_DIR", str(Path(certifi.where()).parent))

from rocketride_client import RocketRideAggregator  # noqa: E402
from vision import VideoSceneValidator, VisionConfig  # noqa: E402

aggregator = RocketRideAggregator()


def _build_validator() -> VideoSceneValidator:
    return VideoSceneValidator(
        VisionConfig(
            api_key=os.getenv("TOKENROUTER_API_KEY") or None,
            base_url=os.getenv("TOKENROUTER_BASE_URL", "https://api.tokenrouter.com/v1"),
            model=os.getenv("TOKENROUTER_MODEL", "gpt-4o"),
        )
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the persistent RocketRide pipeline (ttl=0) so the first request is fast.
    try:
        token = await aggregator.start()
        if token:
            print(f"[rocketride] persistent pipeline started (ttl=0): {token[:16]}...")
    except Exception as exc:  # noqa: BLE001
        print(f"[rocketride] warm-up skipped: {type(exc).__name__}: {exc}")
    yield
    await aggregator.close()


app = FastAPI(title="Video Validator", version="1.0.0", lifespan=lifespan)

_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "vision_provider_configured": bool(os.getenv("TOKENROUTER_API_KEY")),
        "rocketride_aggregation_enabled": aggregator.enabled,
        "rocketride_pipeline_running": aggregator.is_running,
        "model": os.getenv("TOKENROUTER_MODEL", "gpt-4o"),
    }


def _parse_scene(raw: bytes, filename: str) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Scene file '{filename}' is not valid JSON: {exc}",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Scene definition must be a JSON object.")
    return data


@app.post("/api/validate")
async def validate(video: UploadFile = File(...), scene: UploadFile = File(...)) -> JSONResponse:
    scene_bytes = await scene.read()
    scene_data = _parse_scene(scene_bytes, scene.filename or "scene")

    suffix = Path(video.filename or "upload.mp4").suffix or ".mp4"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await video.read())
            tmp_path = tmp.name

        validator = _build_validator()
        shots = await asyncio.to_thread(validator.validate, tmp_path, scene_data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Vision validation failed: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    analysis = await aggregator.aggregate(shots, scene_data)

    return JSONResponse(
        {
            "shots": shots,
            "analysis": analysis,
            "meta": {
                "shot_count": len(shots),
                "model": os.getenv("TOKENROUTER_MODEL", "gpt-4o"),
                "aggregation_source": analysis.get("source", "unknown"),
            },
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
