"""utterance 를 wav + json 사이드카로 저장."""
from __future__ import annotations

import json
import re
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np


_SAFE_CHARS_RE = re.compile(r"[^\w\uac00-\ud7a3]+")


def _sanitize_for_filename(text: str, max_len: int = 30) -> str:
    t = _SAFE_CHARS_RE.sub("_", text).strip("_")
    return t[:max_len] if t else "silent"


class UtteranceRecorder:
    def __init__(self, save_dir: Path, sample_rate: int, enabled: bool):
        self.save_dir = Path(save_dir)
        self.sample_rate = sample_rate
        self.enabled = enabled
        if self.enabled:
            self.save_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        audio_float32: np.ndarray,
        label: str,
        text: str,
        sidecar: dict[str, Any],
    ) -> Optional[Path]:
        if not self.enabled:
            return None

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        tag = _sanitize_for_filename(text)
        base = self.save_dir / f"{ts}_{label}_{tag}"
        wav_path = base.with_suffix(".wav")
        json_path = base.with_suffix(".json")

        # float32 [-1,1] → int16 PCM
        clipped = np.clip(audio_float32, -1.0, 1.0)
        pcm = (clipped * 32767.0).astype(np.int16)

        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(pcm.tobytes())

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sidecar, f, ensure_ascii=False, indent=2)

        return wav_path
