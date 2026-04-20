from __future__ import annotations

import base64
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.live_voice_backend import (
    ASRParams,
    AudioParams,
    BackendConfig,
    BackendLaunchConfig,
    LiveVoiceBackend,
    RustAudioBackend,
    VADParams,
    _RmsVoiceActivityDetector,
)


class _FakeSegment:
    def __init__(self, text: str, *, avg_logprob: float = -0.2, no_speech_prob: float = 0.05) -> None:
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class _FakeWhisper:
    def transcribe(self, audio, **kwargs):  # noqa: ANN001
        del audio, kwargs
        return iter([_FakeSegment("댄스 모드 시작")]), {"language": "ko"}


class LiveVoiceBackendTest(unittest.TestCase):
    def test_rms_vad_collects_segment_with_padding(self) -> None:
        detector = _RmsVoiceActivityDetector(
            threshold=300,
            silence_chunks_to_end=2,
            speech_pad_chunks=1,
            min_speech_ms=0,
            sample_rate=16000,
        )
        silence = np.zeros(512, dtype=np.float32)
        speech = np.full(512, 0.05, dtype=np.float32)

        self.assertFalse(detector.process(silence).started)

        started = detector.process(speech)
        self.assertTrue(started.started)
        self.assertFalse(started.ended)

        detector.process(speech)
        detector.process(silence)
        ended = detector.process(silence)

        self.assertTrue(ended.ended)
        self.assertIsNotNone(ended.audio)
        self.assertEqual(len(ended.audio), 512 * 4)
        self.assertEqual(ended.duration_ms, 128)

    def test_transcribe_and_feed_emits_worker_frames(self) -> None:
        capture = AudioCapture()
        backend = LiveVoiceBackend(
            capture=capture,
            config=BackendConfig(
                audio=AudioParams(mic_gain_percent=None),
                vad=VADParams(),
                asr=ASRParams(min_logprob=-1.0),
            ),
        )
        backend._whisper = _FakeWhisper()

        backend._transcribe_and_feed(np.full(1600, 0.1, dtype=np.float32))

        first = capture.read_chunk()
        second = capture.read_chunk()
        third = capture.read_chunk()

        self.assertEqual(first, {"speech": True})
        self.assertEqual(second["speech"], True)
        self.assertEqual(second["transcript"], "댄스 모드 시작")
        self.assertGreater(second["confidence"], 0.0)
        self.assertEqual(third, {"speech": False})

    def test_prepare_input_source_prefers_configured_pulse_source(self) -> None:
        backend = LiveVoiceBackend(
            capture=AudioCapture(),
            config=BackendConfig(
                audio=AudioParams(device="pulse", gain_target_source="AB13X", mic_gain_percent=None),
                vad=VADParams(),
                asr=ASRParams(),
            ),
        )

        with patch("src.app.adapters.audio.live_voice_backend.ensure_default_input_source") as ensure_default:
            backend._prepare_input_source()

        ensure_default.assert_called_once_with("AB13X")

    def test_prepare_input_source_skips_non_pulse_devices(self) -> None:
        backend = LiveVoiceBackend(
            capture=AudioCapture(),
            config=BackendConfig(
                audio=AudioParams(device="hw:2,0", gain_target_source="AB13X", mic_gain_percent=None),
                vad=VADParams(),
                asr=ASRParams(),
            ),
        )

        with patch("src.app.adapters.audio.live_voice_backend.ensure_default_input_source") as ensure_default:
            backend._prepare_input_source()

        ensure_default.assert_not_called()

    def test_rust_backend_utterance_message_decodes_and_feeds_capture(self) -> None:
        capture = AudioCapture()
        backend = RustAudioBackend(
            capture=capture,
            config=BackendConfig(
                audio=AudioParams(mic_gain_percent=None),
                vad=VADParams(),
                asr=ASRParams(min_logprob=-1.0),
                launch=BackendLaunchConfig(type="rust", worker_path="missing"),
            ),
        )
        backend._whisper = _FakeWhisper()
        backend._send_command = lambda payload: None  # type: ignore[method-assign]

        thread = threading.Thread(target=backend._decode_loop, daemon=True)
        thread.start()
        try:
            utterance = np.full(1600, 0.1, dtype=np.float32)
            backend._handle_worker_message(
                {
                    "type": "utterance",
                    "sample_rate": 16000,
                    "pcm_f32_b64": base64.b64encode(utterance.tobytes()).decode("ascii"),
                }
            )

            deadline = time.time() + 2.0
            while len(capture._buffer) < 3 and time.time() < deadline:
                time.sleep(0.01)

            first = capture.read_chunk()
            second = capture.read_chunk()
            third = capture.read_chunk()

            self.assertEqual(first, {"speech": True})
            self.assertEqual(second["speech"], True)
            self.assertEqual(second["transcript"], "댄스 모드 시작")
            self.assertGreater(second["confidence"], 0.0)
            self.assertEqual(third, {"speech": False})
        finally:
            backend._stop.set()
            backend._utterance_q.put_nowait(None)
            thread.join(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
