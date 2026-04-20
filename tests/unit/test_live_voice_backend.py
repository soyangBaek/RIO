from __future__ import annotations

import unittest

import numpy as np

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.live_voice_backend import (
    ASRParams,
    AudioParams,
    BackendConfig,
    LiveVoiceBackend,
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


if __name__ == "__main__":
    unittest.main()
