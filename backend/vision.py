"""Per-shot video validation engine.

Reimplements the behaviour of the project's `validate.py` for the web backend:
detect shots, extract a representative keyframe per shot, and compare each frame
against the matching entry in the uploaded scene definition using a
vision-capable model served through Token Router (OpenAI-compatible API).

Output contract per shot (mirrors validate.py):
    {shot_index, start_time, end_time, timestamp, Valid, Issues[], Score}
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any

import cv2
from scenedetect import ContentDetector, detect

VISION_SYSTEM_PROMPT = (
    "You are a strict video QA inspector. You are given a single frame extracted "
    "from a shot of a video, plus the text description of what that shot is "
    "SUPPOSED to contain. Compare the frame to the description and respond with "
    "ONLY a JSON object matching this schema:\n"
    "{\n"
    '  "Valid": boolean,   // true if the frame largely matches the description\n'
    '  "Issues": [string], // discrepancies, missing elements, lighting/composition problems\n'
    '  "Score": integer    // 0-100, 100 = perfect match, 0 = nothing matches\n'
    "}"
)


@dataclass
class VisionConfig:
    api_key: str | None = None
    base_url: str = "https://api.tokenrouter.com/v1"
    model: str = "gpt-4o"
    max_shots: int = 50
    content_threshold: float = 27.0
    field_names: list[str] = field(
        default_factory=lambda: ["scene", "description", "camera", "style", "movements", "audio"]
    )


class VideoSceneValidator:
    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or VisionConfig()
        self._client: Any = None
        if self.config.api_key:
            # Imported lazily so the module still imports without the SDK present.
            from openai import OpenAI

            self._client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)

    # -- scene helpers -----------------------------------------------------
    @staticmethod
    def _scene_shots(scene: dict[str, Any]) -> list[dict[str, Any]]:
        shots = scene.get("shots")
        return shots if isinstance(shots, list) else []

    def _describe_scene_shot(self, scene: dict[str, Any], index: int) -> str:
        """Build a natural-language expectation for a given shot index."""
        shots = self._scene_shots(scene)
        parts: list[str] = []

        if 0 <= index < len(shots):
            shot = shots[index]
            if shot.get("scene"):
                parts.append(f"Scene: {shot['scene']}")
            if shot.get("description"):
                parts.append(f"Description: {shot['description']}")
            camera = shot.get("camera")
            if isinstance(camera, dict) and camera.get("description"):
                parts.append(f"Camera: {camera['description']}")
            style = shot.get("style")
            if isinstance(style, dict):
                style_bits = ", ".join(f"{k}: {v}" for k, v in style.items() if v)
                if style_bits:
                    parts.append(f"Style: {style_bits}")
            movements = shot.get("movements")
            if isinstance(movements, list) and movements:
                parts.append("Movements: " + "; ".join(str(m) for m in movements))
            audio = shot.get("audio")
            if isinstance(audio, dict):
                if audio.get("description"):
                    parts.append(f"Audio: {audio['description']}")
                dialogue = audio.get("dialogue")
                if isinstance(dialogue, list) and dialogue:
                    lines = [f"{d.get('speaker', '?')}: {d.get('text', '')}" for d in dialogue]
                    parts.append("Dialogue: " + " | ".join(lines))

        # Enrich with overview context (characters/objects) so the model can resolve IDs like C1/O2.
        overview = scene.get("overview")
        if isinstance(overview, dict):
            for group in ("characters", "objects"):
                items = overview.get(group)
                if isinstance(items, list) and items:
                    described = [f"{i.get('id', '?')}={i.get('description', '')}" for i in items]
                    parts.append(f"{group.capitalize()}: " + "; ".join(described))

        if not parts:
            # Fall back to any top-level description on the scene document.
            fallback = scene.get("description") or scene.get("video_title") or "the described scene"
            parts.append(f"Description: {fallback}")

        return "\n".join(parts)

    # -- video helpers -----------------------------------------------------
    def _detect_shots(self, video_path: str) -> list[tuple[float, float]]:
        """Return list of (start_seconds, end_seconds) per shot."""
        scene_list = detect(video_path, ContentDetector(threshold=self.config.content_threshold))
        shots = [(s.get_seconds(), e.get_seconds()) for s, e in scene_list]

        if not shots:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
            duration = (total_frames / fps) if fps else 0.0
            shots = [(0.0, duration)]

        return shots[: self.config.max_shots]

    def _extract_frame_b64(self, video_path: str, start_s: float, end_s: float) -> str | None:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        mid_frame = int(((start_s + end_s) / 2.0) * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(mid_frame, 0))
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return base64.b64encode(buffer).decode("utf-8")

    # -- vision call -------------------------------------------------------
    def _compare(self, frame_b64: str, expectation: str) -> dict[str, Any]:
        if not self._client:
            return {
                "Valid": True,
                "Issues": ["Vision provider not configured; returning mock analysis."],
                "Score": 75,
            }

        response = self._client.chat.completions.create(
            model=self.config.model,
            response_format={"type": "json_object"},
            max_tokens=500,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Expected shot description:\n{expectation}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"},
                        },
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        return self._coerce(raw)

    @staticmethod
    def _coerce(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"Valid": False, "Issues": ["Failed to parse vision response."], "Score": 0}
        return {
            "Valid": bool(data.get("Valid", False)),
            "Issues": list(data.get("Issues", []) or []),
            "Score": int(data.get("Score", 0) or 0),
        }

    # -- public API --------------------------------------------------------
    def validate(self, video_path: str, scene: dict[str, Any]) -> list[dict[str, Any]]:
        shots = self._detect_shots(video_path)
        results: list[dict[str, Any]] = []

        for idx, (start_s, end_s) in enumerate(shots):
            expectation = self._describe_scene_shot(scene, idx)
            frame_b64 = self._extract_frame_b64(video_path, start_s, end_s)
            if frame_b64 is None:
                analysis = {
                    "Valid": False,
                    "Issues": ["Could not extract a frame for this shot."],
                    "Score": 0,
                }
            else:
                try:
                    analysis = self._compare(frame_b64, expectation)
                except Exception as exc:  # noqa: BLE001 - degrade per shot on provider errors
                    analysis = {
                        "Valid": False,
                        "Issues": [f"Vision provider error: {type(exc).__name__}: {exc}"],
                        "Score": 0,
                    }

            results.append(
                {
                    "shot_index": idx,
                    "start_time": round(start_s, 2),
                    "end_time": round(end_s, 2),
                    "timestamp": round((start_s + end_s) / 2.0, 2),
                    "expectation": expectation,
                    **analysis,
                }
            )

        return results
