"""RocketRide aggregation client.

Sends the per-shot vision findings + scene definition to the RocketRide
`video_validator.pipe` (webhook source) and returns the synthesized analysis
produced by the pipeline's Token Router LLM step.

If RocketRide is disabled or unreachable, a deterministic local aggregation is
computed so the app still returns a useful analysis (degraded mode).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

PIPE_PATH = str(Path(__file__).resolve().parent.parent / "video_validator.pipe")
PROJECT_ID = "7f788d4e-69ea-4217-b5df-c3228d717c3e"
SOURCE = "webhook_1"


def local_aggregate(shots: list[dict[str, Any]], scene: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback analysis derived purely from the per-shot results."""
    n = len(shots)
    scores = [int(s.get("Score", 0) or 0) for s in shots]
    valid_flags = [bool(s.get("Valid", False)) for s in shots]
    overall_score = round(sum(scores) / n) if n else 0
    pass_rate = round(sum(valid_flags) / n, 2) if n else 0.0

    key_issues: list[str] = []
    for s in shots:
        for issue in s.get("Issues", []) or []:
            if issue not in key_issues:
                key_issues.append(issue)

    title = scene.get("video_title") or "the scene definition"
    summary = (
        f"Analyzed {n} shot(s) against {title}. "
        f"{sum(valid_flags)} of {n} shots matched their expected description "
        f"(average score {overall_score}/100)."
    )
    recommendations: list[str] = []
    if pass_rate < 1.0:
        recommendations.append("Review shots flagged as invalid and re-check framing/content against the scene.")
    if overall_score < 70:
        recommendations.append("Overall match is low; verify the scene definition aligns with the uploaded video.")

    return {
        "overall_valid": pass_rate >= 0.5 and overall_score >= 60,
        "overall_score": overall_score,
        "pass_rate": pass_rate,
        "summary": summary,
        "key_issues": key_issues[:10],
        "recommendations": recommendations,
        "shots": shots,
        "source": "local",
    }


def _coerce_json(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    # Fall back to the outermost {...} span if there is surrounding prose.
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


class RocketRideAggregator:
    def __init__(self) -> None:
        self.enabled = os.getenv("ROCKETRIDE_AGGREGATION_ENABLED", "true").lower() == "true"
        self._client: Any = None
        self._token: str | None = None
        self._prev_answers: list[Any] = []
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """True once the persistent pipeline has been started this process."""
        return self._token is not None

    async def _ensure_client(self) -> Any:
        """Connect the shared client once (reused across requests)."""
        if self._client is not None and self._client.is_connected():
            return self._client
        from rocketride import RocketRideClient  # lazy import

        client = RocketRideClient()  # reads ROCKETRIDE_URI / ROCKETRIDE_APIKEY from env
        await client.connect()
        self._client = client
        return client

    async def _ensure_pipeline(self) -> tuple[Any, str]:
        """Start one persistent pipeline (ttl=0) and reuse it across requests.

        The instance is started clean once per backend process, then kept
        running so the frontend hits a warm, long-lived pipeline.
        """
        client = await self._ensure_client()
        if self._token is not None:
            return client, self._token

        # Start from a clean slate so the answer history begins empty.
        try:
            existing = await client.get_task_token(PROJECT_ID, SOURCE)
            if existing:
                await client.terminate(existing)
        except Exception:  # noqa: BLE001
            pass
        try:
            result = await client.use(filepath=PIPE_PATH, ttl=0)
        except Exception:  # noqa: BLE001 - fall back to reusing a running instance
            result = await client.use(filepath=PIPE_PATH, use_existing=True, ttl=0)
        self._token = result["token"]
        self._prev_answers = []
        return client, self._token

    async def start(self) -> str | None:
        """Warm the persistent pipeline at backend startup. Returns the token."""
        if not self.enabled:
            return None
        async with self._lock:
            _, token = await self._ensure_pipeline()
            return token

    def _select_new_answer(self, result: Any) -> tuple[dict[str, Any] | None, str | None]:
        """Pick the answer added by the latest send from the accumulating lane."""
        if not isinstance(result, dict):
            return None, None
        candidate: Any = None
        for key in ("analysis", "answers", "json", "text"):
            if key in result and result[key] not in (None, "", []):
                candidate = result[key]
                break
        if candidate is None:
            return None, None

        if not isinstance(candidate, list):
            if isinstance(candidate, dict):
                return candidate, None
            if isinstance(candidate, str):
                parsed = _coerce_json(candidate)
                return (parsed, None) if parsed is not None else (None, candidate)
            return None, None

        # Only consider answers that weren't present before this send.
        new_items = [x for x in candidate if x not in self._prev_answers]
        self._prev_answers = candidate
        pool = new_items or candidate

        prose: str | None = None
        for item in reversed(pool):
            if isinstance(item, dict):
                return item, None
            if isinstance(item, str):
                parsed = _coerce_json(item)
                if parsed is not None:
                    return parsed, None
                if prose is None:
                    prose = item
        return None, prose

    def _build_payload(self, shots: list[dict[str, Any]], scene: dict[str, Any]) -> str:
        return json.dumps(
            {
                "scene_definition": scene,
                "shot_findings": [
                    {
                        "shot_index": s["shot_index"],
                        "timestamp": s["timestamp"],
                        "Valid": s["Valid"],
                        "Issues": s["Issues"],
                        "Score": s["Score"],
                    }
                    for s in shots
                ],
            },
            ensure_ascii=False,
        )

    async def aggregate(self, shots: list[dict[str, Any]], scene: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return local_aggregate(shots, scene)

        local = local_aggregate(shots, scene)
        try:
            payload = self._build_payload(shots, scene)
            async with self._lock:
                client, token = await self._ensure_pipeline()
                result = await client.send(token, payload, mimetype="text/plain")
                parsed, prose = self._select_new_answer(result)
            if parsed is not None:
                # Always keep the authoritative per-shot detail from the backend.
                parsed["shots"] = shots
                for key in (
                    "overall_valid",
                    "overall_score",
                    "pass_rate",
                    "summary",
                    "key_issues",
                    "recommendations",
                ):
                    parsed.setdefault(key, local[key])
                parsed["source"] = "rocketride"
                return parsed
            if prose:
                local["summary"] = prose.strip()
                local["source"] = "rocketride (prose)"
                return local

            local["source"] = "local (empty pipeline response)"
            return local
        except Exception as exc:  # noqa: BLE001 - degrade gracefully for any RR/SDK issue
            local["source"] = f"local (rocketride error: {type(exc).__name__}: {exc})"
            return local

    async def close(self) -> None:
        # Only disconnect the client. The pipeline was started with ttl=0, so it
        # keeps running on RocketRide after the client detaches.
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
