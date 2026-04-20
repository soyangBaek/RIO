from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.live_voice_backend import LiveVoiceBackend, RustAudioBackend
from src.app.main import _build_voice_backend


class VoiceBackendFactoryTest(unittest.TestCase):
    def _voice_cfg(self, worker_path: str) -> dict[str, object]:
        return {
            "backend": {
                "type": "rust",
                "worker_path": worker_path,
                "fallback_to_python": True,
                "startup_timeout_ms": 3000,
            },
            "audio": {
                "device": "pulse",
                "sample_rate": 16000,
                "channels": 1,
                "blocksize": 512,
                "dtype": "float32",
                "mic_gain_percent": None,
            },
            "vad": {
                "threshold": 350,
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 30,
                "min_speech_ms": 150,
            },
            "asr": {
                "model": "base",
                "language": "ko",
                "beam_size": 1,
                "compute_type": "int8",
                "device": "cpu",
            },
            "concurrency": {
                "drop_while_busy": True,
            },
        }

    @patch("src.app.main.importlib.util.find_spec", return_value=object())
    def test_build_voice_backend_prefers_rust_when_worker_exists(self, _find_spec) -> None:
        with tempfile.NamedTemporaryFile() as handle:
            cfg = self._voice_cfg(handle.name)
            with patch("src.app.main._load_yaml", return_value=cfg):
                backend = _build_voice_backend(AudioCapture())

        self.assertIsInstance(backend, RustAudioBackend)

    @patch("src.app.main.importlib.util.find_spec", return_value=object())
    def test_build_voice_backend_falls_back_to_python_when_worker_missing(self, _find_spec) -> None:
        missing_path = str(Path(tempfile.gettempdir()) / "rio-audio-worker-missing")
        cfg = self._voice_cfg(missing_path)
        with patch("src.app.main._load_yaml", return_value=cfg):
            backend = _build_voice_backend(AudioCapture())

        self.assertIsInstance(backend, LiveVoiceBackend)


if __name__ == "__main__":
    unittest.main()
